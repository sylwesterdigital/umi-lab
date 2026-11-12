"""Regression coverage for missing module Blender errors and real deploy preflight."""
import io
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from deploy import install
from backend import mesh_optimize

ROOT=Path(__file__).resolve().parents[1]

class BlenderModuleRepairTests(unittest.TestCase):
    def test_identifies_module_name_from_real_blender_traceback(self):
        result=SimpleNamespace(stdout=b'Blender quit\n',stderr=b'''Traceback (most recent call last):
  File "/tmp/a.py", line 31, in execute
    import json
ModuleNotFoundError: No module named 'numpy'
Blender quit
''',returncode=1)
        self.assertEqual(mesh_optimize.blender_missing_module(result),'numpy')
        self.assertIn('numpy',mesh_optimize.blender_error_details(result))
        self.assertNotIn('/tmp/',mesh_optimize.blender_error_details(result))

    def test_clean_environment_excludes_flask_python_vars(self):
        with patch.dict(os.environ,{'PYTHONPATH':'/danger','PYTHONHOME':'/other','VIRTUAL_ENV':'/venv'},clear=False):
            environment=mesh_optimize.blender_runtime_env()
            self.assertNotIn('PYTHONPATH',environment)
            self.assertNotIn('PYTHONHOME',environment)
            self.assertNotIn('VIRTUAL_ENV',environment)
            self.assertEqual(environment['PYTHONNOUSERSITE'],'1')

    def test_preflight_sample_is_valid_glb(self):
        blob=install._blender_sample_glb()
        self.assertEqual(blob[:4],b'glTF')
        self.assertEqual(struct.unpack_from('<I',blob,8)[0],len(blob))
        self.assertEqual(blob[16:20],b'JSON')
        document_len=struct.unpack_from('<I',blob,12)[0]
        self.assertEqual(blob[20+document_len+4:20+document_len+8],b'BIN\0')
        self.assertEqual(len(blob)%4,0)

    def test_preflight_runs_before_current_release_switch(self):
        script=(ROOT/'deploy/install.py').read_text()
        self.assertLess(script.index('        verify_blender_optimiser(release)'),script.index('        seed_admin(release)'))
        self.assertIn("cmd=['runuser','-u','umi-lab','--',*cmd]",script)
        self.assertIn("'python3-numpy'",script)

    def test_missing_module_error_from_optimizer_has_named_code(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'sample.glb'; source.write_bytes(install._blender_sample_glb())
            status={'ready':True}
            result=SimpleNamespace(returncode=52,stdout=b'Blender quit',stderr=b"UMI_BLENDER_MODULE_MISSING: numpy")
            with patch.object(mesh_optimize,'blender_status',return_value=status),\
                 patch.object(mesh_optimize.shutil,'which',return_value='/usr/bin/blender'),\
                 patch.object(mesh_optimize.subprocess,'run',return_value=result):
                with self.assertRaises(mesh_optimize.BlenderError) as caught:
                    mesh_optimize.optimized_glb(source)
            self.assertEqual(caught.exception.code,'BLENDER_MODULE_MISSING')
            self.assertIn('numpy',str(caught.exception))

if __name__=='__main__':unittest.main()
