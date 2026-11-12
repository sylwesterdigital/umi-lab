"""Blender-side native Draco self-test (run as the UMI service user)."""
import sys, json, struct, traceback
from pathlib import Path

def main():
    import bpy
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    if len(args)!=1:raise RuntimeError('output path required')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    result=bpy.ops.export_scene.gltf(filepath=args[0],export_format='GLB',
       export_draco_mesh_compression_enable=True,export_draco_mesh_compression_level=6)
    if 'FINISHED' not in result:raise RuntimeError('Draco export did not finish')
    content=Path(args[0]).read_bytes()
    if len(content)<24 or content[:4]!=b'glTF':raise RuntimeError('Draco probe produced invalid GLB')
    length,kind=struct.unpack_from('<I4s',content,12)
    if kind!=b'JSON' or length>len(content)-20:raise RuntimeError('GLB JSON chunk missing')
    doc=json.loads(content[20:20+length])
    if 'KHR_draco_mesh_compression' not in doc.get('extensionsUsed',[]):
       raise RuntimeError('Blender produced GLB without Draco compression extension')
    print('UMI_DRACO_OK',flush=True)

if __name__=='__main__':
    try:main()
    except Exception:
        traceback.print_exc()
        sys.exit(54)
