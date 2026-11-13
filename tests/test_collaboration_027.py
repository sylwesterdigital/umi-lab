"""v0.2.27: additive schema, private permissions and live multi-editor conflict tests."""
import hashlib
import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from backend import db, collaboration

ROOT=Path(__file__).resolve().parent.parent

class CollaborationSchema(unittest.TestCase):
    def test_existing_projects_survive_repeated_additive_upgrade(self):
        with tempfile.TemporaryDirectory() as t:
            db.init(t)
            with db.connect(t) as conn:
                user=db.create_user(conn,'creator','strong-production-password','Creator')
                pid=db.create_project(conn,user,'Existing board')
                conn.execute("UPDATE projects SET settings=? WHERE id=?",(json.dumps({'tabletop':{'nodes':[{'id':'note-1','kind':'note','x':3,'y':4}]}}),pid))
                conn.commit()
            for _ in range(3):collaboration.setup(db,t)
            with db.connect(t) as conn:
                project=conn.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
                self.assertEqual(project['board_version'],0)
                self.assertEqual(json.loads(project['settings'])['tabletop']['nodes'][0]['x'],3)
                self.assertEqual(project['user_id'],user)
                tables={r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertTrue({'project_invites','project_links','project_members','board_presence','board_locks'}.issubset(tables))
                self.assertIsNotNone(collaboration.accessible(conn,user,pid))
                other=db.create_guest(conn,'Invitee')
                self.assertIsNone(collaboration.accessible(conn,other,pid))
                conn.execute('INSERT INTO project_members VALUES(?,?,?)',(pid,other,1));conn.commit()
                self.assertIsNotNone(collaboration.accessible(conn,other,pid))
                self.assertIsNone(db.project_for(conn,other,pid)) # Owner-only legacy mutations remain protected.
                conn.execute('DELETE FROM projects WHERE id=?',(pid,));conn.commit()
                self.assertFalse(conn.execute('SELECT 1 FROM project_members WHERE project_id=?',(pid,)).fetchone())

    def test_release_ui_and_network_guards(self):
        js=(ROOT/'frontend/js/app.js').read_text()
        html=(ROOT/'frontend/index.html').read_text()
        api=(ROOT/'backend/app.py').read_text()
        for element in ('boardPeers','joinBoardForm','inviteBoardForm','boardInviteList','refreshBoard','collabCursorLayer','linkedBoardList'):
            self.assertIn(f'id="{element}"',html)
        for item in ('function collabMove(ev)', 'function collabPulse()', 'function lockItems(ids)', 'function saveTable()', "'collab/board'", 'collabLocked'):
            if item=="'collab/board'":self.assertIn('collab/board',js)
            else:self.assertIn(item,js)
        self.assertIn("'/collab/' not in request.path",api)
        self.assertIn("collaboration.register(app, store, DATA, authenticated)",api)
        self.assertIn('board_version=board_version+1',api)
        self.assertIn('0.2.27',(ROOT/'version.json').read_text())

try:
    from flask import Flask
    from PIL import Image
    from cryptography.fernet import Fernet
    HAS_FLASK=True
except ImportError:HAS_FLASK=False

@unittest.skipUnless(HAS_FLASK,'Full Flask stack not installed: Ubuntu watcher must execute')
class CollaborationAPI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.saved={k:os.environ.get(k) for k in ('UMI_DATA_DIR','UMI_ENABLE_SETUP','UMI_SESSION_KEY','UMI_FERNET_KEY')}
        os.environ.update(UMI_DATA_DIR=self.tmp.name,UMI_ENABLE_SETUP='1',
                          UMI_SESSION_KEY='development-test-secret-only-not-production',
                          UMI_FERNET_KEY=Fernet.generate_key().decode())
        from backend import app as api
        self.api=importlib.reload(api)
        self.owner=self.api.app.test_client();self.guest=self.api.app.test_client();self.stranger=self.api.app.test_client()
        created=self.owner.post('/api/setup',json={'password':'super-secret-long-password'})
        self.assertEqual(created.status_code,200,created.json)
        self.ocsrf=created.json['csrf']
        guest_csrf=self.guest.get('/api/session').json['csrf']
        stranger_csrf=self.stranger.get('/api/session').json['csrf']
        self.gcsrf=self.guest.post('/api/guest',json={'name':'Invitee'},headers={'X-CSRF-Token':guest_csrf}).json['csrf']
        self.scsrf=self.stranger.post('/api/guest',json={'name':'Stranger'},headers={'X-CSRF-Token':stranger_csrf}).json['csrf']
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for k,v in self.saved.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v

    def post(self,client,csrf,url,data):return client.post(url,json=data,headers={'X-CSRF-Token':csrf})
    def patch(self,client,csrf,url,data):return client.patch(url,json=data,headers={'X-CSRF-Token':csrf})

    def create_invite(self):
        pid=self.post(self.owner,self.ocsrf,'/api/projects',{'name':'Shared library'}).json['id']
        invite=self.post(self.owner,self.ocsrf,f'/api/projects/{pid}/invitations',{'pin':'950371','days':7})
        self.assertEqual(invite.status_code,201,invite.json)
        token=invite.json['token']
        with db.connect(self.tmp.name) as conn:
            stored=conn.execute('SELECT * FROM project_invites WHERE project_id=?',(pid,)).fetchone()
            self.assertEqual(stored['token_hash'],hashlib.sha256(token.encode()).hexdigest())
            self.assertNotIn(token,str(dict(stored)))
            self.assertNotIn('950371',str(dict(stored)))
        return pid,invite.json

    def test_invitation_access_privacy_expiry_revoke_and_link(self):
        pid,inv=self.create_invite()
        self.assertEqual(self.guest.get('/api/projects/'+pid).status_code,404)
        self.assertEqual(self.post(self.guest,self.gcsrf,'/api/invitations/join',{'token':inv['token'],'pin':'wrong'}).status_code,400)
        self.assertEqual(self.post(self.guest,self.gcsrf,'/api/invitations/join',{'token':inv['token'],'pin':'000000'}).status_code,403)
        joined=self.post(self.guest,self.gcsrf,'/api/invitations/join',{'token':inv['token'],'pin':'950371'})
        self.assertEqual(joined.status_code,200,joined.json)
        self.assertEqual(self.guest.get('/api/projects/'+pid).status_code,200)
        self.assertEqual(self.guest.get('/api/projects').json['projects'][0]['is_owner'],False)
        self.assertEqual(self.patch(self.guest,self.gcsrf,'/api/projects/'+pid,{'name':'Stolen'}).status_code,403)
        self.assertEqual(self.guest.delete('/api/projects/'+pid,headers={'X-CSRF-Token':self.gcsrf}).status_code,403)
        self.assertEqual(self.post(self.guest,self.gcsrf,'/api/projects/'+pid+'/invitations',{'pin':'123456'}).status_code,404)
        self.assertEqual(self.stranger.get('/api/projects/'+pid).status_code,404)
        # Link changes never grant a guest access to a different board.
        second=self.post(self.owner,self.ocsrf,'/api/projects',{'name':'Hidden B'}).json['id']
        linked=self.post(self.owner,self.ocsrf,f'/api/projects/{pid}/links',{'project_id':second})
        self.assertEqual(linked.status_code,200,linked.json)
        self.assertEqual(self.guest.get(f'/api/projects/{second}').status_code,404)
        self.assertEqual(self.guest.get(f'/api/projects/{pid}/links').json['links'],[])
        self.assertEqual(self.post(self.owner,self.ocsrf,f"/api/projects/{pid}/invitations/{inv['id']}/revoke",{}).status_code,200)
        self.assertEqual(self.post(self.stranger,self.scsrf,'/api/invitations/join',{'token':inv['token'],'pin':'950371'}).status_code,404)
        self.assertEqual(self.guest.get('/api/projects/'+pid).status_code,200) # link revocation ≠ member removal
        guest_uid=self.guest.get('/api/session').json['user']['id']
        self.assertEqual(self.post(self.owner,self.ocsrf,f'/api/projects/{pid}/members/{guest_uid}/remove',{}).status_code,200)
        self.assertEqual(self.guest.get('/api/projects/'+pid).status_code,404)

    def test_live_cursors_locks_and_unrelated_item_merge(self):
        pid,inv=self.create_invite()
        self.post(self.guest,self.gcsrf,'/api/invitations/join',{'token':inv['token'],'pin':'950371'})
        a='a'*32;b='b'*32;endpoint=f'/api/projects/{pid}/collab'
        self.assertEqual(self.post(self.owner,self.ocsrf,endpoint+'/presence',{'client':a,'x':12,'y':-5}).status_code,200)
        self.assertEqual(self.post(self.guest,self.gcsrf,endpoint+'/presence',{'client':b,'x':45,'y':11}).status_code,200)
        seen=self.guest.get(endpoint+'/state?client='+b).json
        self.assertEqual(len(seen['people']),1)
        self.assertEqual(seen['people'][0]['x'],12)
        snapshot={'nodes':[],'packs':[]}
        node1={'id':'note-one','kind':'note','x':0,'y':0,'content':'Owner'}
        node2={'id':'note-two','kind':'note','x':10,'y':0,'content':'Guest'}
        owner=self.patch(self.owner,self.ocsrf,endpoint+'/board',{'client':a,'base':snapshot,'board':{'nodes':[node1],'packs':[]}})
        self.assertEqual(owner.status_code,200,owner.json)
        guest=self.patch(self.guest,self.gcsrf,endpoint+'/board',{'client':b,'base':snapshot,'board':{'nodes':[node2],'packs':[]}})
        self.assertEqual(guest.status_code,200,guest.json)
        self.assertEqual({n['id'] for n in guest.json['board']['nodes']},{'note-one','note-two'})
        stale=self.patch(self.guest,self.gcsrf,endpoint+'/board',{'client':b,'base':snapshot,'board':{'nodes':[{'id':'note-one','kind':'note','x':9,'y':8}],'packs':[]}})
        self.assertEqual(stale.status_code,409,stale.json)
        lock=self.post(self.owner,self.ocsrf,endpoint+'/lock',{'client':a,'object_id':'note-one'})
        self.assertEqual(lock.status_code,200,lock.json)
        refused=self.post(self.guest,self.gcsrf,endpoint+'/lock',{'client':b,'object_id':'note-one'})
        self.assertEqual(refused.status_code,423,refused.json)
        locked=self.patch(self.guest,self.gcsrf,endpoint+'/board',{'client':b,'base':guest.json['board'],'board':{'nodes':[{'id':'note-one','kind':'note','x':99,'y':0},node2],'packs':[]}})
        self.assertEqual(locked.status_code,423,locked.json)
        released=self.post(self.owner,self.ocsrf,endpoint+'/lock',{'client':a,'object_id':'note-one','release':True})
        self.assertEqual(released.status_code,200)
        done=self.patch(self.guest,self.gcsrf,endpoint+'/board',{'client':b,'base':guest.json['board'],'board':{'nodes':[{'id':'note-one','kind':'note','x':99,'y':0},node2],'packs':[]}})
        self.assertEqual(done.status_code,200,done.json)
        self.assertEqual(self.guest.get(f'/api/projects/{pid}/canvas-history').status_code,200)
        self.assertEqual(self.post(self.owner,self.ocsrf,f'/api/projects/{pid}/canvas-history',{'direction':'undo'}).status_code,409)

    def test_pin_bruteforce_timeout(self):
        pid,inv=self.create_invite()
        for _ in range(5):
            self.assertEqual(self.post(self.guest,self.gcsrf,'/api/invitations/join',{'token':inv['token'],'pin':'123456'}).status_code,403)
        self.assertEqual(self.post(self.guest,self.gcsrf,'/api/invitations/join',{'token':inv['token'],'pin':'950371'}).status_code,429)

if __name__=='__main__':unittest.main()
