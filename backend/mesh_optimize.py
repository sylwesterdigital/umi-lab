"""Optional, opt-in local Blender operation with process/output limits."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

class BlenderError(ValueError): pass

def optimized_glb(source,ratio=.65,texture=.5):
    if os.environ.get('UMI_ENABLE_BLENDER')!='1':raise BlenderError('Blender optimisation is disabled. Enable UMI_ENABLE_BLENDER=1 after installing Blender on your server.')
    binary=shutil.which('blender')
    if not binary:raise BlenderError('Blender is not installed on this server')
    source=Path(source)
    if source.suffix.lower()!='.glb' or not source.is_file() or source.stat().st_size>90*1024*1024:raise BlenderError('Choose a valid GLB below 90 MB')
    try:
        ratio=max(.15,min(1,float(ratio)));texture=max(.25,min(1,float(texture)))
    except (ValueError,TypeError):raise BlenderError('Invalid optimisation settings')
    with tempfile.TemporaryDirectory(prefix='umi-blender-') as temp:
        result=Path(temp)/'optimised.glb'
        script=Path(__file__).with_name('blender_clean.py')
        try:
            run=subprocess.run([binary,'--background','--factory-startup','--disable-autoexec','--python',str(script),'--',str(source),str(result),str(ratio),str(texture)],capture_output=True,timeout=115,check=False)
        except (OSError,subprocess.TimeoutExpired) as exc:raise BlenderError('Blender failed or exceeded the time limit') from exc
        if run.returncode!=0 or not result.is_file():raise BlenderError('Blender could not optimise this GLB')
        if result.stat().st_size>100*1024*1024:raise BlenderError('Optimised file exceeded the size limit')
        return result.read_bytes()
