"""Headless non-destructive UMI Blender operations. Source file never modified.

The last positional argument is a JSON options object. It is optional so the
previous installer smoke test and 0.2.16 API remain compatible.
"""
import json
import sys
import traceback
from pathlib import Path

def execute():
    import bpy
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    if len(args) not in (4,5):raise ValueError('Expected source.glb output.glb geometry_ratio texture_scale [options_json]')
    source,output,factor,scale=args[:4]
    config=json.loads(args[4]) if len(args)==5 else {}
    factor=max(.15,min(1,float(factor)))
    scale=max(.25,min(1,float(scale)))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    imported=bpy.ops.import_scene.gltf(filepath=str(Path(source).resolve()))
    if 'FINISHED' not in imported:raise RuntimeError('Blender glTF import did not complete')
    for obj in list(bpy.context.scene.objects):
        if obj.type!='MESH':continue
        rigged=bool(obj.find_armature() or (obj.data.shape_keys and len(obj.data.shape_keys.key_blocks)>0))
        if rigged and not config.get('allow_rigged',False):
            print('UMI_SKIPPED_RIGGED '+obj.name,flush=True)
            continue
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active=obj
        if config.get('clean_loose') or float(config.get('merge_distance',0))>0 or config.get('recalc_normals'):
            import bmesh
            bm=bmesh.new()
            try:
                bm.from_mesh(obj.data)
                if config.get('clean_loose'):
                    loose=[e for e in bm.edges if not e.link_faces]
                    if loose:bmesh.ops.delete(bm,geom=loose,context='EDGES')
                    isolated=[v for v in bm.verts if not v.link_edges]
                    if isolated:bmesh.ops.delete(bm,geom=isolated,context='VERTS')
                dist=float(config.get('merge_distance',0))
                if dist>0 and bm.verts:bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=dist)
                if config.get('recalc_normals') and bm.faces:bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
                bm.to_mesh(obj.data);obj.data.update()
            finally:bm.free()
        if config.get('smooth_faces'):
            for face in obj.data.polygons:face.use_smooth=True
        if config.get('smooth_edges'):
            for edge in obj.data.edges:
                if hasattr(edge,'use_edge_sharp'):edge.use_edge_sharp=False
        if factor<1 and len(obj.data.polygons)>=600:
            modifier=obj.modifiers.new('UMI geometry decimation','DECIMATE')
            modifier.ratio=factor
            try:bpy.ops.object.modifier_apply(modifier=modifier.name)
            except RuntimeError:obj.modifiers.remove(modifier)
        if config.get('weighted_normals') and len(obj.data.polygons)>0:
            try:
                mod=obj.modifiers.new('UMI weighted normals','WEIGHTED_NORMAL')
                bpy.ops.object.modifier_apply(modifier=mod.name)
            except (RuntimeError,TypeError,AttributeError):
                if 'mod' in locals() and mod.name in obj.modifiers:obj.modifiers.remove(mod)
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
        traceback.print_exc();sys.exit(52)
    except Exception:
        traceback.print_exc();sys.exit(53)
