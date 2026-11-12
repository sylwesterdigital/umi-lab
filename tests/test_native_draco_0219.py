"""0.2.19 regression: native Blender Draco is not coupled to glTF Transform."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import struct
from unittest.mock import patch
from backend.mesh_options import validate_plan, PlanError
from backend import mesh_optimize

ROOT=Path(__file__).resolve().parents[1]

class NativeDracoTests(unittest.TestCase):
    def test_level_six_and_five_quantization_settings(self):
        plan=validate_plan({'preset':'custom','geometry_codec':'draco',
            'scope':'mesh','draco_level':6,'draco_position_bits':16,
            'draco_normal_bits':9,'draco_texcoord_bits':11,
            'draco_color_bits':8,'draco_generic_bits':12})
        self.assertEqual(plan['draco_level'],6)
        self.assertEqual(plan['draco_position_bits'],16)
        for bad in (-1,7,99,6.1,True,'7'):
            with self.subTest(bad=bad),self.assertRaises(PlanError):
                validate_plan({'preset':'custom','geometry_codec':'draco','draco_level':bad})
        for bad in (-1,31,True,7.2):
            with self.subTest(bad=bad),self.assertRaises(PlanError):
                validate_plan({'preset':'custom','geometry_codec':'draco','draco_normal_bits':bad})

    def test_codec_uses_blender_not_gltf_cli_and_does_not_touch_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            original=Path(tmp)/'source.glb'
            original.write_bytes(b'glTF'+b'\0'*48)
            commands=[]
            def fake_run(command,**kwargs):
                commands.append(command)
                self.assertIn('--python',command)
                self.assertIn('blender_clean.py',' '.join(map(str,command)))
                args=command[command.index('--')+1:]
                plan=json.loads(args[4]);self.assertEqual(plan['geometry_codec'],'draco')
                self.assertEqual(plan['draco_level'],6)
                doc=json.dumps({'asset':{'version':'2.0'},'extensionsUsed':['KHR_draco_mesh_compression']}).encode()
                doc+=b' '*(-len(doc)%4)
                Path(args[1]).write_bytes(struct.pack('<4sII',b'glTF',2,20+len(doc))+struct.pack('<I4s',len(doc),b'JSON')+doc)
                return SimpleNamespace(returncode=0,stdout=b'UMI_BLENDER_OPTIMISE_OK',stderr=b'')
            with patch.object(mesh_optimize,'gltf_cli',return_value=None),\
                 patch.object(mesh_optimize,'blender_status',return_value={'ready':True,'draco_native':True}),\
                 patch.object(mesh_optimize.shutil,'which',return_value='/usr/bin/blender'),\
                 patch.object(mesh_optimize.subprocess,'run',side_effect=fake_run):
                out=mesh_optimize.optimized_glb(original,options={'preset':'custom','scope':'mesh','geometry_codec':'draco','draco_level':6})
            self.assertTrue(out.startswith(b'glTF'))
            self.assertEqual(original.read_bytes(),b'glTF'+b'\0'*48)
            self.assertEqual(len(commands),1,'must not invoke glTF Transform for Draco')

    def test_unavailable_blender_draco_reports_clear_error(self):
        with patch.object(mesh_optimize,'gltf_cli',return_value=None),\
             patch.object(mesh_optimize,'blender_status',return_value={'ready':True,'draco_native':False}):
            with self.assertRaises(mesh_optimize.BlenderError) as raised:
                mesh_optimize.optimized_glb('source.glb',options={'preset':'custom','scope':'mesh','geometry_codec':'draco'})
        self.assertEqual(raised.exception.code,'DRACO_ENCODER_UNAVAILABLE')

    def test_actual_probe_and_frontend_are_wired(self):
        script=(ROOT/'backend/blender_draco_probe.py').read_text()
        self.assertIn("'KHR_draco_mesh_compression'",script)
        self.assertIn('UMI_DRACO_OK',script)
        blender=(ROOT/'backend/blender_clean.py').read_text()
        self.assertIn('export_draco_mesh_compression_enable=True',blender)
        self.assertIn('export_draco_mesh_compression_level=int(',blender)
        js=(ROOT/'frontend/js/app.js').read_text()
        html=(ROOT/'frontend/index.html').read_text()
        self.assertIn('capabilities.draco_native',js)
        self.assertIn('draco_level:Number(',js)
        for token in ('meshOptDracoLevel','meshOptDracoPosition','meshOptDracoNormal','meshOptDracoUV','meshOptDracoColor','meshOptDracoGeneric'):
            self.assertIn('id="'+token+'"',html)
        self.assertIn('native Draco GLB compression level 6 VERIFIED',(ROOT/'deploy/install.py').read_text())

if __name__=='__main__':unittest.main()
