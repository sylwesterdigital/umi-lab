"""Blender subprocess only. Import geometry/rig/animations, export as self-contained GLB.
Blender must be called with --background --factory-startup --disable-autoexec.
"""
import sys
from pathlib import Path
import bpy


def main():
    args=sys.argv[sys.argv.index('--')+1:]
    src,output,ext=map(str,args[:3])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if ext=='.fbx':bpy.ops.import_scene.fbx(filepath=src)
    elif ext=='.obj':bpy.ops.wm.obj_import(filepath=src)
    elif ext=='.stl':bpy.ops.wm.stl_import(filepath=src)
    elif ext=='.ply':bpy.ops.wm.ply_import(filepath=src)
    elif ext=='.dae':bpy.ops.wm.collada_import(filepath=src)
    elif ext=='.gltf':bpy.ops.import_scene.gltf(filepath=src)
    elif ext in ('.usd','.usda','.usdc','.usdz'):bpy.ops.wm.usd_import(filepath=src)
    else:raise RuntimeError('Unsupported Blender importer: '+ext)
    if not any(o.type in ('MESH','CURVE','SURFACE','FONT') for o in bpy.data.objects):
        raise RuntimeError('No renderable geometry in source model')
    bpy.ops.export_scene.gltf(filepath=output,export_format='GLB',use_selection=False)
    if not Path(output).is_file() or Path(output).stat().st_size<100:
        raise RuntimeError('Blender did not export a valid GLB')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('UMI_MODEL_IMPORT_ERROR: '+str(exc)[:220],file=sys.stderr)
        raise
