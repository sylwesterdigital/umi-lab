"""UMI LAB: authenticated Flask API and single-page studio."""
import base64
import hashlib
import csv
import io
import json
import re
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
import sqlite3
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
from .providers import PRESETS, BY_ID, ProviderError, chat as provider_chat, generate_image, safe_base_url, check_api
from .meta_sam import segment_image

ROOT=Path(__file__).resolve().parent.parent
# Release metadata is the single source of truth for every API/version export.
RELEASE_INFO=json.loads((ROOT/'version.json').read_text(encoding='utf-8'))
RELEASE_VERSION=RELEASE_INFO['version']
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
LOG_DIR=DATA/'logs';LOG_DIR.mkdir(mode=0o700,parents=True,exist_ok=True)
SERVER_LOG=LOG_DIR/'server.jsonl'
file_handler=RotatingFileHandler(SERVER_LOG,maxBytes=1_000_000,backupCount=3,encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(message)s'))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

def user_info(row):
    if not row:return None
    u={k:row[k] for k in ('id','username','display_name','role','bio','focus') if k in row.keys()}
    u['avatar_url']='/api/profile/avatar' if row['avatar_file'] else None
    if row['role']!='guest':
        u['email']=row['email'];u['phone']=row['phone']
    return u

@app.after_request
def audit(resp):
    if request.path.startswith('/api/') and not request.path.startswith(('/api/logs','/api/health','/api/session')):
        if request.method!='GET' or resp.status_code>=400:
            actor=session.get('uid')
            action=f'{request.method} {request.url_rule.rule if request.url_rule else "/api/unknown"}'
            level='ERROR' if resp.status_code>=500 else 'WARN' if resp.status_code>=400 else 'INFO'
            record={'ts':datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    'level':level,'action':action,'status':resp.status_code,
                    'actor':actor[:8] if actor else 'visitor'}
            # Never log request bodies, provider keys, passwords, contact data or cookies.
            try:app.logger.info(json.dumps(record,separators=(',',':')))
            except Exception:pass
            if actor:
                try:
                    with store.connect(DATA) as conn:
                        conn.execute('INSERT INTO events(user_id,session_id,created_at,level,action,status) VALUES(?,?,?,?,?,?)',
                            (actor,session.get('sid',''),int(time.time()),level,action,resp.status_code))
                        conn.execute('''DELETE FROM events WHERE id IN (
                            SELECT id FROM events WHERE user_id=? ORDER BY id DESC LIMIT -1 OFFSET 1500)''',(actor,))
                        conn.commit()
                except Exception:pass
    return resp

BAD_LOGINS={}

@app.after_request
def security(resp):
    resp.headers['X-Content-Type-Options']='nosniff'
    resp.headers['Referrer-Policy']='same-origin'
    resp.headers['X-Frame-Options']='DENY'
    resp.headers['Cache-Control']='no-store' if request.path.startswith('/api/') else 'no-cache'
    resp.headers['Content-Security-Policy']=("default-src 'self'; img-src 'self' data: blob:; "
        "script-src 'self' https://cdn.jsdelivr.net 'sha256-V5W/S/ezCmFEoq8zylsgcbGgPNc2njwXvX8NL5xHP7g='; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; font-src 'self' blob: data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
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
        if request.endpoint not in ('login','setup') and (not session.get('csrf') or not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),session['csrf'])):
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
def health():return jsonify(ok=True,version=RELEASE_VERSION,storage='sqlite',project=RELEASE_INFO['project'])

@app.get('/api/session')
def session_info():
    if 'csrf' not in session:session['csrf']=secrets.token_urlsafe(30)
    if 'sid' not in session:session['sid']=secrets.token_urlsafe(20)
    uid=session.get('uid')
    with store.connect(DATA) as conn:
        count=conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        row=conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone() if uid else None
    return jsonify(authenticated=bool(row),user=user_info(row),
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
        uid=store.create_user(conn,'admin',pwd,str(body.get('name') or 'UMI Creator')[:80],role='admin')
    session.clear();session['uid']=uid;session['csrf']=secrets.token_urlsafe(30);session['sid']=secrets.token_urlsafe(20)
    session.permanent=True
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
    session.clear();session['uid']=row['id'];session['csrf']=secrets.token_urlsafe(30);session['sid']=secrets.token_urlsafe(20)
    session.permanent=True
    return jsonify(ok=True,csrf=session['csrf'],user=user_info(row))

@app.post('/api/guest')
def guest():
    body=request.get_json(silent=True) or {}
    name=str(body.get('name') or '').strip()
    if not 1<=len(name)<=80:return jsonify(error='Enter a name (1–80 characters)'),400
    with store.connect(DATA) as conn:uid=store.create_guest(conn,name)
    session.clear();session['uid']=uid;session['csrf']=secrets.token_urlsafe(30);session['sid']=secrets.token_urlsafe(20);session.permanent=True
    return jsonify(ok=True,csrf=session['csrf'])


def validate_contact(body):
    username=str(body.get('username') or '').strip()
    password=str(body.get('password') or '')
    email=str(body.get('email') or '').strip().lower() or None
    phone=str(body.get('phone') or '').strip() or None
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{2,31}',username) or username.startswith('guest-') or username=='admin':
        return None,'Username must be 3–32 letters, numbers, dots, dashes or underscores'
    if len(password)<12 or len(password)>200:return None,'Password must be 12–200 characters'
    if email and (len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email)):
        return None,'Invalid email address'
    if phone and not re.fullmatch(r'\+[1-9][0-9]{6,14}',phone):return None,'Phone must use international +countrycode format'
    return (username,password,email,phone),None

