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
SCOPES={'full','mesh','textures'}
DIVISORS={1,2,4,8,16}
CODECS={'none','draco','meshopt'}
BOOLS={'clean_loose','recalc_normals','smooth_faces','smooth_edges','weighted_normals','allow_rigged'}
TEXTURE_DEFAULTS={'texture_quality':85,'png_compression':6,'webp_effort':6,'webp_lossless':False}
DRACO_DEFAULTS={'draco_level':6,'draco_position_bits':14,'draco_normal_bits':10,
                'draco_texcoord_bits':12,'draco_color_bits':10,'draco_generic_bits':12}


class PlanError(ValueError):pass

def validate_plan(raw=None):
    raw=raw if isinstance(raw,dict) else {}
    preset=raw.get('preset','balanced')
    if preset not in (*PRESETS,'custom'):raise PlanError('Unknown optimization preset')
    plan=deepcopy(PRESETS['balanced'] if preset=='custom' else PRESETS[preset]);plan['preset']=preset
    plan['scope']=raw.get('scope','full') if preset=='custom' else 'full'
    plan['texture_divisor']=1
    plan.update(DRACO_DEFAULTS)
    plan.update(TEXTURE_DEFAULTS)
    if preset=='custom':
        if 'texture_divisor' in raw:
            try:plan['texture_divisor']=int(raw['texture_divisor'])
            except (TypeError,ValueError) as error:raise PlanError('Invalid texture divisor') from error
            if plan['texture_divisor'] not in DIVISORS:raise PlanError('Texture downscale must be 1×, 2×, 4×, 8× or 16×')
            plan['texture_scale']=1.0
        for key in ('geometry_ratio','texture_scale','merge_distance'):
            if key in raw:
                try:plan[key]=float(raw[key])
                except (TypeError,ValueError):raise PlanError('Invalid '+key)
        if 'texture_divisor' in raw:plan['texture_scale']=1.0
        for key in BOOLS:
            value=raw.get(key,False)
            if not isinstance(value,bool):raise PlanError(key+' must be true or false')
            plan[key]=value
        for key in TEXTURE_DEFAULTS:
            if key not in raw:continue
            value=raw[key]
            if key=='webp_lossless':
                if type(value) is not bool:raise PlanError('webp_lossless must be boolean')
            elif type(value) is not int:raise PlanError(key+' must be an integer')
            plan[key]=value
        for key in DRACO_DEFAULTS:
            if key in raw:
                value=raw[key]
                if type(value) is not int:raise PlanError(key+' must be an integer')
                plan[key]=value
        for key in ('texture_format','geometry_codec'):

            plan[key]=raw.get(key,plan[key])
    else:
        plan['allow_rigged']=False
    for key,lo,hi in (('geometry_ratio',.15,1.0),('texture_scale',.0625,1.0),('merge_distance',0.0,.01)):
        value=plan[key]
        if not lo<=value<=hi:raise PlanError(f'{key} must be between {lo} and {hi}')
    if plan['scope'] not in SCOPES:raise PlanError('Unsupported optimisation scope')
    if plan['scope']=='textures' and plan['geometry_codec']!='none':
        raise PlanError('Texture-only optimisation cannot change geometry compression')
    if plan['texture_format'] not in FORMATS:raise PlanError('Unsupported texture format')
    if plan['geometry_codec'] not in CODECS:raise PlanError('Unsupported geometry compression')
    if not 1<=plan['texture_quality']<=100:raise PlanError('Texture quality must be 1–100')
    if not 0<=plan['png_compression']<=9:raise PlanError('PNG compression must be 0–9')
    if not 0<=plan['webp_effort']<=6:raise PlanError('WebP effort must be 0–6')
    if not 0<=plan['draco_level']<=6:raise PlanError('Draco compression level must be 0–6')
    for key in ('draco_position_bits','draco_normal_bits','draco_texcoord_bits',
                'draco_color_bits','draco_generic_bits'):
        if not 0<=plan[key]<=30:raise PlanError(key+' must be 0–30 bits')

    return plan
