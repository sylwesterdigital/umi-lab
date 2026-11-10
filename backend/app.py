"""UMI LAB v0.1.3: authenticated Flask API and single-page studio."""
import base64
import csv
import io
import json
import os
import secrets
import time
import uuid
import zipfile
from functools import wraps
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, abort, jsonify, request, send_file, send_from_directory, session
from . import db as store
from .providers import PRESETS, BY_ID, ProviderError, chat as provider_chat, generate_image, safe_base_url

ROOT=Path(__file__).resolve().parent.parent
DATA=Path(os.environ.get('UMI_DATA_DIR', str(ROOT/'.umi-data'))).resolve()
DATA.mkdir(mode=0o700,parents=True,exist_ok=True)
MEDIA=DATA/'media'; MEDIA.mkdir(mode=0o700,exist_ok=True)

def persistent_key(filename, env_name, generator):
    value=os.environ.get(env_name)
    if value:return value.encode()
    dest=DATA/filename
    if dest.exists():return dest.read_bytes().strip()
    value=generator()
    fd=os.open(str(dest),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as fp:fp.write(value+b'\n')
    return value

SESSION_KEY=persistent_key('.session-key','UMI_SESSION_KEY',lambda:secrets.token_urlsafe(48).encode())
CRYPT=Fernet(persistent_key('.fernet-key','UMI_FERNET_KEY',Fernet.generate_key))
app=Flask(__name__,static_folder=str(ROOT/'frontend'),static_url_path='/static')
app.config.update(SECRET_KEY=SESSION_KEY,MAX_CONTENT_LENGTH=12*1024*1024,
                  SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',
                  SESSION_COOKIE_SECURE=os.environ.get('UMI_HTTPS','0')=='1',
                  PERMANENT_SESSION_LIFETIME=60*60*24*14)
store.init(DATA)
PARTS=json.loads((ROOT/'parts.json').read_text())
BAD_LOGINS={}

@app.after_request
def security(resp):
    resp.headers['X-Content-Type-Options']='nosniff'
    resp.headers['Referrer-Policy']='same-origin'
    resp.headers['X-Frame-Options']='DENY'
    resp.headers['Cache-Control']='no-store' if request.path.startswith('/api/') else 'no-cache'
    resp.headers['Content-Security-Policy']=("default-src 'self'; img-src 'self' data: blob:; "
        "script-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
    return resp

@app.before_request
def guard_writes():
    if request.method in ('POST','PUT','PATCH','DELETE') and request.path.startswith('/api/'):
        # Verify browser origin when sent; cross-origin HTML forms must not change state.
        origin=request.headers.get('Origin','')
        if origin:
            from urllib.parse import urlparse
            host=urlparse(origin).netloc
            if host!=request.host:abort(403,'Invalid origin')
        if request.endpoint not in ('login','setup') and request.headers.get('X-CSRF-Token')!=session.get('csrf'):
            abort(403,'Invalid CSRF token')

@app.errorhandler(413)
def too_large(e):return jsonify(error='Image exceeds 12 MB'),413

@app.errorhandler(400)
def bad_request(e):return jsonify(error=str(e.description if hasattr(e,'description') else e)),400

@app.errorhandler(403)
def forbidden(e):return jsonify(error=str(e.description if hasattr(e,'description') else e)),403

@app.errorhandler(404)
def missing(e):return jsonify(error='Not found'),404

@app.errorhandler(429)
def throttled(e):return jsonify(error='Too many failed logins; retry later'),429

@app.get('/')
def index():return send_from_directory(str(ROOT/'frontend'),'index.html')

@app.get('/version.json')
def version():return send_from_directory(str(ROOT),'version.json')

@app.get('/api/health')
def health():return jsonify(ok=True,version='0.1.3',storage='sqlite',project='umi-lab')

@app.get('/api/session')
def session_info():
    if 'csrf' not in session:session['csrf']=secrets.token_urlsafe(30)
    uid=session.get('uid')
    with store.connect(DATA) as conn:
        count=conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        row=conn.execute('SELECT id,username,display_name FROM users WHERE id=?',(uid,)).fetchone() if uid else None
    return jsonify(authenticated=bool(row),user=dict(row) if row else None,
                   needs_setup=(count==0 and os.environ.get('UMI_ENABLE_SETUP')=='1'),
                   csrf=session['csrf'])

@app.post('/api/setup')
def setup():
    if os.environ.get('UMI_ENABLE_SETUP')!='1' or request.remote_addr not in ('127.0.0.1','::1'):
        abort(403,'Local setup disabled')
    body=request.get_json(silent=True) or {}
    pwd=str(body.get('password',''))
    if len(pwd)<12:return jsonify(error='Use a password of at least 12 characters'),400
    with store.connect(DATA) as conn:
        if conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]:abort(403,'Account already exists')
        uid=store.create_user(conn,'admin',pwd,str(body.get('name') or 'UMI Creator')[:80])
    session.clear();session['uid']=uid;session['csrf']=secrets.token_urlsafe(30)
    return jsonify(ok=True,csrf=session['csrf'])

@app.post('/api/login')
def login():
    ip=request.remote_addr or 'unknown'
    now=time.time(); BAD_LOGINS[ip]=[x for x in BAD_LOGINS.get(ip,[]) if now-x<900]
    if len(BAD_LOGINS[ip])>=6:abort(429)
    body=request.get_json(silent=True) or {}
    with store.connect(DATA) as conn:
        row=store.authenticate(conn,str(body.get('username','admin')),str(body.get('password','')))
    if not row:
        BAD_LOGINS[ip].append(now)
        return jsonify(error='Invalid login'),401
    BAD_LOGINS.pop(ip,None)
    session.clear();session['uid']=row['id'];session['csrf']=secrets.token_urlsafe(30)
    session.permanent=True
    return jsonify(ok=True,csrf=session['csrf'],user={'id':row['id'],'username':row['username'],'display_name':row['display_name']})

@app.post('/api/logout')
def logout():session.clear();return jsonify(ok=True)


def authenticated(fn):
    @wraps(fn)
    def inner(*args,**kwargs):
        if not session.get('uid'):return jsonify(error='Login required'),401
        return fn(*args,**kwargs)
    return inner

@app.route('/api/profile',methods=['GET','PUT'])
@authenticated
def profile():
    with store.connect(DATA) as conn:
        if request.method=='PUT':
            body=request.get_json(silent=True) or {}
            name=str(body.get('display_name','')).strip()[:80]
            if not name:return jsonify(error='Name required'),400
            conn.execute('UPDATE users SET display_name=? WHERE id=?',(name,session['uid']))
            conn.commit()
        row=conn.execute('SELECT id,username,display_name,created_at FROM users WHERE id=?',(session['uid'],)).fetchone()
    return jsonify(user=dict(row))

@app.get('/api/providers')
@authenticated
def provider_list():
    with store.connect(DATA) as conn:
        records={x['id']:dict(x) for x in conn.execute('SELECT * FROM providers WHERE user_id=?',(session['uid'],))}
    entries=[]
    for preset in PRESETS:
        stored=records.get(preset['id'],{})
        entries.append({**preset,'enabled':bool(stored.get('enabled',False)),
           'model':stored.get('model') or preset['model'],
           'image_model':stored.get('image_model') or preset['image_model'],
           'base_url':stored.get('base_url') or preset['base_url'],
           'has_key':bool(stored.get('encrypted_key'))})
    return jsonify(providers=entries)

@app.put('/api/providers/<provider_id>')
@authenticated
def provider_save(provider_id):
    preset=BY_ID.get(provider_id)
    if not preset:abort(404)
    body=request.get_json(silent=True) or {}
    endpoint=str(body.get('base_url') or preset['base_url']).strip()[:300]
    if not endpoint:return jsonify(error='Endpoint required'),400
    try:base=safe_base_url(endpoint)
    except ProviderError as exc:return jsonify(error=str(exc)),400
    with store.connect(DATA) as conn:
        previous=conn.execute('SELECT encrypted_key FROM providers WHERE user_id=? AND id=?',(session['uid'],provider_id)).fetchone()
        encrypted=previous['encrypted_key'] if previous else ''
        if body.get('clear_key'):encrypted=''
        if body.get('api_key'):encrypted=CRYPT.encrypt(str(body['api_key']).strip().encode()).decode()
        conn.execute('''INSERT INTO providers(user_id,id,enabled,model,image_model,base_url,encrypted_key)
          VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id,id) DO UPDATE SET enabled=excluded.enabled,
          model=excluded.model,image_model=excluded.image_model,base_url=excluded.base_url,
          encrypted_key=excluded.encrypted_key''',
          (session['uid'],provider_id,1 if body.get('enabled') else 0,
           str(body.get('model') or preset['model'])[:180],
           str(body.get('image_model') or preset['image_model'])[:180],base,encrypted))
        conn.commit()
    return jsonify(ok=True,has_key=bool(encrypted))


def get_provider(conn,provider_id):
    preset=BY_ID.get(provider_id)
    if not preset:raise ProviderError('Unknown model provider')
    row=conn.execute('SELECT * FROM providers WHERE user_id=? AND id=?',(session['uid'],provider_id)).fetchone()
    if not row or not row['enabled']:raise ProviderError('Enable this provider in Model Settings')
    key=''
    if row['encrypted_key']:
        try:key=CRYPT.decrypt(row['encrypted_key'].encode()).decode()
        except InvalidToken as exc:raise ProviderError('Encrypted key unavailable; re-enter key') from exc
    return preset,dict(row),key

@app.route('/api/projects',methods=['GET','POST'])
@authenticated
def projects():
    with store.connect(DATA) as conn:
        if request.method=='POST':
            body=request.get_json(silent=True) or {}
            prompt=str(body.get('prompt') or '').strip()[:10000]
            name=str(body.get('name') or (prompt[:42] if prompt else 'Untitled ride'))[:100]
            kind=str(body.get('kind') or 'car')[:32]
            if kind not in ('car','motorcycle','aircraft','boat','drone','robot','other'):kind='other'
            pid=store.create_project(conn,session['uid'],name,prompt,kind)
            return jsonify(id=pid),201
        rows=conn.execute('SELECT * FROM projects WHERE user_id=? ORDER BY updated_at DESC LIMIT 80',(session['uid'],)).fetchall()
    return jsonify(projects=[store.serialize_project(row) for row in rows])

@app.route('/api/projects/<pid>',methods=['GET','PATCH','DELETE'])
@authenticated
def project_detail(pid):
    with store.connect(DATA) as conn:
        row=store.project_for(conn,session['uid'],pid)
        if not row:abort(404)
        if request.method=='DELETE':
            # Remove media after successful DB deletion; random opaque filenames only.
            media=[r['filename'] for r in conn.execute('SELECT filename FROM assets WHERE project_id=?',(pid,))]
            conn.execute('DELETE FROM projects WHERE id=?',(pid,));conn.commit()
            for filename in media:(MEDIA/filename).unlink(missing_ok=True)
            return jsonify(ok=True)
        if request.method=='PATCH':
            body=request.get_json(silent=True) or {}
            name=str(body.get('name',row['name'])).strip()[:100]
            prompt=str(body.get('prompt',row['prompt']))[:10000]
            settings=body.get('settings',json.loads(row['settings']))
            if not isinstance(settings,dict):return jsonify(error='Invalid settings'),400
            if len(json.dumps(settings))>10000:return jsonify(error='Settings too large'),400
            selected=body.get('selected_asset',row['selected_asset'])
            if selected and not conn.execute('SELECT 1 FROM assets WHERE id=? AND project_id=?',(selected,pid)).fetchone():
                return jsonify(error='Unknown asset'),400
            conn.execute('UPDATE projects SET name=?,prompt=?,settings=?,selected_asset=?,updated_at=? WHERE id=?',
               (name or 'Untitled ride',prompt,json.dumps(settings),selected,int(time.time()),pid));conn.commit()
            row=store.project_for(conn,session['uid'],pid)
        assets=[dict(r) for r in conn.execute('SELECT id,view,source,mime,created_at FROM assets WHERE project_id=? ORDER BY created_at DESC',(pid,))]
        messages=[dict(r) for r in conn.execute('SELECT role,content,provider,created_at FROM messages WHERE project_id=? ORDER BY rowid ASC LIMIT 80',(pid,))]
    for asset in assets:asset['url']='/api/media/'+asset['id']
    return jsonify(project=store.serialize_project(row),assets=assets,messages=messages)

@app.get('/api/parts')
@authenticated
def parts():return jsonify(PARTS)

@app.post('/api/chat')
@authenticated
def converse():
    body=request.get_json(silent=True) or {}
    pid=str(body.get('project_id',''));message=str(body.get('message','')).strip()[:6000]
    if not message:return jsonify(error='Write a prompt'),400
    with store.connect(DATA) as conn:
        row=store.project_for(conn,session['uid'],pid)
        if not row:abort(404)
        store.record_message(conn,pid,'user',message)
        selected=str(body.get('provider_id') or '')
        if selected:
            try:
                preset,config,key=get_provider(conn,selected)
                history=[{'role':x['role'],'content':x['content']} for x in conn.execute('''
                    SELECT role,content FROM (SELECT rowid,role,content FROM messages WHERE project_id=?
                    ORDER BY rowid DESC LIMIT 16) ORDER BY rowid ASC''',(pid,))]
                answer=provider_chat(preset,config,key,history)
                mode='model'
            except ProviderError as exc:return jsonify(error=str(exc)),400
        else:
            answer=("Concept brief saved. The parts library and 3D preview are available now. "
                    "For real AI design discussion, enable a chat provider in Model Settings. "
                    "Images do not establish hidden CAD geometry or print tolerances.")
            mode='offline'
        store.record_message(conn,pid,'assistant',answer,selected or 'offline')
        if not row['prompt']:
            conn.execute('UPDATE projects SET prompt=?,name=?,updated_at=? WHERE id=?',
                        (message,message[:42],int(time.time()),pid));conn.commit()
    return jsonify(reply=answer,mode=mode,provider=selected or 'offline')


def save_asset(conn,pid,image_bytes,mime,view,source):
    if len(image_bytes)>9*1024*1024:return None,'Image exceeds 9 MB'
    try:
        im=Image.open(io.BytesIO(image_bytes))
        im.verify()
        im=Image.open(io.BytesIO(image_bytes))
        if im.width*im.height>20_000_000: return None,'Image dimensions too large'
        im.thumbnail((2048,2048))
        out=io.BytesIO()
        if im.mode in ('RGBA','LA') and mime=='image/png':
            im.convert('RGBA').save(out,'PNG',optimize=True);extension='png';mime='image/png'
        else:
            im.convert('RGB').save(out,'JPEG',quality=89,optimize=True);extension='jpg';mime='image/jpeg'
    except (OSError,ValueError,UnidentifiedImageError):return None,'Not a valid image'
    aid=store.new_id();filename=aid+'.'+extension
    dest=MEDIA/filename
    with dest.open('xb') as fp:fp.write(out.getvalue())
    os.chmod(dest,0o600)
    conn.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?)',
      (aid,pid,filename,mime,view,source,int(time.time())))
    conn.execute('UPDATE projects SET selected_asset=?,updated_at=? WHERE id=?',(aid,int(time.time()),pid))
    conn.commit()
    return aid,None

