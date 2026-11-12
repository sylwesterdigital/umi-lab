"""Regression coverage for v0.2.14: avoid missing Blender and inert 3D cards."""
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from deploy import install

ROOT=Path(__file__).resolve().parents[1]

class BlenderInstallTests(unittest.TestCase):
    def test_installer_enables_blender_before_cutover(self):
        source=(ROOT/'deploy/install.py').read_text()
        self.assertIn('prepare_blender()', source)
        self.assertLess(source.index('        prepare_blender()\n        seed_admin(release)'),source.index('        write_atomic(UNIT,unit_source(port))'))
        self.assertIn('Environment=UMI_ENABLE_BLENDER=1',install.unit_source(5057))
        self.assertIn('ReadWritePaths=/var/lib/umi-lab',install.unit_source(5057))

    def test_existing_blender_only_verifies_no_apt(self):
        class Response:
            returncode=0
            stdout='Blender 3.4\nUMI_BLENDER_OK\n'
            stderr=''
        with patch.object(install.shutil,'which',side_effect=lambda n: '/usr/bin/blender' if n=='blender' else None), patch.object(install,'run',return_value=Response()) as call:
            result=install.prepare_blender()
        self.assertEqual(result,'/usr/bin/blender')
        self.assertEqual(call.call_count,1)
        self.assertEqual(call.call_args[0][0][0],'/usr/bin/blender')

    def test_absent_blender_installs_and_verifies(self):
        class Response:
            returncode=0
            stdout='UMI_BLENDER_OK'
            stderr=''
        paths=iter([None,'/usr/bin/blender'])
        def which(name):return next(paths) if name=='blender' else '/usr/bin/apt-get'
        class Disk:
            free=5_000_000_000
        with patch.object(install.shutil,'which',side_effect=which),patch.object(install.shutil,'disk_usage',return_value=Disk()),patch.object(install,'run',return_value=Response()) as call:
            self.assertEqual(install.prepare_blender(),'/usr/bin/blender')
        self.assertIn('apt-get',call.call_args_list[0].args[0][0]);self.assertEqual(call.call_count,2)

    def test_headless_check_is_required(self):
        class Response:
            returncode=1
            stdout=''
            stderr='missing gltf addon'
        with patch.object(install.shutil,'which',return_value='/usr/bin/blender'),patch.object(install,'run',return_value=Response()):
            with self.assertRaisesRegex(install.InstallError,'GLB capability'):install.prepare_blender()

    def test_card_border_and_interior_orbit(self):
        js=(ROOT/'frontend/js/app.js').read_text()
        css=(ROOT/'frontend/css/styles.css').read_text()
        self.assertNotIn("!e.target.closest('header')",js)
        self.assertIn("e.target.closest('model-viewer,.mesh-card-actions",js)
        self.assertIn('card.classList.add(\'is-dragging\')',js)
        self.assertIn('protectMeshOrbit(model)',js)
        self.assertIn('.mesh-card{touch-action:none;cursor:grab}',css)

if __name__=='__main__':unittest.main()
