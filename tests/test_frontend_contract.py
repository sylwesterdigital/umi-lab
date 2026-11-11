"""Design-table contracts: minimal launch, image nodes and generation queue."""
import json
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

class TabletopFrontendTests(unittest.TestCase):
    def setUp(self):
        self.page=(ROOT/'frontend/index.html').read_text()
        self.js=(ROOT/'frontend/js/app.js').read_text()
        self.css=(ROOT/'frontend/css/styles.css').read_text()
    def test_blank_workspace_has_no_legacy_panes(self):
        self.assertIn('What would you love to drive?',self.page)
        self.assertIn('id="board"',self.page)
        self.assertIn('id="pictures"',self.page)
        self.assertIn('id="links"',self.page)
        self.assertIn('id="promptForm"',self.page)
        self.assertNotIn('id="galleryPane"',self.page)
        self.assertNotIn('id="imagePreview"',self.page)
        self.assertNotIn('id="vehicleCanvas"',self.page)
        self.assertNotIn('id="chatFeed"',self.page)
        self.assertIn('id="drawer" class="drawer" hidden',self.page)
    def test_separate_angle_and_part_images(self):
        for marker in ("['front','Front'", "['rear','Rear'", "['side','Left side'", "['top','Top'", "['front_3q','Front ¾'", "['rear_3q','Rear ¾'"):
            self.assertIn(marker,self.js)
        self.assertIn("{mode:'component',label,part_name:label}",self.js)
        self.assertIn('source_asset_id:source||null',self.js)
        self.assertIn('reference_ids:source?[source]:[]',self.js)
        self.assertIn("state.nodes.some(n=>n.parent===source&&n.kind===kind&&n.label===it.label)",self.js)
        self.assertIn('await saveTable()',self.js)
        self.assertIn('state.stopAfter',self.js)
    def test_photoprint_world_and_minimal_feedback(self):
        for marker in ('.picture-inner{background:var(--photo)', '#linkLines path{stroke:', '.picture.hero{--w:', '.job-orb{', '.photo-actions{'):
            self.assertIn(marker,self.css)
        self.assertIn('pointermove',self.js)
        self.assertIn('screenToWorld',self.js)
        self.assertIn('fitView()',self.js)
        self.assertIn('image/png',self.js)
        self.assertIn('id="jobStatus"',self.page)
    def test_api_settings_profiles_and_version(self):
        self.assertIn('id="providerSelect"',self.page)
        self.assertIn('id="providerKey"',self.page)
        self.assertIn('id="authModal"',self.page)
        self.assertIn('id="profileModal"',self.page)
        self.assertIn("api('providers/'+id",self.js)
        self.assertIn("api('profile'",self.js)
        self.assertIn("api('session')",self.js)
        version=json.loads((ROOT/'version.json').read_text())['version']
        self.assertIn(f'content="{version}"',self.page)
        self.assertIn('script defer src="/static/js/app.js"',self.page)
