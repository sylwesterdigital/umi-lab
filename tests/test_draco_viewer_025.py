"""Draco-compressed GLBs must decode under our strict Content Security Policy."""
import io
import pathlib
import tempfile
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parent.parent

class DracoViewerContracts(unittest.TestCase):
    def test_early_local_decoder_config_and_no_external_csp_exception(self):
        page=(ROOT/'frontend/index.html').read_text()
        js=(ROOT/'frontend/js/model-decoder-config.js').read_text()
        backend=(ROOT/'backend/app.py').read_text()
        self.assertIn("settings.dracoDecoderLocation = '/static/decoders/draco/'",js)
        self.assertLess(page.index('/static/js/model-decoder-config.js'),page.index('@google/model-viewer@4.0.0'))
        self.assertIn("worker-src 'self' blob:",backend)
        self.assertIn("'wasm-unsafe-eval'",backend)
        self.assertNotIn('www.gstatic.com',backend)

    def test_asset_headers_and_glb_validation(self):
        from deploy import install
        self.assertTrue(install.valid_decoder_asset('draco_decoder.wasm',b'\x00asm\x01\x00\x00\x00'+b'x'*12000))
        self.assertFalse(install.valid_decoder_asset('draco_decoder.wasm',b'<html>broken</html>'))
        self.assertFalse(install.valid_decoder_asset('draco_decoder.js',b'<html>missing</html>'*200))

    def test_provisions_consistent_matching_decoder_files(self):
        from deploy import install
        wasm=b'\x00asm\x01\x00\x00\x00'+b'x'*12000
        texts={'draco_decoder.js':b'function DracoDecoderModule(){}'+b' '*2000,
               'draco_wasm_wrapper.js':b'function DracoDecoderModule(){}'+b' '*2000,
               'draco_decoder.wasm':wasm}
        seen=[]
        class Response:
            def __init__(self,data):self.data=data
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return self.data[:n]
        def fetch(request,timeout=0):
            seen.append(request.full_url)
            name=request.full_url.rsplit('/',1)[-1]
            return Response(texts[name])
        with tempfile.TemporaryDirectory() as tmp:
            result=install.prepare_draco_decoder(pathlib.Path(tmp),fetch=fetch)
            self.assertTrue((result/'draco_decoder.wasm').read_bytes().startswith(b'\x00asm'))
            self.assertEqual(len(seen),3)
            self.assertEqual({link.rsplit('/',1)[0] for link in seen},{install.DRACO_SOURCES[0].rstrip('/')})
            self.assertEqual(result,install.prepare_draco_decoder(pathlib.Path(tmp),fetch=lambda *_args,**_kw: self.fail('Should reuse verified local files')))

    def test_incomplete_decoder_does_not_provision_successfully(self):
        from deploy import install
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return b'<html>404</html>'
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(install.InstallError,'Cannot provision local Draco GLB decoder'):
                install.prepare_draco_decoder(pathlib.Path(tmp),fetch=lambda *_a,**_kw:Response())
            self.assertFalse((pathlib.Path(tmp)/'frontend/decoders/draco/draco_decoder.wasm').exists())

    def test_installer_before_active_release_switch(self):
        src=(ROOT/'deploy/install.py').read_text()
        self.assertLess(src.index('prepare_draco_decoder(release)'),src.index("link=BASE/'current'"))

if __name__=='__main__':unittest.main()