@app.post('/api/assets/upload')
@authenticated
def upload():
    pid=str(request.form.get('project_id',''))
    image=request.files.get('image')
    if not image:return jsonify(error='Choose a JPG, PNG or WebP image'),400
    if image.mimetype not in ('image/jpeg','image/png','image/webp'):
        return jsonify(error='Only JPG, PNG and WebP supported'),400
    content=image.read(10*1024*1024)
    with store.connect(DATA) as conn:
        if not store.project_for(conn,session['uid'],pid):abort(404)
        aid,err=save_asset(conn,pid,content,image.mimetype,'reference','upload')
    if err:return jsonify(error=err),400
    return jsonify(id=aid,url='/api/media/'+aid),201

@app.get('/api/media/<asset_id>')
@authenticated
def media(asset_id):
    with store.connect(DATA) as conn:
        row=conn.execute('''SELECT a.filename,a.mime FROM assets a JOIN projects p ON p.id=a.project_id
         WHERE a.id=? AND p.user_id=?''',(asset_id,session['uid'])).fetchone()
    if not row:abort(404)
    return send_from_directory(str(MEDIA),row['filename'],mimetype=row['mime'],max_age=0)

VIEWS=[('front_3q','Front 3/4'),('rear_3q','Rear 3/4'),('side','Side profile'),('cockpit','Cockpit')]

