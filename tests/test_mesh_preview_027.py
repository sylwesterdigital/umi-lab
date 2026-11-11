"""3D archive and AHOLO GLB preview recovery regression tests (offline)."""
import io
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from backend.mesh_preview import preview_blob,preview_is_ready
from backend.mesh_gateway import poll_mesh


def glb():
    return b'glTF' + struct.pack('<II',2,12)

class MeshPreview027Tests(unittest.TestCase):
    def test_zip_with_glb_can_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'saved.zip'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('model/part.glb',glb())
                z.writestr('texture/albedo.png',b'123456')
            self.assertTrue(preview_is_ready(p))
            self.assertEqual(preview_blob(p),glb())
    def test_zip_without_glb_is_not_offered_as_viewable(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'saved.zip'
            with zipfile.ZipFile(p,'w') as z:z.writestr('part.obj',b'v 0 0 0')
            self.assertFalse(preview_is_ready(p))
            self.assertIsNone(preview_blob(p))
            side=Path(tmp)/'sidecar.preview.glb'
            side.write_bytes(glb())
            self.assertTrue(preview_is_ready(p,side))
            self.assertEqual(preview_blob(p,side),glb())
    def test_g1_glb_from_second_output_even_without_glb_extension(self):
        result={'c':'0','d':{'status':3,'outputs':[
            {'content':'https://cdn.kujiale.com/model/part.zip'},
            {'content':'https://cdn.kujiale.com/download/signedartifact?token=123'}]}}
        with patch('backend.mesh_gateway._call',return_value=result):
            status,url,_=poll_mesh('aholo',{'base_url':'https://api.aholo.ai/global'},'key','12345',None)
        self.assertEqual(status,'SUCCEEDED')
        self.assertEqual(url,'https://cdn.kujiale.com/download/signedartifact?token=123')
    def test_never_pick_zip_when_second_glb_is_present(self):
        result={'c':'0','d':{'status':3,'outputs':[
            {'content':'https://cdn.kujiale.com/model/saved.zip'},
            {'content':'https://cdn.kujiale.com/model/saved.glb'}]}}
        with patch('backend.mesh_gateway._call',return_value=result):
            status,url,_=poll_mesh('aholo',{'base_url':'https://api.aholo.ai/global'},'key','12345',None)
        self.assertEqual(url,'https://cdn.kujiale.com/model/saved.glb')
