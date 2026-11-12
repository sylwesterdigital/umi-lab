"""Regression checks for canvas selection and actionable mesh optimisation."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from backend import mesh_optimize

ROOT=Path(__file__).resolve().parents[1]

class CanvasTextSelection(unittest.TestCase):
    def test_noneditable_canvas_and_model_labels_not_selectable(self):
        css=(ROOT/'frontend/css/styles.css').read_text()
        js=(ROOT/'frontend/js/app.js').read_text()
        self.assertIn('#studio #board',css)
        self.assertIn('#boardWorld .mesh-card',css)
        self.assertIn('-webkit-user-select:none;user-select:none;',css)
        self.assertIn('#studio .note-editor',css)
        self.assertIn('-webkit-user-select:text;user-select:text;',css)
        self.assertIn("document.addEventListener('selectstart',e=>",js)
        self.assertIn('input,textarea,select,[contenteditable],.note-editor,.file-text-preview',js)
        self.assertIn('Optimising…',js)
        self.assertIn("api('mesh/optimisation/status')",js)

class BlenderDiagnostics(unittest.TestCase):
    def test_reports_actual_running_service_state(self):
        with patch.dict(mesh_optimize.os.environ,{'UMI_ENABLE_BLENDER':'1'}),patch.object(mesh_optimize.shutil,'which',return_value=None):
            self.assertFalse(mesh_optimize.blender_status()['ready'])
            self.assertFalse(mesh_optimize.blender_status()['installed'])
        with patch.dict(mesh_optimize.os.environ,{'UMI_ENABLE_BLENDER':'0'}),patch.object(mesh_optimize.shutil,'which',return_value='/usr/bin/blender'):
            self.assertEqual(mesh_optimize.blender_status()['reason'][:3],'UMI')
            self.assertFalse(mesh_optimize.blender_status()['ready'])
        with patch.dict(mesh_optimize.os.environ,{'UMI_ENABLE_BLENDER':'1'}),patch.object(mesh_optimize.shutil,'which',return_value='/usr/bin/blender'):
            self.assertTrue(mesh_optimize.blender_status()['ready'])

    def test_categorised_failures_and_redacted_log_excerpt(self):
        result=SimpleNamespace(stdout=b'Error: read failure at /var/lib/umi-lab/models/a.glb',stderr=b'',returncode=1)
        self.assertIn('Error:',mesh_optimize.blender_error_details(result))
        self.assertNotIn('/var/lib/umi-lab',mesh_optimize.blender_error_details(result))
        with patch.object(mesh_optimize,'blender_status',return_value={'ready':False,'reason':'Blender missing'}):
            with self.assertRaises(mesh_optimize.BlenderError) as caught:
                mesh_optimize.optimized_glb('/unused.glb')
            self.assertEqual(caught.exception.code,'BLENDER_NOT_READY')

    def test_optimisation_keeps_saved_original_and_handles_zip(self):
        app=(ROOT/'backend/app.py').read_text()
        self.assertIn('preview_blob(original,sidecar)',app)
        self.assertIn('TemporaryDirectory(prefix=\'umi-mesh-source-\'',app)
        self.assertIn("'action':'mesh_optimise'",app)
        self.assertIn('3D optimise: ',app)
        self.assertIn("@app.get('/api/mesh/optimisation/status')",app)

if __name__=='__main__':unittest.main()
