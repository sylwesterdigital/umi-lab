"""Offline 3D provider request and status contracts; no paid API calls."""
import unittest
from unittest.mock import patch
from backend.mesh_gateway import submit_mesh, poll_mesh, _aholo_root, _gpu_root, ProviderError

class MeshGatewayTests(unittest.TestCase):
    def test_meshy_submit_cost_and_model(self):
        calls=[]
        def fake_http(method,url,key,payload=None):
            calls.append((method,url,payload));return {'result':'abc123456789'}
        ident,status,cost=submit_mesh('meshy',{'model':'meshy-7.1'},'key',b'im','image/png',True,fake_http)
        self.assertEqual((ident,status,cost),('abc123456789','PENDING',30))
        self.assertEqual(calls[0][2]['target_formats'],['glb'])
    def test_tripo_v3_upload_and_submit(self):
        def fake_call(method,url,key,payload=None,files=None,auth='bearer'):
            if url.endswith('/files'):
                self.assertIn('file',files);return {'code':0,'data':{'file_token':'file_testtoken'}}
            self.assertTrue(url.endswith('/generation/image-to-model'))
            self.assertEqual(payload['input'],'file_testtoken')
            self.assertFalse(payload['texture']);return {'code':0,'data':{'task_id':'task_12345678'}}
        with patch('backend.mesh_gateway._call',side_effect=fake_call):
            ident,status,cost=submit_mesh('tripo',{},'key',b'im','image/png',False,None)
        self.assertEqual((ident,status,cost),('task_12345678','PENDING',0))
    def test_tripo_poll(self):
        with patch('backend.mesh_gateway._call',return_value={'code':0,'data':{'status':'success','output':{'model_url':'https://cdn.tripo3d.ai/part.glb'}}}):
            state,url,err=poll_mesh('tripo',{},'key','task_12345678',None)
        self.assertEqual(state,'SUCCEEDED');self.assertTrue(url.endswith('part.glb'))
    def test_aholo_submit_and_poll(self):
        with patch('backend.mesh_gateway._call',return_value={'c':'0','d':1256173}) as fake:
            ident,status,cost=submit_mesh('aholo',{'model':'G1','base_url':'https://api.aholo.ai'},'key',b'im','image/png',False,None)
        self.assertEqual((ident,status,cost),('1256173','PENDING',0))
        self.assertIn('/global/lux3d/v1/generate/img-to-3d/task/create',fake.call_args.args[1])
        result={'c':'0','d':{'status':3,'outputs':[{'content':'https://cdn.kujiale.com/model.zip'},{'content':'https://cdn.kujiale.com/model.glb'}]}}
        with patch('backend.mesh_gateway._call',return_value=result):
            state,url,err=poll_mesh('aholo',{'base_url':'https://api.aholo.ai/global'},'key','1256173',None)
        self.assertEqual(state,'SUCCEEDED');self.assertTrue(url.endswith('model.glb'))
    def test_gpu_bridge_uses_existing_image_and_model(self):
        with patch('backend.mesh_gateway._call',return_value={'task_id':'task_abcde12'}) as fake:
            ident,status,cost=submit_mesh('gpu-hunyuan',{'base_url':'https://models.example.com','model':'Hunyuan3D'},'key',b'im','image/png',True,None)
        self.assertEqual(status,'PENDING')
        self.assertEqual(fake.call_args.args[3]['model'],'Hunyuan3D')
    def test_gpu_rejects_private_network_endpoint(self):
        with self.assertRaises(ProviderError):_gpu_root({'base_url':'http://192.168.0.5:8000'})
    def test_unknown_provider_rejected(self):
        with self.assertRaises(ProviderError):submit_mesh('unknown',{},'key',b'im','image/png',False,None)

if __name__=='__main__':unittest.main()
