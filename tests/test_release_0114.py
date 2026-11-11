"""Regression checks for the redesigned photo-table UX."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
class TabletopRegressionTests(unittest.TestCase):
    def test_no_incorrect_multiview_sheet(self):
        js=(ROOT/'frontend/js/app.js').read_text()
        self.assertNotIn("generateRequest(source,'sheet'",js)
        self.assertIn("generateSequence(angles.map",js)
        self.assertIn("generateSequence(items,'component')",js)
        self.assertIn("'The exact vehicle shown in the one supplied image'",js)
    def test_component_contract(self):
        src=(ROOT/'backend/app.py').read_text()
        self.assertIn("elif mode=='component':",src)
        self.assertIn('ONE component per image, not a component sheet',src)
        self.assertIn("if mode=='component' and len(ids)!=1",src)
        self.assertIn("'component_images':component_images",src)
    def test_preserve_legacy_data_without_legacy_ui(self):
        js=(ROOT/'frontend/js/app.js').read_text()
        self.assertIn("localStorage.setItem(lastKey,id)",js)
        self.assertIn("if(project?.settings?.tabletop?.nodes?.length)",js)
        self.assertIn('renderSources()',js)
        self.assertIn('selected_asset:state.hero||null',js)
