import unittest
import subprocess
import sys
from backend.providers import PRESETS, safe_base_url, ProviderError

class ProvidersTest(unittest.TestCase):
    def test_mesh_providers_have_distinct_protocol(self):
        from backend.providers import BY_ID
        for provider in ('tripo','meshy','aholo'):
            self.assertTrue(BY_ID[provider]['mesh3d'])
            self.assertFalse(BY_ID[provider]['images'])

    def test_presets_unique_and_have_protocol(self):
        self.assertGreaterEqual(len(PRESETS),15)
        self.assertEqual(len(set(p['id'] for p in PRESETS)),len(PRESETS))
        self.assertEqual({p['id'] for p in PRESETS if p['images']},{'openai','xai','gemini'})
    def test_preset_import_without_third_party_dependencies(self):
        # A fresh macOS Python needs no pip install to verify the release.
        # -S prevents site-packages from being imported, even if installed.
        probe = subprocess.run(
            [sys.executable, '-S', '-c',
             'from backend.providers import PRESETS, safe_base_url; '
             'assert len(PRESETS) >= 15; '
             'assert safe_base_url("https://api.openai.com/v1/").endswith("/v1")'],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)

    def test_base_url_security(self):
        self.assertEqual(safe_base_url('https://api.openai.com/v1/'),'https://api.openai.com/v1')
        self.assertEqual(safe_base_url('http://127.0.0.1:11434/v1'),'http://127.0.0.1:11434/v1')
        for url in ['http://169.254.169.254/latest','http://10.0.0.1','https://127.0.0.1','ftp://example.com','https://x:y@example.com','http://example.com']:
            with self.subTest(url=url),self.assertRaises(ProviderError):safe_base_url(url)

if __name__=='__main__':unittest.main()