@app.post('/api/register')
def register():
    body=request.get_json(silent=True) or {}
    values,err=validate_contact(body)
    if err:return jsonify(error=err),400
    name=str(body.get('name') or values[0]).strip()[:80]
    if not name:return jsonify(error='Display name required'),400
    try:
        with store.connect(DATA) as conn:
            uid=store.create_user(conn,values[0],values[1],name,email=values[2],phone=values[3])
    except sqlite3.IntegrityError:return jsonify(error='Username, email or phone already registered'),409
    session.clear();session['uid']=uid;session['csrf']=secrets.token_urlsafe(30);session['sid']=secrets.token_urlsafe(20);session.permanent=True
    return jsonify(ok=True,csrf=session['csrf'])

@app.post('/api/account/upgrade')
def account_upgrade():
    if not session.get('uid'):return jsonify(error='Login required'),401
    body=request.get_json(silent=True) or {}
    values,err=validate_contact(body)
    if err:return jsonify(error=err),400
    try:
        with store.connect(DATA) as conn:store.upgrade_guest(conn,session['uid'],*values)
    except ValueError as exc:return jsonify(error=str(exc)),400
    except sqlite3.IntegrityError:return jsonify(error='Username, email or phone already registered'),409
    return jsonify(ok=True)

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
        row=conn.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone()
        if not row:abort(404)
        if request.method=='PUT':
            body=request.get_json(silent=True) or {}
            name=str(body.get('display_name',row['display_name'])).strip()[:80]
            if not name:return jsonify(error='Name required'),400
            bio=str(body.get('bio',row['bio']))[:240]
            focus=str(body.get('focus',row['focus']))[:60]
            conn.execute('UPDATE users SET display_name=?,bio=?,focus=? WHERE id=?',(name,bio,focus,session['uid']))
            conn.commit()
            row=conn.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone()
    return jsonify(user=user_info(row))

@app.post('/api/profile/avatar')
@authenticated
def avatar_upload():
    image=request.files.get('image')
    if not image or image.mimetype not in ('image/jpeg','image/png','image/webp'):
        return jsonify(error='Choose a JPG, PNG or WebP avatar'),400
    raw=image.read(3_000_001)
    if len(raw)>3_000_000:return jsonify(error='Avatar exceeds 3 MB'),400
    try:
        im=Image.open(io.BytesIO(raw));im.verify();im=Image.open(io.BytesIO(raw))
        if im.width*im.height>16_000_000:return jsonify(error='Image too large'),400
        im=im.convert('RGB');im.thumbnail((512,512))
        img=io.BytesIO();im.save(img,'JPEG',quality=88,optimize=True)
    except (UnidentifiedImageError,OSError,ValueError):return jsonify(error='Invalid avatar image'),400
    filename=store.new_id()+'.jpg'
    with (MEDIA/filename).open('xb') as handle:handle.write(img.getvalue())
    os.chmod(MEDIA/filename,0o600)
    with store.connect(DATA) as conn:
        row=conn.execute('SELECT avatar_file FROM users WHERE id=?',(session['uid'],)).fetchone()
        old=row['avatar_file'] if row else ''
        conn.execute('UPDATE users SET avatar_file=? WHERE id=?',(filename,session['uid']))
        conn.commit()
    if old:(MEDIA/old).unlink(missing_ok=True)
    return jsonify(url='/api/profile/avatar')

@app.get('/api/profile/avatar')
@authenticated
def avatar_get():
    with store.connect(DATA) as conn:
        row=conn.execute('SELECT avatar_file FROM users WHERE id=?',(session['uid'],)).fetchone()
    if not row or not row['avatar_file']:abort(404)
    return send_from_directory(str(MEDIA),row['avatar_file'],mimetype='image/jpeg',max_age=0)

@app.get('/api/logs')
@authenticated
def logs():
    scope=request.args.get('scope','session')
    try:limit=min(300,max(1,int(request.args.get('limit','160'))))
    except ValueError:limit=160
    with store.connect(DATA) as conn:
        user=conn.execute('SELECT role FROM users WHERE id=?',(session['uid'],)).fetchone()
        if not user:abort(404)
        if scope=='session':
            rows=conn.execute('''SELECT created_at,level,action,status FROM events
                WHERE user_id=? AND session_id=? ORDER BY id DESC LIMIT ?''',(session['uid'],session.get('sid',''),limit)).fetchall()
            entries=[{'time':datetime.fromtimestamp(r['created_at'],timezone.utc).isoformat(),
                      'level':r['level'],'event':r['action'],'status':r['status']} for r in reversed(rows)]
            return jsonify(scope='session',entries=entries)
    if scope!='server':return jsonify(error='Unknown log scope'),400
    if user['role']!='admin':abort(403,'Server logs are available to administrators only')
    # Only the dedicated UMI application log; no system-wide journal or secrets.
    try:
        from collections import deque
        with SERVER_LOG.open('r',encoding='utf-8',errors='replace') as handle:
            lines=deque(handle,maxlen=limit)
        entries=[json.loads(line) for line in lines if line.strip()]
    except (OSError,ValueError):entries=[]
    return jsonify(scope='server',entries=entries)

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



