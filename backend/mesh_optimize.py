"""Bounded, opt-in local Blender operations with actionable diagnostics."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import json


# Blender is a separate Python runtime; do not pass the Flask virtualenv into it.
BLENDER_STRIP_ENV=('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','PYTHONUSERBASE','PYTHONSTARTUP','LD_PRELOAD')

def blender_runtime_env():
    env={k:v for k,v in os.environ.items() if k not in BLENDER_STRIP_ENV}
    env['PYTHONNOUSERSITE']='1'
    return env

class BlenderError(ValueError):
    def __init__(self,message,code='OPTIMISE_FAILED',detail=''):
        super().__init__(message)
        self.code=code
        # Details are shown only to the authenticated project's owner.
        self.detail=detail[:700]

def gltf_cli():
    managed=Path('/opt/umi-lab/tools/gltf-transform/node_modules/.bin/gltf-transform')
    return shutil.which('gltf-transform') or (str(managed) if managed.is_file() else None)

def blender_status():
    binary=shutil.which('blender')
    enabled=os.environ.get('UMI_ENABLE_BLENDER')=='1'
    if not binary:return {'installed':False,'enabled':enabled,'ready':False,'reason':'Blender executable is missing in the UMI service; deployment did not verify a usable installation.'}
    if not enabled:return {'installed':True,'enabled':False,'ready':False,'reason':'UMI Blender optimisation is not enabled in the active service. Re-deploy with the updated UMI installer.'}
    return {'installed':True,'enabled':True,'ready':True,'reason':'Blender executable found and optimisation enabled','version':None,'gltf_transform':bool(gltf_cli())}

def blender_error_details(run):
    """Retain the actual failure (especially a missing module), not Blender's exit banner."""
    chunks=[]
    for value in (getattr(run,'stdout',b''),getattr(run,'stderr',b'')):
        if isinstance(value,bytes):value=value.decode('utf-8','replace')
        if value:chunks.append(str(value))
    output='\n'.join(chunks)
    lines=[line.strip() for line in output.splitlines() if line.strip()]
    markers=('UMI_BLENDER_MODULE_MISSING:', 'ModuleNotFoundError:', 'ImportError:',
             'RuntimeError:', 'AttributeError:', 'ValueError:', 'Error:', 'Exception:')
    informative=[line for line in lines if any(mark in line for mark in markers)]
    if informative:
        # Prefer root cause over any subsequent generic "Blender quit" message.
        root_causes=[line for line in informative if ('ModuleNotFoundError:' in line or 'UMI_BLENDER_MODULE_MISSING:' in line)]
        message=(root_causes[-1] if root_causes else informative[-1])
    else:
        message=lines[-1] if lines else 'Blender process exited without diagnostic output'
    message=re.sub(r'(?:(?:/opt|/var|/tmp|/home)/[^\s]+)', '[file]',message)
    message=re.sub(r'[\x00-\x1f\x7f]', ' ',message)
    return message[:700]

def blender_missing_module(run):
    detail=blender_error_details(run)
    match=re.search(r"(?:ModuleNotFoundError: No module named|UMI_BLENDER_MODULE_MISSING:)\s*['\"]?([A-Za-z0-9_.]+)", detail)
    return match.group(1) if match else None

