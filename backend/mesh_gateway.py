"""Single-asset 3D adapters for Meshy, Tripo v3, AHOLO Lux3D and optional GPU bridge.
All URLs are server-side, validated and private project assets; no credentials in logs.
GPU bridge is a contract for user-provisioned TripoSR/Hunyuan3D, not a bundled model.
"""
import base64
import ipaddress
import re
import socket
from urllib.parse import urlsplit, quote
from .providers import ProviderError, safe_base_url

TRIPO='https://openapi.tripo3d.ai/v3'
AHOLO='https://api.aholo.ai/global'
MESHY='https://api.meshy.ai/openapi/v1/image-to-3d'
ID_PATTERN=re.compile(r'[A-Za-z0-9_-]{1,120}\Z')

def _requests():
    try:import requests
    except ImportError as exc:raise ProviderError('3D transport unavailable; install backend requirements') from exc
    return requests

def _call(method,url,key,payload=None,files=None,auth='bearer'):
    requests=_requests()
    headers={'Authorization':('Bearer '+key if auth=='bearer' else key)}
    try:
        response=requests.request(method,url,headers=headers,json=payload if files is None else None,
                                  files=files,timeout=75,allow_redirects=False)
    except requests.RequestException as exc:raise ProviderError('3D provider connection failed') from exc
    if response.status_code>=300:raise ProviderError('3D provider HTTP '+str(response.status_code))
    try:return response.json()
    except ValueError as exc:raise ProviderError('3D provider returned invalid JSON') from exc

def _valid_id(value):
    value=str(value or '')
    if not ID_PATTERN.fullmatch(value):raise ProviderError('3D provider returned an invalid task ID')
    return value

def _aholo_root(config):
    url=safe_base_url(config.get('base_url') or AHOLO)
    if url=='https://api.aholo.ai':url+='/global'
    if url not in ('https://api.aholo.ai/global','https://api.aholo3d.cn'):
        raise ProviderError('Unrecognized AHOLO API gateway')
    return url

def _gpu_root(config):
    base=safe_base_url(config.get('base_url') or '')
    if not (base.startswith('https://') or base.startswith('http://127.0.0.1:') or base=='http://127.0.0.1'):
        raise ProviderError('GPU bridge requires HTTPS or local loopback')
    return base

def submit_mesh(provider_id,config,key,image,mime,textured,meshy_http):
    if provider_id=='meshy':
        if not key:raise ProviderError('Configure Meshy API key in Models')
        payload={'image_url':'data:'+mime+';base64,'+base64.b64encode(image).decode('ascii'),
                 'ai_model':config.get('model') or 'meshy-7.1','should_texture':textured,'target_formats':['glb']}
        result=meshy_http('POST',MESHY,key,payload)
        return _valid_id(result.get('result')),'PENDING',(30 if textured else 20)
    if provider_id=='tripo':
        if not key:raise ProviderError('Configure Tripo API key in Models')
        # Tripo v3 requires a file_token or public URL; private UMI assets must be uploaded.
        uploaded=_call('POST',TRIPO+'/files',key,files={'file':('part.png',image,mime)})
        if uploaded.get('code')!=0:raise ProviderError('Tripo rejected image upload')
        token=(uploaded.get('data') or {}).get('file_token')
        if not isinstance(token,str) or not token.startswith('file_'):raise ProviderError('Tripo did not issue a file token')
        payload={'input':token,'model':'v3.1-20260211','texture':textured,'pbr':textured}
        created=_call('POST',TRIPO+'/generation/image-to-model',key,payload)
        if created.get('code')!=0:raise ProviderError('Tripo rejected model request')
        return _valid_id((created.get('data') or {}).get('task_id')),'PENDING',0
    if provider_id=='aholo':
        if not key:raise ProviderError('Configure AHOLO API key in Models')
        base=_aholo_root(config)
        payload={'img':'data:'+mime+';base64,'+base64.b64encode(image).decode('ascii'),
                 'version':config.get('model') or 'G1','outputFormat':['glb','zip'],'enablePbr':textured}
        created=_call('POST',base+'/lux3d/v1/generate/img-to-3d/task/create',key,payload,auth='raw')
        if str(created.get('c'))!='0':raise ProviderError('AHOLO rejected model request: '+str(created.get('m',''))[:90])
        return _valid_id(created.get('d')),'PENDING',0
    if provider_id in ('gpu-triposr','gpu-hunyuan'):
        base=_gpu_root(config)
        if not key and not base.startswith('http://127.0.0.1'):
            raise ProviderError('Configure an API token for the GPU endpoint')
        model='TripoSR' if provider_id=='gpu-triposr' else 'Hunyuan3D'
        data=_call('POST',base+'/v1/image-to-3d',key or 'local',
                   {'image':'data:'+mime+';base64,'+base64.b64encode(image).decode('ascii'),
                    'model':model,'textured':textured})
        return _valid_id(data.get('task_id')),'PENDING',0
    raise ProviderError('Unsupported 3D provider')

