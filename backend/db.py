"""SQLite persistence. Every DB connection is request/thread local."""
import json
import hashlib
import hmac
import secrets
import os
import sqlite3
import time
import uuid
from pathlib import Path


def connect(data_dir):
    path = Path(data_dir)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(str(path / 'umi.sqlite3'), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=15000')
    db.execute('PRAGMA journal_mode=WAL')
    return db


def init(data_dir):
    with connect(data_dir) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
          display_name TEXT NOT NULL, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS projects (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
          name TEXT NOT NULL, prompt TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'car',
          settings TEXT NOT NULL DEFAULT '{}', selected_asset TEXT,
          created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          role TEXT NOT NULL, content TEXT NOT NULL, provider TEXT,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assets (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          filename TEXT NOT NULL, mime TEXT NOT NULL, view TEXT NOT NULL,
          source TEXT NOT NULL, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS providers (
          user_id TEXT NOT NULL REFERENCES users(id), id TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 0, model TEXT NOT NULL DEFAULT '',
          image_model TEXT NOT NULL DEFAULT '', base_url TEXT NOT NULL DEFAULT '',
          encrypted_key TEXT NOT NULL DEFAULT '', PRIMARY KEY(user_id,id)
        );
        CREATE INDEX IF NOT EXISTS idx_messages_project ON messages(project_id,created_at);
        CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id,created_at);
        CREATE TABLE IF NOT EXISTS asset_documents (
          id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          user_id TEXT NOT NULL, kind TEXT NOT NULL, provider TEXT NOT NULL DEFAULT '',
          model TEXT NOT NULL DEFAULT '', prompt TEXT NOT NULL DEFAULT '',
          content TEXT NOT NULL, created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_asset_documents_asset ON asset_documents(asset_id,created_at);
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id TEXT NOT NULL, session_id TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL,
          level TEXT NOT NULL, action TEXT NOT NULL, status INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id,id);
        CREATE TABLE IF NOT EXISTS mesh_tasks (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
          user_id TEXT NOT NULL REFERENCES users(id), provider TEXT NOT NULL,
          provider_task_id TEXT NOT NULL, label TEXT NOT NULL, status TEXT NOT NULL,
          model_file TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
          credits_est INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_mesh_tasks_project ON mesh_tasks(project_id,created_at);
        CREATE TABLE IF NOT EXISTS canvas_revisions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          action TEXT NOT NULL, snapshot TEXT NOT NULL, created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_canvas_revisions ON canvas_revisions(project_id,id);
        CREATE TABLE IF NOT EXISTS canvas_revision_cursor (
          project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
          revision_id INTEGER NOT NULL
        );

        ''')
        columns={r['name'] for r in db.execute('PRAGMA table_info(users)')}
        for name,definition in {
            'role':"TEXT NOT NULL DEFAULT 'user'", 'email':'TEXT', 'phone':'TEXT',
            'bio':"TEXT NOT NULL DEFAULT ''", 'focus':"TEXT NOT NULL DEFAULT ''",
            'avatar_file':"TEXT NOT NULL DEFAULT ''"
        }.items():
            if name not in columns:db.execute(f'ALTER TABLE users ADD COLUMN {name} {definition}')
        db.execute("UPDATE users SET role='admin' WHERE username='admin' AND role='user'")
        event_columns={r['name'] for r in db.execute('PRAGMA table_info(events)')}
        if 'session_id' not in event_columns:db.execute("ALTER TABLE events ADD COLUMN session_id TEXT NOT NULL DEFAULT ''")
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_user_email ON users(email) WHERE email IS NOT NULL')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_user_phone ON users(phone) WHERE phone IS NOT NULL')
        db.commit()


def new_id():
    return uuid.uuid4().hex


def password_hash(password):
    salt=secrets.token_bytes(20)
    key=hashlib.scrypt(password.encode(),salt=salt,n=2**14,r=8,p=1,dklen=32)
    return 'scrypt$16384$'+salt.hex()+'$'+key.hex()


def verify_password(password, encoded):
    try:
        scheme,n,salt,digest=encoded.split('$')
        if scheme!='scrypt' or int(n)!=16384:return False
        key=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=2**14,r=8,p=1,dklen=32)
        return hmac.compare_digest(key,bytes.fromhex(digest))
    except (ValueError,TypeError):return False


def create_user(db, username, password, display_name, *, email=None, phone=None, role='user'):
    if len(password) < 12:
        raise ValueError('Password must be at least 12 characters')
    # Only the one locally provisioned admin identity can receive the admin role.
    # Normal registrations and guest upgrades remain unprivileged by default.
    if role not in ('user', 'admin') or (role == 'admin' and username != 'admin'):
        raise ValueError('Invalid account role')
    uid = new_id()
    db.execute('''INSERT INTO users(id,username,password_hash,display_name,created_at,email,phone,role)
        VALUES(?,?,?,?,?,?,?,?)''',
        (uid, username, password_hash(password),display_name,int(time.time()),email,phone,role))
    db.commit()
    return uid


def create_guest(db, display_name):
    uid=new_id()
    db.execute('''INSERT INTO users(id,username,password_hash,display_name,created_at,role)
        VALUES(?,?,?,?,?,?)''', (uid,'guest-'+uid[:20],'!guest',display_name[:80],int(time.time()),'guest'))
    db.commit()
    return uid


def upgrade_guest(db, uid, username, password, email=None, phone=None):
    if len(password)<12:raise ValueError('Password must be at least 12 characters')
    row=db.execute("SELECT role FROM users WHERE id=?",(uid,)).fetchone()
    if not row or row['role']!='guest':raise ValueError('Guest profile required')
    db.execute('''UPDATE users SET username=?,password_hash=?,role='user',email=?,phone=?
        WHERE id=?''',(username,password_hash(password),email,phone,uid))
    db.commit()


def authenticate(db, username, password):
    row = db.execute("SELECT * FROM users WHERE (username=? OR email=?) AND role!='guest'", (username,username)).fetchone()
    return row if row and verify_password(password,row['password_hash']) else None


def project_for(db, user_id, project_id):
    return db.execute('SELECT * FROM projects WHERE id=? AND user_id=?',(project_id,user_id)).fetchone()


def serialize_project(row):
    item = dict(row)
    item['settings'] = json.loads(item['settings'])
    return item


def create_project(db, user_id, name, prompt='', kind='car'):
    now = int(time.time())
    pid = new_id()
    db.execute('INSERT INTO projects(id,user_id,name,prompt,kind,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
               (pid,user_id,name[:100],prompt[:10000],kind,now,now))
    db.commit()
    return pid


def record_message(db, project_id, role, content, provider=''):
    db.execute('INSERT INTO messages VALUES(?,?,?,?,?,?)',
               (new_id(),project_id,role,content[:20000],provider,int(time.time())))
    db.commit()


def touch(db, project_id):
    db.execute('UPDATE projects SET updated_at=? WHERE id=?',(int(time.time()),project_id))
    db.commit()
