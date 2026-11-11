"""Prevent missing JavaScript handlers from making the design table unusable."""
import pathlib
import re
import unittest

ROOT=pathlib.Path(__file__).resolve().parent.parent

class StartupBindingsTest(unittest.TestCase):
    def test_activity_refresh_handler_exists(self):
        script=(ROOT/'frontend/js/app.js').read_text()
        self.assertRegex(script, r'async function refreshLogs\s*\(')
        self.assertIn("$('refreshLog').onclick=refreshLogs", script)
        self.assertIn("$('logScope').onchange=refreshLogs", script)
        self.assertIn("if(tab==='logs')refreshLogs()", script)
        self.assertIn("api('logs?scope='",script)
        self.assertIn("output.textContent=state.logText",script)

    def test_all_bound_controls_exist_in_html(self):
        script=(ROOT/'frontend/js/app.js').read_text()
        page=(ROOT/'frontend/index.html').read_text()
        # Controls accessed as literal IDs must exist before binding can finish.
        ids=set(re.findall(r"\$\('([a-zA-Z][a-zA-Z0-9]*)'\)",script))
        missing=sorted(x for x in ids if 'id="'+x+'"' not in page)
        self.assertEqual(missing,[])

if __name__=='__main__':unittest.main()
