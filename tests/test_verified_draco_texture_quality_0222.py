"""v0.2.22 codec quality controls and tested live encoder output (mocked IO)."""
import io
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image, features
from backend.mesh_options import validate_plan, PlanError
from backend.model_textures import replace_glb_textures, split_glb
from deploy import install

ROOT=Path(__file__).resolve().parents[1]

def make_glb(doc, binary=b''):
    js=json.dumps(doc,separators=(',',':')).encode();js+=b' '*((-len(js))%4)
    binary+=b'\0'*((-len(binary))%4)
    return struct.pack('<4sII',b'glTF',2,12+8+len(js)+(8+len(binary) if binary else 0))+struct.pack('<I4s',len(js),b'JSON')+js+(struct.pack('<I4s',len(binary),b'BIN\0')+binary if binary else b'')

def sample_image_glb():
    buffer=io.BytesIO()
    image=Image.new('RGB',(320,192))
    for y in range(192):
        for x in range(320):image.putpixel((x,y),((x*21+y*6)%256,(y*19)%256,(x*6)%256))
    image.save(buffer,format='PNG');binary=buffer.getvalue()
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],
         'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':len(binary)}],
         'images':[{'bufferView':0,'mimeType':'image/png'}],
         'textures':[{'source':0}],
         'materials':[{'pbrMetallicRoughness':{'baseColorTexture':{'index':0}}}]}
    return make_glb(doc,binary)

def image_size(output):
    document,binary,_=split_glb(output)
    image=document['images'][-1]
    view=document['bufferViews'][image['bufferView']]
    return view['byteLength']

class VerifiedEncoderTests(unittest.TestCase):
    def test_user_quality_and_png_effort_are_validated(self):
        data={'preset':'custom','texture_quality':31,'png_compression':9,'webp_effort':3,'webp_lossless':True}
        plan=validate_plan(data)
        for key,val in data.items():
            if key!='preset':self.assertEqual(plan[key],val)
        for key,bad in [('texture_quality',0),('texture_quality',101),('texture_quality','85'),
                        ('png_compression',10),('webp_effort',7),('webp_lossless',1)]:
            with self.subTest(key=key),self.assertRaises(PlanError):
                validate_plan({'preset':'custom',key:bad})

    def test_jpeg_quality_changes_encoded_byte_size(self):
        image=sample_image_glb()
        low=replace_glb_textures(image,texture_format='jpeg',texture_quality=15)
        high=replace_glb_textures(image,texture_format='jpeg',texture_quality=95)
        self.assertLess(image_size(low),image_size(high))
        self.assertEqual(split_glb(low)[0]['images'][0]['mimeType'],'image/jpeg')

    @unittest.skipUnless(features.check('webp'),'WebP not supported by this Pillow build')
    def test_webp_quality_and_effort_reach_encoder(self):
        image=sample_image_glb()
        low=replace_glb_textures(image,texture_format='webp',texture_quality=12,webp_effort=2)
        high=replace_glb_textures(image,texture_format='webp',texture_quality=95,webp_effort=6)
        self.assertLess(image_size(low),image_size(high))
        self.assertIn('EXT_texture_webp',split_glb(low)[0]['extensionsUsed'])
        lossless=replace_glb_textures(image,texture_format='webp',webp_lossless=True)
        self.assertTrue(lossless.startswith(b'glTF'))

    def test_png_effort_is_lossless(self):
        data=sample_image_glb()
        low=replace_glb_textures(data,texture_format='png',png_compression=0)
        high=replace_glb_textures(data,texture_format='png',png_compression=9)
        self.assertLess(image_size(high),image_size(low))
        def content(v):
            doc,b,_=split_glb(v);view=doc['bufferViews'][doc['images'][0]['bufferView']]
            with Image.open(io.BytesIO(b[view['byteOffset']:view['byteOffset']+view['byteLength']])) as img:
                return img.tobytes()
        self.assertEqual(content(low),content(high))

    def test_real_draco_runtime_check_rejects_uncompressed_cli_result(self):
        with tempfile.TemporaryDirectory() as folder:
            def fake_run(args,**kw):
                if '--python-expr' in args:
                    # Last argument embeds the output path inside the expression.
                    expr=args[-1]
                    import re
                    path=re.search(r"filepath='([^']+)'",expr).group(1)
                    Path(path).write_bytes(make_glb({'asset':{'version':'2.0'}}))
                elif 'draco' in args and '--method' in args:
                    target=Path(args[args.index('draco')+2]);target.write_bytes(make_glb({'asset':{'version':'2.0'}}))
                return SimpleNamespace(returncode=0,stdout='OK',stderr='')
            with patch.object(install,'DATA',Path(folder)),patch.object(install,'run',side_effect=fake_run),\
                 patch.object(install.os,'chown'),patch.object(install.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=1001,pw_gid=1001)),\
                 patch.object(install.shutil,'which',side_effect=lambda cmd:'/usr/bin/blender' if cmd=='blender' else '/usr/bin/gltf-transform'):
                with self.assertRaisesRegex(install.InstallError,'failed real compression'):
                    install.verify_draco_runtime(Path(folder))

    def test_ui_and_manifest_source_contains_quality_controls_and_no_junk(self):
        html=(ROOT/'frontend/index.html').read_text()
        js=(ROOT/'frontend/js/app.js').read_text()
        for name in ('meshOptQuality','meshOptPngLevel','meshOptWebpEffort','meshOptWebpLossless'):
            self.assertIn('id="'+name+'"',html)
            self.assertIn("$('"+name+"')",js)
        self.assertIn('verify_draco_runtime(release)',(ROOT/'deploy/install.py').read_text())
        self.assertFalse((ROOT/'--background').exists())

if __name__=='__main__':unittest.main()