@app.post('/api/concepts/generate')
@authenticated
def concepts():
    body=request.get_json(silent=True) or {}
    pid=str(body.get('project_id',''));provider_id=str(body.get('provider_id',''))
    with store.connect(DATA) as conn:
        row=store.project_for(conn,session['uid'],pid)
        if not row:abort(404)
        try:preset,config,key=get_provider(conn,provider_id)
        except ProviderError as exc:return jsonify(error=str(exc)),400
        if not preset.get('images'):return jsonify(error='Select OpenAI, xAI or Gemini for image generation'),400
        brief=str(body.get('prompt') or row['prompt'] or 'Futuristic performance car')[:3000]
        made=[];errors=[]
        for view,label in VIEWS:
            if view=='cockpit':
                angle='Driver cockpit interior view from passenger seat, detailed dashboard, steering wheel, front seats and center console'
            else:angle=label+' exterior camera view'
            instruction=(f'Premium vehicle industrial design concept art. SINGLE vehicle identity: {brief}. '
                         f'View: {angle}. Studio photo lighting, neutral dark gray seamless studio, '
                         'visible correct components, crisp silhouette, realistic materials, no text, '
                         'no labels, no typography, no watermarks. 3:2 landscape composition.')
            try:
                content,mime=generate_image(preset,config,key,instruction)
                aid,err=save_asset(conn,pid,content,mime,view,'ai:'+provider_id)
                if err:raise ProviderError(err)
                made.append({'id':aid,'url':'/api/media/'+aid,'view':view,'source':'ai:'+provider_id})
            except (ProviderError,ValueError,KeyError) as exc:
                errors.append(f'{label}: {exc}')
                # Avoid paying for further failed requests if the first request fails.
                if not made:break
    if not made:return jsonify(error='; '.join(errors) or 'No images returned'),502
    return jsonify(assets=made,warnings=errors,views_requested=4,views_completed=len(made))


