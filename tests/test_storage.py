import tempfile
import unittest
from backend import db

class StorageTest(unittest.TestCase):
    def test_user_project_and_ownership(self):
        with tempfile.TemporaryDirectory() as d:
            db.init(d)
            with db.connect(d) as conn:
                uid=db.create_user(conn,'admin','long-secure-password','Creator')
                self.assertTrue(db.authenticate(conn,'admin','long-secure-password'))
                self.assertIsNone(db.authenticate(conn,'admin','wrong'))
                pid=db.create_project(conn,uid,'Terrain beast','An off-road crawler')
                self.assertEqual(db.project_for(conn,uid,pid)['name'],'Terrain beast')
                self.assertIsNone(db.project_for(conn,'someone-else',pid))
                db.record_message(conn,pid,'user','Build it')
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0],1)

    def test_db_reopen_keeps_data(self):
        with tempfile.TemporaryDirectory() as d:
            db.init(d)
            with db.connect(d) as conn:db.create_user(conn,'admin','a-reasonable-password','Creator')
            db.init(d)
            with db.connect(d) as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM users').fetchone()[0],1)

if __name__=='__main__':unittest.main()