def optimized_glb(source,ratio=.65,texture=.5,options=None):
    """Create a new model; texture-only mode skips Blender and preserves mesh/rig bytes."""
    from .mesh_options import validate_plan, PlanError
    from .model_textures import replace_glb_textures, TextureError
    if options is None:
        options={'preset':'custom','geometry_ratio':ratio,'texture_scale':texture}
    try:plan=validate_plan(options)
    except PlanError as error:raise BlenderError(str(error),'INVALID_OPTIONS') from error
    scope=plan['scope'];fmt=plan['texture_format'];codec=plan['geometry_codec']
    cli=gltf_cli()
    if (codec!='none' or fmt in ('webp','ktx2-etc1s','ktx2-uastc')) and not cli:
        raise BlenderError('WebP, KTX2, Draco and Meshopt require glTF Transform. Native PNG/JPEG and texture downscaling remain available.','ADVANCED_CODEC_UNAVAILABLE')
    if scope!='textures':
        info=blender_status()
        if not info['ready']:raise BlenderError(info['reason'],'BLENDER_NOT_READY')
    source=Path(source)
    if source.suffix.lower()!='.glb' or not source.is_file():
        raise BlenderError('The selected result has no standalone GLB. Recover its preview first.','INVALID_SOURCE')
    if source.stat().st_size>90*1024*1024:raise BlenderError('GLB exceeds the 90 MB limit','TOO_LARGE')
    with tempfile.TemporaryDirectory(prefix='umi-blender-') as temp:
        intermediate=Path(temp)/'mesh.glb'
        if scope=='textures':
            intermediate.write_bytes(source.read_bytes())
        else:
            binary=shutil.which('blender')
            script=Path(__file__).with_name('blender_clean.py')
            # Material downscaling occurs *after* Blender export, independently of geometry.
            try:
                run=subprocess.run([binary,'--background','--factory-startup','--disable-autoexec',
                                    '--python',str(script),'--',str(source),str(intermediate),
                                    str(plan['geometry_ratio']), '1.0',json.dumps(plan,separators=(',',':'))],
                                   capture_output=True,timeout=115,check=False,env=blender_runtime_env())
            except subprocess.TimeoutExpired as error:
                raise BlenderError('Blender optimisation exceeded 115 seconds. Try a smaller model.','BLENDER_TIMEOUT') from error
            except OSError as error:
                raise BlenderError('Blender could not start under the UMI service account.','BLENDER_START_FAILED') from error
            if run.returncode!=0 or not intermediate.is_file():
                missing=blender_missing_module(run)
                if missing:raise BlenderError('Blender Python module missing: '+missing,'BLENDER_MODULE_MISSING',blender_error_details(run))
                raise BlenderError('Blender failed while simplifying or exporting the GLB.','BLENDER_EXEC_FAILED',blender_error_details(run))
        # Direct PNG/JPEG image processing supports formats without glTF Transform.
        # Geometry-only mode leaves embedded textures unchanged.
        current=intermediate
        if scope!='mesh' and (plan['texture_scale']<1 or plan['texture_divisor']>1 or fmt!='original'):
            native_format=fmt if fmt in ('png','jpeg') else 'original'
            try:
                binary=replace_glb_textures(current.read_bytes(),divisor=plan['texture_divisor'],
                         texture_scale=plan['texture_scale'],texture_format=native_format)
            except TextureError as error:
                if scope!='full' or 'No editable embedded' not in str(error):
                    raise BlenderError(str(error),'TEXTURE_PROCESSING_FAILED') from error
            else:
                native=Path(temp)/'materials.glb';native.write_bytes(binary);current=native
        if fmt in ('webp','ktx2-etc1s','ktx2-uastc') and scope!='mesh':
            cmd={'webp':'webp','ktx2-etc1s':'etc1s','ktx2-uastc':'uastc'}[fmt]
            # Avoid lossy normal map conversion for WebP. KTX2 codec preserves
            # the standard glTF texture semantics and required extensions.
            args=['--slots','{baseColorTexture,emissiveTexture}'] if fmt=='webp' else []
            candidate=Path(temp)/'encoded.glb'
            try:
                completed=subprocess.run([cli,cmd,str(current),str(candidate),*args],
                    capture_output=True,timeout=120,check=False,env=blender_runtime_env())
            except subprocess.TimeoutExpired as error:
                raise BlenderError('Texture encoding timed out','CODEC_TIMEOUT') from error
            if completed.returncode or not candidate.is_file():
                raise BlenderError('Texture encoder could not apply '+cmd,'CODEC_FAILED',blender_error_details(completed))
            current=candidate
        if codec!='none' and scope!='textures':
            candidate=Path(temp)/'compressed.glb'
            try:
                completed=subprocess.run([cli,codec,str(current),str(candidate)],
                    capture_output=True,timeout=120,check=False,env=blender_runtime_env())
            except subprocess.TimeoutExpired as error:
                raise BlenderError('Geometry compression timed out','CODEC_TIMEOUT') from error
            if completed.returncode or not candidate.is_file():
                raise BlenderError('Geometry encoder could not apply '+codec,'CODEC_FAILED',blender_error_details(completed))
            current=candidate
        if current.stat().st_size>100*1024*1024:raise BlenderError('Optimised result exceeds 100 MB','RESULT_TOO_LARGE')
        with current.open('rb') as input:file_header=input.read(12)
        if current.stat().st_size<20 or file_header[:4]!=b'glTF':
            raise BlenderError('Operation did not produce a valid GLB','INVALID_RESULT')
        return current.read_bytes()