@app.post('/api/providers/<provider_id>/check')
@authenticated
def provider_check(provider_id):
    preset=BY_ID.get(provider_id)
    if not preset:abort(404)
    body=request.get_json(silent=True) or {}
    with store.connect(DATA) as conn:
        saved=conn.execute('SELECT * FROM providers WHERE user_id=? AND id=?',(session['uid'],provider_id)).fetchone()
    config=dict(saved) if saved else dict(preset)
    for name in ('model','image_model','base_url'):
        if name in body and isinstance(body[name],str):config[name]=body[name].strip()[:300]
    key=str(body.get('api_key') or '')[:4000]
    if not key and saved and saved['encrypted_key']:
        try:key=CRYPT.decrypt(saved['encrypted_key'].encode()).decode()
        except InvalidToken:return jsonify(error='Saved credential cannot be decrypted'),400
    try:result=check_api(preset,config,key)
    except ProviderError as exc:return jsonify(error=str(exc)),400
    return jsonify(result)


def get_provider(conn,provider_id,temp=None):
    preset=BY_ID.get(provider_id)
    if not preset:raise ProviderError('Unknown model provider')
    row=conn.execute('SELECT * FROM providers WHERE user_id=? AND id=?',(session['uid'],provider_id)).fetchone()
    temp=temp if isinstance(temp,dict) else None
    if not (row and row['enabled']) and not (temp and temp.get('enabled')):
        raise ProviderError('Enable this provider in Settings')
    key=''
    if row and row['encrypted_key']:
        try:key=CRYPT.decrypt(row['encrypted_key'].encode()).decode()
        except InvalidToken as exc:raise ProviderError('Encrypted key unavailable; re-enter key') from exc
    config=dict(row) if row else dict(preset)
    if temp and temp.get('enabled'):
        for field in ('model','image_model','base_url'):
            if field in temp and isinstance(temp[field],str):config[field]=temp[field].strip()[:300]
        key=str(temp.get('api_key') or key)[:4000]
    return preset,config,key

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
            if len(json.dumps(settings))>300000:return jsonify(error='Settings too large'),400
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
                preset,config,key=get_provider(conn,selected,body.get('temp_provider'))
                history=[{'role':x['role'],'content':x['content']} for x in conn.execute('''
                    SELECT role,content FROM (SELECT rowid,role,content FROM messages WHERE project_id=?
                    ORDER BY rowid DESC LIMIT 16) ORDER BY rowid ASC''',(pid,))]
                started=time.monotonic()
                inference_event(conn,'chat',selected,config.get('model') or preset.get('model',''),'started',102)
                try:
                    answer=provider_chat(preset,config,key,history)
                except ProviderError:
                    inference_event(conn,'chat',selected,config.get('model') or preset.get('model',''),'failed',502,round((time.monotonic()-started)*1000))
                    raise
                inference_event(conn,'chat',selected,config.get('model') or preset.get('model',''),'completed',200,round((time.monotonic()-started)*1000))
                mode='model'
            except ProviderError as exc:return jsonify(error=str(exc)),400
        else:
            if not conn.execute('SELECT 1 FROM assets WHERE project_id=? LIMIT 1',(pid,)).fetchone():
                answer='Brief saved. No images yet. What body shape, terrain and materials should define this vehicle?'
            else:
                answer='Brief updated. Would you like to refine the selected images or create a six-view sheet?'

            mode='offline'
        store.record_message(conn,pid,'assistant',answer,selected or 'offline')
        if not row['prompt']:
            conn.execute('UPDATE projects SET prompt=?,name=?,updated_at=? WHERE id=?',
                        (message,message[:42],int(time.time()),pid));conn.commit()
    return jsonify(reply=answer,mode=mode,provider=selected or 'offline')



