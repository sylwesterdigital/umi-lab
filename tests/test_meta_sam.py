"""Meta SAM segmentation transport contract, no paid inference calls."""
import json
import sys
import types
import unittest
from unittest.mock import Mock, patch
from backend.meta_sam import segment_image
from backend.providers import BY_ID, ProviderError

class MockResponse:
    status_code=200
    headers={'Content-Type':'text/event-stream; charset=utf-8'}
    def iter_lines(self,decode_unicode=False):
        events=[{'type':'response.output_text.delta','delta':'<0f>0<|box;x1=4;y1=7;x2=25;y2=33;w=100;h=80|><|mask;x=0;y=0;data=3,5,!encoded|>'},
                {'type':'response.completed'}]
        for event in events:yield b'data: '+json.dumps(event).encode()
        yield b'data: [DONE]'
    def close(self):pass

class SegmentationTests(unittest.TestCase):
    def test_meta_sam_request_and_records(self):
        # The watcher validates on macOS without installed transport dependencies.
        # Supply a fake requests module so the contract test remains offline.
        fake_requests=types.ModuleType('requests')
        fake_requests.RequestException=Exception
        fake_requests.post=Mock(return_value=MockResponse())
        with patch.dict(sys.modules,{'requests':fake_requests}):
            result=segment_image(BY_ID['meta'],BY_ID['meta'],'secret',b'png','image/png','front bumper')
        call=fake_requests.post
        self.assertEqual(result['count'],1)
        self.assertEqual(result['mask_count'],1)
        self.assertEqual(result['objects'][0]['box'],[4,7,26,34])
        self.assertIn('<|mask;',result['objects'][0]['mask_token'])
        args,kw=call.call_args
        self.assertEqual(args[0],'https://api.meta.ai/v1/responses')
        self.assertEqual(kw['json']['model'],'sam-3.1')
        self.assertEqual(kw['json']['input'][0]['content'][0]['text'],'front bumper')
        self.assertTrue(kw['json']['stream'])
        self.assertEqual(kw['headers']['Accept'],'text/event-stream')

    def test_non_meta_denied_without_request(self):
        with self.assertRaises(ProviderError):
            segment_image(BY_ID['xai'],BY_ID['xai'],'secret',b'png','image/png','wheel')

if __name__=='__main__':unittest.main()
