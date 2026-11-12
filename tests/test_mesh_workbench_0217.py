"""v0.2.17 profile validation, non-destructive outputs and mesh card UI contracts."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from backend import db,mesh_optimize
from backend.mesh_options import validate_plan,PlanError,PRESETS

ROOT=Path(__file__).resolve().parents[1]

class MeshWorkbenchTests(unittest.TestCase):
    def test_four_presets_and_custom_controls(self):
        self.assertEqual(set(PRESETS),{'quality','balanced','small','ultra'})
        self.assertEqual(validate_plan({'preset':'quality'})['geometry_ratio'],1)
        self.assertEqual(validate_plan({'preset':'ultra'})['texture_scale'],.25)
        plan=validate_plan({'preset':'custom','geometry_ratio':.4,'texture_scale':.5,
                            'merge_distance':.0002,'clean_loose':True,'smooth_edges':True,
                            'texture_format':'webp','geometry_codec':'meshopt'})
        self.assertTrue(plan['smooth_edges'])
        self.assertEqual(plan['geometry_codec'],'meshopt')
        for raw in ({'preset':'unknown'},
                    {'preset':'custom','geometry_ratio':0},
                    {'preset':'custom','texture_format':'executable'},
                    {'preset':'custom','clean_loose':'false'},
                    {'preset':'custom','merge_distance':42}):
            with self.subTest(raw=raw),self.assertRaises(PlanError):validate_plan(raw)

    def test_codec_unavailable_fails_before_blender_process(self):
        with patch.object(mesh_optimize,'gltf_cli',return_value=None),patch.object(mesh_optimize.subprocess,'run') as run:
            with self.assertRaises(mesh_optimize.BlenderError) as caught:
                mesh_optimize.optimized_glb('example.glb',options={'preset':'custom','texture_format':'webp'})
            self.assertEqual(caught.exception.code,'ADVANCED_CODEC_UNAVAILABLE')
            run.assert_not_called()

    def test_optimisation_records_are_separate_from_source(self):
        with tempfile.TemporaryDirectory() as root:
            db.init(root)
            with db.connect(root) as connection:
                fields=[field['name'] for field in connection.execute('PRAGMA table_info(mesh_optimisations)')]
            for field in ('task_id','source_task_id','before_bytes','after_bytes','options'):
                self.assertIn(field,fields)
        source=(ROOT/'backend/app.py').read_text()
        self.assertIn('new_id=store.new_id()',source)
        self.assertIn("source_size=source_glb_size",source)
        self.assertIn('INSERT INTO mesh_optimisations',source)
        self.assertIn('after_bytes',source)

    def test_canvas_actions_are_compact_and_progress_visible(self):
        html=(ROOT/'frontend/index.html').read_text()
        js=(ROOT/'frontend/js/app.js').read_text()
        css=(ROOT/'frontend/css/styles.css').read_text()
        for token in ('meshOptPresetsTab','meshOptCustomTab','meshOptGeometry','meshOptMerge',
                      'meshOptDeleteLoose','meshOptSmooth','meshOptSmoothEdges','meshOptTextureFormat','meshOptCodec'):
            self.assertIn('id="'+token+'"',html)
        self.assertIn("more.className='mesh-more'",js)
        self.assertIn("menu.className='mesh-menu'",js)
        self.assertIn('function drawMeshProcessingCards(',js)
        self.assertIn('function meshFileSize(',js)
        self.assertIn("card.className='mesh-card is-processing'",js)
        self.assertIn('.mesh-optimize-backdrop',css)
        self.assertNotIn("actions.className='mesh-card-actions'",js)

    def test_deployer_keeps_blender_preflight_and_optional_codec(self):
        source=(ROOT/'deploy/install.py').read_text()
        self.assertIn('verify_blender_optimiser(release)',source)
        self.assertIn('prepare_gltf_transform()',source)
        self.assertIn("'@gltf-transform/cli@4.5.0'",source)
        self.assertIn('check=False',source)

if __name__=='__main__':unittest.main()
