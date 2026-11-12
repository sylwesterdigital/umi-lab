"""Locally imported 3D models: bounded validation, Blender conversion, GLB metadata.

No remote URL fetching. No archive extraction, and no execution of embedded scripts.
"""
from __future__ import annotations
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

SUPPORTED={'.glb': 'model/gltf-binary', '.gltf': 'model/gltf+json',
           '.fbx': 'application/octet-stream', '.obj': 'text/plain',
           '.stl': 'application/octet-stream', '.ply': 'application/octet-stream',
           '.dae': 'model/vnd.collada+xml', '.usd': 'application/octet-stream',
           '.usda': 'application/octet-stream', '.usdc': 'application/octet-stream',
           '.usdz': 'model/vnd.usdz+zip'}
MAX_UPLOAD_3D=64*1024*1024
MAX_PREVIEW_3D=60_000_000

class ModelImportError(ValueError):
    pass


def glb_document(data: bytes) -> dict:
    if len(data)<20 or data[:4]!=b'glTF':
        raise ModelImportError('Not a GLB 2.0 file')
    version, size=struct.unpack_from('<II',data,4)
    if version!=2 or size!=len(data) or size>MAX_PREVIEW_3D:
        raise ModelImportError('Invalid GLB version, length, or maximum preview size (60 MB)')
    chunk_size,chunk_type=struct.unpack_from('<II',data,12)
    if chunk_type!=0x4E4F534A or 20+chunk_size>size:
        raise ModelImportError('Missing GLB JSON chunk')
    try:
        doc=json.loads(data[20:20+chunk_size].decode('utf-8').rstrip('\x00 \t\r\n'))
    except (UnicodeDecodeError,ValueError) as error:
        raise ModelImportError('Invalid GLB JSON') from error
    if not isinstance(doc,dict) or not isinstance(doc.get('asset'),dict) or doc['asset'].get('version','')[:1]!='2':
        raise ModelImportError('Not a glTF 2.0 asset')
    pos=20+chunk_size
    while pos<size:
        if pos+8>size:raise ModelImportError('Truncated GLB chunk')
        length,_=struct.unpack_from('<II',data,pos)
        pos+=8+length
        if pos>size:raise ModelImportError('GLB chunk exceeds declared length')
    return doc


def model_metadata(path: Path) -> dict:
    """Read only the bounded JSON chunk, not textures or mesh buffers."""
    with Path(path).open('rb') as stream:
        header=stream.read(20)
        if len(header)<20 or header[:4]!=b'glTF':
            raise ModelImportError('No viewable GLB file')
        version,size,chunk_size,chunk_type=struct.unpack_from('<IIII',header,4)
        if version!=2 or size!=path.stat().st_size or size>MAX_PREVIEW_3D or chunk_type!=0x4E4F534A or chunk_size>8*1024*1024 or chunk_size+20>size:
            raise ModelImportError('Invalid GLB structure or preview size')
        try:doc=json.loads(stream.read(chunk_size).decode('utf-8').rstrip('\x00 \t\r\n'))
        except (ValueError,UnicodeDecodeError) as error:raise ModelImportError('Invalid GLB metadata') from error
    animations=doc.get('animations',[]) if isinstance(doc,dict) else []
    if not isinstance(animations,list):animations=[]
    names=[str(a.get('name') or f'Animation {i+1}')[:80] for i,a in enumerate(animations[:40]) if isinstance(a,dict)]
    skins=doc.get('skins',[]) if isinstance(doc,dict) else []
    return {'animations':names,'rigged':bool(skins),'skin_count':len(skins) if isinstance(skins,list) else 0}


def validate_gltf_payload(data: bytes):
    try:doc=json.loads(data.decode('utf-8'))
    except (ValueError,UnicodeDecodeError) as exc:raise ModelImportError('Invalid glTF JSON file') from exc
    if not isinstance(doc,dict) or not str(doc.get('asset',{}).get('version','')).startswith('2.'):
        raise ModelImportError('glTF 2.0 required')
    # Single-file import only: never resolve local paths, file:// URIs or external URLs.
    uris=[v.get('uri','') for v in doc.get('buffers',[])+doc.get('images',[]) if isinstance(v,dict) and 'uri' in v]
    if any(not str(uri).startswith('data:') for uri in uris):
        raise ModelImportError('External glTF textures/buffers need to be embedded; export as .glb')


def convert_to_glb(src:Path,dest:Path,extension:str,script:Path,timeout=170):
    extension=extension.lower()
    if extension not in SUPPORTED:
        raise ModelImportError('Unsupported 3D extension')
    if extension=='.glb':
        data=src.read_bytes()
        glb_document(data)
        shutil.copyfile(src,dest)
        return model_metadata(dest)
    if extension=='.gltf':validate_gltf_payload(src.read_bytes())
    blender=shutil.which('blender')
    if not blender:raise ModelImportError('Blender converter unavailable on this server; GLB imports work directly')
    env={k:v for k,v in os.environ.items() if not k.startswith(('PYTHONHOME','PYTHONPATH','PYTHONUSERBASE','VIRTUAL_ENV','PYTHONNOUSERSITE'))}
    try:
        p=subprocess.run([blender,'--background','--factory-startup','--disable-autoexec','--threads','2','--python',str(script),'--',str(src),str(dest),extension],
                         capture_output=True,text=True,timeout=timeout,env=env,cwd=str(src.parent))
    except subprocess.TimeoutExpired as exc:raise ModelImportError('Blender 3D import timed out') from exc
    if p.returncode or not dest.is_file():
        # Do not expose filesystem paths or environment. Surface the meaningful exporter error.
        lines=[line.strip() for line in (p.stderr+'\n'+p.stdout).splitlines() if 'Error:' in line or 'UMI_MODEL_IMPORT_ERROR' in line]
        message=(lines[-1] if lines else 'Blender could not convert this model')[:240]
        raise ModelImportError(message)
    return model_metadata(dest)
