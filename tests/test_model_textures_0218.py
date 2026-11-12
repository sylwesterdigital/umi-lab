"""Release 0.2.18: 3D imports and reversible texture-only workflows."""
import io
import json
import struct
import random
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from backend.model_textures import split_glb,texture_archive,read_texture_archive,replace_glb_textures,TextureError
from backend.model_import import glb_document, model_metadata
from backend.mesh_optimize import optimized_glb
from backend.mesh_options import validate_plan, PlanError

ROOT=Path(__file__).resolve().parents[1]

def synthetic_glb():
    image=io.BytesIO()
    Image.frombytes('RGB',(128,80),random.Random(42).randbytes(128*80*3)).save(image,format='PNG')
    png=image.getvalue()
    geometry=struct.pack('<fff',0.1,2.4,0.8)
    binary=geometry+png
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],
         'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':12},
                        {'buffer':0,'byteOffset':12,'byteLength':len(png)}],
         'accessors':[{'bufferView':0,'componentType':5126,'count':1,'type':'VEC3'}],
         'images':[{'bufferView':1,'mimeType':'image/png'}],
         'textures':[{'source':0}],
         'skins':[{'name':'Humanoid rig'}],
         'animations':[{'name':'Idle'},{'name':'Walk'}]}
    js=json.dumps(doc,separators=(',',':')).encode()
    js+=b' '*(-len(js)%4)
    binary+=b'\0'*(-len(binary)%4)
    size=12+8+len(js)+8+len(binary)
    return struct.pack('<4sII',b'glTF',2,size)+struct.pack('<II',len(js),0x4e4f534a)+js+struct.pack('<II',len(binary),0x004e4942)+binary

class TextureEditorTests(unittest.TestCase):
    def test_downscale_exact_factors_preserves_geometry_animation_and_rig(self):
        original=synthetic_glb()
        old,old_data,_=split_glb(original)
        geometry=old_data[:12]
        for divisor in (1,2,4,8,16):
            with self.subTest(divisor=divisor):
                result=replace_glb_textures(original,divisor=divisor,texture_format='jpeg')
                self.assertLess(len(result),len(original))
                glb_document(result)
                doc,binary,_=split_glb(result)
                v=doc['bufferViews'][0]
                self.assertEqual(binary[v['byteOffset']:v['byteOffset']+v['byteLength']],geometry)
                self.assertEqual(doc['animations'],old['animations'])
                self.assertEqual(doc['skins'],old['skins'])
                iv=doc['bufferViews'][doc['images'][0]['bufferView']]
                with Image.open(io.BytesIO(binary[iv['byteOffset']:iv['byteOffset']+iv['byteLength']])) as texture:
                    self.assertEqual(texture.size,(max(1,round(128/divisor)),max(1,round(80/divisor))))
                    self.assertEqual(texture.format,'JPEG')

    def test_zip_export_reimport_changes_only_material(self):
        source=synthetic_glb();raw=texture_archive(source)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertIn('texture-0000.png',z.namelist())
            manifest=z.read('manifest.json')
            replace=io.BytesIO()
            Image.new('RGB',(32,32),'#0033ff').save(replace,format='JPEG')
            rebuilt=io.BytesIO()
            with zipfile.ZipFile(rebuilt,'w') as out:
                out.writestr('manifest.json',manifest)
                out.writestr('texture-0000.jpg',replace.getvalue())
        replacements=read_texture_archive(rebuilt.getvalue(),source)
        result=replace_glb_textures(source,replacements=replacements)
        doc,bin_data,_=split_glb(result)
        self.assertEqual(doc['images'][0]['mimeType'],'image/jpeg')
        self.assertEqual(bin_data[:12],split_glb(source)[1][:12])
        self.assertEqual(doc['animations'][1]['name'],'Walk')
        with self.assertRaises(TextureError):read_texture_archive(rebuilt.getvalue(),b'another source')

    def test_invalid_zip_contents_are_rejected(self):
        source=synthetic_glb();raw=texture_archive(source)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:manifest=z.read('manifest.json')
        pack=io.BytesIO()
        with zipfile.ZipFile(pack,'w') as z:
            z.writestr('manifest.json',manifest)
            z.writestr('../escape.png',b'bad')
        with self.assertRaises(TextureError):read_texture_archive(pack.getvalue(),source)

    def test_texture_only_without_blender_or_gltf_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.glb';path.write_bytes(synthetic_glb())
            with patch('backend.mesh_optimize.blender_status',side_effect=AssertionError('Blender called')):
                with patch('backend.mesh_optimize.gltf_cli',return_value=None):
                    plan={'preset':'custom','scope':'textures','texture_divisor':4,'texture_format':'jpeg'}
                    output=optimized_glb(path,options=plan)
            self.assertTrue(output.startswith(b'glTF'))
            self.assertLess(len(output),path.stat().st_size)
        with self.assertRaises(PlanError):validate_plan({'preset':'custom','scope':'textures','geometry_codec':'draco'})
        self.assertEqual(validate_plan({'preset':'custom','texture_divisor':16})['texture_scale'],1.0)

    def test_imported_model_filetypes_and_endpoints(self):
        js=(ROOT/'frontend/js/app.js').read_text()
        html=(ROOT/'frontend/index.html').read_text()
        api=(ROOT/'backend/app.py').read_text()
        self.assertIn('function uploadModel(',js)
        for ext in ('.glb','.fbx','.obj','.stl','.ply','.dae','.usd','.usdz'):
            self.assertIn(ext,html)
        self.assertIn("@app.post('/api/projects/<pid>/models/import')",api)
        self.assertIn("@app.post('/api/projects/<pid>/models/<task_id>/textures')",api)
        self.assertIn('meshTexturePackInput',html)
        self.assertIn('Export textures ZIP',js)
        self.assertIn("'INSERT INTO mesh_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)'",api)

if __name__=='__main__':unittest.main()
