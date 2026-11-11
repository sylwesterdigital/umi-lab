"""Dependency-free checks for reliable reference-first image workflows."""
import json
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

class Release141Tests(unittest.TestCase):
    def test_brand_and_release_notes(self):
        page=(ROOT/'frontend/index.html').read_text()
        app=(ROOT/'frontend/js/app.js').read_text()
        notes=(ROOT/'frontend/js/release-notes.js').read_text()
        ver=json.loads((ROOT/'version.json').read_text())['version']
        self.assertEqual(ver,'0.1.16')
        for element in ('releaseVersion','releaseNotes','releaseNotesList','updatesButton','closeReleaseNotes'):
            self.assertIn('id="'+element+'"',page)
        self.assertIn("'umi.release.seen.'+RELEASE_VERSION",app)
        self.assertIn('showReleaseNotes(false)',app)
        self.assertIn("version:'0.1.16'",notes)
        self.assertIn('Development updates',page)

    def test_selection_move_and_busy_indicators(self):
        page=(ROOT/'frontend/index.html').read_text()
        editor=(ROOT/'frontend/js/image-editor.js').read_text()
        app=(ROOT/'frontend/js/app.js').read_text()
        for ident in ('previewMove','previewProcessing','previewProcessingText','previewProcessingClock',
                      'galleryProgress','galleryProgressText','galleryProgressClock','gallerySource'):
            self.assertIn('id="'+ident+'"',page)
        self.assertIn("drag={kind:'move'",editor)
        self.assertIn("ev.key.toLowerCase()==='g'",editor)
        self.assertIn("clamp(original.x+pt.x-drag.from.x,0,image.naturalWidth-original.w)",editor)
        self.assertIn("busy=true;busyStarted=Date.now()",editor)
        self.assertIn('galleryProgress(',app)

    def test_annotate_uses_open_image_not_stale_chat(self):
        app=(ROOT/'frontend/js/app.js').read_text()
        backend=(ROOT/'backend/app.py').read_text()
        self.assertIn("focusGalleryAsset(asset.id);previewEditor.open",app)
        self.assertIn("if(!automatic&&['annotate','system','part','segment'].includes(mode))",app)
        self.assertIn("source_asset_id:refs[0]||null",app)
        self.assertIn("if references:brief='The exact same vehicle shown in the supplied reference image(s)'",backend)
        self.assertIn("return jsonify(error='Active source must be a selected reference'),400",backend)

if __name__=='__main__':unittest.main()
