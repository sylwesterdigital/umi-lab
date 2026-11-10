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
        actual=self.client.get('/api/health').json
        self.assertTrue(actual['ok'])
        from pathlib import Path
        expected=json.loads((Path(__file__).resolve().parent.parent/'version.json').read_text())['version']
        self.assertEqual(actual['version'],expected)
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
    def test_region_crop_and_ai_edit_preserve_outside(self):
        from unittest.mock import patch
        pid=self.post('/api/projects',{'name':'Truck'}).json['id']
        original=Image.new('RGB',(100,80),(10,20,30))
        raw=io.BytesIO();original.save(raw,'PNG');raw.seek(0)
        upload=self.client.post('/api/assets/upload',data={'project_id':pid,'image':(raw,'truck.png')},
            headers={'X-CSRF-Token':self.csrf},content_type='multipart/form-data')
        self.assertEqual(upload.status_code,201,upload.json)
        source=upload.json['id'];rect={'x':.2,'y':.25,'w':.3,'h':.5}
        cropped=self.post('/api/assets/region',{'project_id':pid,'asset_id':source,'operation':'crop','rect':rect})
        self.assertEqual(cropped.status_code,200,cropped.json)
        result=Image.open(io.BytesIO(self.client.get(cropped.json['url']).data))
        self.assertEqual(result.size,(30,40))
        self.assertEqual(result.convert('RGB').getpixel((1,1)),(10,20,30))
        self.client.put('/api/providers/xai',json={'enabled':True,'api_key':'test-key','model':'grok-4.7',
            'image_model':'grok-imagine-image-2.0','base_url':'https://api.x.ai/v1'},headers={'X-CSRF-Token':self.csrf})
        replacement=io.BytesIO();Image.new('RGB',(35,45),(255,0,0)).save(replacement,'PNG')
        with patch.object(self.module,'generate_image',return_value=(replacement.getvalue(),'image/png')) as gen:
            edited=self.post('/api/assets/region',{'project_id':pid,'asset_id':source,'operation':'edit',
                 'rect':rect,'prompt':'Make bumper red','provider_id':'xai'})
        self.assertEqual(edited.status_code,200,edited.json)
        self.assertEqual(len(gen.call_args.kwargs['reference_images']),1)
        output=Image.open(io.BytesIO(self.client.get(edited.json['url']).data)).convert('RGB')
        self.assertEqual(output.getpixel((10,10)),(10,20,30))
        self.assertEqual(output.getpixel((90,60)),(10,20,30))
        self.assertEqual(output.getpixel((30,30)),(255,0,0))
        self.assertEqual(self.client.get(f'/api/projects/{pid}').json['project']['selected_asset'],source)
        other=self.post('/api/projects',{'name':'Elsewhere'}).json['id']
        denied=self.post('/api/assets/region',{'project_id':other,'asset_id':source,'operation':'crop','rect':rect})
        self.assertEqual(denied.status_code,404)
        bad=self.post('/api/assets/region',{'project_id':pid,'asset_id':source,'operation':'crop',
                 'rect':{'x':.9,'y':.2,'w':.5,'h':.5}})
        self.assertEqual(bad.status_code,400)

    def test_provider_save_hides_key_and_csrf(self):
        r=self.client.put('/api/providers/openai',json={'enabled':True,'api_key':'top-secret','model':'gpt-4.1-mini','base_url':'https://api.openai.com/v1'})
        self.assertEqual(r.status_code,403)
        r=self.client.put('/api/providers/openai',json={'enabled':True,'api_key':'top-secret','model':'gpt-4.1-mini','base_url':'https://api.openai.com/v1'},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(r.status_code,200,r.json)
        result=self.client.get('/api/providers').json
        p=next(p for p in result['providers'] if p['id']=='openai')
        self.assertTrue(p['has_key']);self.assertNotIn('top-secret',str(result))
    def test_provider_check_uses_nonbillable_request(self):
        from unittest.mock import patch
        with patch.object(self.module,'check_api',return_value={'ok':True,'status':'API verified','balance':24,'detail':'Non-billable check passed'}) as mock:
            response=self.post('/api/providers/tripo/check',{'api_key':'test-key','base_url':'https://api.tripo3d.ai/v2/openapi'})
            self.assertEqual(response.status_code,200,response.json)
            self.assertEqual(response.json['balance'],24)
            self.assertEqual(mock.call_args.args[2],'test-key')
            result=self.client.get('/api/providers').json
            item=next(p for p in result['providers'] if p['id']=='tripo')
            self.assertFalse(item['has_key'])

    def test_resume_ai_asks_once_on_unfinished_project(self):
        from unittest.mock import patch
        pid=self.post('/api/projects',{'name':'Unfinished terrain car'}).json['id']
        logged=self.post('/api/chat',{'project_id':pid,'message':'Need a rocky road vehicle'})
        self.assertEqual(logged.status_code,200,logged.json)
        configured=self.client.put('/api/providers/xai',json={'enabled':True,'api_key':'test-key',
            'model':'grok-4.7','image_model':'grok-imagine-image-2.0','base_url':'https://api.x.ai/v1'},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(configured.status_code,200,configured.json)
        with patch.object(self.module,'provider_chat',return_value='How much ground clearance should it have?') as infer:
            answer=self.post('/api/projects/'+pid+'/continue',{'provider_id':'xai'})
            repeated=self.post('/api/projects/'+pid+'/continue',{'provider_id':'xai'})
        self.assertEqual(answer.status_code,200,answer.json)
        self.assertIn('ground clearance',answer.json['reply'])
        self.assertTrue(repeated.json.get('skipped'))
        self.assertEqual(infer.call_count,1)
        data=self.client.get('/api/projects/'+pid).json
        self.assertTrue(data['project']['settings']['resume_asked'])
        self.assertEqual(data['messages'][-1]['role'],'assistant')

    def test_six_view_sheet_uses_actual_selected_images(self):
        from unittest.mock import patch
        pid=self.post('/api/projects',{'name':'Terrain beast','prompt':'Rock crawler'}).json['id']
        image=Image.new('RGB',(128,92),'black');buf=io.BytesIO();image.save(buf,'PNG');buf.seek(0)
        uploaded=self.client.post('/api/assets/upload',data={'project_id':pid,'image':(buf,'reference.png')},
            headers={'X-CSRF-Token':self.csrf},content_type='multipart/form-data')
        self.assertEqual(uploaded.status_code,201,uploaded.json)
        aid=uploaded.json['id']
        configured=self.client.put('/api/providers/xai',json={'enabled':True,'api_key':'test-key','model':'grok-4.7','image_model':'grok-imagine-image-2.0','base_url':'https://api.x.ai/v1'},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(configured.status_code,200,configured.json)
        output=io.BytesIO();Image.new('RGB',(80,60),'white').save(output,'PNG')
        with patch.object(self.module,'generate_image',return_value=(output.getvalue(),'image/png')) as gen:
            response=self.post('/api/concepts/generate',{'project_id':pid,'provider_id':'xai','mode':'sheet',
                'prompt':'Terrain beast','instructions':'Blueprint linework','reference_ids':[aid]})
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['views_completed'],6)
        self.assertEqual(response.json['images_created'],1)
        self.assertEqual(response.json['reference_count'],1)
        self.assertEqual(len(gen.call_args.kwargs['reference_images']),1)
        self.assertIn('SIX equal',gen.call_args.args[3])
        current=self.client.get('/api/projects/'+pid).json
        self.assertEqual(current['project']['selected_asset'],aid)
        self.assertEqual(current['project']['settings']['last_generation']['mode'],'sheet')
        self.assertEqual(current['project']['settings']['last_generation']['reference_ids'],[aid])
        self.assertTrue(any('AI image' in item['event'] for item in self.client.get('/api/logs?scope=session').json['entries']))
        second=self.post('/api/projects',{'name':'Different car'}).json['id']
        denied=self.post('/api/concepts/generate',{'project_id':second,'provider_id':'xai','mode':'sheet','reference_ids':[aid]})
        self.assertEqual(denied.status_code,400,denied.json)


    def test_parts_workflow_modes_update_manifest(self):
        from unittest.mock import patch
        pid=self.post('/api/projects',{'name':'Breakdown truck','prompt':'Rocky terrain truck'}).json['id']
        image=Image.new('RGB',(96,64),'gray');buf=io.BytesIO();image.save(buf,'PNG');buf.seek(0)
        uploaded=self.client.post('/api/assets/upload',data={'project_id':pid,'image':(buf,'reference.png')},
            headers={'X-CSRF-Token':self.csrf},content_type='multipart/form-data')
        aid=uploaded.json['id']
        self.client.put('/api/providers/xai',json={'enabled':True,'api_key':'test-key','model':'grok-4.7','image_model':'grok-imagine-image-2.0','base_url':'https://api.x.ai/v1'},headers={'X-CSRF-Token':self.csrf})
        output=io.BytesIO();Image.new('RGB',(120,80),'white').save(output,'PNG')
        with patch.object(self.module,'generate_image',return_value=(output.getvalue(),'image/png')):
            annotated=self.post('/api/concepts/generate',{'project_id':pid,'provider_id':'xai','mode':'annotate','reference_ids':[aid]})
            system=self.post('/api/concepts/generate',{'project_id':pid,'provider_id':'xai','mode':'system','system_id':'body','reference_ids':[aid]})
            part=self.post('/api/concepts/generate',{'project_id':pid,'provider_id':'xai','mode':'part','part_name':'Front bumper','reference_ids':[aid]})
        self.assertEqual(annotated.status_code,200,annotated.json)
        self.assertEqual(system.status_code,200,system.json)
        self.assertEqual(part.status_code,200,part.json)
        manifest=self.client.get(f'/api/projects/{pid}/manifest').json
        self.assertEqual(manifest['stages']['segmentation'],'annotated')
        self.assertIn('body',manifest['parts_workflow']['system_sheets'])
        self.assertIn('Front bumper',manifest['parts_workflow']['part_sheets'])
        exported=self.client.get(f'/api/projects/{pid}/export')
        self.assertEqual(exported.status_code,200)

    def test_meta_sam_authenticated_segmentation_export(self):
        from unittest.mock import patch
        pid=self.post('/api/projects',{'name':'Muse test vehicle'}).json['id']
        image=Image.new('RGB',(120,90),'gray');buf=io.BytesIO();image.save(buf,'PNG');buf.seek(0)
        uploaded=self.client.post('/api/assets/upload',data={'project_id':pid,'image':(buf,'car.png')},
            headers={'X-CSRF-Token':self.csrf},content_type='multipart/form-data')
        self.assertEqual(uploaded.status_code,201,uploaded.json)
        aid=uploaded.json['id']
        saved=self.client.put('/api/providers/meta',json={'enabled':True,'api_key':'test-key','model':'muse-spark-1.3',
            'image_model':'muse-image-1.0','base_url':'https://api.meta.ai/v1'},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(saved.status_code,200,saved.json)
        mock_result={'model':'sam-3.1','noun':'front bumper','completed':True,'count':1,'mask_count':1,
                     'objects':[{'id':'0','box':[5,5,40,35],'size':[120,90],'confidence':None,
                                'mask_token':'<|mask;x=0;y=0;data=30,36,!encoded|>'}]}
        with patch.object(self.module,'segment_image',return_value=mock_result) as infer:
            out=self.post('/api/segments/generate',{'project_id':pid,'asset_id':aid,'noun':'front bumper'})
        self.assertEqual(out.status_code,200,out.json)
        self.assertEqual(out.json['matches'],1)
        self.assertEqual(out.json['masks'],1)
        self.assertEqual(infer.call_count,1)
        self.assertEqual(self.client.get(out.json['data_url']).status_code,200)
        manifest=self.client.get(f'/api/projects/{pid}/manifest').json
        self.assertEqual(manifest['stages']['segmentation'],'sam_masks_available')
        self.assertEqual(len(manifest['parts_workflow']['sam_runs']),1)
        bundle=self.client.get(f'/api/projects/{pid}/export')
        self.assertEqual(bundle.status_code,200)
        import zipfile
        with zipfile.ZipFile(io.BytesIO(bundle.data)) as archive:
            self.assertTrue(any(p.startswith('segmentations/') for p in archive.namelist()))

    def test_chat_offline_and_login(self):
        pid=self.post('/api/projects',{'name':'Car'}).json['id']
        response=self.post('/api/chat',{'project_id':pid,'message':'A red supercar'})
        self.assertEqual(response.json['mode'],'offline')
        response=self.post('/api/logout',{})
        self.assertTrue(response.json['ok'])
        self.assertEqual(self.client.get('/api/projects').status_code,401)
        self.assertEqual(self.client.post('/api/login',json={'username':'admin','password':'a-secure-passphrase'}).status_code,200)

if __name__=='__main__':unittest.main()