@app.post('/api/projects/<pid>/continue')
@authenticated
def continue_unfinished(pid):
    # Resume only once on an unfinished project, with user-configured chat provider.
    body=request.get_json(silent=True) or {}
    chosen=str(body.get('provider_id') or '')
    with store.connect(DATA) as conn:
        row=store.project_for(conn,session['uid'],pid)
        if not row:abort(404)
        settings=json.loads(row['settings'])
        if settings.get('resume_asked'):
            return jsonify(skipped=True,reason='Already continued')
        has_images=conn.execute('SELECT 1 FROM assets WHERE project_id=? LIMIT 1',(pid,)).fetchone()
        has_chat=conn.execute('SELECT 1 FROM messages WHERE project_id=? LIMIT 1',(pid,)).fetchone()
        if has_images or not has_chat:return jsonify(skipped=True,reason='No unfinished conversation')
        if not chosen:return jsonify(error='Select a conversational model first'),400
        try:preset,config,key=get_provider(conn,chosen,body.get('temp_provider'))
        except ProviderError as exc:return jsonify(error=str(exc)),400
        history=[{'role':x['role'],'content':x['content']} for x in conn.execute('''
            SELECT role,content FROM (SELECT rowid,role,content FROM messages WHERE project_id=?
            ORDER BY rowid DESC LIMIT 12) ORDER BY rowid ASC''',(pid,))]
        history.append({'role':'user','content':
            'We are resuming this unfinished vehicle design. No concept image has been created yet. '
            'Ask ONE short, specific question that helps decide the design before generating reference images. '
            'Do not repeat the entire specification and do not claim an image was generated.'})
        started=time.monotonic()
        inference_event(conn,'chat',chosen,config.get('model') or preset.get('model',''),'resume-start',102)
        try:
            answer=provider_chat(preset,config,key,history)
        except ProviderError as exc:
            inference_event(conn,'chat',chosen,config.get('model') or preset.get('model',''),'resume-failed',502,round((time.monotonic()-started)*1000))
            return jsonify(error=str(exc)),502
        if not answer:return jsonify(error='Provider returned an empty follow-up'),502
        store.record_message(conn,pid,'assistant',answer[:2000],chosen)
        settings['resume_asked']=True
        conn.execute('UPDATE projects SET settings=?,updated_at=? WHERE id=?',
                     (json.dumps(settings),int(time.time()),pid));conn.commit()
        elapsed=round((time.monotonic()-started)*1000)
        inference_event(conn,'chat',chosen,config.get('model') or preset.get('model',''),'resume-complete',200,elapsed)
    return jsonify(reply=answer,provider=chosen,elapsed_ms=elapsed)


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

@app.post('/api/assets/region')
@authenticated
def create_region_asset():
    """Crop or generate a pixel-isolated regional edit from an owned project image."""
    body=request.get_json(silent=True) or {}
    pid=str(body.get('project_id') or '')
    asset_id=str(body.get('asset_id') or '')
    operation=str(body.get('operation') or '')
    if operation not in ('crop','edit'):return jsonify(error='Unknown region action'),400
    rect=body.get('rect')
    if not isinstance(rect,dict):return jsonify(error='Select a region first'),400
    try:
        x,y,w,h=(float(rect[k]) for k in ('x','y','w','h'))
    except (ValueError,KeyError,TypeError):return jsonify(error='Invalid selection'),400
    import math
    if (not all(math.isfinite(n) for n in (x,y,w,h)) or x<0 or y<0 or w<=0 or h<=0
            or x+w>1.00001 or y+h>1.00001):
        return jsonify(error='Selection outside image'),400
    with store.connect(DATA) as conn:
        project=store.project_for(conn,session['uid'],pid)
        if not project:abort(404)
        asset=conn.execute('SELECT * FROM assets WHERE id=? AND project_id=?',(asset_id,pid)).fetchone()
        if not asset:abort(404)
        try:
            original=Image.open(MEDIA/asset['filename'])
            original.load()
        except (OSError,ValueError):return jsonify(error='Cannot decode source image'),400
        W,H=original.size
        left=max(0,min(W-1,int(round(x*W))))
        top=max(0,min(H-1,int(round(y*H))))
        right=min(W,max(left+1,int(round((x+w)*W))))
        bottom=min(H,max(top+1,int(round((y+h)*H))))
        if right-left<8 or bottom-top<8:return jsonify(error='Select an area at least 8 pixels wide and tall'),400
        selected=original.crop((left,top,right,bottom)).convert('RGBA')
        if operation=='edit':
            provider_id=str(body.get('provider_id') or '')
            prompt=str(body.get('prompt') or '').strip()[:600]
            if not prompt:return jsonify(error='Describe the desired change'),400
            try:preset,config,key=get_provider(conn,provider_id,body.get('temp_provider'))
            except ProviderError as exc:return jsonify(error=str(exc)),400
            if not preset.get('images'):return jsonify(error='Choose an image generation provider'),400
            # Give the provider only the chosen region; the rest is never generated.
            reference=io.BytesIO();selected.save(reference,'PNG')
            instruction=('Edit ONLY this supplied crop. Preserve composition, edges, lighting and viewpoint. '
                         'Change: '+prompt+'. Return ONE rectangular image of the same composition, filled to the edges, '
                         'without borders, text, watermarks or extra panels.')
            model=config.get('image_model') or preset.get('image_model') or ''
            started=time.monotonic()
            inference_event(conn,'image',provider_id,model,'region-started',102,0,1)
            try:
                image_bytes,mime=generate_image(preset,config,key,instruction,
                          reference_images=[(reference.getvalue(),'image/png')])
                edited=Image.open(io.BytesIO(image_bytes));edited.load()
                if edited.width*edited.height>20_000_000:raise ProviderError('Image dimensions too large')
                edited=edited.convert('RGBA').resize(selected.size,Image.Resampling.LANCZOS)
            except (ProviderError,ValueError,OSError,UnidentifiedImageError) as exc:
                inference_event(conn,'image',provider_id,model,'region-failed',502,
                     round((time.monotonic()-started)*1000),1)
                return jsonify(error=str(exc)),502
            canvas=original.convert('RGBA')
            # Pixel perfect outside selected bounds; no provider response can alter it.
            canvas.paste(edited,(left,top))
            view='region_edit';source='ai-region:'+provider_id
            elapsed_ms=round((time.monotonic()-started)*1000)
        else:
            canvas=selected;view='crop';source='crop';elapsed_ms=0
        payload=io.BytesIO();canvas.save(payload,'PNG',optimize=True)
        saved_id,err=save_asset(conn,pid,payload.getvalue(),'image/png',view,source)
        if err:return jsonify(error=err),400
        # Keep the original reference selected; derivatives can be explicitly selected later.
        conn.execute('UPDATE projects SET selected_asset=? WHERE id=?',(project['selected_asset'],pid))
        settings=json.loads(project['settings'])
        history=settings.setdefault('region_history',[])
        history.append({'asset_id':saved_id,'source_asset_id':asset_id,'action':operation,
                        'bounds_px':[left,top,right,bottom],'created_at':int(time.time())})
        settings['region_history']=history[-60:]
        conn.execute('UPDATE projects SET settings=? WHERE id=?',(json.dumps(settings),pid))
        conn.commit()
        if operation=='edit':
            inference_event(conn,'image',provider_id,model,'region-completed',200,elapsed_ms,1)
    return jsonify(id=saved_id,url='/api/media/'+saved_id,view=view,operation=operation,
                   bounds_px=[left,top,right,bottom],elapsed_ms=elapsed_ms)

