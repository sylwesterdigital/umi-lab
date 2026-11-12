"""User-reported canvas interaction regressions: folders must not change viewport."""
import pathlib
import re
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]

class FolderPointer0213(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js=(ROOT/'frontend/js/app.js').read_text()

    def test_enter_and_leave_folder_keep_viewport_stable(self):
        block=self.js.split('function openFolder(pack){',1)[1].split('\nfunction cancelPackPreview',1)[0]
        self.assertIn('state.openPack=was===pack.id?(pack.parentId||null):pack.id',block)
        self.assertIn('drawPictures();renderPackShelf()',block)
        for expr in ('fitPackView(', 'focusNode(', 'state.pan=', 'state.zoom=', 'setView('):
            self.assertNotIn(expr,block)

    def test_hold_and_release_keep_viewport_stable(self):
        block=self.js.split('function cancelPackPreview(){',1)[1].split('\nconst nodeAsset=',1)[0]
        self.assertIn('state.peekPack=null;drawPictures();renderPackShelf()',block)
        for expr in ('state.pan=', 'state.zoom=', 'setView(', 'fitPackView('):
            self.assertNotIn(expr,block)
        self.assertIn('state.peekPack=pack.id;drawPictures();renderPackShelf()',self.js)
        self.assertNotIn('fitPackView(pack.id)',self.js)

    def test_back_button_keeps_viewport_stable(self):
        block=self.js.split("back.onclick=()=>{",1)[1].split("};shelf.append(back)",1)[0]
        self.assertIn('state.openPack=active?.parentId||null',block)
        self.assertNotIn('state.pan=',block)
        self.assertNotIn('state.zoom=',block)
        self.assertNotIn('setView(',block)

    def test_add_menu_tracks_pointer_and_aligns_right_edge(self):
        self.assertIn("document.addEventListener('pointermove',e=>{addMenuPointer.x=e.clientX;addMenuPointer.y=e.clientY;}",self.js)
        block=self.js.split('function positionAddMenu(){',1)[1].split('\nfunction toggleAddMenu',1)[0]
        self.assertIn('anchorX-width',block)
        self.assertIn('window.innerHeight-height-gap',block)
        self.assertIn("m.style.bottom='auto'",block)
        self.assertIn("m.style.left=Math.max(gap",block)
        self.assertIn('positionAddMenu()',self.js)

if __name__=='__main__':unittest.main()
