"""Bounded, opt-in local Blender operations with actionable diagnostics."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

class BlenderError(ValueError):
    def __init__(self,message,code='OPTIMISE_FAILED',detail=''):
        super().__init__(message)
        self.code=code
        # Details are shown only to the authenticated project's owner.
        self.detail=detail[:700]

def blender_status():
    binary=shutil.which('blender')
    enabled=os.environ.get('UMI_ENABLE_BLENDER')=='1'
    if not binary:return {'installed':False,'enabled':enabled,'ready':False,'reason':'Blender executable is missing in the UMI service; deployment did not verify a usable installation.'}
    if not enabled:return {'installed':True,'enabled':False,'ready':False,'reason':'UMI Blender optimisation is not enabled in the active service. Re-deploy with the updated UMI installer.'}
    return {'installed':True,'enabled':True,'ready':True,'reason':'Blender executable found and optimisation enabled','version':None}

def blender_error_details(run):
    # Blender stdout may contain a traceback; return only the final useful line
    # with paths and control characters redacted. Never log environment variables.
    stream=run.stderr or run.stdout or b''
    if isinstance(stream,bytes):stream=stream.decode('utf-8','replace')
    lines=[line.strip() for line in stream.splitlines() if line.strip()]
    informative=[line for line in lines if any(x in line.lower() for x in ('error','traceback','failed','exception','cannot','unsupported','out of memory'))]
    detail=(informative[-1] if informative else (lines[-1] if lines else 'No diagnostic output from Blender'))[:700]
    detail=re.sub(r'(?:(?:/opt|/var|/tmp|/home)/[^\s]+)', '[file]',detail)
    detail=re.sub(r'[\x00-\x1f\x7f]',' ',detail)
    return detail

def optimized_glb(source,ratio=.65,texture=.5):
    info=blender_status()
    if not info['ready']:
        raise BlenderError(info['reason'],'BLENDER_NOT_READY')
    binary=shutil.which('blender')
    source=Path(source)
    if source.suffix.lower()!='.glb' or not source.is_file():
        raise BlenderError('The selected 3D result has no standalone GLB to optimise. Recover its preview first.','INVALID_SOURCE')
    if source.stat().st_size>90*1024*1024:
        raise BlenderError('GLB is larger than the 90 MB optimisation limit.','TOO_LARGE')
    try:
        ratio=max(.15,min(1,float(ratio)));texture=max(.25,min(1,float(texture)))
    except (ValueError,TypeError):raise BlenderError('Invalid geometry or texture settings','INVALID_OPTIONS')
    with tempfile.TemporaryDirectory(prefix='umi-blender-') as temp:
        result=Path(temp)/'optimised.glb'
        script=Path(__file__).with_name('blender_clean.py')
        try:
            run=subprocess.run([binary,'--background','--factory-startup','--disable-autoexec','--python',str(script),'--',str(source),str(result),str(ratio),str(texture)],capture_output=True,timeout=115,check=False)
        except subprocess.TimeoutExpired as exc:raise BlenderError('Blender optimisation exceeded 115 seconds. Try a smaller model.','BLENDER_TIMEOUT') from exc
        except OSError as exc:raise BlenderError('Blender could not start under the UMI service account.','BLENDER_START_FAILED') from exc
        if run.returncode!=0 or not result.is_file():
            raise BlenderError('Blender failed while reading, simplifying or exporting the GLB.','BLENDER_EXEC_FAILED',blender_error_details(run))
        if result.stat().st_size>100*1024*1024:
            raise BlenderError('Optimised file exceeded the size limit','RESULT_TOO_LARGE')
        with result.open('rb') as stream:header=stream.read(4)
        if result.stat().st_size<12 or header!=b'glTF':
            raise BlenderError('Blender did not produce a valid GLB','INVALID_RESULT')
        return result.read_bytes()
