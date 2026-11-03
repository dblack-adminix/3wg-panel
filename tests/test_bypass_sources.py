import ipaddress
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import bypass_sources as sources


class BypassSourcesTest(unittest.TestCase):
    def test_feed_validation(self):
        self.assertEqual(sources.parse_source('ipv4', '# comment\n8.8.8.8/32\n8.8.8.8/32\n'), ['8.8.8.8/32'])
        self.assertEqual(sources.parse_source('domains', 'EXAMPLE.RU.\n'), ['example.ru'])
        for kind, value in [('ipv4','::/0'),('ipv4','0.0.0.0/0'),('ipv6','8.8.8.8/32'),('domains','https://example.ru'),('domains','*.example.ru'),('ipv4','')]:
            with self.assertRaises(ValueError): sources.parse_source(kind,value)

    def test_combines_selected_sources_and_manual_entries(self):
        catalog={'sources':[{'id':'ipv4','items':['8.8.8.8/32']},{'id':'ipv6','items':['2001:4860::/32']}]}
        groups, networks, routes=sources.resolve_policy([{'name':'Manual','targets':['1.1.1.1']}],{'ipv4':['8.8.8.8/32'],'ipv6':['2001:4860::/32']},catalog)
        self.assertEqual(groups[0]['name'],'Manual')
        self.assertEqual(len(networks),2)
        parsed=list(map(ipaddress.ip_network,routes))
        for value in ['8.8.8.8','1.1.1.1','2001:4860::1']:
            self.assertFalse(any(ipaddress.ip_address(value) in n for n in parsed))
        self.assertTrue(any(ipaddress.ip_address('9.9.9.9') in n for n in parsed))

    def test_rejects_unknown_sources_and_entries(self):
        for selected in [{'url':['https://evil.example']},{'ipv4':['0.0.0.0/0']},{'ipv4':'8.8.8.8/32'}]:
            with self.assertRaises(ValueError):sources.resolve_policy([],selected,{'sources':[]})

    def test_domain_limit_checked_before_dns(self):
        domains=[f's{i}.example.ru' for i in range(129)]
        with patch.object(sources,'resolve_groups') as resolver:
            with self.assertRaises(ValueError):sources.resolve_policy([],{'domains':domains},{'sources':[{'id':'domains','items':domains}]})
            resolver.assert_not_called()

    def test_cached_catalog_and_failed_refresh_preserve_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sources.json'
            previous={'updated_at':int(time.time()),'sources':[{'id':'ipv4','items':['8.8.8.8/32']}],'stale':False,'grouping_version':1}
            path.write_text(json.dumps(previous))
            before=path.read_bytes()
            with patch.object(sources.urllib.request,'urlopen',side_effect=OSError('offline')) as fetch:
                self.assertEqual(sources.load_catalog(path),previous);fetch.assert_not_called()
                result=sources.load_catalog(path,refresh=True)
            self.assertTrue(result['stale']);self.assertEqual(result['sources'],previous['sources'])
            self.assertEqual(path.read_bytes(),before)

    def test_sources_are_optional(self):
        groups,networks,routes=sources.resolve_policy([{'name':'Manual','targets':['8.8.8.8']}],{}, {'sources':[]})
        self.assertEqual(groups[0]['targets'],['8.8.8.8/32']);self.assertEqual(networks,[])
        self.assertNotIn('0.0.0.0/0',routes)

    def test_groups_cover_every_item_and_keep_shared_networks(self):
        catalog=[{'id':'domains','items':['bank.example.ru','other.example.ru']},{'id':'ipv4','items':['8.8.8.0/24','9.9.9.9/32']},{'id':'ipv6','items':['2001:4860::/32']}]
        metadata={'categories':[{'id':'banks','title':'Банки','services':[{'name':'Банк','tier':'lite','ipv4':['8.8.8.8/32'],'ipv6':['2001:4860::1/128']}]},{'id':'payments','title':'Платежи','services':[{'name':'Платёж','tier':'standard','ipv4':['8.8.8.9/32'],'ipv6':[]}]}]}
        configs={'banks':{'services':[{'name':'Банк','domains':['bank.example.ru']}]},'payments':{'services':[]}}
        original={source['id']:list(source['items']) for source in catalog}
        sources.group_sources(catalog,metadata,configs)
        for source in catalog:
            self.assertEqual(source['items'],original[source['id']])
            self.assertEqual(set(source['items']),{value for group in source['groups'] for value in group['items']})
        ipv4=next(source for source in catalog if source['id']=='ipv4')
        self.assertEqual([g['id'] for g in ipv4['groups'] if '8.8.8.0/24' in g['items']],['banks','payments'])
        self.assertEqual(ipv4['groups'][-1]['id'],'other')

    def test_old_cache_gets_group_metadata_without_changing_policy_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sources.json'
            path.write_text(json.dumps({'updated_at':int(time.time()),'sources':[]}))
            with patch.object(sources,'download',side_effect=[b'example.ru',b'8.8.8.8/32',b'2001:4860::/32']),patch.object(sources,'fetch_groups') as group:
                result=sources.load_catalog(path)
            group.assert_called_once()
            self.assertEqual(result['grouping_version'],1)
            self.assertEqual(result['sources'][1]['items'],['8.8.8.8/32'])


if __name__=='__main__':unittest.main()
