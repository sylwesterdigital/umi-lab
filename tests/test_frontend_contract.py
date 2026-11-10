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