@app.get('/api/media/<asset_id>')
@authenticated
def media(asset_id):
    with store.connect(DATA) as conn:
        row=conn.execute('''SELECT a.filename,a.mime FROM assets a JOIN projects p ON p.id=a.project_id
         WHERE a.id=? AND p.user_id=?''',(asset_id,session['uid'])).fetchone()
    if not row:abort(404)
    return send_from_directory(str(MEDIA),row['filename'],mimetype=row['mime'],max_age=0)

VIEWS={
    'front':'front elevation, straight-on orthographic view',
    'rear':'rear elevation, straight-on orthographic view',
    'side':'left side elevation, true orthographic side view',
    'top':'top-down roof plan view, straight overhead orthographic',
    'front_3q':'front three-quarter perspective from driver side',
    'rear_3q':'rear three-quarter perspective from driver side',
    'cockpit':'front cockpit interior from passenger seat showing dashboard, steering and seats',
}
SHEET_ORDER=('front','rear','side','top','front_3q','rear_3q')
SYSTEM_LABELS={g['id']:g['name'] for g in PARTS['assemblies']}

def inference_event(conn,category,provider,model,phase,status,elapsed_ms=0,reference_count=0):
    # Audit progress and timing; deliberately exclude image bytes, prompt, credentials and responses.
    provider=re.sub('[^a-zA-Z0-9_.-]','',provider)[:45]
    model=re.sub('[^a-zA-Z0-9_.-]','',model)[:90]
    action=f'AI {category} / {provider} / {model} / {phase} / {elapsed_ms}ms / refs={reference_count}'
    event={'ts':datetime.now(timezone.utc).isoformat(timespec='seconds'),
           'level':'ERROR' if status>=400 else 'INFO','action':action,
           'status':status,'actor':str(session.get('uid',''))[:8]}
    app.logger.info(json.dumps(event,separators=(',',':')))
    conn.execute('INSERT INTO events(user_id,session_id,created_at,level,action,status) VALUES(?,?,?,?,?,?)',
      (session['uid'],session.get('sid',''),int(time.time()),event['level'],action,status))
    conn.commit()


