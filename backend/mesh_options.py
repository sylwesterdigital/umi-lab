"""Validated, repeatable optimization plans for source-preserving GLB exports."""
from copy import deepcopy

PRESETS={
    'quality': dict(geometry_ratio=1.0,texture_scale=1.0,clean_loose=True,merge_distance=0.0,
                    recalc_normals=False,smooth_faces=False,weighted_normals=False,
                    texture_format='original',geometry_codec='none'),
    'balanced': dict(geometry_ratio=.8,texture_scale=.75,clean_loose=True,merge_distance=0.0,
                     recalc_normals=False,smooth_faces=False,weighted_normals=False,
                     texture_format='original',geometry_codec='none'),
    'small': dict(geometry_ratio=.55,texture_scale=.5,clean_loose=True,merge_distance=0.0,
                  recalc_normals=False,smooth_faces=False,weighted_normals=False,
                  texture_format='original',geometry_codec='none'),
    'ultra': dict(geometry_ratio=.30,texture_scale=.25,clean_loose=True,merge_distance=0.0,
                  recalc_normals=False,smooth_faces=False,weighted_normals=False,
                  texture_format='original',geometry_codec='none'),
}
FORMATS={'original','png','jpeg','webp','ktx2-etc1s','ktx2-uastc'}
CODECS={'none','draco','meshopt'}
BOOLS={'clean_loose','recalc_normals','smooth_faces','smooth_edges','weighted_normals','allow_rigged'}

class PlanError(ValueError):pass

def validate_plan(raw=None):
    raw=raw if isinstance(raw,dict) else {}
    preset=raw.get('preset','balanced')
    if preset not in (*PRESETS,'custom'):raise PlanError('Unknown optimization preset')
    plan=deepcopy(PRESETS['balanced'] if preset=='custom' else PRESETS[preset]);plan['preset']=preset
    if preset=='custom':
        for key in ('geometry_ratio','texture_scale','merge_distance'):
            if key in raw:
                try:plan[key]=float(raw[key])
                except (TypeError,ValueError):raise PlanError('Invalid '+key)
        for key in BOOLS:
            value=raw.get(key,False)
            if not isinstance(value,bool):raise PlanError(key+' must be true or false')
            plan[key]=value
        for key in ('texture_format','geometry_codec'):
            plan[key]=raw.get(key,plan[key])
    else:
        plan['allow_rigged']=False
    for key,lo,hi in (('geometry_ratio',.15,1.0),('texture_scale',.25,1.0),('merge_distance',0.0,.01)):
        value=plan[key]
        if not lo<=value<=hi:raise PlanError(f'{key} must be between {lo} and {hi}')
    if plan['texture_format'] not in FORMATS:raise PlanError('Unsupported texture format')
    if plan['geometry_codec'] not in CODECS:raise PlanError('Unsupported geometry compression')
    return plan
