"""Optional headless Blender geometry simplification; executed in a separate Blender process.
Arguments: source.glb, output.glb, decimation fraction, texture resolution factor.
"""
import sys
from pathlib import Path
try:
    import bpy
except ImportError:
    raise SystemExit('Blender Python required')
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
if len(args)!=4:raise SystemExit('Usage: blender_clean.py -- input.glb output.glb factor textures')
source,output,factor,scale=args
factor=max(.15,min(1,float(factor)));scale=max(.25,min(1,float(scale)))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(Path(source).resolve()))
for obj in list(bpy.context.scene.objects):
    if obj.type!='MESH' or len(obj.data.polygons)<600:continue
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    modifier=obj.modifiers.new('UMI geometry decimation','DECIMATE');modifier.ratio=factor
    try:bpy.ops.object.modifier_apply(modifier=modifier.name)
    except RuntimeError:pass
if scale<1:
    for img in bpy.data.images:
        if img.size[0]>0 and img.size[1]>0 and img.source=='FILE':
            img.scale(max(4,int(img.size[0]*scale)),max(4,int(img.size[1]*scale)))
bpy.ops.export_scene.gltf(filepath=str(Path(output).resolve()),export_format='GLB',export_apply=True)
