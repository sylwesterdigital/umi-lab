"""Installation must use the actual UMI service user and preserve isolation."""
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from deploy import install


class DracoServiceInstall026(unittest.TestCase):
    def test_service_user_npm_install_and_scoped_home(self):
        with TemporaryDirectory() as temp:
            base=Path(temp)/'umi';data=Path(temp)/'data';data.mkdir()
            expected=base/'tools/gltf-transform/node_modules/.bin/gltf-transform'
            commands=[]
            def fake_run(command,**kwargs):
                commands.append(command)
                if 'install' in command:
                    expected.parent.mkdir(parents=True,exist_ok=True)
                    expected.write_text('mock binary')
                return SimpleNamespace(returncode=0,stdout='ok',stderr='')
            with patch.object(install,'BASE',base),patch.object(install,'DATA',data),\
                 patch.object(install,'ensure_scoped_node',return_value=('/opt/node22/bin/node','/opt/node22/bin/npm')),\
                 patch.object(install.os,'geteuid',return_value=0),\
                 patch.object(install,'run',side_effect=fake_run),\
                 patch.object(install,'_service_command_works',return_value=True):
                self.assertTrue(install.prepare_gltf_transform())
                env=install._node_runtime_env('/opt/node22/bin/node')
            self.assertEqual(env['HOME'],str(data))
            self.assertEqual(env['npm_config_cache'],str(base/'tools/npm-cache'))
            self.assertEqual(env['npm_config_userconfig'],'/dev/null')
            installs=[x for x in commands if 'install' in x]
            self.assertEqual(len(installs),1)
            self.assertEqual(installs[0][:4],['runuser','-u','umi-lab','--'])
            self.assertTrue(any(x[:3]==['chown','-R','umi-lab:umi-lab'] for x in commands))
            self.assertTrue(all(str(base) in ' '.join(map(str,x)) for x in commands if x[0]=='chown'))

    def test_root_fallback_is_limited_to_app_tools(self):
        with TemporaryDirectory() as temp:
            base=Path(temp)/'umi';data=Path(temp)/'data';data.mkdir()
            expected=base/'tools/gltf-transform/node_modules/.bin/gltf-transform'
            commands=[]
            def fake_run(command,**kwargs):
                commands.append(command)
                if 'install' in command and command[0]!="runuser":
                    expected.parent.mkdir(parents=True,exist_ok=True)
                    expected.write_text('mock')
                    return SimpleNamespace(returncode=0,stdout='ok',stderr='')
                if 'install' in command:
                    return SimpleNamespace(returncode=1,stdout='',stderr='network denied for user')
                return SimpleNamespace(returncode=0,stdout='ok',stderr='')
            with patch.object(install,'BASE',base),patch.object(install,'DATA',data),\
                 patch.object(install,'ensure_scoped_node',return_value=('/opt/node22/bin/node','/opt/node22/bin/npm')),\
                 patch.object(install.os,'geteuid',return_value=0),\
                 patch.object(install,'run',side_effect=fake_run),\
                 patch.object(install,'_service_command_works',return_value=True):
                self.assertTrue(install.prepare_gltf_transform())
            installs=[c for c in commands if 'install' in c]
            self.assertEqual(len(installs),3)
            self.assertEqual(installs[-1][0],'/opt/node22/bin/npm')
            self.assertIn(str(base/'tools/gltf-transform'),installs[-1])

    def test_backend_surfaces_safe_codec_error(self):
        import json
        from backend import mesh_optimize
        with TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'codec-diagnostics.json').write_text(json.dumps({'reason':'npm registry unavailable; encoder was not installed'}))
            mesh_optimize.blender_draco_probe.cache_clear()
            with patch.dict(mesh_optimize.os.environ,{'UMI_ENABLE_BLENDER':'1','UMI_DATA_DIR':str(root)}),\
                 patch.object(mesh_optimize.shutil,'which',side_effect=lambda n:'/usr/bin/blender' if n=='blender' else None),\
                 patch.object(mesh_optimize,'gltf_cli',return_value=None),\
                 patch.object(mesh_optimize,'blender_draco_probe',return_value={'available':False,'reason':'native addon missing'}):
                status=mesh_optimize.blender_status()
            self.assertFalse(status['draco_available'])
            self.assertIn('registry unavailable',status['draco_install_reason'])


if __name__=='__main__':unittest.main()
