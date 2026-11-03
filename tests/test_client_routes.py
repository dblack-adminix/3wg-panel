import importlib.util
import ipaddress
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('client_routes', Path(__file__).resolve().parents[1] / 'app/client_routes.py')
routes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(routes)


class ClientRoutesTest(unittest.TestCase):
    def test_dual_stack_exclusions_and_remaining_addresses(self):
        result = [ipaddress.ip_network(n) for n in routes.allowed_routes(['8.8.8.8/32', '2001:4860:4860::8888/128'])]
        for address in ['8.8.8.8', '2001:4860:4860::8888']:
            self.assertFalse(any(ipaddress.ip_address(address) in n for n in result))
        for address in ['8.8.4.4', '1.1.1.1', '2606:4700:4700::1111']:
            self.assertTrue(any(ipaddress.ip_address(address) in n for n in result))

    def test_overlap_collapsed_and_empty_policy_is_full_tunnel(self):
        self.assertEqual(routes.allowed_routes([]), ['0.0.0.0/0', '::/0'])
        self.assertEqual(routes.allowed_routes(['8.8.8.0/24']), routes.allowed_routes(['8.8.8.0/24', '8.8.8.8/32']))

    def test_domains_resolved_for_both_protocols(self):
        with patch.object(routes.socket, 'getaddrinfo', return_value=[(2,1,6,'',('8.8.8.8',0)), (10,1,6,'',('2001:4860:4860::8888',0,0,0))]):
            groups, _ = routes.resolve_groups([{'name':'Example', 'targets':['example.ru']}])
        self.assertEqual(set(groups[0]['networks']), {'8.8.8.8/32','2001:4860:4860::8888/128'})

    def test_bad_targets_and_unresolved_domains_rejected(self):
        for target in ['https://example.ru', '*.example.ru', '0.0.0.0/0', '::/0', '8.8.8.8/99']:
            with self.assertRaises(ValueError):
                routes.resolve_groups([{'name':'Example','targets':[target]}])
        with patch.object(routes.socket,'getaddrinfo',side_effect=routes.socket.gaierror()):
            with self.assertRaises(ValueError):
                routes.resolve_groups([{'name':'Example','targets':['example.ru']}])


if __name__ == '__main__':
    unittest.main()
