import base64
import socket
import asyncio
import json
import sqlite3
import tempfile
import time
import sys
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

try:
    import paramiko
except ImportError:
    raise unittest.SkipTest('SSH integration tests run inside the Control image')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'control-center'))
import exit_nodes
from cryptography.fernet import Fernet


class ProvisionTest(unittest.TestCase):
    def test_root_password_is_not_persisted_and_job_completes(self):
        with tempfile.TemporaryDirectory() as directory:
            connections=[]
            def db():
                c=sqlite3.connect(Path(directory)/'test.db');c.row_factory=sqlite3.Row;connections.append(c);return c
            handlers={}
            class App:
                def route(self,path):
                    def decorator(fn):handlers[path]=fn;return fn
                    return decorator
                get=route
                post=route
            fernet=Fernet(Fernet.generate_key());exit_nodes.register(App(),db,lambda _:None,fernet,'secret')
            data=dict(name='Test exit',ip='8.8.8.8',ssh_port=22,password='temporary-root-password',confirmed=True)
            data['confirmation']=exit_nodes.confirmation('secret',dict(ip=data['ip'],port=22,key='a2V5',fingerprint='SHA256:test',expires=time.time()+60))
            class Request:
                async def json(self):return data
            try:
                with patch.object(exit_nodes.POOL,'submit') as submit:
                    result=asyncio.run(handlers['/api/exits/install'](Request(),'admin'))
                    self.assertEqual(submit.call_args.args[2],data['password'])
                with db() as conn:
                    row=conn.execute('SELECT * FROM exit_nodes').fetchone()
                self.assertNotIn(data['password'],str(dict(row)))
                material=json.loads(fernet.decrypt(row['secrets_enc'].encode()))
                self.assertNotIn(data['password'],str(material))
                files={}
                class Stream:
                    def __init__(self,path):self.path=path
                    def __enter__(self):return self
                    def __exit__(self,*args):pass
                    def write(self,content):files[self.path]=content
                class SFTP:
                    def mkdir(self,*args,**kwargs):pass
                    def chmod(self,*args):pass
                    def close(self):pass
                    def open(self,path,mode):return Stream(path)
                class Transport:
                    def close(self):pass
                def command(*args,**kwargs):return b'{"ok":true,"running":true}'
                with patch.object(exit_nodes,'ssh_connect',return_value=Transport()),patch.object(exit_nodes,'command',side_effect=command),patch.object(exit_nodes.paramiko.SFTPClient,'from_transport',return_value=SFTP()):
                    exit_nodes.install_worker(result['id'],data['password'],db,fernet)
                with db() as conn:row=conn.execute('SELECT * FROM exit_nodes').fetchone()
                self.assertEqual(row['status'],'waiting_gateway')
                self.assertNotIn(data['password'],str(dict(row)))
                self.assertFalse(any(data['password'].encode() in value for value in files.values()))
                public=asyncio.run(handlers['/api/exits']('admin'))
                self.assertNotIn('secrets_enc',public['exits'][0])
                self.assertEqual(exit_nodes.PENDING,0)
            finally:
                exit_nodes.PENDING=0
                for conn in connections:conn.close()


class Server(paramiko.ServerInterface):
    passwords=[]
    def check_auth_password(self,username,password):
        self.passwords.append(password)
        return paramiko.AUTH_SUCCESSFUL if username=='root' and password=='test-only-password' else paramiko.AUTH_FAILED
    def get_allowed_auths(self,username):return 'password'


class SSHTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.key=paramiko.RSAKey.generate(2048)
    def server(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
        port=listener.getsockname()[1];event=threading.Event();Server.passwords=[]
        def run():
            transport=None
            try:
                conn,_=listener.accept();transport=paramiko.Transport(conn);transport.add_server_key(self.key);transport.start_server(server=Server());event.wait(5)
            except Exception:pass
            finally:
                if transport:transport.close()
                listener.close()
        thread=threading.Thread(target=run);thread.start()
        return port,event,thread
    def test_pinned_key_allows_authentication(self):
        port,event,thread=self.server()
        try:
            row=dict(ip='127.0.0.1',ssh_port=port,host_key=base64.b64encode(self.key.asbytes()).decode())
            client=exit_nodes.ssh_connect(row,password='test-only-password')
            self.assertTrue(client.is_authenticated());client.close()
            self.assertEqual(Server.passwords,['test-only-password'])
        finally:event.set();thread.join(10)
    def test_changed_host_key_rejected_before_password(self):
        port,event,thread=self.server()
        try:
            row=dict(ip='127.0.0.1',ssh_port=port,host_key=base64.b64encode(b'wrong-key').decode())
            with self.assertRaises(RuntimeError):exit_nodes.ssh_connect(row,password='test-only-password')
            self.assertEqual(Server.passwords,[])
        finally:event.set();thread.join(10)


if __name__=='__main__':unittest.main()
