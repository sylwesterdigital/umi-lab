"""Optional, provider-agnostic visual inventory; no inferred identity or unverifiable prices."""
import base64
import io
import json
import re
from PIL import Image
from .providers import _post, safe_base_url, ProviderError

PROMPT = ("Inspect the supplied image, not its file name or chat history. Reply with a JSON object only, "
          "with keys title (brief), summary, subject (free text, not a predefined category), "
          "materials (array of short visible or plausible materials), and objects (array of up to 45 objects). "
          "Each object: name, group, material, confidence ('high','medium','low'), visible (boolean), notes. "
          "Include separable components, accessories, and useful subassemblies. "
          "Only identify a brand when a legible visible logo or marking supports it; do not invent brands, models, market prices, "
          "a person's age, identity or other sensitive traits. Do not claim CAD geometry. "
          "Be precise, concise, and say uncertain where needed.")


def normalize(raw):
    if isinstance(raw, str):
        text=raw.strip()
        text=re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.I)
        try:raw=json.loads(text)
        except (ValueError,TypeError) as exc:raise ProviderError('Vision provider did not return structured scene data') from exc
    if not isinstance(raw,dict):raise ProviderError('Invalid scene analysis response')
    objects=[]
    for obj in (raw.get('objects') or [])[:80]:
        if not isinstance(obj,dict):continue
        name=str(obj.get('name','')).strip()[:85]
        if not name:continue
        objects.append({'name':name,'group':str(obj.get('group') or 'Objects')[:55],
                        'material':str(obj.get('material') or 'unknown')[:100],
                        'confidence':str(obj.get('confidence') or 'low').lower() if str(obj.get('confidence') or 'low').lower() in ('high','medium','low') else 'low',
                        'visible':bool(obj.get('visible',True)), 'notes':str(obj.get('notes') or '')[:200]})
        if len(objects)>=45:break
    if not objects:raise ProviderError('No identifiable components returned; try a clearer image or add parts manually')
    return {'title':str(raw.get('title') or 'Image analysis')[:100],
            'summary':str(raw.get('summary') or '')[:350],
            'subject':str(raw.get('subject') or 'Object')[:90],
            'materials':[str(m)[:80] for m in (raw.get('materials') or [])[:20] if isinstance(m,str)],
            'objects':objects,'source':'AI visual inventory (unverified)',
            'market_verified':False}


def analyze(preset,config,key,blob,mime):
    if preset.get('mesh3d') or preset.get('protocol')=='anthropic':
        raise ProviderError('Choose a configured vision-capable Meta, OpenAI-compatible or Gemini model')
    if not key and not preset.get('local'):
        raise ProviderError('Connect a vision model in Workspace → Models first')
    model=config.get('model') or preset.get('model')
    if not model:raise ProviderError('Configure a multimodal chat model first')
    base=safe_base_url(config.get('base_url') or preset['base_url'])
    with Image.open(io.BytesIO(blob)) as raw:
        raw=raw.convert('RGB')
        raw.thumbnail((1280,1280))
        buf=io.BytesIO();raw.save(buf,format='JPEG',quality=82)
    img=base64.b64encode(buf.getvalue()).decode('ascii')
    if preset['protocol']=='gemini':
        result=_post(base+'/models/'+model+':generateContent',{'x-goog-api-key':key},
                     {'contents':[{'parts':[{'text':PROMPT},{'inlineData':{'mimeType':'image/jpeg','data':img}}]}],
                      'generationConfig':{'responseMimeType':'application/json'}},timeout=90)
        try:text=''.join(x.get('text','') for x in result['candidates'][0]['content']['parts'])
        except (KeyError,IndexError,TypeError) as exc:raise ProviderError('Empty Gemini vision response') from exc
    else:
        result=_post(base+'/chat/completions',{'Authorization':'Bearer '+(key or 'local')},
                     {'model':model,'stream':False,'max_tokens':2400,
                      'messages':[{'role':'user','content':[{'type':'text','text':PROMPT},
                      {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+img}}]}]},timeout=90)
        try:text=result['choices'][0]['message']['content']
        except (KeyError,IndexError,TypeError) as exc:raise ProviderError('Empty vision response') from exc
        if isinstance(text,list):text=''.join(x.get('text','') for x in text if isinstance(x,dict))
    return normalize(text)
