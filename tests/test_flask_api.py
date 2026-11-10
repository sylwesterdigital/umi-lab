"""Integration tests run when Flask, Pillow and cryptography are installed."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

try:
    import flask
    from PIL import Image
    from cryptography.fernet import Fernet
    HAS_FLASK=True
except ImportError:HAS_FLASK=False

@unittest.skipUnless(HAS_FLASK,'Flask stack not installed in local validator; server checks required')
class FlaskTest(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.saved={k:os.environ.get(k) for k in ['UMI_DATA_DIR','UMI_ENABLE_SETUP','UMI_SESSION_KEY','UMI_FERNET_KEY']}
        os.environ['UMI_DATA_DIR']=self.dir.name
        os.environ['UMI_ENABLE_SETUP']='1'
        os.environ['UMI_SESSION_KEY']='test-only-session-key-long-and-random'
        os.environ['UMI_FERNET_KEY']=Fernet.generate_key().decode()
        # Reload once per test: separate data dirs and sessions.
        import importlib
        from backend import app as a
        self.module=importlib.reload(a)
        self.client=self.module.app.test_client()
        self.addCleanup(self.restore)
        self.assertEqual(self.client.get('/api/health').json['ok'],True)
        res=self.client.post('/api/setup',json={'name':'Test Creator','password':'a-secure-passphrase'})
        self.assertEqual(res.status_code,200,res.json)
        self.csrf=res.json['csrf']
    def restore(self):
        for k,v in self.saved.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v
    def post(self,url,body):return self.client.post(url,json=body,headers={'X-CSRF-Token':self.csrf})
    def test_crud_manifest_and_zip(self):
        res=self.post('/api/projects',{'name':'Red Beast','prompt':'Red off-road car'})
        self.assertEqual(res.status_code,201,res.json)
        pid=res.json['id']
        r=self.client.get(f'/api/projects/{pid}')
        self.assertEqual(r.json['project']['name'],'Red Beast')
        manifest=self.client.get(f'/api/projects/{pid}/manifest').json
        self.assertGreater(manifest['part_count'],140)
        self.assertFalse(manifest['manufacturing_ready'])
        for part in manifest['parts']:self.assertFalse(part['printable'])
        r=self.client.get(f'/api/projects/{pid}/export')
        self.assertEqual(r.status_code,200)
        import zipfile
        with zipfile.ZipFile(io.BytesIO(r.data)) as archive:
            self.assertIn('manifest.json',archive.namelist())
            self.assertIn('bom.csv',archive.namelist())
    def test_upload_and_authenticated_asset(self):
        pid=self.post('/api/projects',{'name':'Car'}).json['id']
        image=Image.new('RGB',(60,40),'red');out=io.BytesIO();image.save(out,'PNG');out.seek(0)
        response=self.client.post('/api/assets/upload',data={'project_id':pid,'image':(out,'car.png')},
            headers={'X-CSRF-Token':self.csrf},content_type='multipart/form-data')
        self.assertEqual(response.status_code,201,response.json)
        self.assertEqual(self.client.get(response.json['url']).status_code,200)
        self.assertEqual(self.client.get(f'/api/projects/{pid}').json['project']['selected_asset'],response.json['id'])
    def test_provider_save_hides_key_and_csrf(self):
        r=self.client.put('/api/providers/openai',json={'enabled':True,'api_key':'top-secret','model':'gpt-4.1-mini','base_url':'https://api.openai.com/v1'})
        self.assertEqual(r.status_code,403)
        r=self.client.put('/api/providers/openai',json={'enabled':True,'api_key':'top-secret','model':'gpt-4.1-mini','base_url':'https://api.openai.com/v1'},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(r.status_code,200,r.json)
        result=self.client.get('/api/providers').json
        p=next(p for p in result['providers'] if p['id']=='openai')
        self.assertTrue(p['has_key']);self.assertNotIn('top-secret',str(result))
    def test_chat_offline_and_login(self):
        pid=self.post('/api/projects',{'name':'Car'}).json['id']
        response=self.post('/api/chat',{'project_id':pid,'message':'A red supercar'})
        self.assertEqual(response.json['mode'],'offline')
        response=self.post('/api/logout',{})
        self.assertTrue(response.json['ok'])
        self.assertEqual(self.client.get('/api/projects').status_code,401)
        self.assertEqual(self.client.post('/api/login',json={'username':'admin','password':'a-secure-passphrase'}).status_code,200)

if __name__=='__main__':unittest.main()
