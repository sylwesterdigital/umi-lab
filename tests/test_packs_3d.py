"""Dependency-free version, packs, queue and verified Meshy API contract tests."""
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from backend import db

ROOT=pathlib.Path(__file__).resolve().parent.parent

class CollectionTest(unittest.TestCase):
    def test_222_catalogue_entries(self):
        catalog=json.loads((ROOT/'parts.json').read_text())
        self.assertEqual(sum(len(group['parts']) for group in catalog['assemblies']),222)
    def test_queue_and_pack_are_restorable(self):
        script=(ROOT/'frontend/js/app.js').read_text()
        page=(ROOT/'frontend/index.html').read_text()
        for literal in ['state.queue=table.queue', "q.status='running'", "q.status=failed?'failed'", "await saveTable()", "status:'planned'", 'renderPackShelf()', 'renderPackDetail()', "function focusNode("]:
            self.assertIn(literal,script)
        for id in ['partCollection','partSearch','partPreview','partsPlan','partsStart','queueRest','resumeQueue','retryFailed','followMode','packShelf','packName','packNotes','meshTaskList','imageSearch']:
            self.assertIn('id="'+id+'"',page)
    def test_persistent_mesh_tasks_table(self):
        with tempfile.TemporaryDirectory() as path:
            db.init(path)
            with db.connect(path) as conn:
                names=[x[1] for x in conn.execute('PRAGMA table_info(mesh_tasks)').fetchall()]
            for col in ('project_id','asset_id','user_id','provider_task_id','status','model_file','credits_est'):
                self.assertIn(col,names)
    def test_mesh_http_is_restricted(self):
        source=(ROOT/'backend/app.py').read_text()
        self.assertIn("https://api.meshy.ai/openapi/v1/image-to-3d",source)
        self.assertIn("if not url.startswith('https://api.meshy.ai/openapi/v1/image-to-3d')",source)
        gateway=(ROOT/'backend/mesh_gateway.py').read_text()
        self.assertIn("meshy.ai",gateway)
        self.assertIn("SELECT id,status FROM mesh_tasks",source)
        self.assertIn("target_formats",gateway)
        self.assertIn("return jsonify(error='3D task already exists",source)

if __name__=='__main__':unittest.main()
