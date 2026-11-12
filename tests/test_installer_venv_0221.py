"""Regression: Ubuntu deploy helper must not import Pillow via system Python."""
import builtins
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from deploy import install

class InstallerIsolationTests(unittest.TestCase):
    def test_smoke_helpers_have_no_external_dependencies(self):
        real_import=builtins.__import__
        def block_pillow(name,*args,**kwargs):
            if name=='PIL' or name.startswith('PIL.'):
                raise ModuleNotFoundError("No module named 'PIL'")
            return real_import(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=block_pillow):
            environment=install._blender_smoke_env()
            failure=SimpleNamespace(stdout='Blender quit',stderr="ModuleNotFoundError: No module named 'numpy'")
            self.assertEqual(install._blender_smoke_missing(failure),'numpy')
            self.assertIn('numpy',install._blender_smoke_error(failure))
            self.assertEqual(environment.get('PYTHONNOUSERSITE'),'1')
        source=(Path(__file__).resolve().parents[1]/'deploy/install.py').read_text()
        # This was the exact deployment regression in v0.2.20.
        self.assertNotIn("spec_from_file_location('_umi_blender_helper'",source)
        self.assertIn('blender_missing_module=_blender_smoke_missing',source)

    def test_blender_preflight_runs_without_importing_pil(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def fake_run(command,**kwargs):
                if 'blender_clean.py' in str(command):
                    # The installer verifies that the Blender smoke creates a GLB.
                    out=Path(command[-3])
                    out.write_bytes(install._blender_sample_glb())
                    return SimpleNamespace(returncode=0,stdout='Blender ran',stderr='')
                return SimpleNamespace(returncode=0,stdout='UMI_DRACO_OK',stderr='')
            user=SimpleNamespace(pw_uid=os.getuid(),pw_gid=os.getgid())
            real_import=builtins.__import__
            def block_pillow(name,*args,**kwargs):
                if name=='PIL' or name.startswith('PIL.'):
                    raise ModuleNotFoundError("No module named 'PIL'")
                return real_import(name,*args,**kwargs)
            with patch.object(install,'DATA',root),\
                 patch.object(install.pwd,'getpwnam',return_value=user),\
                 patch.object(install.shutil,'which',side_effect=lambda key:'/usr/bin/blender' if key=='blender' else '/usr/sbin/runuser'),\
                 patch.object(install,'run',side_effect=fake_run),\
                 patch('builtins.__import__',side_effect=block_pillow):
                install.verify_blender_optimiser(root)

if __name__=='__main__':unittest.main()
