"""Model adapters. Providers outside the supported protocols remain configurable only via router."""
import base64
import ipaddress
import json
import socket
from urllib.parse import urlparse

# Presets are editable; model names are examples, not an exhaustive list.
PRESETS = [
 {'id':'openai','name':'OpenAI','protocol':'openai','base_url':'https://api.openai.com/v1','model':'gpt-4.1-mini','image_model':'gpt-image-2.5-flare','images':True},
 {'id':'xai','name':'xAI / Grok','protocol':'openai','base_url':'https://api.x.ai/v1','model':'grok-4.7','image_model':'grok-imagine-image-2.0','images':True},
 {'id':'gemini','name':'Google Gemini','protocol':'gemini','base_url':'https://generativelanguage.googleapis.com/v1beta','model':'gemini-2.5-flash','image_model':'gemini-3.1-flash-image','images':True},
 {'id':'anthropic','name':'Anthropic','protocol':'anthropic','base_url':'https://api.anthropic.com/v1','model':'claude-sonnet-4-5','image_model':'','images':False},
 {'id':'openrouter','name':'OpenRouter','protocol':'openai','base_url':'https://openrouter.ai/api/v1','model':'openai/gpt-4.1-mini','image_model':'','images':False},
 {'id':'deepseek','name':'DeepSeek','protocol':'openai','base_url':'https://api.deepseek.com/v1','model':'deepseek-chat','image_model':'','images':False},
 {'id':'groq','name':'Groq','protocol':'openai','base_url':'https://api.groq.com/openai/v1','model':'llama-3.3-70b-versatile','image_model':'','images':False},
 {'id':'together','name':'Together / Meta','protocol':'openai','base_url':'https://api.together.xyz/v1','model':'meta-llama/Llama-3.3-70B-Instruct-Turbo','image_model':'','images':False},
 {'id':'fireworks','name':'Fireworks','protocol':'openai','base_url':'https://api.fireworks.ai/inference/v1','model':'accounts/fireworks/models/llama-v3p3-70b-instruct','image_model':'','images':False},
 {'id':'cerebras','name':'Cerebras','protocol':'openai','base_url':'https://api.cerebras.ai/v1','model':'llama3.1-8b','image_model':'','images':False},
 {'id':'mistral','name':'Mistral','protocol':'openai','base_url':'https://api.mistral.ai/v1','model':'mistral-small-latest','image_model':'','images':False},
 {'id':'perplexity','name':'Perplexity','protocol':'openai','base_url':'https://api.perplexity.ai','model':'sonar','image_model':'','images':False},
 {'id':'moonshot','name':'Moonshot / Kimi','protocol':'openai','base_url':'https://api.moonshot.ai/v1','model':'kimi-k2-0905-preview','image_model':'','images':False},
 {'id':'nvidia','name':'NVIDIA NIM','protocol':'openai','base_url':'https://integrate.api.nvidia.com/v1','model':'meta/llama-3.1-70b-instruct','image_model':'','images':False},
 {'id':'siliconflow','name':'SiliconFlow','protocol':'openai','base_url':'https://api.siliconflow.com/v1','model':'deepseek-ai/DeepSeek-V3','image_model':'','images':False},
 {'id':'huggingface','name':'Hugging Face','protocol':'openai','base_url':'https://router.huggingface.co/v1','model':'meta-llama/Llama-3.3-70B-Instruct','image_model':'','images':False},
 {'id':'ollama','name':'Ollama','protocol':'openai','base_url':'http://127.0.0.1:11434/v1','model':'llama3.2','image_model':'','images':False,'local':True},
 {'id':'lmstudio','name':'LM Studio','protocol':'openai','base_url':'http://127.0.0.1:1234/v1','model':'local-model','image_model':'','images':False,'local':True},
 {'id':'vllm','name':'vLLM','protocol':'openai','base_url':'http://127.0.0.1:8000/v1','model':'local-model','image_model':'','images':False,'local':True},
 {'id':'tripo','name':'Tripo 3D','protocol':'tripo','base_url':'https://api.tripo3d.ai/v2/openapi','model':'Turbo-v1.0','image_model':'','images':False,'mesh3d':True},
 {'id':'aholo','name':'AHOLO Lux3D','protocol':'aholo','base_url':'https://api.aholo.ai','model':'G1','image_model':'','images':False,'mesh3d':True},
 {'id':'meshy','name':'Meshy 3D','protocol':'meshy','base_url':'https://api.meshy.ai','model':'meshy-7.1','image_model':'','images':False,'mesh3d':True},
 {'id':'custom','name':'Custom Router','protocol':'openai','base_url':'','model':'','image_model':'','images':False},
]
BY_ID = {p['id']:p for p in PRESETS}

class ProviderError(ValueError):
    pass


