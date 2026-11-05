import asyncio
import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from test_admin_password import functions, HttpError


class TenantTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connections = []
        def db():
            conn = sqlite3.connect(Path(self.temp.name) / 'test.db')
            conn.row_factory = sqlite3.Row
            self.connections.append(conn)
            return conn
        self.ns = dict(db=db,sqlite3=sqlite3,base64=base64,hashlib=hashlib,hmac=hmac,
                       secrets=secrets,time=time,re=re,USER='admin',PASSWORD='Test-password-123',
                       SESSION_SECRET='test-secret',HTTPException=HttpError,Request=object,
                       Cookie=lambda **kw:None)
        functions(Path(__file__).resolve().parents[1]/'control-center/app.py',
                  {'init_db','control_password_hash','hash_password','valid_password','sign_session',
                   'authenticated','require_auth','tenant_session','session_tenant','require_node_access',
                   'save_tenant','state','list_tenants'},self.ns)
        self.ns['init_db']()
        with db() as conn:
            for n in range(1,4):
                conn.execute('INSERT INTO nodes(id,name,url,api_key_enc,created_at) VALUES(?,?,?,?,?)',(n,f'Node {n}',f'https://node{n}.example','secret',0))
        self.admin=self.ns['sign_session'](int(time.time())+3600)

    def tearDown(self):
        for conn in self.connections:conn.close()
        self.temp.cleanup()

    def save(self,name='Client',username='client',nodes=None,tenant_id=None,password='Test-tenant-password',token=None,enabled=True):
        class Request:
            async def json(self_):
                return dict(name=name,username=username,password=password,node_ids=nodes or [],enabled=enabled)
        return asyncio.run(self.ns['save_tenant'](Request(),token or self.admin,tenant_id))

    def tenant(self,id):
        with self.ns['db']() as conn:row=conn.execute('SELECT * FROM tenants WHERE id=?',(id,)).fetchone()
        return self.ns['tenant_session'](row,int(time.time())+3600)

    def test_sessions_and_node_isolation(self):
        a=self.save(nodes=[1])['id'];b=self.save(username='other',nodes=[2])['id']
        token=self.tenant(a)
        self.assertFalse(self.ns['authenticated'](token))
        self.assertEqual(self.ns['session_tenant'](token)['id'],a)
        self.ns['require_node_access'](token,1)
        for id in [2,3,999]:
            with self.assertRaises(HttpError) as error:self.ns['require_node_access'](token,id)
            self.assertEqual(error.exception.status_code,404)
        with self.assertRaises(HttpError):self.ns['require_auth'](token)
        with self.assertRaises(HttpError):asyncio.run(self.ns['list_tenants'](token))
        self.ns['require_node_access'](self.admin,2)

    def test_password_reset_and_disable_revoke_sessions(self):
        id=self.save(nodes=[1])['id'];token=self.tenant(id)
        self.save(nodes=[1],tenant_id=id,password='Replacement-password-123')
        self.assertIsNone(self.ns['session_tenant'](token))
        token=self.tenant(id)
        self.save(nodes=[1],tenant_id=id,password='',enabled=False)
        self.assertIsNone(self.ns['session_tenant'](token))

    def test_node_cannot_be_assigned_twice_and_changes_are_atomic(self):
        a=self.save(nodes=[1])['id'];b=self.save(username='other',nodes=[2])['id']
        with self.assertRaises(HttpError) as error:self.save(username='other',nodes=[3,1],tenant_id=b)
        self.assertEqual(error.exception.status_code,409)
        with self.ns['db']() as conn:
            self.assertEqual([r[0] for r in conn.execute('SELECT node_id FROM tenant_nodes WHERE tenant_id=?',(b,))],[2])
        self.save(tenant_id=a,nodes=[],password='')
        self.save(username='other',tenant_id=b,nodes=[1,2],password='')

    def test_bad_input_and_unknown_nodes_do_not_create_accounts(self):
        for kwargs in [dict(username='admin'),dict(username='../bad'),dict(password='short'),dict(nodes=[999]),dict(nodes=['1']),dict(nodes=[True])]:
            with self.assertRaises(HttpError):self.save(**kwargs)
        self.assertEqual(asyncio.run(self.ns['list_tenants'](self.admin))['tenants'],[])

    def test_state_filters_nodes_and_sensitive_snapshot_fields(self):
        id=self.save(nodes=[1])['id'];token=self.tenant(id)
        self.ns['public_node']=lambda r:dict(id=r['id'],name=r['name'],last_sync_at=None,last_ok_at=None,last_error='',snapshot={'peers':[dict(id=7,name='Peer',private_key='secret',config='secret')],'protocols':[]})
        data=asyncio.run(self.ns['state'](token))
        self.assertEqual(data['role'],'tenant')
        self.assertEqual([n['id'] for n in data['nodes']],[1])
        self.assertEqual(data['nodes'][0]['snapshot']['peers'],[dict(id=7,name='Peer')])
        self.assertNotIn('secret',str(data))
        self.assertEqual(len(asyncio.run(self.ns['state'](self.admin))['nodes']),3)

    def test_expired_tampered_and_garbage_sessions_rejected(self):
        id=self.save()['id'];token=self.tenant(id)
        for value in [None,'garbage',token[:-4]+'aaaa',self.admin]:
            self.assertIsNone(self.ns['session_tenant'](value))
        with self.ns['db']() as conn:row=conn.execute('SELECT * FROM tenants WHERE id=?',(id,)).fetchone()
        self.assertIsNone(self.ns['session_tenant'](self.ns['tenant_session'](row,0)))


if __name__=='__main__':unittest.main()
