"""Ubuntu Flask integration checks: upload GLB, export and reimport textures."""
import io
import json
import os
import tempfile
import unittest
import zipfile

try:
    import flask
    from cryptography.fernet import Fernet
    HAS_FLASK=True
except ImportError:
    HAS_FLASK=False

from tests.test_model_textures_0218 import synthetic_glb

@unittest.skipUnless(HAS_FLASK,'Flask integration runs during Ubuntu deployment')
class ModelImportAPITests(unittest.TestCase):
    def setUp(self):
        from importlib import reload
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        keys=['UMI_DATA_DIR','UMI_ENABLE_SETUP','UMI_SESSION_KEY','UMI_FERNET_KEY']
        previous={k:os.environ.get(k) for k in keys}
        def restore():
            for name,value in previous.items():
                if value is None:os.environ.pop(name,None)
                else:os.environ[name]=value
        self.addCleanup(restore)
        os.environ.update(UMI_DATA_DIR=self.directory.name,UMI_ENABLE_SETUP='1',
            UMI_SESSION_KEY='integration-test-key-long',UMI_FERNET_KEY=Fernet.generate_key().decode())
        from backend import app as module
        self.app=reload(module)
        self.client=self.app.app.test_client()
        session=self.client.post('/api/setup',json={'name':'3D Creator','password':'secure-passphrase-3d'}).json
        self.assertTrue(session)
        self.csrf={'X-CSRF-Token':session['csrf']}
        result=self.client.post('/api/projects',json={'name':'3D import'},headers=self.csrf)
        self.assertEqual(result.status_code,201,result.json)
        self.pid=result.json['id']

    def test_glb_import_and_texture_export_reimport(self):
        uploaded=self.client.post(f'/api/projects/{self.pid}/models/import',
            data={'model':(io.BytesIO(synthetic_glb()),'test.glb')},
            content_type='multipart/form-data',headers=self.csrf)
        self.assertEqual(uploaded.status_code,201,uploaded.json)
        task=uploaded.json['task']
        self.assertTrue(task['preview_url'])
        self.assertEqual(len(task['animations']),2)
        before=self.client.get(task['preview_url'])
        self.assertEqual(before.status_code,200)
        downloaded=self.client.get(f'/api/projects/{self.pid}/models/{task["id"]}/textures')
        self.assertEqual(downloaded.status_code,200,downloaded.json)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(downloaded.data)))
        replaced=self.client.post(f'/api/projects/{self.pid}/models/{task["id"]}/textures',
            data={'textures':(io.BytesIO(downloaded.data),'textures.zip')},
            content_type='multipart/form-data',headers=self.csrf)
        self.assertEqual(replaced.status_code,201,replaced.json)
        self.assertNotEqual(replaced.json['id'],task['id'])
        self.assertTrue(replaced.json['preview_url'])
        self.assertEqual(self.client.get(task['preview_url']).data,before.data)
        tasks=self.client.get(f'/api/projects/{self.pid}/mesh-tasks').json['tasks']
        self.assertEqual(len(tasks),2)
        self.assertEqual({x['provider'] for x in tasks},{'import','texture-workbench'})

    def test_owner_boundary_and_bad_replacement(self):
        imported=self.client.post(f'/api/projects/{self.pid}/models/import',
            data={'model':(io.BytesIO(synthetic_glb()),'test.glb')},
            content_type='multipart/form-data',headers=self.csrf).json
        tid=imported['task']['id']
        other=self.client.post('/api/projects',json={'name':'Other'},headers=self.csrf).json['id']
        export=self.client.get(f'/api/projects/{other}/models/{tid}/textures')
        self.assertEqual(export.status_code,404)
        bad=self.client.post(f'/api/projects/{self.pid}/models/{tid}/textures',
            data={'textures':(io.BytesIO(b'garbage'),'bad.zip')},
            content_type='multipart/form-data',headers=self.csrf)
        self.assertEqual(bad.status_code,422)

if __name__=='__main__':unittest.main()
