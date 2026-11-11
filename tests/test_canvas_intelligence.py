"""v0.2.4: no paid inference calls; contracts and persistent history tests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import db, scene_analysis
ROOT=Path(__file__).resolve().parent.parent

class SceneAnalysisTests(unittest.TestCase):
    def test_normalize_arbitrary_objects(self):
        result=scene_analysis.normalize("""```json
{"subject":"workspace with bicycle and jewelry","title":"Desk display", "materials":["steel","glass"],
 "objects":[{"name":"Pearl pendant","group":"Jewelry","material":"pearl","confidence":"medium","visible":true},
 {"name":"Electric bicycle","group":"Transport","material":"metal","confidence":"high","visible":true}]}
```""")
        self.assertEqual(result['subject'],'workspace with bicycle and jewelry')
        self.assertEqual(result['objects'][0]['name'],'Pearl pendant')
        self.assertFalse(result['market_verified'])
    def test_image_goes_to_configured_vision_model(self):
        from PIL import Image
        import io
        buf=io.BytesIO();Image.new('RGB',(50,40),'blue').save(buf,'PNG')
        preset={'id':'meta','protocol':'openai','base_url':'https://api.meta.ai/v1','model':'muse-spark-1.3'}
        with patch('backend.scene_analysis._post',return_value={'choices':[{'message':{'content':json.dumps({'subject':'unknown object','objects':[{'name':'hinge'}]})}}]}) as post:
            result=scene_analysis.analyze(preset,preset,'fake',buf.getvalue(),'image/png')
        self.assertEqual(result['objects'][0]['name'],'hinge')
        payload=post.call_args.args[2]
        self.assertEqual(payload['messages'][0]['content'][1]['type'],'image_url')
        self.assertIn('data:image/jpeg;base64,',payload['messages'][0]['content'][1]['image_url']['url'])
        self.assertNotIn('age_years',result)
    def test_history_storage_survives_reopen(self):
        with tempfile.TemporaryDirectory() as path:
            db.init(path)
            with db.connect(path) as conn:
                names={r['name'] for r in conn.execute('PRAGMA table_info(canvas_revisions)')}
                self.assertTrue({'project_id','snapshot','action','created_at'}.issubset(names))
                self.assertIsNotNone(conn.execute("SELECT name FROM sqlite_master WHERE name='canvas_revision_cursor'").fetchone())
    def test_frontend_controls_are_wired(self):
        app=(ROOT/'frontend/js/app.js').read_text()
        page=(ROOT/'frontend/index.html').read_text()
        style=(ROOT/'frontend/css/styles.css').read_text()
        for control in ('selectionTool','marquee','selectionBar','selectionToPack','selectionCopy','selectionRemove','historyUndo','historyRedo','analyzePhoto','analysisResults','deletePack'):
            self.assertIn('id="'+control+'"',page)
        for mark in ("projects/'+state.project.id+'/canvas-history", 'function travelHistory(', 'function analyzeCurrent(', 'state.analyses=', 'function moveSelectionToPack(', 'function duplicateSelection(', "e.key.toLowerCase()==='x'", 'state.queues[source]=state.queue'):
            self.assertIn(mark,app)
        self.assertIn('top:135px;right:20px;bottom:auto',style)
        self.assertIn('!n.archived', (ROOT/'frontend/js/canvas-layouts.js').read_text())
        self.assertIn('id="sceneKind" hidden',page)

if __name__=='__main__':unittest.main()