def make_manifest(row):
    settings=json.loads(row['settings'])
    parts=[]
    for group in PARTS['assemblies']:
        for i,name in enumerate(group['parts']):
            parts.append({'id':f"{group['id']}.{i+1:03d}",'label':name,'assembly':group['id'],
                'status':'concept','mask':None,'mesh':None,'cad':None,'material':None,
                'dimensions_mm':None,'tolerance_mm':None,'printable':False,
                'attachment_points':[],'confidence':None})
    return {'schema':'umi.manifest/1.0','version':'0.1.3','project':{'id':row['id'],'name':row['name'],
      'prompt':row['prompt'],'kind':row['kind'],'selected_asset':row['selected_asset']},
      'units':'mm','coordinates':PARTS['coordinate_system'],'design_settings':settings,
      'stages':{'reference':'available' if row['selected_asset'] else 'missing',
                'segmentation':'not_run','multiview':'not_reconciled',
                'mesh':'not_generated','cad':'not_generated','manufacturing':'not_validated'},
      'part_count':len(parts),'parts':parts,'manufacturing_ready':False,
      'disclaimer':'Concept BOM only. No inferred geometry is fabrication-ready.'}

@app.get('/api/projects/<pid>/manifest')
@authenticated
def manifest(pid):
    with store.connect(DATA) as conn:row=store.project_for(conn,session['uid'],pid)
    if not row:abort(404)
    return jsonify(make_manifest(row))

