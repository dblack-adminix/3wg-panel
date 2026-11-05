import base64
import hashlib
import hmac
import ipaddress
import json
import time
import unittest
from pathlib import Path
from test_admin_password import functions, HttpError


class ExitProvisionerTest(unittest.TestCase):
    def setUp(self):
        self.ns=dict(base64=base64,hashlib=hashlib,hmac=hmac,ipaddress=ipaddress,json=json,time=time,HTTPException=HttpError)
        functions(Path(__file__).resolve().parents[1]/'control-center/exit_nodes.py',{'target','confirmation','verify_confirmation','fingerprint'},self.ns)

    def test_only_public_ipv4_and_valid_ports(self):
        self.assertEqual(self.ns['target']('8.8.8.8',22),('8.8.8.8',22))
        for ip,port in [('127.0.0.1',22),('10.0.0.1',22),('169.254.169.254',22),('::1',22),('example.com',22),('8.8.8.8;id',22),('8.8.8.8',0),('8.8.8.8',True),('8.8.8.8','22')]:
            with self.assertRaises(HttpError):self.ns['target'](ip,port)

    def test_confirmation_is_signed_bound_and_expiring(self):
        data=dict(ip='8.8.8.8',port=22,key='test-key',expires=int(time.time())+60)
        token=self.ns['confirmation']('secret',data)
        self.assertEqual(self.ns['verify_confirmation']('secret',token,'8.8.8.8',22),data)
        for secret,token_,ip,port in [('wrong',token,'8.8.8.8',22),('secret',token,'1.1.1.1',22),('secret',token,'8.8.8.8',2222),('secret',token+'a','8.8.8.8',22),('secret','bad','8.8.8.8',22)]:
            with self.assertRaises(HttpError):self.ns['verify_confirmation'](secret,token_,ip,port)
        data['expires']=0
        with self.assertRaises(HttpError):self.ns['verify_confirmation']('secret',self.ns['confirmation']('secret',data),'8.8.8.8',22)

    def test_fingerprint_uses_full_ssh_key(self):
        key=type('Key',(),{'asbytes':lambda self:b'public-key'})()
        expected='SHA256:'+base64.b64encode(hashlib.sha256(b'public-key').digest()).decode().rstrip('=')
        self.assertEqual(self.ns['fingerprint'](key),expected)

    def test_forced_command_does_not_allow_arbitrary_commands(self):
        source=(Path(__file__).resolve().parents[1]/'control-center/provision/agent.py').read_text()
        self.assertIn("action in ('restart','stop')",source)
        self.assertNotIn('shell=True',source)
        self.assertNotIn('SSH_ORIGINAL_COMMAND',source)
        self.assertIn("['docker',action,'3wg-exit']",source)


if __name__=='__main__':unittest.main()