def poll_mesh(provider_id,config,key,remote_id,meshy_http):
    tid=_valid_id(remote_id)
    if provider_id=='meshy':
        result=meshy_http('GET',MESHY+'/'+quote(tid),key)
        status=str(result.get('status') or 'UNKNOWN').upper()
        if status not in ('PENDING','IN_PROGRESS','SUCCEEDED','FAILED','CANCELED'):status='UNKNOWN'
        return status,(result.get('model_urls') or {}).get('glb',''),str((result.get('task_error') or {}).get('message',''))[:200]
    if provider_id=='tripo':
        result=_call('GET',TRIPO+'/tasks/'+quote(tid),key)
        if result.get('code')!=0:raise ProviderError('Tripo task query failed')
        task=result.get('data') or {}
        status={'queued':'PENDING','running':'IN_PROGRESS','success':'SUCCEEDED','failed':'FAILED','cancelled':'CANCELED','banned':'FAILED','expired':'FAILED'}.get(str(task.get('status','')).lower(),'UNKNOWN')
        return status,(task.get('output') or {}).get('model_url',''),str(task.get('error_message',''))[:200]
    if provider_id=='aholo':
        result=_call('GET',_aholo_root(config)+'/lux3d/v1/generate/task/get?taskid='+quote(tid),key,auth='raw')
        if str(result.get('c'))!='0':raise ProviderError('AHOLO task query failed')
        task=result.get('d') or {}
        status={'0':'PENDING','1':'IN_PROGRESS','3':'SUCCEEDED','4':'FAILED','6':'CANCELED'}.get(str(task.get('status')),'UNKNOWN')
        outputs=task.get('outputs') or []
        urls=[o.get('content','') if isinstance(o,dict) else '' for o in outputs]
        urls=[u if isinstance(u,str) and u.startswith('https://') else '' for u in urls]
        # AHOLO G1 delivers ZIP in slot 0 and a separate PBR GLB in slot 1.
        # Use output ordering when a signed URL does not end in an extension.
        glb=next((u for u in urls if urlsplit(u).path.lower().endswith('.glb')), '')
        if not glb and len(urls)>1 and urls[1] and not urlsplit(urls[1]).path.lower().endswith('.zip'):
            glb=urls[1]
        archive=next((u for u in urls if urlsplit(u).path.lower().endswith('.zip')), '')
        output=glb or archive or next((u for u in urls if u),'')
        return status,output,str(task.get('message') or result.get('m') or '')[:200]
    if provider_id in ('gpu-triposr','gpu-hunyuan'):
        result=_call('GET',_gpu_root(config)+'/v1/image-to-3d/tasks/'+quote(tid),key or 'local')
        status={'queued':'PENDING','running':'IN_PROGRESS','succeeded':'SUCCEEDED','completed':'SUCCEEDED','failed':'FAILED','cancelled':'CANCELED'}.get(str(result.get('status','')).lower(),'UNKNOWN')
        return status,str(result.get('model_url') or ''),str(result.get('error') or '')[:200]
    raise ProviderError('Unsupported 3D provider')

ALLOWED_MODEL_HOSTS=('meshy.ai','tripo3d.ai','tripo3d.com','aholo.ai','aholo3d.cn','kujiale.com','kujiale.com.cn','myqcloud.com')

def _output_host_allowed(provider_id,config,host):
    if provider_id in ('gpu-triposr','gpu-hunyuan'):
        return host==urlsplit(_gpu_root(config)).hostname
    return any(host==root or host.endswith('.'+root) for root in ALLOWED_MODEL_HOSTS)

def download_mesh_output(provider_id,config,url,limit):
    if not isinstance(url,str):raise ProviderError('Provider has not returned a downloadable model')
    parsed=urlsplit(url); host=parsed.hostname or ''
    local_bridge=(provider_id in ('gpu-triposr','gpu-hunyuan') and parsed.scheme=='http' and host in ('127.0.0.1','localhost'))
    if (parsed.scheme!='https' and not local_bridge) or not host or not _output_host_allowed(provider_id,config,host):
        raise ProviderError('Model download host is not approved')
    # Public DNS only: do not fetch private/link-local/loopback addresses via redirects or DNS.
    if not local_bridge:
        try:
            ips=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
            if not ips or any(not ipaddress.ip_address(v[4][0]).is_global for v in ips):
                raise ProviderError('Model download host must resolve to public IP addresses')
        except socket.gaierror as exc:raise ProviderError('Model download host is unavailable') from exc
    requests=_requests()
    try:
        response=requests.get(url,timeout=75,stream=True,allow_redirects=False)
        if response.status_code!=200:raise ProviderError('Model download returned HTTP '+str(response.status_code))
        blocks=[];total=0
        for block in response.iter_content(65536):
            total+=len(block)
            if total>limit:raise ProviderError('Model exceeds size limit')
            blocks.append(block)
    except requests.RequestException as exc:raise ProviderError('Model download failed') from exc
    blob=b''.join(blocks)
    if len(blob)<20:raise ProviderError('Provider returned empty model file')
    suffix=parsed.path.lower().split('/')[-1]
    extension='zip' if suffix.endswith('.zip') else 'glb'
    if extension=='zip' and not blob.startswith(b'PK\x03\x04'):
        raise ProviderError('Downloaded model is not a valid ZIP')
    if extension=='glb' and not blob.startswith(b'glTF'):
        raise ProviderError('Downloaded model is not a valid GLB')
    return blob,extension
