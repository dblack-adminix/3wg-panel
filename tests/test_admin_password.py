import ast
import base64
import asyncio
import hashlib
import hmac
import json
import secrets
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HttpError(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail


class Reply:
    def __init__(self, body, status_code=200):
        self.body, self.status_code, self.deleted = body, status_code, []

    def delete_cookie(self, name):
        self.deleted.append(name)


def functions(path, names, namespace):
    tree = ast.parse(path.read_text())
    definitions = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            node.decorator_list = []
            definitions.append(node)
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), 'exec'), namespace)


class PasswordTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.db'
        self.connections = []
        def db():
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            self.connections.append(conn)
            return conn
        self.db = db
        with db() as conn:
            conn.execute('CREATE TABLE panel_settings(key TEXT PRIMARY KEY,value TEXT,updated_at INTEGER)')
            conn.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT)')
            conn.execute('CREATE TABLE panel_users(username TEXT,enabled INTEGER)')
        self.ns = dict(base64=base64,hashlib=hashlib,hmac=hmac,secrets=secrets,json=json,time=time,db=db,
                       PANEL_USER='admin',PANEL_PASSWORD='Initial-Test-Password',SESSION_SECRET='test-secret',
                       SESSION_VERSION='v1',IS_EASY=False,SESSION_COOKIE='test',Request=object)
        self.ns['admin_user'] = lambda: {'username':'admin','is_env_admin':True,'role':'admin'}
        functions(ROOT/'app/app.py', {'panel_setting_get','panel_setting_set','password_hash','password_verify','make_user_session','verify_user_session','make_session_token','authenticate_user'}, self.ns)

    def tearDown(self):
        for conn in self.connections:
            conn.close()
        self.temp.cleanup()

    def test_core_password_change_revokes_sessions_and_env_password(self):
        self.assertIsNone(self.ns['authenticate_user']('admin','Неверный пароль'))
        self.assertIsNone(self.ns['authenticate_user']('Администратор','Initial-Test-Password'))
        old = self.ns['make_user_session']('admin','admin')
        legacy = self.ns['make_session_token']()
        hashed = self.ns['password_hash']('New-Test-Password-123')
        self.ns['panel_setting_set']('admin_password_hash',hashed)
        self.assertIsNone(self.ns['verify_user_session'](old))
        self.assertNotEqual(legacy,self.ns['make_session_token']())
        self.assertIsNone(self.ns['authenticate_user']('admin','Initial-Test-Password'))
        self.assertTrue(self.ns['authenticate_user']('admin','New-Test-Password-123'))
        self.assertTrue(self.ns['verify_user_session'](self.ns['make_user_session']('admin','admin')))
        self.assertNotIn('New-Test-Password-123',hashed)

    def test_control_password_change_revokes_sessions(self):
        self.ns.update(USER='admin',PASSWORD='Initial-Test-Password')
        functions(ROOT/'control-center/app.py', {'control_password_hash','hash_password','valid_password','sign_session','authenticated'}, self.ns)
        old = self.ns['sign_session'](int(time.time())+3600)
        self.assertTrue(self.ns['authenticated'](old))
        with self.db() as conn:
            conn.execute("INSERT INTO settings(key,value) VALUES('admin_password_hash',?)",(self.ns['hash_password']('New-Test-Password-123'),))
        self.assertFalse(self.ns['authenticated'](old))
        self.assertFalse(self.ns['valid_password']('Initial-Test-Password'))
        self.assertTrue(self.ns['valid_password']('New-Test-Password-123'))
        self.assertTrue(self.ns['authenticated'](self.ns['sign_session'](int(time.time())+3600)))

    def test_core_endpoint_checks_current_password_and_confirmation(self):
        async def read(request):
            return request.data
        self.ns.update(api_read_payload=read,HTTPException=HttpError,JSONResponse=Reply,
                       api_error=lambda text,status_code=400: Reply({'error':text},status_code),
                       api_audit_log=lambda *args: None)
        functions(ROOT/'app/app.py', {'api_admin_password_change'}, self.ns)
        request = type('Request',(),{})()
        request.cookies={'test':self.ns['make_user_session']('admin','admin')}
        for old,new,confirmation in [('wrong','New-Test-Password-123','New-Test-Password-123'),('Initial-Test-Password','short','short'),('Initial-Test-Password','New-Test-Password-123','different')]:
            request.data={'current_password':old,'new_password':new,'confirm_password':confirmation}
            result=asyncio.run(self.ns['api_admin_password_change'](request))
            self.assertEqual(result.status_code,400)
            self.assertIsNone(self.ns['panel_setting_get']('admin_password_hash'))
        request.data={'current_password':'Initial-Test-Password','new_password':'New-Test-Password-123','confirm_password':'New-Test-Password-123'}
        result=asyncio.run(self.ns['api_admin_password_change'](request))
        self.assertEqual(result.status_code,200)
        self.assertIn('test',result.deleted)
        with self.assertRaises(HttpError):
            asyncio.run(self.ns['api_admin_password_change'](request))


if __name__ == '__main__':
    unittest.main()
