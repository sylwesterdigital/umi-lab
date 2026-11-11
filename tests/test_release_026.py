"""Regression contracts for world envelopes, 3D progress and media documents."""
import json
import tempfile
import unittest
from pathlib import Path
from backend import db

ROOT=Path(__file__).resolve().parent.parent

class Canvas026Contract(unittest.TestCase):
    def test_release_versions_and_script_syntax_contract(self):
        version=json.loads((ROOT/'version.json').read_text())['version']
        self.assertEqual(version,'0.2.6')
        self.assertIn('content="0.2.6"',(ROOT/'frontend/index.html').read_text())

    def test_envelopes_are_in_scaled_canvas_and_position_worldwise(self):
        html=(ROOT/'frontend/index.html').read_text()
        js=(ROOT/'frontend/js/app.js').read_text()
        css=(ROOT/'frontend/css/styles.css').read_text()
        self.assertLess(html.index('id="boardWorld"'),html.index('id="packShelf"'))
        self.assertLess(html.index('id="packShelf"'),html.index('id="marquee"'))
        self.assertIn('wrapper.style.left=pack.x',js)
        self.assertIn('screenToWorld(ev.clientX,ev.clientY)',js)
        self.assertIn('function migratePackCoords()',js)
        self.assertIn('#boardWorld>.pack-shelf',css)
        # The dragged card must remain transparent for elementFromPoint hit-testing.
        self.assertLess(js.index('const hit=document.elementFromPoint(ev.clientX,ev.clientY);fig.classList.remove'),js.index('const dropPack=hit?.closest'))

    def test_3d_status_and_preview(self):
        app=(ROOT/'frontend/js/app.js').read_text()
        api=(ROOT/'backend/app.py').read_text()
        html=(ROOT/'frontend/index.html').read_text()
        self.assertIn('function drawMeshCards()',app)
        self.assertIn('function scheduleMeshPoll()',app)
        self.assertIn('id="meshCards"',html)
        self.assertIn('id="meshStageViewer"',html)
        self.assertIn("@app.get('/api/mesh-tasks/<task_id>/preview')",api)
        self.assertIn('with z.open(member)',api)
        self.assertIn('status=status',api)

    def test_persistent_image_documents_and_exports(self):
        with tempfile.TemporaryDirectory() as t:
            db.init(t)
            with db.connect(t) as conn:
                names=[r['name'] for r in conn.execute("PRAGMA table_info('asset_documents')")]
            self.assertIn('content',names)
            self.assertIn('model',names)
            self.assertIn('prompt',names)
        api=(ROOT/'backend/app.py').read_text()
        self.assertIn('def save_asset_document(',api)
        self.assertIn('def list_asset_documents(',api)
        self.assertIn("z.writestr(name,json.dumps(doc_obj,indent=2))",api)

    def test_video_preview_and_private_media(self):
        html=(ROOT/'frontend/index.html').read_text()
        js=(ROOT/'frontend/js/app.js').read_text()
        api=(ROOT/'backend/app.py').read_text()
        self.assertIn('id="videoStagePlayer"',html)
        self.assertIn('video/mp4,video/webm',html)
        self.assertIn('function openVideoPreview(',js)
        self.assertIn('if not asset[\'mime\'].startswith(\'image/\'):',api)
        self.assertIn("@authenticated\ndef media(",api)

if __name__=='__main__':unittest.main()
