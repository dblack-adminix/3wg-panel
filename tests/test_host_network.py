import importlib.util
import json
import tempfile
import time
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('host_network', Path(__file__).resolve().parents[1] / 'scripts/host_network.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeNetwork(module.NetworkManager):
    def __init__(self, base):
        super().__init__(base)
        self.writes = []
        self.dns_addresses = ['8.8.8.8', '8.8.4.4']
        self.fail_next = False

    def inventory(self):
        return [{'ip': ip, 'interface': 'eth0'} for ip in ['8.8.8.8', '8.8.4.4']]

    def dns(self, host):
        return self.dns_addresses

    def topology(self, config):
        return [{'name': 'vpn', 'addresses': ['172.19.0.2']}]

    def run(self, *args, input=None):
        if args[0] == 'ip':
            return json.dumps([{'dev': 'eth0'}])
        if args[0] == 'iptables':
            return ''
        if args[0] == 'iptables-restore':
            if self.fail_next:
                self.fail_next = False
                raise RuntimeError('simulated firewall error')
            self.writes.append(input)
            return ''
        raise AssertionError(args)


class HostNetworkTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        (self.base / '.env').write_text('PANEL_HOST=vpn.example.com\nVPN_ENDPOINT_HOST=vpn.example.com\nPRIVATE_SETTING=keep-me\nVPN_EGRESS_IP=\n')
        self.manager = FakeNetwork(self.base)

    def tearDown(self):
        self.temp.cleanup()

    def test_apply_confirm_and_private_backup(self):
        before = (self.base / '.env').read_bytes()
        result = self.manager.command('network-apply', {'ip': '8.8.8.8'})
        backup = Path(result['pending']['backup'])
        self.assertEqual(backup.read_bytes(), before)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertIn('PRIVATE_SETTING=keep-me', (self.base / '.env').read_text())
        self.assertIn('-s 172.19.0.2/32 -o eth0 -j SNAT --to-source 8.8.8.8', self.manager.writes[-1])
        self.assertNotIn('-F POSTROUTING', self.manager.writes[-1])
        self.assertNotIn('INPUT', self.manager.writes[-1])
        result = self.manager.command('network-confirm', {'ip': '8.8.8.8'})
        self.assertIsNone(result['pending'])
        self.assertEqual(FakeNetwork(self.base).status()['active_ip'], '8.8.8.8')

    def test_unassigned_or_wrong_dns_rejected_before_changes(self):
        for ip in ['1.1.1.1', '127.0.0.1', '8.8.8.8\n-j ACCEPT', '::1']:
            with self.assertRaises(ValueError):
                self.manager.command('network-apply', {'ip': ip})
        self.manager.dns_addresses = ['1.1.1.1']
        with self.assertRaises(ValueError):
            self.manager.command('network-apply', {'ip': '8.8.8.8'})
        self.assertEqual(self.manager.writes, [])
        self.assertFalse(self.manager.path.exists())

    def test_rollback_restores_previous_selection_without_dns(self):
        self.manager.command('network-apply', {'ip': '8.8.8.8'})
        self.manager.command('network-confirm', {'ip': '8.8.8.8'})
        self.manager.command('network-apply', {'ip': '8.8.4.4'})
        self.manager.dns_addresses = []
        result = self.manager.command('network-rollback', {})
        self.assertEqual(result['active_ip'], '8.8.8.8')
        self.assertIn('VPN_EGRESS_IP=8.8.8.8', (self.base / '.env').read_text())

    def test_apply_failure_rolls_back(self):
        self.manager.fail_next = True
        with self.assertRaises(RuntimeError):
            self.manager.command('network-apply', {'ip': '8.8.8.8'})
        self.assertIsNone(self.manager.state()['pending'])
        self.assertEqual(self.manager.state()['active_ip'], '')

    def test_pending_cannot_be_overwritten_or_confirmed_late(self):
        self.manager.command('network-apply', {'ip': '8.8.8.8'})
        with self.assertRaises(ValueError):
            self.manager.command('network-apply', {'ip': '8.8.4.4'})
        with self.assertRaises(ValueError):
            self.manager.command('network-confirm', {'ip': '8.8.4.4'})
        state = self.manager.state()
        state['pending']['deadline'] = int(time.time()) - 1
        self.manager.save(state)
        with self.assertRaises(ValueError):
            self.manager.command('network-confirm', {'ip': '8.8.8.8'})
        restarted = FakeNetwork(self.base)
        restarted.maintain_once()
        self.assertIsNone(restarted.state()['pending'])
        self.assertEqual(restarted.state()['active_ip'], '')

    def test_confirmed_selection_reapplied_after_restart(self):
        self.manager.command('network-apply', {'ip': '8.8.8.8'})
        self.manager.command('network-confirm', {'ip': '8.8.8.8'})
        restarted = FakeNetwork(self.base)
        restarted.dns_addresses = []
        restarted.maintain_once()
        self.assertIn('--to-source 8.8.8.8', restarted.writes[-1])


if __name__ == '__main__':
    unittest.main()
