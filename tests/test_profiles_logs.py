"""Guest and protected identities, profiles, contact privacy and audit access."""
import io
import os
import sqlite3
import tempfile
import unittest
from backend import db

class GuestDatabaseTests(unittest.TestCase):
    def test_guest_can_upgrade_without_losing_projects(self):
        with tempfile.TemporaryDirectory() as temp:
            db.init(temp)
            with db.connect(temp) as con:
                uid=db.create_guest(con,'Guest Designer')
                pid=db.create_project(con,uid,'Red vehicle')
                self.assertIsNone(db.authenticate(con,'guest-'+uid[:20],'not-a-password'))
                db.upgrade_guest(con,uid,'vehiclepilot','strong-secret-password','user@example.net','+447123456789')
                person=db.authenticate(con,'user@example.net','strong-secret-password')
                self.assertEqual(person['id'],uid)
                self.assertEqual(person['role'],'user')
                self.assertEqual(person['phone'],'+447123456789')
                self.assertEqual(db.project_for(con,uid,pid)['name'],'Red vehicle')

    def test_old_database_migrates_and_preserves_admin(self):
        with tempfile.TemporaryDirectory() as temp:
            with db.connect(temp) as con:
                con.execute('''CREATE TABLE users(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL, display_name TEXT NOT NULL, created_at INTEGER NOT NULL)''')
                con.execute("INSERT INTO users VALUES('legacy','admin','old-hash','Creator',10)")
                con.commit()
            db.init(temp)
            with db.connect(temp) as con:
                person=con.execute("SELECT * FROM users WHERE id='legacy'").fetchone()
                self.assertEqual(person['role'],'admin')
                self.assertIsNone(person['email'])
                self.assertEqual(person['avatar_file'],'')

try:
    from flask import Flask
    from PIL import Image
    from cryptography.fernet import Fernet
    HAS_FLASK=True
except ImportError:
    HAS_FLASK=False

@unittest.skipUnless(HAS_FLASK,'Flask stack not installed; required integration checks run on Ubuntu')
class GuestAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        variables=['UMI_DATA_DIR','UMI_SESSION_KEY','UMI_FERNET_KEY','UMI_ENABLE_SETUP']
        saved={name:os.environ.get(name) for name in variables}
        def restore():
            for name,value in saved.items():
                if value is None:os.environ.pop(name,None)
                else:os.environ[name]=value
        self.addCleanup(restore)
        os.environ.update(UMI_DATA_DIR=self.temp.name,UMI_SESSION_KEY='integration-key-for-local-testing',
                          UMI_FERNET_KEY=Fernet.generate_key().decode(),UMI_ENABLE_SETUP='1')
        import importlib
        from backend import app as module
        self.app=importlib.reload(module)
        self.client=self.app.app.test_client()
        self.csrf=self.client.get('/api/session').json['csrf']
    def req(self,uri,payload):return self.client.post('/api/'+uri,json=payload,headers={'X-CSRF-Token':self.csrf})
    def test_guest_profile_log_and_upgrade(self):
        self.assertEqual(self.client.get('/api/logs').status_code,401)
        guest=self.req('guest',{'name':'Sam'})
        self.assertEqual(guest.status_code,200,guest.json)
        self.csrf=guest.json['csrf']
        state=self.client.get('/api/session').json
        self.assertEqual(state['user']['role'],'guest')
        self.assertNotIn('email',state['user'])
        self.assertEqual(self.client.get('/api/logs?scope=server').status_code,403)
        changed=self.client.put('/api/profile',json={'display_name':'S. Designer','bio':'Concepts','focus':'Cars'},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(changed.status_code,200,changed.json)
        self.assertTrue(self.client.get('/api/logs?scope=session').json['entries'])
        upgraded=self.req('account/upgrade',{'username':'designer','password':'strong-secret-password','email':'designer@example.org','phone':'+447123456789'})
        self.assertEqual(upgraded.status_code,200,upgraded.json)
        self.assertEqual(self.client.get('/api/session').json['user']['email'],'designer@example.org')
        self.req('logout',{})
        response=self.client.post('/api/login',json={'username':'designer','password':'strong-secret-password'})
        self.assertEqual(response.status_code,200,response.json)
    def test_avatar_and_private_contact(self):
        guest=self.req('guest',{'name':'Sam'});self.csrf=guest.json['csrf']
        image=Image.new('RGB',(32,32),'blue');buff=io.BytesIO();image.save(buff,'PNG');buff.seek(0)
        res=self.client.post('/api/profile/avatar',data={'image':(buff,'avatar.png')},content_type='multipart/form-data',headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(res.status_code,200,res.json)
        self.assertEqual(self.client.get('/api/profile/avatar').mimetype,'image/jpeg')
        self.assertEqual(self.client.get('/api/session').json['user']['avatar_url'],'/api/profile/avatar')
    def test_admin_only_server_log(self):
        setup=self.client.post('/api/setup',json={'name':'Admin','password':'a-secure-passphrase'})
        self.assertEqual(setup.status_code,200,setup.json)
        self.assertEqual(self.client.get('/api/session').json['user']['role'],'admin')
        self.assertEqual(self.client.get('/api/logs?scope=server').status_code,200)
        entries=self.client.get('/api/logs?scope=server').json['entries']
        self.assertTrue(entries)
        self.assertNotIn('a-secure-passphrase',str(entries))

    def test_registered_user_has_no_server_log_access(self):
        created=self.req('register',{'username':'ordinary','password':'a-strong-password','name':'Regular User'})
        self.assertEqual(created.status_code,200,created.json)
        self.assertEqual(self.client.get('/api/session').json['user']['role'],'user')
        self.assertEqual(self.client.get('/api/logs?scope=server').status_code,403)

if __name__=='__main__':unittest.main()
