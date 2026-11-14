"""Offline endpoint-shaped fixtures; opt-in live checks: ASX_LIVE_TESTS=1."""
import copy
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    import asx_disclosures as asx
except ModuleNotFoundError:
    asx = None


class LookupTests(unittest.TestCase):
    def test_numeric_leading_codes_are_queried_and_survive_entity_cache(self):
        client = asx.ASXClient()
        codes = {'360': 525458059, '4DX': 456}
        universe = [{'ticker': code + '.AX'} for code in codes]
        records = {s['ticker']: {'reviewedOn': '2026-11-12'} for s in universe}
        now = datetime(2026, 11, 14, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as cache, patch.object(asx, 'ASXClient', return_value=client), \
                patch.object(client, 'lookup_entity', side_effect=lambda code: codes[code]) as lookup, \
                patch.object(client, 'announcements', return_value=[]):
            first, _ = asx.discover_updates(universe, records, now, cache)
            second, _ = asx.discover_updates(universe, records, now, cache)
            stored = json.loads((Path(cache) / 'asx-entities.json').read_text())
        self.assertEqual(stored, {'version': 2, 'entities': {
            code: {'xidEntity': entity, 'verifiedAt': '2026-11-14T12:00:00+11:00'}
            for code, entity in codes.items()}})
        self.assertTrue(all(u['status'] == 'current' for u in first.values()), first)
        self.assertTrue(all(u['status'] == 'current' for u in second.values()), second)
        self.assertEqual(lookup.call_count, 2)

    def test_exact_symbol_not_first_predictive_result(self):
        self.assertIsNotNone(asx, 'ASX discovery implementation is missing')
        client = asx.ASXClient()
        payload = {'data': {'items': [
            {'symbol': 'NABPH', 'xidEntity': 111},
            {'symbol': 'NAB', 'xidEntity': 204274613}]}}
        with patch.object(client, 'get_json', return_value=payload):
            self.assertEqual(client.lookup_entity('NAB'), 204274613)

    def test_missing_ambiguous_malformed_predictive_results_fail_closed(self):
        client = asx.ASXClient()
        for payload in (
                {'data': {'items': [{'symbol': 'NABPH', 'xidEntity': 1}]}},
                {'data': {'items': [{'symbol': 'NAB', 'xidEntity': 1},
                                     {'symbol': 'NAB', 'xidEntity': 2}]}},
                {'data': {'items': [{'symbol': 'NAB', 'xidEntity': True}]}},
                {'data': {'items': None}}, {'data': {}},
                {'data': {'items': [None]}},
                {'data': {'items': [{'symbol': 'NAB'}]}}):
            with self.subTest(payload=payload), patch.object(client, 'get_json', return_value=payload):
                with self.assertRaises(asx.DiscoveryError):
                    client.lookup_entity('NAB')


def row(key='doc-1', symbol='NAB', headline='Dividend/Distribution - NAB',
        when='2026-11-12T23:00:00.000Z'):
    return {'documentKey': key, 'headline': headline, 'date': when,
            'symbol': symbol, 'companyInfo': [{'symbol': symbol}],
            'companies': [{'symbolDisplay': symbol}], 'announcementTypes': []}


def page(items, count):
    return {'data': {'items': items, 'count': count}}


class PaginationTests(unittest.TestCase):
    def fetch(self, pages, size=2):
        client = asx.ASXClient()
        with patch.object(client, 'get_json', side_effect=pages) as get:
            result = client.announcements([204274613, 199003248],
                                          '2026-11-01', '2026-11-14', size)
        return result, get

    def test_bulk_pages_reconcile_unique_document_count(self):
        rows = [row('a'), row('b'), row('c')]
        result, get = self.fetch([page(rows[:2], 3), page(rows[2:], 3)])
        self.assertEqual(result, rows)
        self.assertEqual(get.call_count, 2)
        params = get.call_args_list[1].args[1]
        self.assertEqual(params['entityXids'], '204274613,199003248')
        self.assertEqual(params['page'], 1)

    def test_incomplete_duplicate_or_moving_pages_are_errors(self):
        cases = [
            [page([row('a'), row('b')], 3), page([], 3)],
            [page([row('a'), row('b')], 3), page([row('a')], 3)],
            [page([row('a'), row('b')], 3), page([row('c')], 4)],
            [page([row('a'), row('a')], 2)],
            [page([row('a')], 0)],
            [{'data': {'items': []}}],
            [page([], True)],
        ]
        for pages in cases:
            with self.subTest(pages=pages), self.assertRaises(asx.DiscoveryError):
                self.fetch(pages)

    def test_declared_zero_is_verified_empty(self):
        self.assertEqual(self.fetch([page([], 0)])[0], [])


class DiscoveryTests(unittest.TestCase):
    now = datetime(2026, 11, 14, 1, tzinfo=timezone.utc)
    records = {'NAB.AX': {'reviewedOn': '2026-11-12T12:00:00+11:00',
                          'validUntil': '2026-11-13', 'announcedOn': '2026-11-01'}}

    def run_discovery(self, rows, records=None, universe=None, now=None):
        client = asx.ASXClient()
        client.lookup_entity = lambda code: {'NAB': 204274613, 'BHP': 199003248}[code]
        client.announcements = lambda *args: rows
        with tempfile.TemporaryDirectory() as cache, patch.object(asx, 'ASXClient', return_value=client):
            return asx.discover_updates(universe or [{'ticker': 'NAB.AX'}, {'ticker': 'BHP.AX'}],
                                        self.records if records is None else records,
                                        now or self.now, cache)

    def test_material_new_announcement_requires_review_without_renewal(self):
        before = copy.deepcopy(self.records)
        updates, meta = self.run_discovery([row()])
        result = updates['NAB.AX']
        self.assertEqual(result['status'], 'needs_review')
        self.assertEqual(result['latestRelevant']['headline'], 'Dividend/Distribution - NAB')
        self.assertEqual(result['latestRelevant']['date'], '2026-11-13T10:00:00+11:00')
        self.assertEqual(result['latestRelevant']['url'],
                         'https://asx.api.cmfyapp.com/asx-research/1.0/file/doc-1&v=undefined')
        self.assertEqual(result['checkedAt'], '2026-11-14T12:00:00+11:00')
        self.assertEqual(self.records, before)
        self.assertNotIn('validUntil', result)
        self.assertTrue(meta['complete'])
        self.assertEqual(updates['BHP.AX']['status'], 'needs_review')  # no reviewed basis

    def test_review_datetime_not_utc_or_lexical_date_comparison(self):
        records = {'NAB.AX': {'reviewedOn': '2026-11-13T10:00:01+11:00'}}
        updates, _ = self.run_discovery([row()], records)
        self.assertEqual(updates['NAB.AX']['status'], 'current')
        self.assertIsNotNone(updates['NAB.AX']['latestRelevant'])

    def test_date_only_review_keeps_same_day_announcement_pending(self):
        updates, _ = self.run_discovery([row()], {'NAB.AX': {'reviewedOn': '2026-11-13'}})
        self.assertEqual(updates['NAB.AX']['status'], 'needs_review')

    def test_only_complete_no_issuer_announcements_can_be_current(self):
        updates, _ = self.run_discovery([], {'NAB.AX': {'reviewedOn': '2026-11-12'}})
        self.assertEqual(updates['NAB.AX']['status'], 'current')
        self.assertEqual(updates['NAB.AX']['announcementCount'], 0)
        self.assertIsNone(updates['NAB.AX']['latestRelevant'])

    def test_income_material_headlines_types_and_updates_trigger_review(self):
        headlines = [
            'Update - Dividend/Distribution - NAB',
            'Cancellation - Dividend/Distribution - NAB', 'Return of capital',
            'Capital reduction proposal', 'FY2026 Financial Report',
            'Revised earnings guidance', 'Amendment - FY results',
            'Withdrawal of profit outlook', 'Appendix 4D', 'Annual Report',
            'Full Year Results', 'Half-year results', 'Distribution timetable',
        ]
        for headline in headlines:
            with self.subTest(headline=headline):
                updates, _ = self.run_discovery([row(headline=headline)])
                self.assertEqual(updates['NAB.AX']['status'], 'needs_review')
        typed = row(headline='NAB document')
        typed['announcementTypes'] = ['Dividend Rate']
        updates, _ = self.run_discovery([typed])
        self.assertEqual(updates['NAB.AX']['status'], 'needs_review')

    def test_unknown_or_malformed_record_is_unavailable_not_no_announcements(self):
        bad_rows = [None, {}, row(when=None), row(when='not-a-date'),
                    row(when='2026-11-13T10:00:00'), row(when='2026-11-13'),
                    row(when='2026-11-15T00:00:00Z'),
                    row(when='2025-11-13T00:00:00Z'),
                    {**row(), 'companyInfo': [None]},
                    {**row(), 'symbol': None, 'companyInfo': []},
                    {**row(), 'headline': ''}, {**row(), 'documentKey': None}]
        for item in bad_rows:
            with self.subTest(item=item):
                updates, meta = self.run_discovery([item])
                self.assertEqual(updates['NAB.AX']['status'], 'unavailable')
                self.assertFalse(meta['complete'])

    def test_missing_secondary_mentions_do_not_invalidate_wrong_issuer(self):
        secondary = row(symbol='SPX', headline='Financial results')
        secondary['companies'].append({'symbolDisplay': 'NAB'})
        secondary['symbolsSecondary'] = ['SPX', 'NAB', '']
        updates, _ = self.run_discovery([secondary])
        self.assertEqual(updates['NAB.AX']['status'], 'current')
        self.assertEqual(updates['NAB.AX']['announcementCount'], 0)

    def test_old_review_gap_does_not_claim_current(self):
        updates, _ = self.run_discovery([], {'NAB.AX': {'reviewedOn': '2025-01-01'}})
        self.assertEqual(updates['NAB.AX']['status'], 'unavailable')
        self.assertIn('gap', updates['NAB.AX']['reason'])

    def test_valid_review_older_than_sixty_days_expands_complete_discovery_window(self):
        updates, meta = self.run_discovery([], {'NAB.AX': {'reviewedOn': '2026-01-01'}})
        self.assertEqual(meta['windowStart'], '2026-01-01')
        self.assertEqual(updates['NAB.AX']['status'], 'current')

    def test_sydney_day_window_and_dst(self):
        summer = self.run_discovery([], now=datetime(2026, 11, 13, 14, tzinfo=timezone.utc))[1]
        winter = self.run_discovery([], now=datetime(2026, 7, 1, 15, tzinfo=timezone.utc))[1]
        self.assertEqual(summer['windowEnd'], '2026-11-14')
        self.assertTrue(summer['checkedAt'].endswith('+11:00'))
        self.assertEqual(winter['windowEnd'], '2026-07-02')
        self.assertTrue(winter['checkedAt'].endswith('+10:00'))

    def test_failure_is_unavailable_not_current(self):
        client = asx.ASXClient()
        with tempfile.TemporaryDirectory() as cache, patch.object(asx, 'ASXClient', return_value=client), \
                patch.object(client, 'lookup_entity', return_value=204274613), \
                patch.object(client, 'announcements', side_effect=asx.DiscoveryError('count changed')):
            updates, meta = asx.discover_updates([{'ticker': 'NAB.AX'}], self.records, self.now, cache)
        self.assertEqual(updates['NAB.AX']['status'], 'unavailable')
        self.assertIn('count changed', updates['NAB.AX']['reason'])
        self.assertFalse(meta['complete'])


class Response(io.BytesIO):
    status = 200


class TransportTests(unittest.TestCase):
    def test_real_urllib_headers_timeout_and_shared_rate_limit(self):
        clock, starts, requests = [100.0], [], []

        def sleep(seconds):
            clock[0] += seconds

        def open_request(request, timeout):
            starts.append(clock[0])
            requests.append((request, timeout))
            return Response(b'{"data":{"items":[],"count":0}}')

        # Patch only the network boundary, not the client rate limiter.
        with patch.object(asx, 'urlopen', side_effect=open_request, create=True), \
                patch.object(asx, '_last_request', 0.0, create=True), \
                patch('time.monotonic', side_effect=lambda: clock[0]), \
                patch('time.sleep', side_effect=sleep):
            one, two = asx.ASXClient(), asx.ASXClient()
            one.get_json('search/predictive', {'searchText': 'NAB', 'useBondsLookup': 'true'})
            two.get_json('search/predictive', {'searchText': 'BHP', 'useBondsLookup': 'true'})
        self.assertGreaterEqual(starts[1] - starts[0], 0.149)
        self.assertEqual(requests[0][1], 20)
        self.assertIn('searchText=NAB', requests[0][0].full_url)
        headers = dict((k.lower(), v) for k, v in requests[0][0].header_items())
        self.assertEqual(headers['referer'], 'https://www.asx.com.au/')
        self.assertIn('Mozilla/5.0', headers['user-agent'])
        self.assertEqual(headers['accept'], 'application/json')
        self.assertNotIn('cookie', headers)
        self.assertNotIn('authorization', headers)

    def test_network_failure_has_two_retries_then_explicit_error(self):
        with patch.object(asx, 'urlopen', side_effect=OSError('offline'), create=True) as get, \
                patch('time.sleep'):
            with self.assertRaisesRegex(asx.DiscoveryError, 'offline'):
                asx.ASXClient().get_json('search/predictive', {'searchText': 'NAB'})
        self.assertEqual(get.call_count, 3)

    def test_malformed_success_cannot_masquerade_as_empty(self):
        for raw in (b'not json', b'[]', b'{"data":null}'):
            with self.subTest(raw=raw), \
                    patch.object(asx, 'urlopen', return_value=Response(raw), create=True), \
                    patch('time.sleep'), self.assertRaises(asx.DiscoveryError):
                asx.ASXClient().get_json('markets/announcements', {})


class CacheTests(unittest.TestCase):
    now = datetime(2026, 11, 14, 1, tzinfo=timezone.utc)
    universe = [{'ticker': 'NAB.AX'}]
    records = {'NAB.AX': {'reviewedOn': '2026-11-12'}}

    def test_legacy_identity_requires_exact_lookup_and_queries_new_identity(self):
        calls = []

        def fixture(path, params):
            calls.append((path, params))
            if path == 'search/predictive':
                return {'data': {'items': [{'symbol': 'NABPH', 'xidEntity': 111},
                                           {'symbol': 'NAB', 'xidEntity': 222}]}}
            return page([], 0)

        with tempfile.TemporaryDirectory() as cache, patch.object(asx.ASXClient, 'get_json', side_effect=fixture):
            (Path(cache) / 'asx-entities.json').write_text(json.dumps(
                {'version': 1, 'entities': {'NAB': 111}}))
            updates, _ = asx.discover_updates(self.universe, self.records, self.now, cache)
            stored = json.loads((Path(cache) / 'asx-entities.json').read_text())
        self.assertEqual([p['searchText'] for path, p in calls if path == 'search/predictive'], ['NAB'])
        self.assertEqual([p['entityXids'] for path, p in calls if path == 'markets/announcements'], ['222'])
        self.assertEqual(stored, {'version': 2, 'entities': {
            'NAB': {'xidEntity': 222, 'verifiedAt': '2026-11-14T12:00:00+11:00'}}})
        self.assertEqual(updates['NAB.AX']['status'], 'current')

    def test_expired_or_unverifiable_identity_relooks_up_exact_symbol(self):
        for mapping in (
                {'xidEntity': 111, 'verifiedAt': '2026-11-13T00:59:59Z'},
                {'xidEntity': 111, 'verifiedAt': '2026-11-14T01:00:01Z'},
                {'xidEntity': 111, 'verifiedAt': 'not-a-date'},
                {'xidEntity': 111, 'verifiedAt': '2026-11-14'},
                {'xidEntity': 111, 'verifiedAt': '2026-11-14T01:00:00'},
                {'xidEntity': 111, 'verifiedAt': None},
                {'xidEntity': 111},
                {'xidEntity': True, 'verifiedAt': '2026-11-14T01:00:00Z'},
                {'xidEntity': 0, 'verifiedAt': '2026-11-14T01:00:00Z'}):
            calls = []

            def fixture(path, params):
                calls.append((path, params))
                if path == 'search/predictive':
                    return {'data': {'items': [{'symbol': 'NABPH', 'xidEntity': 111},
                                               {'symbol': 'NAB', 'xidEntity': 222}]}}
                return page([], 0)

            with self.subTest(mapping=mapping), tempfile.TemporaryDirectory() as cache, \
                    patch.object(asx.ASXClient, 'get_json', side_effect=fixture):
                (Path(cache) / 'asx-entities.json').write_text(json.dumps(
                    {'version': 2, 'entities': {'NAB': mapping}}))
                updates, _ = asx.discover_updates(self.universe, self.records, self.now, cache)
                self.assertEqual([p['searchText'] for path, p in calls if path == 'search/predictive'], ['NAB'])
                self.assertEqual([p['entityXids'] for path, p in calls if path == 'markets/announcements'], ['222'])
                self.assertEqual(updates['NAB.AX']['status'], 'current')

    def test_failed_expired_identity_lookup_cannot_establish_current_or_query_old_id(self):
        client = asx.ASXClient()
        with tempfile.TemporaryDirectory() as cache, patch.object(asx, 'ASXClient', return_value=client), \
                patch.object(client, 'lookup_entity', side_effect=asx.DiscoveryError('offline')) as lookup, \
                patch.object(client, 'announcements', return_value=[]) as fetch:
            (Path(cache) / 'asx-entities.json').write_text(json.dumps({'version': 2, 'entities': {
                'NAB': {'xidEntity': 111, 'verifiedAt': '2026-11-13T00:59:59Z'}}}))
            updates, meta = asx.discover_updates(self.universe, self.records, self.now, cache)
        lookup.assert_called_once_with('NAB')
        fetch.assert_not_called()
        self.assertEqual(updates['NAB.AX']['status'], 'unavailable')
        self.assertFalse(meta['complete'])

    def test_fresh_identity_reused_through_exact_twenty_four_hour_boundary(self):
        for verified in ('2026-11-13T01:00:00Z', '2026-11-14T01:00:00Z',
                         '2026-11-13T12:00:00+11:00'):
            client = asx.ASXClient()
            with self.subTest(verified=verified), tempfile.TemporaryDirectory() as cache, \
                    patch.object(asx, 'ASXClient', return_value=client), \
                    patch.object(client, 'lookup_entity') as lookup, \
                    patch.object(client, 'announcements', return_value=[]) as fetch:
                (Path(cache) / 'asx-entities.json').write_text(json.dumps({'version': 2, 'entities': {
                    'NAB': {'xidEntity': 111, 'verifiedAt': verified}}}))
                updates, _ = asx.discover_updates(self.universe, self.records, self.now, cache)
                stored = json.loads((Path(cache) / 'asx-entities.json').read_text())
            lookup.assert_not_called()
            self.assertEqual(fetch.call_args.args[0], [111])
            self.assertEqual(stored['entities']['NAB']['verifiedAt'], verified)
            self.assertEqual(updates['NAB.AX']['status'], 'current')

    def test_entity_mapping_persists_but_failure_is_not_cached(self):
        client = asx.ASXClient()
        with tempfile.TemporaryDirectory() as cache, patch.object(asx, 'ASXClient', return_value=client), \
                patch.object(client, 'lookup_entity', return_value=204274613) as lookup, \
                patch.object(client, 'announcements', side_effect=[asx.DiscoveryError('offline'), []]) as fetch:
            first, _ = asx.discover_updates(self.universe, self.records, self.now, cache)
            second, _ = asx.discover_updates(self.universe, self.records, self.now, cache)
            stored = json.loads((Path(cache) / 'asx-entities.json').read_text())
        self.assertEqual(stored, {'version': 2, 'entities': {'NAB': {
            'xidEntity': 204274613, 'verifiedAt': '2026-11-14T12:00:00+11:00'}}})
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(first['NAB.AX']['status'], 'unavailable')
        self.assertEqual(second['NAB.AX']['status'], 'current')

    def test_complete_poll_reused_only_same_sydney_day_with_original_check_time(self):
        client = asx.ASXClient()
        later = datetime(2026, 11, 14, 1, 10, tzinfo=timezone.utc)
        tomorrow = datetime(2026, 11, 14, 14, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as cache, patch.object(asx, 'ASXClient', return_value=client), \
                patch.object(client, 'lookup_entity', return_value=204274613) as lookup, \
                patch.object(client, 'announcements', return_value=[]) as fetch:
            first, _ = asx.discover_updates(self.universe, self.records, self.now, cache)
            second, meta = asx.discover_updates(self.universe, self.records, later, cache)
            self.assertEqual(first['NAB.AX']['checkedAt'], second['NAB.AX']['checkedAt'])
            self.assertEqual(meta['cachedBatches'], 1)
            asx.discover_updates(self.universe, self.records, tomorrow, cache)
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(fetch.call_count, 2)

    def test_same_day_cache_older_than_thirty_minutes_discovers_new_announcement(self):
        client = asx.ASXClient()
        later = datetime(2026, 11, 14, 1, 31, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as cache, patch.object(asx, 'ASXClient', return_value=client), \
                patch.object(client, 'lookup_entity', return_value=204274613), \
                patch.object(client, 'announcements', side_effect=[[], [row(when='2026-11-14T01:20:00Z')]]) as fetch:
            first, _ = asx.discover_updates(self.universe, self.records, self.now, cache)
            second, _ = asx.discover_updates(self.universe, self.records, later, cache)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(first['NAB.AX']['status'], 'current')
        self.assertEqual(second['NAB.AX']['status'], 'needs_review')

    def test_atomic_write_failure_keeps_previous_json_and_removes_temp(self):
        with tempfile.TemporaryDirectory() as cache:
            target = Path(cache) / 'asx-entities.json'
            target.write_text('{"old":true}')
            with patch.object(asx.os, 'replace', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    asx._atomic_json(target, {'new': True})
            self.assertEqual(json.loads(target.read_text()), {'old': True})
            self.assertEqual([p.name for p in Path(cache).iterdir()], ['asx-entities.json'])

    def test_corrupt_mapping_recovered_by_exact_lookup(self):
        client = asx.ASXClient()
        with tempfile.TemporaryDirectory() as cache, patch.object(asx, 'ASXClient', return_value=client), \
                patch.object(client, 'lookup_entity', return_value=204274613) as lookup, \
                patch.object(client, 'announcements', return_value=[]):
            (Path(cache) / 'asx-entities.json').write_text('not json')
            updates, meta = asx.discover_updates(self.universe, self.records, self.now, cache)
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(updates['NAB.AX']['status'], 'current')
        self.assertTrue(meta['cacheWarnings'])


class EndpointIntegrationTests(unittest.TestCase):
    now = datetime(2026, 11, 14, 1, tzinfo=timezone.utc)

    def test_incomplete_count_does_not_prove_per_company_empty(self):
        def fixture(path, params):
            if path == 'search/predictive':
                return {'data': {'items': [{'symbol': params['searchText'], 'xidEntity': 123}]}}
            return page([], 1)

        with tempfile.TemporaryDirectory() as cache, patch.object(asx.ASXClient, 'get_json', side_effect=fixture):
            updates, meta = asx.discover_updates([{'ticker': 'NAB.AX'}],
                {'NAB.AX': {'reviewedOn': '2026-11-12'}}, self.now, cache)
            polls = list(Path(cache).glob('asx-announcements-*.json'))
        self.assertEqual(updates['NAB.AX']['status'], 'unavailable')
        self.assertFalse(meta['complete'])
        self.assertEqual(polls, [])

    def test_batches_forty_with_isolated_batch_failure_and_explicit_symbol_override(self):
        universe = [{'ticker': f'T{i:02}.AX'} for i in range(41)]
        universe[0] = {'ticker': 'alias.AX', 'code': 'T00'}
        calls = []

        def fixture(path, params):
            calls.append((path, params))
            if path == 'search/predictive':
                code = params['searchText']
                return {'data': {'items': [{'symbol': code, 'xidEntity': 100 + int(code[1:])}]}}
            ids = params['entityXids'].split(',')
            if len(ids) == 1:
                raise asx.DiscoveryError('second batch offline')
            return page([], 0)

        records = {entry['ticker']: {'reviewedOn': '2026-11-12'} for entry in universe}
        with tempfile.TemporaryDirectory() as cache, patch.object(asx.ASXClient, 'get_json', side_effect=fixture):
            updates, meta = asx.discover_updates(universe, records, self.now, cache)
        batches = [params for path, params in calls if path == 'markets/announcements']
        self.assertEqual([len(p['entityXids'].split(',')) for p in batches], [40, 1])
        self.assertEqual(meta['counts'], {'current': 40, 'needs_review': 0, 'unavailable': 1})
        self.assertEqual(len(updates), 41)
        self.assertEqual(updates['alias.AX']['status'], 'current')
        self.assertEqual(updates['T40.AX']['status'], 'unavailable')

    def test_invalid_symbol_does_not_make_predictive_network_request(self):
        with tempfile.TemporaryDirectory() as cache, patch.object(asx.ASXClient, 'get_json') as get:
            updates, _ = asx.discover_updates([{'ticker': 'BHP.AX', 'code': 'BHP?'}], {}, self.now, cache)
        self.assertEqual(updates['BHP.AX']['status'], 'unavailable')
        get.assert_not_called()


@unittest.skipUnless(os.environ.get('ASX_LIVE_TESTS') == '1', 'opt-in public ASX HTTP checks')
class LiveTests(unittest.TestCase):
    def test_official_nab_bhp_afi_urllib_lookup_and_bulk_discovery(self):
        client = asx.ASXClient()
        identities = {code: client.lookup_entity(code) for code in ('NAB', 'BHP', 'AFI')}
        self.assertEqual(identities, {'NAB': 204274613, 'BHP': 199003248, 'AFI': 204204764})
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as cache:
            updates, meta = asx.discover_updates([{'ticker': code + '.AX'} for code in identities], {}, now, cache)
        self.assertEqual(len(updates), 3)
        self.assertTrue(meta['complete'], meta)
        self.assertTrue(all(u['status'] == 'needs_review' for u in updates.values()), updates)
        print('ASX live verified HTTP200 identities:', identities,
              'issuer counts:', {ticker: u['announcementCount'] for ticker, u in updates.items()},
              'requests:', meta['requests'])


if __name__ == '__main__':
    unittest.main()
