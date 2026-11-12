"""Regression tests for v0.2.8 CSP and refining-image visibility."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

class VisibleRefinement028(unittest.TestCase):
    def test_policy_allows_glb_blob_textures_without_unsafe_inline_js(self):
        code=(ROOT/'backend/app.py').read_text()
        self.assertIn("connect-src 'self' blob: https://cdn.jsdelivr.net",code)
        self.assertNotIn("script-src 'self' 'unsafe-inline'",code)
    def test_source_image_shows_unobscured_activity(self):
        js=(ROOT/'frontend/js/app.js').read_text()
        css=(ROOT/'frontend/css/styles.css').read_text()
        self.assertIn('function updateRefineBadge(id,label)',js)
        self.assertIn('clearRefineBadge(node.id)',js)
        self.assertIn('progress();ticker=setInterval(progress,900)',js)
        self.assertIn('The original stays unchanged.',js)
        self.assertIn('.picture.is-refining .picture-inner img{opacity:1!important;filter:none!important}',css)
        self.assertIn('prefers-reduced-motion',css)
    def test_result_is_visible_and_retry_is_possible(self):
        js=(ROOT/'frontend/js/app.js').read_text()
        self.assertIn('selectPhoto(a.id);focusNode(byId(a.id),false)',js)
        self.assertIn("commitHistory('Refine image · '+node.label)",js)
        self.assertIn('Your prompt is still available to retry.',js)
        self.assertIn('r.assets?.[0]',js)
        self.assertIn("if(type==='image'&&!isReady",js)

if __name__=='__main__': unittest.main()
