"""Regression tests for restored Ubuntu media and 3D interaction contracts."""
import unittest
from pathlib import Path
from backend.media_tools import media_type, MediaError
ROOT=Path(__file__).resolve().parent.parent

class Release0210(unittest.TestCase):
    def test_browser_wav_mime_variants(self):
        for claimed in ('audio/wav','audio/x-wav','audio/wave','audio/vnd.wave','audio/x-pn-wav'):
            self.assertEqual(media_type('voice.wav',claimed),'audio/wav')
        with self.assertRaises(MediaError):media_type('voice.wav','video/mp4')
    def test_dialog_is_in_page_not_browser_confirm(self):
        script=(ROOT/'frontend/js/app.js').read_text()
        page=(ROOT/'frontend/index.html').read_text()
        self.assertIn('id="actionModal"',page)
        self.assertIn('id="actionError"',page)
        self.assertIn('id="actionMeshProvider"',page)
        self.assertIn('async function createMesh()',script)
        self.assertIn('function actionDialog(',script)
        self.assertNotIn('window.confirm(',script)
        self.assertIn('meshProviderReady(value.provider_id)',script)
    def test_viewer_native_pointer_isolation(self):
        script=(ROOT/'frontend/js/app.js').read_text()
        self.assertIn('function protectMeshOrbit(',script)
        self.assertIn("protectMeshOrbit($('meshStageViewer'))",script)
        self.assertIn("closest('model-viewer,.mesh-card,.mesh-stage')",script)
        self.assertIn("e.target.closest('model-viewer,.mesh-card-actions",script)

if __name__=='__main__':unittest.main()
