"""Opt-in share links. No asset ever becomes public without an owner-created grant."""
import hashlib
import hmac
import html
import secrets
import time
from pathlib import Path
from flask import Blueprint,abort,jsonify,request,session,send_file,redirect,Response
from . import db as store


def setup_sharing(app, data, media, meshes):
    bp=Blueprint('studio_shares',__name__)
    with store.connect(data) as conn:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS share_links (
            token TEXT PRIMARY KEY, user_id TEXT NOT NULL, project_id TEXT NOT NULL,
            kind TEXT NOT NULL, object_id TEXT NOT NULL, permission TEXT NOT NULL,
            salt TEXT NOT NULL DEFAULT '', pin_hash TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
          );
          CREATE TABLE IF NOT EXISTS share_requests (
            id TEXT PRIMARY KEY, token TEXT NOT NULL REFERENCES share_links(token) ON DELETE CASCADE,
            visitor TEXT NOT NULL, name TEXT NOT NULL, message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL
          );
          CREATE INDEX IF NOT EXISTS share_owner_idx ON share_links(user_id,project_id);
        ''')
    def identity():
        uid=session.get('uid')
        if not uid:abort(401)
        return uid
    def owned(conn,pid):
        uid=identity()
        if not store.project_for(conn,uid,pid):abort(404)
        return uid
    def share_by_token(conn,token):
        row=conn.execute('SELECT * FROM share_links WHERE token=? AND revoked=0',(token,)).fetchone()
        if not row:abort(404)
        return row
    def visitor():
        if not session.get('umi_share_visitor'):session['umi_share_visitor']=secrets.token_urlsafe(22)
        return session['umi_share_visitor']
    def permitted(conn,link):
        if link['permission']=='public' and not link['pin_hash']:return True
        grants=session.get('umi_share_unlocked',[])
        if link['token'] in grants:return True
        if link['permission']=='approval':
            result=conn.execute("SELECT 1 FROM share_requests WHERE token=? AND visitor=? AND status='approved' LIMIT 1",(link['token'],visitor())).fetchone()
            if result:return True
        return False
    @bp.post('/api/projects/<pid>/shares')
    def new_share(pid):
        payload=request.get_json(silent=True) or {}
        mode=payload.get('permission','private')
        if mode not in ('public','pin','approval'):return jsonify(error='Invalid sharing mode'),400
        kind=payload.get('kind','asset');oid=str(payload.get('object_id',''))
        if kind not in ('asset','mesh','note') or not oid:return jsonify(error='Select an object'),400
        pin=str(payload.get('pin','')).strip()
        if mode=='pin' and not (4<=len(pin)<=40):return jsonify(error='PIN must be 4 to 40 characters'),400
        with store.connect(data) as conn:
            uid=owned(conn,pid)
            if kind=='asset':valid=conn.execute('SELECT 1 FROM assets WHERE id=? AND project_id=?',(oid,pid)).fetchone()
            elif kind=='note':
                project=conn.execute('SELECT settings FROM projects WHERE id=?',(pid,)).fetchone()
                import json
                nodes=json.loads(project['settings']).get('tabletop',{}).get('nodes',[]) if project else []
                valid=any(n.get('id')==oid and n.get('kind')=='note' for n in nodes)
            else:valid=conn.execute('SELECT 1 FROM mesh_tasks WHERE id=? AND project_id=? AND user_id=?',(oid,pid,uid)).fetchone()
            if not valid:return jsonify(error='File not in project'),404
            token=secrets.token_hex(20);salt=secrets.token_hex(16) if pin else ''
            hashed=hashlib.pbkdf2_hmac('sha256',pin.encode(),bytes.fromhex(salt),190000).hex() if pin else ''
            conn.execute('INSERT INTO share_links VALUES(?,?,?,?,?,?,?,?,?,0)',(token,uid,pid,kind,oid,mode,salt,hashed,int(time.time())))
            conn.commit()
        return jsonify(token=token,url='/share/'+token,permission=mode),201
    @bp.get('/api/projects/<pid>/shares')
    def owner_shares(pid):
        with store.connect(data) as conn:
            uid=owned(conn,pid)
            shares=[dict(r) for r in conn.execute('SELECT token,kind,object_id,permission,created_at,revoked FROM share_links WHERE project_id=? AND user_id=? ORDER BY created_at DESC',(pid,uid))]
            requests=[dict(r) for r in conn.execute('''SELECT r.id,r.token,r.name,r.message,r.status,r.created_at FROM share_requests r JOIN share_links s ON s.token=r.token WHERE s.user_id=? AND s.project_id=? AND s.revoked=0 ORDER BY r.created_at DESC LIMIT 120''',(uid,pid))]
        return jsonify(shares=shares,requests=requests)
    @bp.post('/api/projects/<pid>/shares/<token>/revoke')
    def revoke(pid,token):
        with store.connect(data) as conn:
            uid=owned(conn,pid)
            result=conn.execute('UPDATE share_links SET revoked=1 WHERE token=? AND project_id=? AND user_id=?',(token,pid,uid));conn.commit()
            if not result.rowcount:abort(404)
        return jsonify(ok=True)
    @bp.post('/api/projects/<pid>/share-requests/<rid>')
    def decide(pid,rid):
        status=(request.get_json(silent=True) or {}).get('status')
        if status not in ('approved','denied'):return jsonify(error='Invalid decision'),400
        with store.connect(data) as conn:
            uid=owned(conn,pid)
            result=conn.execute('''UPDATE share_requests SET status=? WHERE id=? AND token IN (SELECT token FROM share_links WHERE user_id=? AND project_id=? AND revoked=0)''',(status,rid,uid,pid))
            conn.commit()
            if not result.rowcount:abort(404)
        return jsonify(ok=True)
    def note_text_for_share(link):
        import json
        with store.connect(data) as conn:
            project=conn.execute('SELECT settings FROM projects WHERE id=? AND user_id=?',(link['project_id'],link['user_id'])).fetchone()
        if not project:return ''
        nodes=json.loads(project['settings']).get('tabletop',{}).get('nodes',[])
        return next((str(n.get('content',''))[:100000] for n in nodes if n.get('id')==link['object_id'] and n.get('kind')=='note'),'')
    @bp.get('/share/<token>')
    def share_page(token):
        with store.connect(data) as conn:
            link=share_by_token(conn,token)
            allowed=permitted(conn,link)
        safe=html.escape(token)
        css='''body{background:#141b1b;color:#ebf5ef;font:16px system-ui;margin:0;min-height:100vh;display:grid;place-items:center}main{max-width:min(94vw,900px);width:100%;padding:25px}h1{font-size:20px;font-weight:600}button,input,textarea{font:inherit;background:#243532;border:1px solid #557568;color:#fff;border-radius:10px;padding:12px;box-sizing:border-box}button{cursor:pointer;background:#b7dbc8;color:#13201b}input,textarea{display:block;width:100%;margin:10px 0}img,video,audio,model-viewer,iframe{display:block;width:100%;max-height:72vh;object-fit:contain;background:#eef1ed;border:0;border-radius:8px}model-viewer{height:70vh}a{color:#badbcf}small{color:#aebdb6}'''
        body=''
        if allowed:
            with store.connect(data) as conn:
                if link['kind']=='asset':
                    a=conn.execute('SELECT mime,view FROM assets WHERE id=? AND project_id=?',(link['object_id'],link['project_id'])).fetchone()
                else:a=None
            if link['kind']=='mesh':body=f'<model-viewer camera-controls auto-rotate src="/share/{safe}/file" alt="Shared 3D model"></model-viewer><script type="module" src="https://cdn.jsdelivr.net/npm/@google/model-viewer@4.0.0/dist/model-viewer.min.js"></script>'
            elif link['kind']=='note':
                body=f'<pre style="white-space:pre-wrap;background:#fff;color:#172420;padding:20px;max-height:72vh;overflow:auto">{html.escape(note_text_for_share(link))}</pre>'
            elif not a:abort(404)
            elif a['mime'].startswith('image/'):body=f'<img src="/share/{safe}/file" alt="Shared picture">'
            elif a['mime'].startswith('audio/'):body=f'<audio controls src="/share/{safe}/file"></audio>'
            elif a['mime'].startswith('video/'):body=f'<video controls playsinline src="/share/{safe}/file"></video>'
            elif a['mime']=='application/pdf':body=f'<iframe src="/share/{safe}/file" title="Shared PDF"></iframe>'
            else:body=f'<a href="/share/{safe}/file">Read/download this file</a>'
            body+=f'<p><a href="/share/{safe}/file" download>Download</a></p>'
        elif link['permission']=='pin':body=f'<p>Enter the share PIN to view.</p><form method="post" action="/share/{safe}/unlock"><input type="password" name="pin" placeholder="PIN" autocomplete="off" required><button>Unlock</button></form>'
        else:body=f'<p>This private item requires owner approval.</p><form method="post" action="/share/{safe}/request"><input name="name" placeholder="Your name" maxlength="80" required><textarea name="message" maxlength="300" placeholder="Request a preview"></textarea><button>Ask owner</button></form><small>If you have requested access, reload after approval.</small>'
        return Response(f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>UMI LAB · Shared item</title><style>{css}</style><main><h1>UMI LAB · Shared item</h1>{body}</main></html>',mimetype='text/html')
    @bp.post('/share/<token>/unlock')
    def unlock(token):
        with store.connect(data) as conn:link=share_by_token(conn,token)
        if link['permission']!='pin':abort(403)
        # Session-scoped throttling; intentionally not logging the submitted secret.
        key='umi_share_attempt_'+token[:8]
        if session.get(key,0)>8:abort(429)
        pin=str(request.form.get('pin',''))[:100]
        verified=bool(link['pin_hash']) and hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',pin.encode(),bytes.fromhex(link['salt']),190000).hex(),link['pin_hash'])
        if not verified:
            session[key]=session.get(key,0)+1
            return Response('Incorrect PIN. Return to the link and retry.',status=403,mimetype='text/plain')
        grants=session.get('umi_share_unlocked',[]);grants=(grants+[token])[-60:];session['umi_share_unlocked']=grants
        return redirect('/share/'+token,code=303)
    @bp.post('/share/<token>/request')
    def request_permission(token):
        with store.connect(data) as conn:
            link=share_by_token(conn,token)
            if link['permission']!='approval':abort(403)
            user=visitor()
            if not conn.execute('SELECT 1 FROM share_requests WHERE visitor=? AND token=?',(user,token)).fetchone():
                conn.execute('INSERT INTO share_requests VALUES(?,?,?,?,?,?,?)',(store.new_id(),token,user,str(request.form.get('name',''))[:80],str(request.form.get('message',''))[:300],'pending',int(time.time())))
                conn.commit()
        return redirect('/share/'+token,code=303)
    @bp.get('/share/<token>/file')
    def shared_file(token):
        with store.connect(data) as conn:
            link=share_by_token(conn,token)
            if not permitted(conn,link):abort(403)
            if link['kind']=='note':
                content=note_text_for_share(link)
                return Response(content,mimetype='text/plain',headers={'Content-Disposition':'attachment; filename=umi-note.txt'})
            if link['kind']=='asset':
                a=conn.execute('SELECT filename,mime FROM assets WHERE id=? AND project_id=?',(link['object_id'],link['project_id'])).fetchone()
                if not a:abort(404)
                path=Path(media)/a['filename'];mime=a['mime']
            else:
                m=conn.execute('SELECT id,model_file FROM mesh_tasks WHERE id=? AND project_id=? AND user_id=?',(link['object_id'],link['project_id'],link['user_id'])).fetchone()
                if not m or not m['model_file']:abort(404)
                preview=Path(meshes)/(m['id']+'.preview.glb')
                path=preview if preview.is_file() else Path(meshes)/m['model_file']
                mime='model/gltf-binary' if path.suffix.lower()=='.glb' else 'application/zip'
        if not path.is_file():abort(404)
        response=send_file(path,mimetype=mime,conditional=True,as_attachment=mime in ('text/markdown','text/plain','application/zip'))
        if mime in ('application/pdf','image/svg+xml'):
            response.headers['Content-Security-Policy']="default-src 'none'; sandbox; frame-ancestors 'self'"
            response.headers['X-Content-Type-Options']='nosniff'
        return response
    app.register_blueprint(bp)