def safe_base_url(url):
    """Prevent non-loopback cleartext endpoints and embedded credentials."""
    parsed=urlparse(url)
    if not url or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderError('Invalid API endpoint')
    if parsed.scheme == 'https' and parsed.hostname:
        # Prevent straightforward server-side calls to private IPv4/IPv6 over HTTPS.
        try:
            ip = ipaddress.ip_address(parsed.hostname)
            if not ip.is_global: raise ProviderError('Private IP endpoints are not allowed')
        except ValueError as exc:
            if isinstance(exc,ProviderError):raise
        return url.rstrip('/')
    if parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1','localhost','::1'):
        return url.rstrip('/')
    raise ProviderError('Use HTTPS or local HTTP on loopback')


def _json_response(resp):
    if not resp.ok:
        try:
            message=resp.json().get('error',{})
            if isinstance(message,dict):message=message.get('message','Provider error')
        except ValueError:
            message='Provider returned HTTP '+str(resp.status_code)
        raise ProviderError(str(message)[:350])
    try:return resp.json()
    except ValueError as exc:raise ProviderError('Provider returned invalid JSON') from exc


def _post(url, headers, payload, timeout=75):
    # Keep provider presets/URL validation dependency-free for macOS ZIP checks.
    # HTTP transport is required only when a real model request is made.
    try:
        import requests
    except ImportError as exc:
        raise ProviderError('Model transport unavailable: install backend requirements') from exc
    try:
        # No redirects: avoid credential forwarding and unexpected SSRF.
        response = requests.post(url,json=payload,headers=headers,timeout=timeout,allow_redirects=False)
    except requests.RequestException as exc:
        raise ProviderError('Provider unreachable: '+str(exc)[:180]) from exc
    return _json_response(response)


def chat(preset, config, key, messages):
    if preset.get('mesh3d'):raise ProviderError('Use 3D generation rather than chat for this provider')
    model=config['model'] or preset['model']
    if not model:raise ProviderError('Set a chat model in Settings')
    base=safe_base_url(config['base_url'] or preset['base_url'])
    if not key and not preset.get('local') and not base.startswith('http://127.0.0.1'):
        raise ProviderError('Add an API key in Settings')
    if preset['protocol']=='gemini':
        parts=[{'role':'model' if m['role']=='assistant' else 'user','parts':[{'text':m['content']}]} for m in messages]
        data=_post(base+'/models/'+model+':generateContent', {'x-goog-api-key':key}, {'contents':parts},timeout=85)
        try:return ''.join(part.get('text','') for part in data['candidates'][0]['content']['parts']).strip()
        except (KeyError,IndexError,TypeError) as exc:raise ProviderError('Empty Gemini response') from exc
    if preset['protocol']=='anthropic':
        system='You are UMI LAB, an expert vehicle designer. Be precise; never claim an image reveals hidden geometry or dimensions.'
        data=_post(base+'/messages',{'x-api-key':key,'anthropic-version':'2023-06-01'},
                   {'model':model,'max_tokens':1500,'system':system,'messages':messages},timeout=85)
        return '\n'.join(p.get('text','') for p in data.get('content',[]) if p.get('type')=='text').strip()
    headers={'Authorization':'Bearer '+(key or 'local'),'Content-Type':'application/json'}
    data=_post(base+'/chat/completions',headers,{'model':model,'messages':[{'role':'system','content':'You are UMI LAB, an expert vehicle concept engineer. Give concise practical advice. Concept-only geometry is not validated for manufacturing.'}]+messages,'stream':False},timeout=85)
    try:
        content=data['choices'][0]['message']['content']
        return content if isinstance(content,str) else ' '.join(x.get('text','') for x in content if isinstance(x,dict))
    except (KeyError,IndexError,TypeError) as exc:raise ProviderError('Empty chat completion') from exc


