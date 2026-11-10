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
    def test_systemd_isolation(self):
        text=install.unit_source(5071)
        self.assertIn('User=umi-lab',text)
        self.assertIn('ReadWritePaths=/var/lib/umi-lab',text)
        self.assertIn('127.0.0.1:5071',text)

if __name__=='__main__':unittest.main()
