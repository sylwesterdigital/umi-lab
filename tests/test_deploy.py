import unittest
from deploy import install

class InstallConfigTest(unittest.TestCase):
    def test_http_isolated(self):
        text=install.http_nginx(5069)
        self.assertIn('server_name umi-lab.top;',text)
        self.assertIn('127.0.0.1:5069',text)
        self.assertNotIn('vehiclelab.xyz',text)
        self.assertNotIn('default_server',text)
    def test_https_isolated(self):
        text=install.https_nginx(5069)
        self.assertIn('listen 443 ssl',text)
        self.assertIn('ssl_certificate',text)
        self.assertIn('127.0.0.1:5069',text)
    def test_health_version_is_release_metadata(self):
        import json
        from pathlib import Path
        root=Path(__file__).resolve().parent.parent
        backend=(root/'backend/app.py').read_text()
        version=json.loads((root/'version.json').read_text())['version']
        self.assertIn("RELEASE_VERSION=RELEASE_INFO['version']",backend)
        self.assertIn('def health():return jsonify(ok=True,version=RELEASE_VERSION',backend)
        self.assertNotIn("version='0.1.5'",backend)
        self.assertIn(version,(root/'frontend/index.html').read_text())

    def test_health_check_reports_mismatch(self):
        from unittest.mock import patch
        import io,json
        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self,*args):return None
            def read(self,limit):return json.dumps({'ok':True,'version':'old','storage':'sqlite'}).encode()
        with patch('urllib.request.urlopen',return_value=FakeResponse()), patch('time.sleep',return_value=None):
            with self.assertRaisesRegex(install.InstallError,'expected release 0.1.7, got version'):
                install.http_health(5057,'0.1.7')

    def test_systemd_isolation(self):
        text=install.unit_source(5071)
        self.assertIn('User=umi-lab',text)
        self.assertIn('ReadWritePaths=/var/lib/umi-lab',text)
        self.assertIn('127.0.0.1:5071',text)

if __name__=='__main__':unittest.main()