def concept_instruction(brief,mode,style,reference_count,system_id='',part_name=''):
    identity=('CRITICAL: use the supplied reference images as the SAME physical vehicle, preserving body shape, wheelbase, color, materials, features, and graphic style. '
              if reference_count else 'Design one internally consistent vehicle with a stable design identity. ')
    if mode=='sheet':
        composition=('Generate ONE LANDSCAPE TECHNICAL BLUEPRINT CONTACT SHEET with EXACTLY SIX equal, clean panels in a 3-column by 2-row grid, '
          'showing the identical vehicle. Panels in reading order: (1) FRONT straight orthographic, (2) REAR straight orthographic, '
          '(3) LEFT SIDE orthographic, (4) TOP overhead orthographic, (5) FRONT THREE-QUARTER, (6) REAR THREE-QUARTER. '
          'Align vehicle proportions, silhouette, wheelbase, number of doors, colors and component placement across ALL panels. '
          'Use clean linework, coherent materials, simple neutral background; only small panel names, no watermarks. '
          'Never substitute another vehicle, never produce multiple variants.')
    elif mode=='annotate':
        composition=('Generate ONE annotated design-dissection board of the same vehicle. Show the full vehicle as the hero image and overlay clear callouts for major visible systems and components. '
          'Include concise labels for body, doors, glass, lights, cockpit, wheels, suspension, brakes, underbody and hardware where visible. '
          'Keep the layout neat, legible and presentation-ready. This is a concept dissection, not manufacturing CAD.')
    elif mode=='system':
        system_name=SYSTEM_LABELS.get(system_id,system_id or 'selected system')
        composition=(f'Generate ONE focused system sheet for the {system_name} of the same vehicle. Highlight the relevant areas, include 3 to 6 supporting detail crops or isolated elements as needed, and add short labels for the major visible components in that system. Keep the rest of the vehicle subdued for context.')
    elif mode=='component':
        part=(part_name or 'selected component')[:80]
        composition=(f'Using exactly the supplied single vehicle reference photograph, produce ONE photorealistic isolated component: {part}. '
          'Keep the exact same design language, material, finish, color and proportions. Show only that one component, large and centered, '
          'against a simple neutral light studio background. Do not include the complete vehicle, other parts, inset views, grids, annotations, arrows, captions, diagrams, writing or watermarks. '
          'ONE component per image, not a component sheet. For parts not visible in the reference, provide a plausible visual concept, never invented dimensions or manufacturing claims.')
    elif mode=='part':
        part=(part_name or 'selected part')[:80]
        if reference_count==1:
            composition=(f'Edit the provided source image of the same vehicle and keep the SAME composition, camera angle, framing, lighting, paint color, reflections, and background. '
              f'Apply ONLY the requested component change related to "{part}". If the request asks for exclusions such as no tyres, no glass, or only chassis, remove or hide those excluded components while preserving the rest of the image. '
              'Return ONE clean image only. Do NOT create a contact sheet, multiple views, arrows, labels, captions, or any other text.')
        else:
            composition=(f'Generate ONE isolated part sheet for the vehicle component "{part}". Show the part clearly separated from the vehicle and include multiple informative views or callouts if useful. Preserve the same styling and design language as the parent vehicle. Add short labels only.')
    else:
        composition=('ONE IMAGE ONLY: '+VIEWS[mode]+'. Accurate vehicle proportions, consistent with all supplied references, '
          'full vehicle in frame, no artistic reinterpretation. Plain unobtrusive background. No watermarks or unrelated vehicles.')
    return f'UMI LAB consistent vehicle reference generation. {identity} Vehicle brief: {brief}. {composition} {style}'.strip()

@app.post('/api/concepts/generate')
@authenticated
def concepts():
    body=request.get_json(silent=True) or {}
    pid=str(body.get('project_id',''));provider_id=str(body.get('provider_id',''))
    mode=str(body.get('mode') or ('front_3q' if body.get('view_count')==1 else 'sheet'))
    if mode not in {'sheet','annotate','system','part','component'} and mode not in VIEWS:return jsonify(error='Unknown view type'),400
    with store.connect(DATA) as conn:
        row=store.project_for(conn,session['uid'],pid)
        if not row:abort(404)
        try:preset,config,key=get_provider(conn,provider_id,body.get('temp_provider'))
        except ProviderError as exc:return jsonify(error=str(exc)),400
        if not preset.get('images'):return jsonify(error='Choose an image generation provider'),400
        brief=str(body.get('prompt') or row['prompt'] or 'Vehicle design')[:3000]
        style=str(body.get('instructions') or '').strip()[:700]
        ids=body.get('reference_ids')
        if ids is None:ids=[row['selected_asset']] if row['selected_asset'] else []
        if not isinstance(ids,list) or len(ids)>5 or any(not isinstance(v,str) for v in ids):
            return jsonify(error='Choose up to five image references'),400
        if len(set(ids))!=len(ids):return jsonify(error='Duplicate image reference'),400
        source_id=body.get('source_asset_id')
        if source_id is not None and (not isinstance(source_id,str) or source_id not in ids):
            return jsonify(error='Active source must be a selected reference'),400
        references=[]
        for aid in ids:
            asset=conn.execute('SELECT filename,mime FROM assets WHERE id=? AND project_id=?',(aid,pid)).fetchone()
            if not asset:return jsonify(error='Unknown reference image'),400
            image=(MEDIA/asset['filename']).read_bytes()
            references.append((image,asset['mime']))
        if sum(len(image) for image,_ in references)>12_000_000:
            return jsonify(error='Selected references are too large'),400
        system_id=str(body.get('system_id') or '').strip(); part_name=str(body.get('part_name') or '').strip()[:80]
        if mode=='system' and system_id not in SYSTEM_LABELS:return jsonify(error='Choose a valid system'),400
        if mode in ('part','component') and len(part_name)<2:return jsonify(error='Enter a part name'),400
        if mode=='component' and len(ids)!=1:return jsonify(error='Select exactly one source photo for component images'),400
        # When actual images are supplied, they define vehicle identity; historical
        # chat/project prompts may describe a different car and must not override them.
        if references:brief='The exact same vehicle shown in the supplied reference image(s)'
        instruction=concept_instruction(brief,mode,style,len(references),system_id,part_name)
        model=config.get('image_model') or preset.get('image_model') or ''
        started=time.monotonic()
        inference_event(conn,'image',provider_id,model,'started',102,0,len(references))
        try:
            content,mime=generate_image(preset,config,key,instruction,reference_images=references)
            asset_view={'sheet':'six_view_sheet','annotate':'annotated_parts_map','system':'system_sheet','part':'isolated_part','component':'component'}.get(mode,mode)
            aid,err=save_asset(conn,pid,content,mime, asset_view,'ai:'+provider_id)
            if err:raise ProviderError(err)
            # Maintain active source: generating a derivative must not silently change the reference.
            if row['selected_asset']:
                conn.execute('UPDATE projects SET selected_asset=? WHERE id=?',(row['selected_asset'],pid))
                conn.commit()
            elapsed_ms=round((time.monotonic()-started)*1000)
            settings=json.loads(row['settings'])
            settings['last_generation']={'mode':mode,'model':model[:100],'provider':provider_id,
                'reference_count':len(references),'reference_ids':ids,'images_created':1,
                'views_in_sheet':6 if mode=='sheet' else 1,'duration_ms':elapsed_ms,'created_at':int(time.time()),
                'system_id':system_id or None,'part_name':part_name or None,'source_asset_id':source_id or (ids[0] if ids else None)}
            workflow=settings.setdefault('parts_workflow',{})
            workflow.setdefault('dissection_source_ids', ids)
            workflow['updated_at']=int(time.time())
            if mode=='annotate':
                workflow.setdefault('annotated_assets',[]).append(aid)
                workflow['annotated_from']=ids
            elif mode=='system':
                systems=workflow.setdefault('system_sheets',{})
                systems.setdefault(system_id,[]).append(aid)
            elif mode=='part':
                parts=workflow.setdefault('part_sheets',{})
                parts.setdefault(part_name,[]).append(aid)
            elif mode=='component':
                components=workflow.setdefault('component_images',{})
                components.setdefault(part_name,[]).append(aid)
            conn.execute('UPDATE projects SET settings=? WHERE id=?',(json.dumps(settings),pid))
            conn.commit()
            inference_event(conn,'image',provider_id,model,'completed',200,elapsed_ms,len(references))
        except (ProviderError,ValueError,KeyError,OSError) as exc:
            elapsed_ms=round((time.monotonic()-started)*1000)
            inference_event(conn,'image',provider_id,model,'failed',502,elapsed_ms,len(references))
            return jsonify(error=str(exc)),502
    result_view={'sheet':'six_view_sheet','annotate':'annotated_parts_map','system':'system_sheet','part':'isolated_part','component':'component'}.get(mode,mode)
    return jsonify(assets=[{'id':aid,'url':'/api/media/'+aid,'view': result_view}],
                   warnings=[],views_requested=6 if mode=='sheet' else 1,views_completed=6 if mode=='sheet' else 1,
                   images_created=1,mode=mode,reference_count=len(references),model=model,elapsed_ms=elapsed_ms,system_id=system_id or None,part_name=part_name or None,source_asset_id=source_id or (ids[0] if ids else None))


