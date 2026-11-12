"""Bounded, opt-in local Blender operations with actionable diagnostics."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

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

def blender_status():
    binary=shutil.which('blender')
    enabled=os.environ.get('UMI_ENABLE_BLENDER')=='1'
    if not binary:return {'installed':False,'enabled':enabled,'ready':False,'reason':'Blender executable is missing in the UMI service; deployment did not verify a usable installation.'}
    if not enabled:return {'installed':True,'enabled':False,'ready':False,'reason':'UMI Blender optimisation is not enabled in the active service. Re-deploy with the updated UMI installer.'}
    return {'installed':True,'enabled':True,'ready':True,'reason':'Blender executable found and optimisation enabled','version':None}

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
            run=subprocess.run([binary,'--background','--factory-startup','--disable-autoexec','--python',str(script),'--',str(source),str(result),str(ratio),str(texture)],capture_output=True,timeout=115,check=False,env=blender_runtime_env())
        except subprocess.TimeoutExpired as exc:raise BlenderError('Blender optimisation exceeded 115 seconds. Try a smaller model.','BLENDER_TIMEOUT') from exc
        except OSError as exc:raise BlenderError('Blender could not start under the UMI service account.','BLENDER_START_FAILED') from exc
        if run.returncode!=0 or not result.is_file():
            missing=blender_missing_module(run)
            if missing:
                raise BlenderError('Blender is missing Python module '+missing+'. Server deployment must repair this dependency.',
                                   'BLENDER_MODULE_MISSING',blender_error_details(run))
            raise BlenderError('Blender failed while reading, simplifying or exporting the GLB.','BLENDER_EXEC_FAILED',blender_error_details(run))
        if result.stat().st_size>100*1024*1024:
            raise BlenderError('Optimised file exceeded the size limit','RESULT_TOO_LARGE')
        with result.open('rb') as stream:header=stream.read(4)
        if result.stat().st_size<12 or header!=b'glTF':
            raise BlenderError('Blender did not produce a valid GLB','INVALID_RESULT')
        return result.read_bytes()