@app.get('/api/projects/<pid>/export')
@authenticated
def export(pid):
    with store.connect(DATA) as conn:
        row=store.project_for(conn,session['uid'],pid)
        if not row:abort(404)
        assets=conn.execute('SELECT filename,view,mime FROM assets WHERE project_id=?',(pid,)).fetchall()
    manifest=make_manifest(row)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',json.dumps(manifest,indent=2))
        out=io.StringIO();writer=csv.writer(out)
        writer.writerow(['part_id','name','assembly','status','printable'])
        for part in manifest['parts']:
            writer.writerow([part['id'],part['label'],part['assembly'],part['status'],'false'])
        z.writestr('bom.csv',out.getvalue())
        z.writestr('README.txt','UMI LAB concept export v0.1.3\nImages and BOM are design references, not CAD/STL files.\nAll dimensions, interfaces and tolerances require validation.\n')
        for a in assets:
            filename=a['filename']
            if (MEDIA/filename).is_file():z.write(MEDIA/filename,'references/'+filename)
    stream.seek(0)
    return send_file(stream,mimetype='application/zip',as_attachment=True,download_name='UMI_LAB_'+pid[:8]+'_CONCEPT.zip')

if __name__=='__main__':
    app.run(host='127.0.0.1',port=int(os.environ.get('UMI_PORT','5057')),debug=False)
