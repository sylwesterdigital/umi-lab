"""Release-level offline guarantees for a minimal 3D-first studio."""
import json
import re
import unittest
from pathlib import Path

BASE=Path(__file__).resolve().parent.parent

class FrontendContractTests(unittest.TestCase):
    def test_clean_launch_has_no_marketing_panels(self):
        page=(BASE/'frontend/index.html').read_text()
        self.assertIn('What car or vehicle would you like to create?',page)
        self.assertIn('id="vehicleCanvas"',page)
        self.assertNotIn('brand-mark',page)
        self.assertNotIn('intro-orb',page)
        self.assertIn('id="galleryPane" class="gallery-tray" hidden',page)
        self.assertIn('id="logWindow" class="log-window" hidden',page)
        self.assertIn('id="authOverlay" class="auth-overlay" hidden',page)

    def test_browser_csp_and_settings_contract(self):
        import base64,hashlib
        page=(BASE/'frontend/index.html').read_text()
        js=(BASE/'frontend/js/app.js').read_text()
        backend=(BASE/'backend/app.py').read_text()
        match=re.search(r'<script type="importmap">(.*?)</script>',page,re.S)
        self.assertIsNotNone(match)
        hashed=base64.b64encode(hashlib.sha256(match.group(1).encode()).digest()).decode()
        self.assertIn('sha256-'+hashed,backend)
        self.assertNotIn('unsafe-inline',backend.split('script-src')[1].split(';')[0])
        self.assertIn('id="modelsSettings"',page)
        self.assertIn("$('#'+name+'Settings')",js)
        self.assertNotIn('id="modelSettings"',page)
        self.assertIn('id="providerSelect"',page)
        self.assertIn('id="providerEditor"',page)
        self.assertNotIn('id="providerList"',page)
        self.assertIn("form.className='provider-fields-compact'",js)
        self.assertIn('temp_provider:tempConfig',js)
        self.assertIn('reference_ids:refs',js)
        self.assertIn("mode=automatic?'front_3q':",js)
        self.assertIn('enableGalleryDrag',js)
        self.assertIn('openPreview',js)
        self.assertIn('addResumeHint',js)
        self.assertIn('/continue',js)

    def test_real_physics_and_logs_controls(self):
        page=(BASE/'frontend/index.html').read_text()
        viewer=(BASE/'frontend/js/viewer.js').read_text()
        javascript=(BASE/'frontend/js/app.js').read_text()
        self.assertIn('cannon-es',page)
        self.assertIn('CANNON.RaycastVehicle',viewer)
        self.assertIn('world.step(',viewer)
        for token in ('enableLogDrag','copyLogs','refreshLogs','logLarger','logSmaller','collapseLogs','showAuth','uploadFont'):
            self.assertIn(token,javascript)
        self.assertIn('indexedDB.open',javascript)

if __name__=='__main__':unittest.main()
