"""Legacy region edit API remains intact despite the simplified canvas UI."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
class ImageDataCompatibilityTests(unittest.TestCase):
    def test_region_edit_endpoint_retained(self):
        src=(ROOT/'backend/app.py').read_text()
        self.assertIn("@app.post('/api/assets/region')",src)
        self.assertIn("canvas.paste(edited,(left,top))",src)
        self.assertIn("Image.Resampling.LANCZOS",src)
    def test_board_keeps_photos_without_editor_ui(self):
        page=(ROOT/'frontend/index.html').read_text()
        self.assertNotIn('previewProcessing',page)
        self.assertNotIn('editor-rail',page)
        self.assertIn('id="pictures"',page)
