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
        ''')


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


def create_user(db, username, password, display_name):
    if len(password) < 12:
        raise ValueError('Password must be at least 12 characters')
    uid = new_id()
    db.execute('INSERT INTO users VALUES(?,?,?,?,?)',
               (uid, username, password_hash(password),display_name,int(time.time())))
    db.commit()
    return uid


def authenticate(db, username, password):
    row = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
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