@app.post('/api/segments/generate')
@authenticated
def generate_segmentation():
    body=request.get_json(silent=True) or {}
    pid=str(body.get('project_id') or '')
    aid=str(body.get('asset_id') or '')
    noun=str(body.get('noun') or '').strip()[:90]
    if not aid:return jsonify(error='Select one reference image'),400
    if not noun or len(noun.split())>12:return jsonify(error='Enter one short part noun phrase'),400
    with store.connect(DATA) as conn:
        project=store.project_for(conn,session['uid'],pid)
        if not project:abort(404)
        asset=conn.execute('SELECT filename,mime FROM assets WHERE id=? AND project_id=?',(aid,pid)).fetchone()
        if not asset:return jsonify(error='Selected image not found in project'),400
        try:preset,config,key=get_provider(conn,'meta',body.get('temp_provider'))
        except ProviderError as exc:return jsonify(error=str(exc)),400
        original=(MEDIA/asset['filename']).read_bytes()
        started=time.monotonic()
        inference_event(conn,'segment','meta','sam-3.1','started',102,0,1)
        try:
            segmented=segment_image(preset,config,key,original,asset['mime'],noun)
            # Visualization is explicitly boxes, not a false claim of mask rasterization.
            from PIL import ImageDraw,ImageFont
            canvas=Image.open(io.BytesIO(original)).convert('RGB')
            pen=ImageDraw.Draw(canvas)
            for idx,obj in enumerate(segmented['objects']):
                pen.rectangle(obj['box'],outline='#28d7b5',width=max(2,canvas.width//300))
                pen.text((obj['box'][0]+3,max(1,obj['box'][1]-18)),f'{noun} {idx+1}',fill='#28d7b5')
            picture=io.BytesIO();canvas.save(picture,'PNG')
            generated_id,err=save_asset(conn,pid,picture.getvalue(),'image/png','sam_box_preview','meta:sam-3.1')
            if err:raise ProviderError(err)
            if project['selected_asset']:
                conn.execute('UPDATE projects SET selected_asset=? WHERE id=?',(project['selected_asset'],pid))
            run_id=store.new_id()
            folder=DATA/'segmentations';folder.mkdir(mode=0o700,exist_ok=True)
            data={'schema':'umi.segmentation/1.0','project_id':pid,'source_asset':aid,'preview_asset':generated_id,
                  'created_at':int(time.time()),**segmented}
            target=folder/(run_id+'.json')
            with target.open('x',encoding='utf-8') as output:json.dump(data,output)
            target.chmod(0o600)
            settings=json.loads(project['settings'])
            runs=settings.setdefault('parts_workflow',{}).setdefault('sam_runs',[])
            runs.append({'id':run_id,'noun':noun,'source_asset':aid,'preview_asset':generated_id,
                         'matches':segmented['count'],'masks':segmented['mask_count'],'model':'sam-3.1'})
            conn.execute('UPDATE projects SET settings=?,updated_at=? WHERE id=?',
                         (json.dumps(settings),int(time.time()),pid))
            conn.commit()
            elapsed=round((time.monotonic()-started)*1000)
            inference_event(conn,'segment','meta','sam-3.1','completed',200,elapsed,1)
        except (ProviderError,ValueError,OSError) as exc:
            inference_event(conn,'segment','meta','sam-3.1','failed',502,round((time.monotonic()-started)*1000),1)
            return jsonify(error=str(exc)),502
    return jsonify(id=run_id,model='sam-3.1',matches=segmented['count'],masks=segmented['mask_count'],
                   preview={'id':generated_id,'url':'/api/media/'+generated_id,'view':'sam_box_preview'},
                   data_url=f'/api/projects/{pid}/segmentation/{run_id}',elapsed_ms=elapsed)

@app.get('/api/projects/<pid>/segmentation/<run_id>')
@authenticated
def segmentation_data(pid,run_id):
    if not re.fullmatch(r'[a-f0-9]{32}',run_id):abort(404)
    with store.connect(DATA) as conn:
        row=store.project_for(conn,session['uid'],pid)
        if not row:abort(404)
        records=json.loads(row['settings']).get('parts_workflow',{}).get('sam_runs',[])
        if not any(r.get('id')==run_id for r in records):abort(404)
    target=DATA/'segmentations'/(run_id+'.json')
    if not target.is_file():abort(404)
    return send_file(target,mimetype='application/json',as_attachment=True,download_name='UMI_SAM_'+run_id[:8]+'.json')


def make_manifest(row):
    settings=json.loads(row['settings'])
    workflow=settings.get('parts_workflow',{})
    system_sheets=workflow.get('system_sheets',{})
    part_sheets=workflow.get('part_sheets',{})
    component_images=workflow.get('component_images',{})
    board=settings.get('tabletop',{}) if isinstance(settings.get('tabletop'),dict) else {}
    photo_nodes=board.get('nodes',[]) if isinstance(board.get('nodes'),list) else []
    angle_modes={'front','rear','side','top','front_3q','rear_3q'}
    individual_angles=sum(1 for n in photo_nodes if isinstance(n,dict) and n.get('kind')=='angle' and n.get('label') in ('Front','Rear','Left side','Top','Front ¾','Rear ¾'))
    parts=[]
    for group in PARTS['assemblies']:
        group_status='mapped' if workflow.get('annotated_assets') else 'concept'
        if group['id'] in system_sheets: group_status='system_sheet'
        for i,name in enumerate(group['parts']):
            part_status='component_image' if name in component_images else 'isolated_sheet' if name in part_sheets else group_status
            parts.append({'id':f"{group['id']}.{i+1:03d}",'label':name,'assembly':group['id'],
                'status':part_status,'mask':None,'mesh':None,'cad':None,'material':None,
                'dimensions_mm':None,'tolerance_mm':None,'printable':False,
                'attachment_points':[],'confidence':None})
    return {'schema':'umi.manifest/1.0','version':RELEASE_VERSION,'project':{'id':row['id'],'name':row['name'],
      'prompt':row['prompt'],'kind':row['kind'],'selected_asset':row['selected_asset']},
      'units':'mm','coordinates':PARTS['coordinate_system'],'design_settings':settings,
      'parts_workflow':{'annotated_assets':workflow.get('annotated_assets',[]),'system_sheets':system_sheets,'part_sheets':part_sheets,'component_images':component_images,'source_references':workflow.get('dissection_source_ids',[]),'sam_runs':workflow.get('sam_runs',[])},
      'stages':{'reference':'available' if row['selected_asset'] else 'missing',
                'segmentation':'sam_masks_available' if workflow.get('sam_runs') else 'annotated' if workflow.get('annotated_assets') else 'not_run',
                'multiview':'individual_views_available' if individual_angles>=6 else 'partial_views' if individual_angles else 'available' if settings.get('last_generation',{}).get('mode')=='sheet' else 'not_reconciled',
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
        z.writestr('README.txt',f'UMI LAB concept export v{RELEASE_VERSION}\nImages and BOM are design references, not CAD/STL files.\nAll dimensions, interfaces and tolerances require validation.\n')
        for run in manifest.get('parts_workflow',{}).get('sam_runs',[]):
            rid=run.get('id','')
            if re.fullmatch(r'[a-f0-9]{32}',rid):
                seg=DATA/'segmentations'/(rid+'.json')
                if seg.is_file():z.write(seg,'segmentations/'+rid+'.json')
        for a in assets:
            filename=a['filename']
            if (MEDIA/filename).is_file():z.write(MEDIA/filename,'references/'+filename)
    stream.seek(0)
    return send_file(stream,mimetype='application/zip',as_attachment=True,download_name='UMI_LAB_'+pid[:8]+'_CONCEPT.zip')

if __name__=='__main__':
    app.run(host='127.0.0.1',port=int(os.environ.get('UMI_PORT','5057')),debug=False)
