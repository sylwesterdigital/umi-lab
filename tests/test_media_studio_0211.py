"""v0.2.11 dependency-free contracts and safe local conversion regression tests."""
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from backend.media_tools import media_type,MediaError
from backend.media_pipeline import transform_media,hls_from_file,ffmpeg_binary
ROOT=Path(__file__).resolve().parent.parent

class MediaStudio211(unittest.TestCase):
    def test_import_text_and_browser_audio_aliases(self):
        for name,mime in [('notes.txt','text/plain'),('brief.md','text/plain'),('brief.markdown','text/markdown'),('voice.weba','audio/webm')]:
            self.assertIn(media_type(name,mime),('text/plain','text/markdown','audio/webm'))
        with self.assertRaises(MediaError):media_type('danger.html','text/html')
        with self.assertRaises(MediaError):media_type('voice.weba','text/html')
    def test_bounded_image_conversion(self):
        from PIL import Image
        b=io.BytesIO();Image.new('RGB',(90,80),'blue').save(b,'PNG')
        for operation,expected in [('webp','image/webp'),('jpeg','image/jpeg'),('png','image/png'),('shrink','image/webp')]:
            result,mime,extension,label=transform_media(b.getvalue(),'image/png',operation,{'quality':65,'scale':.5})
            self.assertEqual(mime,expected)
            self.assertGreater(len(result),30)
            self.assertLess(len(result),35*1024*1024)
    def test_reject_incompatible_conversion(self):
        with self.assertRaises(MediaError):transform_media(b'abc','application/pdf','speed',{})
        with self.assertRaises(MediaError):transform_media(b'abc','audio/mpeg','gif',{})
        with self.assertRaises(MediaError):transform_media(b'abc','video/mp4','audio-replace',{})
    def test_optional_hls_on_small_audio(self):
        ff=ffmpeg_binary()
        if not ff:self.skipTest('FFmpeg unavailable')
        with tempfile.TemporaryDirectory() as d:
            audio=Path(d)/'tone.mp3';output=Path(d)/'hls'
            cmd=[ff,'-nostdin','-loglevel','error','-f','lavfi','-i','sine=frequency=700:duration=0.6','-c:a','libmp3lame','-y',str(audio)]
            if subprocess.run(cmd,capture_output=True,timeout=8).returncode:self.skipTest('This FFmpeg lacks MP3 encoding')
            self.assertTrue(hls_from_file(audio,output,'audio/mpeg'))
            self.assertTrue((output/'index.m3u8').is_file())
            self.assertTrue(list(output.glob('seg_*.ts')))
    def test_media_ui_contract(self):
        page=(ROOT/'frontend/index.html').read_text()
        js=(ROOT/'frontend/js/app.js').read_text()
        for ident in ('captureCamera','captureMicrophone','captureSpectrum','mediaTools','shareModal','shareOwnerList','addMenu','packMenu','mediaAudioSource'):
            self.assertIn('id="'+ident+'"',page)
        for token in ('async function openCapture(mode)','function openShareDialog(','function bindStreamMedia(','function openMediaTools(','function newEnvelope(','function movePackInside(','function createShare('):
            self.assertIn(token,js)
    def test_routes_present_and_ownership(self):
        source=(ROOT/'backend/app.py').read_text()
        share=(ROOT/'backend/studio_share.py').read_text()
        for route in ("@app.get('/api/media/<asset_id>/hls/<filename>')","@app.post('/api/projects/<pid>/media/process')","@app.post('/api/projects/<pid>/packs/archive')","@app.post('/api/projects/<pid>/media/transcribe')"):
            self.assertIn(route,source)
        for route in ("'/api/projects/<pid>/shares'","'/share/<token>/file'","'/api/projects/<pid>/share-requests/<rid>'"):
            self.assertIn(route,share)
        self.assertIn('store.project_for(conn,uid,pid)',share)
        self.assertIn('if not permitted(conn,link):abort(403)',share)

if __name__=='__main__':unittest.main()
