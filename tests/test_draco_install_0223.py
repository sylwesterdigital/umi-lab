"""v0.2.23: Draco must not take a working website offline."""
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from deploy import install

class DracoDeploymentSafetyTest(unittest.TestCase):
    def test_root_only_node_is_not_used_for_codec_install(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            node=base/'tools/node-current/bin/node'
            npm=base/'tools/node-current/bin/npm'
            node.parent.mkdir(parents=True)
            node.write_text('node')
            npm.write_text('npm')
            def service_works(cmd,env=None,timeout=12):
                return str(cmd[0]).startswith(str(base))
            with patch.object(install,'BASE',base),\
                 patch.object(install.shutil,'which',side_effect=lambda n:'/root/.nvm/'+n),\
                 patch.object(install,'run',return_value=SimpleNamespace(returncode=0,stdout='v22.16.0',stderr='')),\
                 patch.object(install,'_service_command_works',side_effect=service_works):
                found=install.ensure_scoped_node()
            self.assertEqual(found,(str(node),str(npm)))

    def test_failed_optional_codec_install_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            error=SimpleNamespace(returncode=1,stdout='',stderr='ETIMEDOUT registry.npmjs.org')
            with patch.object(install,'BASE',base),\
                 patch.object(install,'ensure_scoped_node',return_value=('/opt/umi/node','/opt/umi/npm')),\
                 patch.object(install,'run',return_value=error) as calls:
                self.assertFalse(install.prepare_gltf_transform())
            self.assertEqual(calls.call_count,2)
            for call in calls.call_args_list:
                self.assertIn('@gltf-transform/cli@4.5.0',call.args[0])

    def test_failed_draco_does_not_restart_old_site_during_preflight(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            stage=root/'stage';(stage/'app').mkdir(parents=True)
            (stage/'app/version.json').write_text('{"project":"umi-lab","version":"0.2.25"}')
            release=root/'release';release.mkdir()
            snap=root/'backup';snap.mkdir()
            unit=root/'umi-lab.service'
            service_calls=[]
            def reject_draco(*_):raise install.InstallError('encoder unavailable')
            def fake_write(path,data,*args,**kwargs):
                if path==unit:raise install.InstallError('preactivation test stop')
            with patch.object(install,'BASE',root),\
                 patch.object(install,'UNIT',unit),\
                 patch.object(install.os,'geteuid',return_value=0),\
                 patch.object(install,'choose_port',return_value=5057),\
                 patch.object(install,'check_binary'),\
                 patch.object(install,'prepare_identity'),\
                 patch.object(install,'snapshot',return_value=(snap,{'old_current':None})),\
                 patch.object(install,'prepare_release',return_value=release),\
                 patch.object(install,'prepare_blender'),\
                 patch.object(install,'verify_blender_optimiser'),\
                 patch.object(install,'prepare_draco_decoder'),\
                 patch.object(install,'seed_admin'),\
                 patch.object(install,'prepare_gltf_transform',return_value=False),\
                 patch.object(install,'verify_draco_runtime',side_effect=reject_draco),\
                 patch.object(install,'write_atomic',side_effect=fake_write),\
                 patch.object(install,'rollback') as rollback,\
                 patch.object(install,'run') as run:
                # The installer emits an expected pre-activation warning. Keep that
                # expected diagnostic out of unittest's own stderr stream: watcher
                # v0.1.3 incorrectly treated any uppercase failure keyword printed
                # by a passing test as a failed test suite.
                emitted=StringIO()
                with redirect_stderr(emitted):
                    with self.assertRaisesRegex(install.InstallError,'preactivation test stop'):
                        install.install(stage,'0.2.25','unit-test-safe')
                self.assertIn('PRE-ACTIVATION FAILED',emitted.getvalue())
                rollback.assert_not_called()
                run.assert_not_called()

if __name__=='__main__':unittest.main()
