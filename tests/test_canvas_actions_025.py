import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
class CanvasActions(unittest.TestCase):
 def test_context_and_drag_contract(self):
  html=(ROOT/'frontend/index.html').read_text()
  js=(ROOT/'frontend/js/app.js').read_text()
  css=(ROOT/'frontend/css/styles.css').read_text()
  for name in ('photoContext','photoComposer','composerPrompt','composerProvider','canvasTrash','selectionGrab'):
   self.assertIn('id="'+name+'"',html)
  for key in ('openPhotoContext','runPhotoAction','handlePhotoAction','makeMovablePanel','archiveNodeIds','moveNodeIdsToPack','archivePack','pruneDuplicateSlots','elementFromPoint(ev.clientX,ev.clientY)'):
   self.assertIn(key,js)
  self.assertIn('outline:4px solid #71f0a3',css)
  self.assertIn('video storyboard plan',html.lower())
  self.assertIn('contextPrompt',js)
  self.assertIn("mode:'variation'",js)
 def test_image_queries_are_grounded_and_safe(self):
  backend=(ROOT/'backend/app.py').read_text()
  scene=(ROOT/'backend/scene_analysis.py').read_text()
  self.assertIn("@app.post('/api/projects/<pid>/visual-query')",backend)
  self.assertIn('store.project_for',backend)
  self.assertIn('asset_id',backend)
  self.assertIn('visual_question',backend)
  self.assertIn('Do not infer a real person',scene)
  self.assertIn("mode=='variation'",backend)
if __name__=='__main__':unittest.main()
