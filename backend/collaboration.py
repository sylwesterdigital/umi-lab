"""UMI LAB board collaboration: scoped invitations, short leases, presence and diff merges.

All shared operations are within the UMI database. No external queues, sockets or services.
"""
import hashlib
import hmac
import json
import re
import secrets
import time

CLIENT_ID=re.compile(r'^[a-f0-9]{32}$')
OBJECT_ID=re.compile(r'^[a-zA-Z0-9:_-]{1,120}$')
ABSENT=object()


def setup(db, data_dir):
    with db.connect(data_dir) as conn:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS project_members (
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            joined_at INTEGER NOT NULL, PRIMARY KEY(project_id,user_id));
          CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members(user_id,project_id);
          CREATE TABLE IF NOT EXISTS project_invites (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE, pin_hash TEXT NOT NULL,
            expires_at INTEGER NOT NULL, max_uses INTEGER NOT NULL,
            uses INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
            blocked_until INTEGER NOT NULL DEFAULT 0, revoked INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL);
          CREATE INDEX IF NOT EXISTS idx_project_invites_project ON project_invites(project_id);
          CREATE TABLE IF NOT EXISTS board_presence (
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            client_id TEXT NOT NULL, x REAL, y REAL, seen_at INTEGER NOT NULL,
            PRIMARY KEY(project_id,user_id,client_id));
          CREATE INDEX IF NOT EXISTS idx_board_presence_seen ON board_presence(seen_at);
          CREATE TABLE IF NOT EXISTS board_locks (
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            object_id TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            client_id TEXT NOT NULL, expires_at INTEGER NOT NULL,
            PRIMARY KEY(project_id,object_id));
          CREATE INDEX IF NOT EXISTS idx_board_locks_expire ON board_locks(expires_at);
          CREATE TABLE IF NOT EXISTS project_links (
            first_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            second_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            created_at INTEGER NOT NULL, PRIMARY KEY(first_id,second_id),
            CHECK(first_id < second_id));
        ''')
        cols={c['name'] for c in conn.execute('PRAGMA table_info(projects)')}
        if 'board_version' not in cols:
            conn.execute('ALTER TABLE projects ADD COLUMN board_version INTEGER NOT NULL DEFAULT 0')
        conn.commit()


def accessible(db, uid, pid):
    return db.execute('''SELECT p.* FROM projects p WHERE p.id=? AND
      (p.user_id=? OR EXISTS(SELECT 1 FROM project_members m WHERE m.project_id=p.id AND m.user_id=?))''',
      (pid,uid,uid)).fetchone()


def editor(db, uid, pid):
    return accessible(db,uid,pid)


def register(app, store, data_dir, authenticated):
    from flask import abort, jsonify, request, session
    def owner(conn,pid):
        row=store.project_for(conn,session['uid'],pid)
        if not row:abort(404)
        return row

    def member(conn,pid):
        row=accessible(conn,session['uid'],pid)
        if not row:abort(404)
        return row

    def get_body():
        body=request.get_json(silent=True)
        if not isinstance(body,dict):abort(400,'JSON object required')
        return body

    @app.route('/api/projects/<pid>/invitations',methods=['GET','POST'])
    @authenticated
    def collab_invitations(pid):
        with store.connect(data_dir) as conn:
            owner(conn,pid)
            if request.method=='GET':
                rows=conn.execute('''SELECT id,expires_at,max_uses,uses,revoked,created_at
                   FROM project_invites WHERE project_id=? ORDER BY created_at DESC LIMIT 30''',(pid,)).fetchall()
                return jsonify(invitations=[dict(r) for r in rows])
            body=get_body()
            pin=str(body.get('pin',''))
            if not re.fullmatch(r'[0-9]{6,12}',pin):return jsonify(error='Use a PIN of 6–12 digits'),400
            ttl=int(body.get('days',7)) if str(body.get('days',7)).isdigit() else 0
            if ttl not in (1,7):return jsonify(error='Invitation lifetime must be 1 or 7 days'),400
            active=conn.execute('SELECT COUNT(*) FROM project_invites WHERE project_id=? AND revoked=0 AND expires_at>?',(pid,int(time.time()))).fetchone()[0]
            if active>=10:return jsonify(error='Revoke an existing link before creating more'),409
            raw=secrets.token_urlsafe(32)
            digest=hashlib.sha256(raw.encode()).hexdigest()
            now=int(time.time());iid=store.new_id()
            conn.execute('''INSERT INTO project_invites(id,project_id,token_hash,pin_hash,expires_at,max_uses,created_at)
               VALUES(?,?,?,?,?,?,?)''',(iid,pid,digest,store.password_hash(pin),now+ttl*86400,25,now))
            conn.commit()
            # Raw token is returned ONCE, never stored or logged.
            return jsonify(id=iid,token=raw,expires_at=now+ttl*86400,pin_required=True),201

    @app.post('/api/projects/<pid>/invitations/<iid>/revoke')
    @authenticated
    def collab_revoke(pid,iid):
        with store.connect(data_dir) as conn:
            owner(conn,pid)
            conn.execute('UPDATE project_invites SET revoked=1 WHERE project_id=? AND id=?',(pid,iid))
            conn.commit()
        return jsonify(ok=True)

    @app.post('/api/invitations/join')
    @authenticated
    def collab_join():
        body=get_body();token=str(body.get('token',''));pin=str(body.get('pin',''))
        if not 30<=len(token)<=128 or not re.fullmatch(r'[0-9]{6,12}',pin):return jsonify(error='Invalid invitation'),400
        digest=hashlib.sha256(token.encode()).hexdigest();now=int(time.time())
        with store.connect(data_dir) as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT * FROM project_invites WHERE token_hash=?',(digest,)).fetchone()
            if not row or row['revoked'] or row['expires_at']<=now or row['uses']>=row['max_uses']:
                return jsonify(error='Invitation unavailable or expired'),404
            if row['blocked_until']>now:return jsonify(error='Too many attempts. Try later.'),429
            if not store.verify_password(pin,row['pin_hash']):
                attempts=row['attempts']+1
                conn.execute('UPDATE project_invites SET attempts=?,blocked_until=? WHERE id=?',
                             (0 if attempts>=5 else attempts,now+900 if attempts>=5 else 0,row['id']))
                conn.commit()
                return jsonify(error='Invalid invitation PIN'),403
            project=conn.execute('SELECT user_id FROM projects WHERE id=?',(row['project_id'],)).fetchone()
            if not project:return jsonify(error='Project unavailable'),404
            already=conn.execute('SELECT 1 FROM project_members WHERE project_id=? AND user_id=?',
                                 (row['project_id'],session['uid'])).fetchone()
            if session['uid']!=project['user_id'] and not already:
                conn.execute('INSERT INTO project_members VALUES(?,?,?)',(row['project_id'],session['uid'],now))
                conn.execute('UPDATE project_invites SET uses=uses+1 WHERE id=?',(row['id'],))
            conn.execute('UPDATE project_invites SET attempts=0,blocked_until=0 WHERE id=?',(row['id'],))
            conn.commit()
            return jsonify(id=row['project_id'],ok=True)

    @app.get('/api/projects/<pid>/collab/state')
    @authenticated
    def collab_state(pid):
        now=int(time.time());client=str(request.args.get('client',''))
        with store.connect(data_dir) as conn:
            project=member(conn,pid)
            people=conn.execute('''SELECT p.user_id,p.client_id,p.x,p.y,u.display_name FROM board_presence p
               JOIN users u ON u.id=p.user_id WHERE p.project_id=? AND p.seen_at>?
               ORDER BY p.seen_at DESC LIMIT 35''',(pid,now-18)).fetchall()
            locks=conn.execute('''SELECT l.object_id,l.user_id,l.client_id,u.display_name FROM board_locks l
               JOIN users u ON u.id=l.user_id WHERE l.project_id=? AND l.expires_at>?
               LIMIT 100''',(pid,now)).fetchall()
            return jsonify(version=project['board_version'],people=[dict(p) for p in people
              if p['user_id']!=session['uid'] or p['client_id']!=client],locks=[dict(l) for l in locks])

    @app.post('/api/projects/<pid>/collab/presence')
    @authenticated
    def collab_presence(pid):
        body=get_body();client=str(body.get('client',''))
        if not CLIENT_ID.fullmatch(client):return jsonify(error='Invalid client'),400
        x=body.get('x');y=body.get('y')
        if x is not None or y is not None:
            if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and abs(v)<100000 for v in (x,y)):
                return jsonify(error='Invalid pointer coordinates'),400
        now=int(time.time())
        with store.connect(data_dir) as conn:
            member(conn,pid)
            if body.get('leave'):
                conn.execute('DELETE FROM board_presence WHERE project_id=? AND user_id=? AND client_id=?',(pid,session['uid'],client))
                conn.execute('DELETE FROM board_locks WHERE project_id=? AND user_id=? AND client_id=?',(pid,session['uid'],client))
            else:
                conn.execute('''INSERT INTO board_presence(project_id,user_id,client_id,x,y,seen_at) VALUES(?,?,?,?,?,?)
                   ON CONFLICT(project_id,user_id,client_id) DO UPDATE SET x=excluded.x,y=excluded.y,seen_at=excluded.seen_at''',
                   (pid,session['uid'],client,x,y,now))
                conn.execute('UPDATE board_locks SET expires_at=? WHERE project_id=? AND user_id=? AND client_id=? AND expires_at>?',
                             (now+15,pid,session['uid'],client,now))
            conn.execute('DELETE FROM board_presence WHERE seen_at<?',(now-30,))
            conn.execute('DELETE FROM board_locks WHERE expires_at<?',(now,))
            conn.commit()
        return jsonify(ok=True)

    @app.post('/api/projects/<pid>/collab/lock')
    @authenticated
    def collab_lock(pid):
        body=get_body();client=str(body.get('client',''));obj=str(body.get('object_id',''))
        if not CLIENT_ID.fullmatch(client) or not OBJECT_ID.fullmatch(obj):return jsonify(error='Invalid lock target'),400
        now=int(time.time())
        with store.connect(data_dir) as conn:
            member(conn,pid)
            conn.execute('BEGIN IMMEDIATE')
            if body.get('release'):
                conn.execute('DELETE FROM board_locks WHERE project_id=? AND object_id=? AND user_id=? AND client_id=?',
                             (pid,obj,session['uid'],client))
            else:
                other=conn.execute('SELECT * FROM board_locks WHERE project_id=? AND object_id=? AND expires_at>?',
                                   (pid,obj,now)).fetchone()
                if other and (other['user_id'],other['client_id'])!=(session['uid'],client):
                    return jsonify(error='Another collaborator is editing this item'),423
                conn.execute('''INSERT INTO board_locks(project_id,object_id,user_id,client_id,expires_at)
                  VALUES(?,?,?,?,?) ON CONFLICT(project_id,object_id) DO UPDATE SET
                  user_id=excluded.user_id,client_id=excluded.client_id,expires_at=excluded.expires_at''',
                  (pid,obj,session['uid'],client,now+15))
            conn.commit()
        return jsonify(ok=True)

    @app.patch('/api/projects/<pid>/collab/board')
    @authenticated
    def collab_board(pid):
        body=get_body();base=body.get('base') or {};changed=body.get('board') or {}
        client=str(body.get('client',''))
        if not CLIENT_ID.fullmatch(client) or not isinstance(base,dict) or not isinstance(changed,dict):
            return jsonify(error='Invalid canvas update'),400
        if len(json.dumps(body,separators=(',',':'))) > 2400000:return jsonify(error='Canvas update too large'),413
        for snapshot in (base,changed):
            if not isinstance(snapshot.get('nodes',[]),list) or not isinstance(snapshot.get('packs',[]),list):
                return jsonify(error='Invalid canvas objects'),400
            if len(snapshot.get('nodes',[]))>600 or len(snapshot.get('packs',[]))>200:
                return jsonify(error='Canvas item limit exceeded'),400
        def keyed(snapshot,key):
            result={}
            for item in snapshot.get(key,[]):
                if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not OBJECT_ID.fullmatch(item['id']) or item['id'] in result:
                    raise ValueError('Invalid or duplicate canvas item')
                result[item['id']]=item
            return result
        now=int(time.time())
        with store.connect(data_dir) as conn:
            conn.execute('BEGIN IMMEDIATE')
            project=member(conn,pid)
            current_settings=json.loads(project['settings']);current=current_settings.get('tabletop') or {}
            if not isinstance(current,dict):current={}
            merged=dict(current)
            dirty=False
            try:
                for key in ('nodes','packs'):
                    before=keyed(base,key);after=keyed(changed,key);latest=keyed(current,key)
                    for obj in before.keys() | after.keys():
                        old=before.get(obj,ABSENT);new=after.get(obj,ABSENT)
                        if old==new:continue
                        dirty=True
                        active=conn.execute('''SELECT user_id,client_id FROM board_locks
                            WHERE project_id=? AND object_id=? AND expires_at>?''',(pid,obj,now)).fetchone()
                        if active and (active['user_id'],active['client_id'])!=(session['uid'],client):
                            return jsonify(error='Item is locked by another editor',object_id=obj),423
                        live=latest.get(obj,ABSENT)
                        if live!=old:
                            return jsonify(error='Someone else changed this item. Refresh the board before editing it.',object_id=obj),409
                        if new is ABSENT:latest.pop(obj,None)
                        else:latest[obj]=new
                    merged[key]=list(latest.values())
            except ValueError as exc:return jsonify(error=str(exc)),400
            # Merge independent metadata fields without overwriting another editor's newer value.
            # Local viewport changes are deliberately kept outside shared document state.
            for key in set(base)|set(changed):
                if key in ('nodes','packs','pan','zoom'):continue
                old=base.get(key,ABSENT);new=changed.get(key,ABSENT)
                if old==new:continue
                dirty=True
                live=current.get(key,ABSENT)
                if live!=old:return jsonify(error='Canvas settings changed elsewhere; refresh and retry'),409
                if new is ABSENT:merged.pop(key,None)
                else:merged[key]=new
            if not dirty:return jsonify(ok=True,board=current,version=project['board_version'])
            current_settings['tabletop']=merged
            encoded=json.dumps(current_settings,separators=(',',':'))
            if len(encoded)>1100000:return jsonify(error='Canvas exceeds project storage limit'),413
            # Keep the legacy selected_asset pointer in sync when the canvas hero changes;
            # planned notes / foreign assets can never become a selected media file.
            selected=project['selected_asset']
            if base.get('hero',ABSENT)!=changed.get('hero',ABSENT):
                hero=merged.get('hero')
                selected=hero if isinstance(hero,str) and conn.execute(
                    'SELECT 1 FROM assets WHERE id=? AND project_id=?',(hero,pid)).fetchone() else None
            conn.execute('''UPDATE projects SET settings=?,selected_asset=?,updated_at=?,
                            board_version=board_version+1 WHERE id=?''',(encoded,selected,now,pid))
            conn.commit()
            return jsonify(ok=True,board=merged,version=project['board_version']+1)

    @app.route('/api/projects/<pid>/links',methods=['GET','POST','DELETE'])
    @authenticated
    def collab_links(pid):
        with store.connect(data_dir) as conn:
            member(conn,pid)
            if request.method=='GET':
                result=conn.execute('''SELECT p.id,p.name FROM project_links l JOIN projects p
                 ON p.id=(CASE WHEN l.first_id=? THEN l.second_id ELSE l.first_id END)
                 WHERE (l.first_id=? OR l.second_id=?) AND p.user_id=? ORDER BY p.name LIMIT 50''',
                 (pid,pid,pid,session['uid'])).fetchall()
                return jsonify(links=[dict(x) for x in result])
            owner(conn,pid)
            body=get_body();target=str(body.get('project_id',''))
            if target==pid or not store.project_for(conn,session['uid'],target):return jsonify(error='Choose another project you own'),400
            a,b=sorted([pid,target])
            if request.method=='POST':
                conn.execute('INSERT OR IGNORE INTO project_links VALUES(?,?,?)',(a,b,int(time.time())))
            else:
                conn.execute('DELETE FROM project_links WHERE first_id=? AND second_id=?',(a,b))
            conn.commit()
            return jsonify(ok=True)

    @app.post('/api/projects/<pid>/members/<uid>/remove')
    @authenticated
    def collab_remove_member(pid,uid):
        with store.connect(data_dir) as conn:
            if session['uid']!=uid:owner(conn,pid)
            else:member(conn,pid)
            conn.execute('DELETE FROM project_members WHERE project_id=? AND user_id=?',(pid,uid))
            conn.execute('DELETE FROM board_presence WHERE project_id=? AND user_id=?',(pid,uid))
            conn.execute('DELETE FROM board_locks WHERE project_id=? AND user_id=?',(pid,uid))
            conn.commit()
        return jsonify(ok=True)

    @app.get('/api/projects/<pid>/members')
    @authenticated
    def collab_members(pid):
        with store.connect(data_dir) as conn:
            member(conn,pid)
            rows=conn.execute('''SELECT u.id,u.display_name FROM project_members m
               JOIN users u ON u.id=m.user_id WHERE m.project_id=? ORDER BY m.joined_at LIMIT 100''',(pid,)).fetchall()
        return jsonify(members=[dict(r) for r in rows])
