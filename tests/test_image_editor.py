"""Offline contracts for the floating image editor, source safety and deployment."""
import re
import unittest
from pathlib import Path

BASE=Path(__file__).resolve().parent.parent
class ImageEditorContract(unittest.TestCase):
    def test_window_selection_and_dock_controls(self):
        html=(BASE/'frontend/index.html').read_text()
        editor=(BASE/'frontend/js/image-editor.js').read_text()
        app=(BASE/'frontend/js/app.js').read_text()
        for element in ('previewStage','previewCanvas','previewRect','previewPan','previewRatio',
                        'previewZoomIn','previewZoomOut','previewFit','previewCrop',
                        'previewEdit','previewEditPrompt','previewResize','previewCollapse',
                        'promptHandle','promptDock','promptCollapse','chatButton'):
            self.assertIn('id="'+element+'"',html)
        self.assertIn('setupImageEditor',app)
        self.assertIn("api('assets/region'",app)
        self.assertIn('image.naturalWidth',editor)
        self.assertIn("'3:4':3/4",editor)
        self.assertIn("'4:3':4/3",editor)
        self.assertIn('selectionPayload',editor)
        self.assertIn("ev.key==='Enter'",editor)
        self.assertIn("ev.key==='Escape'",editor)
        self.assertIn('positionDockedPrompt',app)
        self.assertIn("$('#homeButton').onclick=()=>{if(state.project)",app)
    def test_edit_progress_never_occludes_image(self):
        editor=(BASE/'frontend/js/image-editor.js').read_text()
        css=(BASE/'frontend/css/styles.css').read_text()
        self.assertIn('if(busy){',editor)
        self.assertIn('ctx.createLinearGradient(',editor)
        self.assertIn('ctx.strokeRect(sx+border/2',editor)
        self.assertIn('if(busy){\n        // During AI edits',editor)
        self.assertIn('}else{\n        ctx.beginPath();ctx.rect',editor)
        self.assertNotIn("progress.style.width=Math.max(40,sw)",editor)
        self.assertNotIn("progress.style.height=Math.max(40,sh)",editor)
        self.assertIn('width:max-content;height:auto',css)
        self.assertIn('pointer-events:none;overflow:hidden;text-align:left',css)
        self.assertNotIn('linear-gradient(#050a10a3,#050a10a3)',css)

    def test_regions_endpoint_preserves_unselected_pixels(self):
        source=(BASE/'backend/app.py').read_text()
        self.assertIn("@app.post('/api/assets/region')",source)
        self.assertIn("'crop','edit'",source)
        self.assertIn("canvas=original.convert('RGBA')",source)
        self.assertIn("canvas.paste(edited,(left,top))",source)
        self.assertIn('id=? AND project_id=?',source)
        self.assertIn("Image.Resampling.LANCZOS",source)
if __name__=='__main__':unittest.main()
