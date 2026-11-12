"""UMI headless Blender GLB importer, non-destructive mesh/texture reduction.
Run by Blender's own Python runtime, never by Gunicorn's venv Python.
"""
import sys
import traceback
from pathlib import Path

def execute():
    import bpy
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    if len(args)!=4:raise ValueError('Expected source.glb output.glb geometry_ratio texture_scale')
    source,output,factor,scale=args
    factor=max(.15,min(1,float(factor)))
    scale=max(.25,min(1,float(scale)))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    imported=bpy.ops.import_scene.gltf(filepath=str(Path(source).resolve()))
    if 'FINISHED' not in imported:raise RuntimeError('Blender glTF import did not complete')
    for obj in list(bpy.context.scene.objects):
        if obj.type!='MESH' or len(obj.data.polygons)<600:continue
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active=obj
        modifier=obj.modifiers.new('UMI geometry decimation','DECIMATE')
        modifier.ratio=factor
        try:bpy.ops.object.modifier_apply(modifier=modifier.name)
        except RuntimeError:
            # A non-applied modifier should not break the original geometry.
            obj.modifiers.remove(modifier)
    if scale<1:
        for img in bpy.data.images:
            if img.size[0]>0 and img.size[1]>0 and img.source=='FILE':
                try:img.scale(max(4,int(img.size[0]*scale)),max(4,int(img.size[1]*scale)))
                except RuntimeError:pass
    exported=bpy.ops.export_scene.gltf(filepath=str(Path(output).resolve()),export_format='GLB',export_apply=True)
    if 'FINISHED' not in exported:raise RuntimeError('Blender glTF export did not complete')
    if not Path(output).is_file():raise RuntimeError('Blender did not create an output GLB')
    print('UMI_BLENDER_OPTIMISE_OK',flush=True)

if __name__=='__main__':
    try:execute()
    except ModuleNotFoundError as error:
        print('UMI_BLENDER_MODULE_MISSING: '+str(error.name or 'unknown'),file=sys.stderr,flush=True)
        traceback.print_exc()
        sys.exit(52)
    except Exception:
        traceback.print_exc()
        sys.exit(53)
