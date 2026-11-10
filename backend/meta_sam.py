"""Meta SAM 3.1 image segmentation. Preserve pixel mask tokens; boxes for lightweight preview.
The packed masks are NOT bounding-box masks. Their bytes are preserved unmodified for
future exact decoding with the official meta-sam-parser.
"""
import base64
import json
import re

from .providers import ProviderError, safe_base_url

BOX = re.compile(r'(\d+)<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)(?:;c=([0-9.]+))?\|>(<\|mask;[^>]{0,1200000}\|>)?')

def segment_image(preset, config, key, image_bytes, mime, noun):
    if preset['id']!='meta':raise ProviderError('SAM 3.1 requires Meta Muse / Model API')
    if not key:raise ProviderError('Connect the Meta Model API key in Settings')
    if not image_bytes or mime not in ('image/png','image/jpeg','image/webp'):
        raise ProviderError('SAM requires a JPG, PNG or WebP image')
    if not noun.strip() or len(noun)>90 or len(noun.split())>12:
        raise ProviderError('Describe one part using a short noun phrase')
    base=safe_base_url(config.get('base_url') or preset['base_url'])
    payload={'model':'sam-3.1','stream':True,'metadata':{'mask_encoding':'one_bit'},
      'input':[{'type':'message','role':'user','content':[
        {'type':'input_text','text':noun.strip()},
        {'type':'input_image','image_url':'data:'+mime+';base64,'+base64.b64encode(image_bytes).decode('ascii')}]}]}
    try:import requests
    except ImportError as exc:raise ProviderError('Install model transport requirements') from exc
    try:
        response=requests.post(base+'/responses',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'text/event-stream'},
            json=payload,timeout=(15,180),stream=True,allow_redirects=False)
        if response.status_code!=200:
            raise ProviderError('Meta SAM returned HTTP '+str(response.status_code))
        if 'text/event-stream' not in response.headers.get('Content-Type',''):
            raise ProviderError('Meta SAM did not return a segmentation stream')
        pieces=[];total=0;complete=False
        for raw in response.iter_lines(decode_unicode=False):
            if not raw or not raw.startswith(b'data: '):continue
            if len(raw)>2_000_000:raise ProviderError('Segmentation event is too large')
            value=raw[6:]
            if value==b'[DONE]':break
            try:evt=json.loads(value)
            except ValueError:raise ProviderError('Invalid segmentation event')
            kind=evt.get('type')
            if kind=='response.output_text.delta':
                fragment=evt.get('delta','')
                if not isinstance(fragment,str):continue
                total+=len(fragment.encode('utf8'))
                if total>4_000_000:raise ProviderError('Segmentation result exceeds safety limit')
                pieces.append(fragment)
            elif kind=='response.completed':complete=True
            elif kind in ('response.failed','error'):
                raise ProviderError('Meta SAM segmentation failed')
        if not complete:raise ProviderError('Meta SAM stream ended without completion')
    except requests.RequestException as exc:
        raise ProviderError('Meta SAM connection failed: '+type(exc).__name__) from exc
    finally:
        if 'response' in locals():response.close()
    raw=''.join(pieces)
    matches=[]
    for found in BOX.finditer(raw):
        oid,x1,y1,x2,y2,width,height,conf,mask=found.groups()
        w,h=int(width),int(height)
        box=[int(x1),int(y1),int(x2)+1,int(y2)+1]
        if w<=0 or h<=0 or w*h>32_000_000 or box[0]<0 or box[1]<0 or box[2]>w or box[3]>h:continue
        matches.append({'id':oid,'box':box,'size':[w,h],'confidence':float(conf) if conf else None,
                        'mask_token':mask or None})
        if len(matches)>=100:break
    return {'model':'sam-3.1','noun':noun.strip(),'completed':True,'count':len(matches),
            'mask_count':sum(bool(x['mask_token']) for x in matches),'objects':matches}
