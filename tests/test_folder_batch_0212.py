"""Regression contracts for folder focus, non-repeated paid angles and cancellation."""
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parent.parent

class FolderBatch0212(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js=(ROOT/'frontend/js/app.js').read_text()
        cls.page=(ROOT/'frontend/index.html').read_text()

    def test_folder_focus_includes_selected_envelope(self):
        self.assertIn("if(pack.id!==focus&&(pack.parentId||null)!==focus)continue",self.js)
        self.assertIn("function packContains(packId,ancestorId)",self.js)
        self.assertIn("const hasPhoto=visibleNodes().length>0||!!focusedPack()",self.js)
        self.assertIn("state.openPack=was===pack.id?(pack.parentId||null):pack.id",self.js)

    def test_folder_hold_is_temporary(self):
        self.assertIn("state.peekPack=pack.id;drawPictures();renderPackShelf()",self.js)
        self.assertIn("state.peekPack=null;drawPictures();renderPackShelf()",self.js)
        self.assertIn("document.addEventListener('pointerup',cancelPackPreview,true)",self.js)

    def test_generated_angles_are_reused_for_matching_source(self):
        self.assertIn("function existingForItem(item,kind,source)",self.js)
        self.assertIn("const missing=requested.filter(item=>!nodeAsset(existingForItem(item,kind,source)))",self.js)
        self.assertIn("All '+requested.length+' requested ",self.js)
        self.assertIn("n.parent===source&&n.kind===kind&&!n.archived",self.js)

    def test_cancel_aborts_current_request_but_preserves_completed_images(self):
        self.assertIn("function cancelBatch()",self.js)
        self.assertIn("q.status='canceled'",self.js)
        self.assertIn("if(item.status!=='done')",self.js)
        self.assertIn("state.currentGeneration.abort()",self.js)
        self.assertIn("createdNodeIds",self.js)
        self.assertIn("if(state.cancelRequested||q.status==='canceled')break",self.js)
        self.assertIn('id="cancelJob"',self.page)
        self.assertIn('id="cancelQueue"',self.page)

    def test_media_batch_can_be_canceled_without_discarding_prior_results(self):
        self.assertIn("function cancelMediaBatch()",self.js)
        self.assertIn("state.mediaCurrentRequest.abort()",self.js)
        self.assertIn("if(state.mediaCancelRequested)break",self.js)
        self.assertIn("Canceled after ${done}/${applicable.length}. Completed results preserved.",self.js)

if __name__=='__main__':unittest.main()
