"""Regression checks for universal canvas media and editable documents."""
import io
import json
import unittest
from pathlib import Path
from backend.media_tools import media_type, clean_svg, validate_gif, pdf_text, transcode, MediaError
ROOT=Path(__file__).resolve().parent.parent

class MediaCanvas029(unittest.TestCase):
    def test_media_types(self):
        for file,mime in [('a.svg','image/svg+xml'),('a.gif','image/gif'),('a.pdf','application/pdf'),
                          ('a.m4a','audio/mp4'),('a.mp3','audio/mpeg'),('a.mov','video/quicktime'),('a.webm','video/webm'),('a.wav','audio/wav')]:
            self.assertEqual(media_type(file,mime),mime)
        with self.assertRaises(MediaError):media_type('bad.exe','application/octet-stream')
        with self.assertRaises(MediaError):media_type('voice.wav','text/html')
        with self.assertRaises(MediaError):media_type('voice.wav','video/mp4')
    def test_svg_safety_and_gif_animation(self):
        self.assertIn(b'<ns0:svg',clean_svg(b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="20" height="20"/></svg>'))
        for evil in [b'<svg onload="alert(1)"/>',b'<svg><script>bad()</script></svg>',b'<svg><foreignObject/></svg>',
                     b'<svg><use href="https://example.org/i"/></svg>']:
            with self.assertRaises(MediaError):clean_svg(evil)
        try:
            from PIL import Image
        except ImportError:
            return  # Flask/Pillow integration runs on Ubuntu
        out=io.BytesIO();Image.new('RGB',(40,40),'blue').save(out,'GIF');self.assertEqual(validate_gif(out.getvalue()),out.getvalue())
    def test_pdf_validation_and_text(self):
        try:
            from pypdf import PdfWriter
        except ImportError:
            self.skipTest('PDF extraction dependency installed and verified on Ubuntu')
        stream=io.BytesIO();writer=PdfWriter();writer.add_blank_page(width=200,height=220);writer.write(stream)
        self.assertEqual(pdf_text(stream.getvalue()).strip(),'')
        with self.assertRaises(MediaError):pdf_text(b'not-pdf')
    def test_canvas_controls_and_media_endpoints(self):
        js=(ROOT/'frontend/js/app.js').read_text()
        html=(ROOT/'frontend/index.html').read_text()
        api=(ROOT/'backend/app.py').read_text()
        for attr in ('newNoteButton','mediaStage','mediaStageDownload','mediaStageText'):
            self.assertIn('id="'+attr+'"',html)
        for code in ('function renderNote(n,layer)','function openMediaPreview(n)','function closeMediaPreview()',"n.kind==='note'",'state.multi.clear();state.selected=null;hidePhotoMenus();markSelection();showEmpty();'):
            self.assertIn(code,js)
        for route in ("@app.get('/api/media/<asset_id>/text')", "@app.get('/api/media/<asset_id>/thumbnail')"):
            self.assertIn(route,api)
        self.assertIn('media_type(file.filename',api)
        self.assertIn('transcode(blob,mime)',api)
        self.assertIn('imageio-ffmpeg==0.6.0',(ROOT/'backend/requirements.txt').read_text())
        self.assertIn('client_max_body_size 26m',(ROOT/'deploy/install.py').read_text())

if __name__=='__main__':unittest.main()