def generate_image(preset, config, key, prompt, reference_images=None):
    if not preset.get('images'):raise ProviderError('This provider does not support native image generation in v0.1')
    model=config['image_model'] or preset['image_model']
    if not model:raise ProviderError('Choose an image model in Settings')
    base=safe_base_url(config['base_url'] or preset['base_url'])
    if not key:raise ProviderError('Set an API key before generating images')
    references=reference_images or []
    if len(references)>5:raise ProviderError('Select at most five image references')
    if preset['protocol']=='gemini':
        parts=[{'text':prompt}]+[{'inlineData':{'mimeType':mime,'data':base64.b64encode(blob).decode('ascii')}} for blob,mime in references]
        data=_post(base+'/models/'+model+':generateContent',{'x-goog-api-key':key},
             {'contents':[{'parts':parts}],'generationConfig':{'responseModalities':['TEXT','IMAGE']}},timeout=150)
        for candidate in data.get('candidates',[]):
            for part in candidate.get('content',{}).get('parts',[]):
                blob=part.get('inlineData') or part.get('inline_data')
                if blob:
                    return base64.b64decode(blob['data'],validate=True),blob.get('mimeType','image/png')
        raise ProviderError('Gemini did not return image data')
    payload={'model':model,'prompt':prompt,'n':1}
    endpoint=base+'/images/generations'
    if preset['id']=='xai':payload.update({'response_format':'b64_json','aspect_ratio':'3:2'})
    if references:
        # Use actual image-edit endpoints; never silently discard selected references.
        endpoint=base+'/images/edits'
        refs=[f'data:{mime};base64,{base64.b64encode(blob).decode("ascii")}' for blob,mime in references]
        if preset['id']=='xai':
            payload={'model':model,'prompt':prompt,'response_format':'b64_json','aspect_ratio':'3:2'}
            if len(refs)==1:payload['image']={'url':refs[0],'type':'image_url'}
            else:payload['images']=[{'url':uri,'type':'image_url'} for uri in refs]
        elif preset['id']=='openai':
            payload={'model':model,'prompt':prompt,'images':[{'image_url':uri} for uri in refs],'n':1}
            if model.startswith('gpt-image-1.5'):payload['input_fidelity']='high'
        else:
            raise ProviderError('Selected provider does not support image-reference editing')
    data=_post(endpoint,{'Authorization':'Bearer '+key,'Content-Type':'application/json'},payload,timeout=180)
    try:
        item=data['data'][0]
        if item.get('b64_json'):
            return base64.b64decode(item['b64_json'],validate=True), 'image/png'
        # xAI can return a temporary URL. Do not fetch arbitrary hosts.
        url=item.get('url','')
        parsed=urlparse(url)
        if preset['id']=='xai' and parsed.scheme=='https' and parsed.hostname and (parsed.hostname=='imgen.x.ai' or parsed.hostname.endswith('.x.ai')):
            try:
                import requests
            except ImportError as exc:
                raise ProviderError('Model transport unavailable: install backend requirements') from exc
            response=requests.get(url,timeout=40,allow_redirects=False,stream=True)
            response.raise_for_status()
            data=b''
            for chunk in response.iter_content(65536):
                data+=chunk
                if len(data)>9*1024*1024:raise ProviderError('Image too large')
            return data,response.headers.get('Content-Type','image/jpeg').split(';')[0]
        raise ProviderError('Provider returned unsupported image URL')
    except (KeyError,IndexError,TypeError,ValueError) as exc:
        if isinstance(exc,ProviderError):raise
        raise ProviderError('Provider did not return image data') from exc


def check_api(preset,config,key):
    """Non-billable endpoint only. Never create a generation job as a key test."""
    base=safe_base_url(config.get('base_url') or preset['base_url'])
    if not key and not preset.get('local'):
        raise ProviderError('Provide a key or use a saved credential')
    try:import requests
    except ImportError as exc:raise ProviderError('Install backend requirements first') from exc
    ident=preset['id']
    if ident=='tripo':path='/user/balance';headers={'Authorization':'Bearer '+key}
    elif ident=='meshy':path='/openapi/v1/balance';headers={'Authorization':'Bearer '+key}
    elif ident=='aholo':path='/global/asset/v1/token';headers={'Authorization':key}
    elif preset['protocol']=='gemini':path='/models';headers={'x-goog-api-key':key}
    elif preset['protocol']=='anthropic':path='/models';headers={'x-api-key':key,'anthropic-version':'2023-06-01'}
    else:path='/models';headers={'Authorization':'Bearer '+(key or 'local')}
    try:response=requests.get(base+path,headers=headers,timeout=18,allow_redirects=False)
    except requests.RequestException as exc:raise ProviderError('Provider is unreachable: '+str(exc)[:90]) from exc
    if response.status_code in (301,302,307,308):raise ProviderError('Unexpected redirect: check the API endpoint')
    if response.status_code in (401,403):raise ProviderError('API rejected credential (HTTP '+str(response.status_code)+')')
    if response.status_code>=400:
        if response.status_code==404 and ident not in ('tripo','meshy','aholo'):
            return {'ok':False,'status':'Listing unsupported','detail':'This provider has no verified non-billable check','balance':None}
        raise ProviderError('API returned HTTP '+str(response.status_code))
    try:data=response.json()
    except ValueError:data={}
    balance=None
    if ident=='tripo':
        if isinstance(data,dict) and data.get('code') not in (0,None):raise ProviderError('Tripo balance endpoint rejected request')
        balance=data.get('data',{}).get('balance') if isinstance(data,dict) else None
    if ident=='meshy':balance=data.get('balance') if isinstance(data,dict) else None
    return {'ok':True,'status':'API verified','balance':balance,'detail':'Non-billable check passed'}
