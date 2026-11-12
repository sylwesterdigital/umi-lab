"""v0.2.20: native WebP + native/CLI Draco fallback regressions."""
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image, features
from backend.model_textures import replace_glb_textures, split_glb
from backend import mesh_optimize


def make_glb(doc,binary):
    data=json.dumps(doc,separators=(',',':')).encode();data+=b' '*(-len(data)%4)
    binary+=b'\x00'*(-len(binary)%4)
    return (struct.pack('<4sII',b'glTF',2,12+8+len(data)+8+len(binary))+
        struct.pack('<I4s',len(data),b'JSON')+data+
        struct.pack('<I4s',len(binary),b'BIN\x00')+binary)


def sample():
    texture=io.BytesIO();Image.new('RGB',(240,160),'#ee2299').save(texture,format='PNG')
    normal=io.BytesIO();Image.new('RGB',(32,32),'#7f7fff').save(normal,format='PNG')
    blob=texture.getvalue();normal_blob=normal.getvalue()
    geom=struct.pack('<3f',1,2,3)
    binary=geom+blob+normal_blob
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],
      'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':12},
                     {'buffer':0,'byteOffset':12,'byteLength':len(blob)},
                     {'buffer':0,'byteOffset':12+len(blob),'byteLength':len(normal_blob)}],
      'accessors':[{'bufferView':0,'componentType':5126,'count':1,'type':'VEC3'}],
      'images':[{'bufferView':1,'mimeType':'image/png'},{'bufferView':2,'mimeType':'image/png'}],
      'textures':[{'source':0},{'source':1}],
      'materials':[{'pbrMetallicRoughness':{'baseColorTexture':{'index':0}},
                    'normalTexture':{'index':1}}],
      'animations':[{'name':'Walk'}]}
    return make_glb(doc,binary)

class CodecTests(unittest.TestCase):
    @unittest.skipUnless(features.check('webp'),'Pillow WebP library is unavailable')
    def test_webp_can_encode_without_cli_preserving_geometry_and_normal_map(self):
        old=sample();old_doc,old_bin,_=split_glb(old)
        output=replace_glb_textures(old,texture_format='webp',divisor=2)
        doc,binary,_=split_glb(output)
        self.assertIn('EXT_texture_webp',doc['extensionsUsed'])
        self.assertIn('EXT_texture_webp',doc['extensionsRequired'])
        self.assertNotIn('source',doc['textures'][0])
        encoded=doc['textures'][0]['extensions']['EXT_texture_webp']['source']
        self.assertEqual(doc['images'][encoded]['mimeType'],'image/webp')
        view=doc['bufferViews'][doc['images'][encoded]['bufferView']]
        blob=binary[view['byteOffset']:view['byteOffset']+view['byteLength']]
        self.assertTrue(blob.startswith(b'RIFF'))
        with Image.open(io.BytesIO(blob)) as image:self.assertEqual(image.size,(120,80))
        self.assertEqual(doc['textures'][1]['source'],1)
        self.assertEqual(doc['images'][1]['mimeType'],'image/png')
        self.assertEqual(doc['animations'],old_doc['animations'])
        self.assertEqual(binary[:12],old_bin[:12])

    @unittest.skipUnless(features.check('webp'),'Pillow WebP library is unavailable')
    def test_texture_only_webp_pipeline_no_blender_and_no_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.glb';path.write_bytes(sample())
            with patch.object(mesh_optimize,'gltf_cli',return_value=None),\
                 patch.object(mesh_optimize,'blender_status',side_effect=AssertionError('blender called')):
                output=mesh_optimize.optimized_glb(path,options={
                    'preset':'custom','scope':'textures','texture_format':'webp'})
            doc,_,_=split_glb(output)
            self.assertIn('EXT_texture_webp',doc['extensionsRequired'])

    def test_draco_fallback_detected_without_native_blender_codec(self):
        with patch.dict(mesh_optimize.os.environ,{'UMI_ENABLE_BLENDER':'1'}),\
             patch.object(mesh_optimize.shutil,'which',return_value='/usr/bin/blender'),\
             patch.object(mesh_optimize,'gltf_cli',return_value='/opt/umi/cli'),\
             patch.object(mesh_optimize,'blender_draco_probe',return_value={'available':False,'reason':'native library missing'}):
            status=mesh_optimize.blender_status()
        self.assertTrue(status['draco_available'])
        self.assertEqual(status['draco_backend'],'gltf-transform')
        self.assertTrue(status['texture_webp']==features.check('webp'))

    def test_cli_fallback_compression_level_and_source_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.glb';raw=sample();path.write_bytes(raw)
            commands=[]
            def run(command,**kw):
                commands.append(command)
                if '--python' in command:
                    Path(command[command.index('--')+2]).write_bytes(raw)
                else:
                    self.assertIn('draco',command)
                    self.assertIn('--encode-speed',command)
                    speed=command[command.index('--encode-speed')+1]
                    self.assertEqual(speed,'0')
                    doc,binary,_=split_glb(raw)
                    doc['extensionsUsed']=['KHR_draco_mesh_compression']
                    Path(command[3]).write_bytes(make_glb(doc,binary))
                return SimpleNamespace(returncode=0,stdout=b'OK',stderr=b'')
            with patch.object(mesh_optimize,'gltf_cli',return_value='/opt/umi/cli'),\
                 patch.object(mesh_optimize,'blender_status',return_value={
                   'ready':True,'draco_native':False,'draco_available':True}),\
                 patch.object(mesh_optimize.shutil,'which',return_value='/usr/bin/blender'),\
                 patch.object(mesh_optimize.subprocess,'run',side_effect=run):
                out=mesh_optimize.optimized_glb(path,options={'preset':'custom','scope':'mesh',
                  'geometry_codec':'draco','draco_level':6})
            self.assertEqual(path.read_bytes(),raw)
            self.assertIn('KHR_draco_mesh_compression',split_glb(out)[0]['extensionsUsed'])
            self.assertEqual(len(commands),2)

    def test_frontend_reports_capability_and_installer_is_isolated(self):
        root=Path(__file__).resolve().parents[1]
        js=(root/'frontend/js/app.js').read_text()
        dep=(root/'deploy/install.py').read_text()
        self.assertIn('capabilities.texture_webp',js)
        self.assertIn('capabilities.draco_available',js)
        self.assertIn('node-current/bin',dep)
        self.assertIn('ensure_scoped_node()',dep)
        self.assertIn('hashlib.sha256(blob).hexdigest()!=digest',dep)

if __name__=='__main__':unittest.main()
