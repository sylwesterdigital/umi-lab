"""Contract checks for image-reference forwarding without contacting paid providers."""
import base64
import unittest
from unittest.mock import patch
from backend.providers import PRESETS, generate_image, ProviderError

class ProviderImageReferenceTests(unittest.TestCase):
    def preset(self,name):return next(p for p in PRESETS if p['id']==name)
    def test_xai_single_reference_uses_edits(self):
        p=self.preset('xai');sample=b'fake-jpeg'
        result={'data':[{'b64_json':base64.b64encode(b'generated-image').decode()}]}
        with patch('backend.providers._post',return_value=result) as post:
            data,mime=generate_image(p,p,'secret','Keep the original SUV',[ (sample,'image/jpeg') ])
        self.assertEqual(data,b'generated-image')
        url,headers,payload=post.call_args.args
        self.assertTrue(url.endswith('/images/edits'))
        self.assertEqual(payload['image']['url'],'data:image/jpeg;base64,'+base64.b64encode(sample).decode())
        self.assertNotIn('images',payload)

    def test_xai_multi_reference_sends_all_images(self):
        p=self.preset('xai');result={'data':[{'b64_json':base64.b64encode(b'new').decode()}]}
        with patch('backend.providers._post',return_value=result) as post:
            generate_image(p,p,'secret','Same vehicle',[(b'a','image/png'),(b'b','image/jpeg')])
        self.assertEqual(len(post.call_args.args[2]['images']),2)
        self.assertTrue(post.call_args.args[0].endswith('/images/edits'))

    def test_openai_multi_reference_edits(self):
        p=self.preset('openai');result={'data':[{'b64_json':base64.b64encode(b'new').decode()}]}
        with patch('backend.providers._post',return_value=result) as post:
            generate_image(p,p,'secret','Match same car',[(b'a','image/png'),(b'b','image/jpeg')])
        payload=post.call_args.args[2]
        self.assertEqual(len(payload['images']),2)
        self.assertEqual(payload['images'][0]['image_url'],'data:image/png;base64,YQ==')
        self.assertTrue(post.call_args.args[0].endswith('/images/edits'))

    def test_gemini_inline_image_reference(self):
        p=self.preset('gemini');result={'candidates':[{'content':{'parts':[{'inlineData':{'data':base64.b64encode(b'new').decode(),'mimeType':'image/png'}}]}}]}
        with patch('backend.providers._post',return_value=result) as post:
            generate_image(p,p,'secret','Reference sheet',[(b'a','image/png')])
        parts=post.call_args.args[2]['contents'][0]['parts']
        self.assertEqual(parts[1]['inlineData']['data'],'YQ==')
        self.assertEqual(parts[0]['text'],'Reference sheet')

    def test_rejects_more_than_five(self):
        p=self.preset('xai')
        with self.assertRaises(ProviderError):generate_image(p,p,'secret','Car',[(b'a','image/png')]*6)

if __name__=='__main__':unittest.main()
