import unittest
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_market_data import summarize_chart, update_market_data, apply_disclosure_update, fetch_chart


class FetchChartTests(unittest.TestCase):
    def payload(self, ticker='NAB.AX'):
        return {'chart': {'result': [{'meta': {
            'symbol': ticker, 'regularMarketPrice': 40.1, 'regularMarketTime': 1794524400,
            'currency': 'AUD', 'gmtoffset': 39600}, 'timestamp': [1794524400],
            'indicators': {'quote': [{'close': [40.1], 'high': [40.5], 'low': [39.9], 'volume': [1000]}]}}],
            'error': None}}

    def malformed_payloads(self):
        cases = [None, {}, {'chart': {'result': []}}, {'chart': {'result': [None]}}]
        for field, value in (('regularMarketPrice', None), ('regularMarketPrice', True),
                             ('regularMarketTime', '1794524400')):
            payload = self.payload()
            payload['chart']['result'][0]['meta'][field] = value
            cases.append(payload)
        for fields in ({'timestamp': 'not-an-array'}, {'indicators': {'quote': [None]}},
                       {'indicators': {'quote': [{'close': []}]}}):
            payload = self.payload()
            payload['chart']['result'][0].update(fields)
            cases.append(payload)
        payload = self.payload()
        payload['chart']['error'] = {'code': 'Bad Request'}
        cases.append(payload)
        return cases

    def test_malformed_cache_payloads_refetch_instead_of_hit_or_crash(self):
        import io
        for index, payload in enumerate(self.malformed_payloads()):
            with self.subTest(case=index), tempfile.TemporaryDirectory() as tmp:
                cache = Path(tmp) / 'charts/NAB.AX.json'
                cache.parent.mkdir()
                cache.write_text(json.dumps({'retrievedAt': datetime.now(timezone.utc).isoformat(),
                                             'payload': payload}), encoding='utf-8')
                with patch('update_market_data.CACHE_DIR', Path(tmp)), \
                        patch('update_market_data.time.sleep'), \
                        patch('update_market_data.urllib.request.urlopen',
                              return_value=io.StringIO(json.dumps(self.payload()))) as request:
                    self.assertEqual(fetch_chart('NAB.AX'), self.payload())
                    request.assert_called_once()
                self.assertEqual(json.loads(cache.read_text())['payload'], self.payload())

    def test_malformed_downloads_are_not_cached_or_returned(self):
        import io
        for index, payload in enumerate(self.malformed_payloads()):
            with self.subTest(case=index), tempfile.TemporaryDirectory() as tmp:
                with patch('update_market_data.CACHE_DIR', Path(tmp)), \
                        patch('update_market_data.time.sleep'), \
                        patch('update_market_data.urllib.request.urlopen',
                              side_effect=lambda *a, **k: io.StringIO(json.dumps(payload))):
                    with self.assertRaises(ValueError):
                        fetch_chart('NAB.AX')
                self.assertFalse((Path(tmp) / 'charts/NAB.AX.json').exists())

    def test_wrong_cached_symbol_is_refetched_and_replaced(self):
        import io
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / 'charts/NAB.AX.json'
            cache.parent.mkdir()
            cache.write_text(json.dumps({'retrievedAt': datetime.now(timezone.utc).isoformat(),
                                         'payload': self.payload('BHP.AX')}), encoding='utf-8')
            with patch('update_market_data.CACHE_DIR', Path(tmp)), \
                    patch('update_market_data.time.sleep'), \
                    patch('update_market_data.urllib.request.urlopen',
                          return_value=io.StringIO(json.dumps(self.payload()))) as request:
                self.assertEqual(fetch_chart('NAB.AX'), self.payload())
                request.assert_called_once()
            self.assertEqual(json.loads(cache.read_text())['payload'], self.payload())

    def test_valid_cached_equity_and_fx_have_exact_requested_identity(self):
        from urllib.parse import quote
        for ticker in ('NAB.AX', 'AUD=X'):
            with self.subTest(ticker=ticker), tempfile.TemporaryDirectory() as tmp:
                cache = Path(tmp) / 'charts' / (quote(ticker, safe='') + '.json')
                cache.parent.mkdir()
                cache.write_text(json.dumps({'retrievedAt': datetime.now(timezone.utc).isoformat(),
                                             'payload': self.payload(ticker)}), encoding='utf-8')
                with patch('update_market_data.CACHE_DIR', Path(tmp)), \
                        patch('update_market_data.urllib.request.urlopen') as request:
                    self.assertEqual(fetch_chart(ticker), self.payload(ticker))
                    request.assert_not_called()

    def test_download_requires_explicit_requested_symbol(self):
        import io
        for symbol in ('BHP.AX', None):
            with self.subTest(symbol=symbol), tempfile.TemporaryDirectory() as tmp:
                payload = self.payload()
                if symbol is None:
                    del payload['chart']['result'][0]['meta']['symbol']
                else:
                    payload['chart']['result'][0]['meta']['symbol'] = symbol
                with patch('update_market_data.CACHE_DIR', Path(tmp)), \
                        patch('update_market_data.time.sleep'), \
                        patch('update_market_data.urllib.request.urlopen',
                              side_effect=lambda *a, **k: io.StringIO(json.dumps(payload))):
                    with self.assertRaises(ValueError):
                        fetch_chart('NAB.AX')
                self.assertFalse((Path(tmp) / 'charts/NAB.AX.json').exists())


class SummarizeChartTests(unittest.TestCase):
    def test_new_relevant_or_failed_poll_invalidates_old_annual_and_tax_basis(self):
        market = {'dividendBasis': {'status': 'verified', 'annualDpsAud': 2.0},
                  'annualOrdinaryCashDps': 2.0, 'franking': {'status': 'verified', 'rate': 1}}
        for status in ('needs_review', 'unavailable'):
            result = apply_disclosure_update(market.copy(), {'status': status, 'checkedAt': '2026-11-14T01:00:00Z'})
            self.assertIsNone(result['annualOrdinaryCashDps'])
            self.assertIsNone(result['dividendBasis']['annualDpsAud'])
            self.assertNotEqual(result['dividendBasis']['status'], 'verified')
            self.assertEqual(result['franking']['status'], 'unknown')

    def test_summarize_includes_historical_screening_and_explicit_unknown_franking(self):
        payload = {'chart': {'result': [{'meta': {'regularMarketPrice': 10, 'regularMarketTime': 1794524400}}]}}
        result = summarize_chart(payload, now=datetime(2026, 11, 14, tzinfo=timezone.utc))
        self.assertIn('annualCashDividends', result['screening'])
        self.assertEqual(result['franking']['status'], 'unknown')

    def test_refresh_uses_all_disclosures_and_shared_currency_quote_without_payment_count(self):
        payload = lambda ticker: {'chart': {'result': [{
            'meta': {'regularMarketPrice': 1.5 if ticker == 'AUD=X' else 10,
                     'regularMarketTime': 1794524400, 'currency': 'AUD', 'gmtoffset': 39600},
        }]}}
        core = [{**s, 'isProxyHolding': True, 'isCore': True} for s in
                json.loads((Path(__file__).resolve().parents[1] / 'data/stock-universe.json').read_text())]
        updates = {s['ticker']: {'status': 'current', 'checkedAt': '2026-11-14T00:00:00Z'} for s in core}
        with tempfile.TemporaryDirectory() as tmp, patch('update_market_data.OUTPUT_PATH', Path(tmp) / 'market.json'), \
                patch('update_market_data.fetch_chart', side_effect=payload), \
                patch('update_market_data.fetch_vas_universe', return_value=(core, {'kind': 'vas_proxy', 'holdingCount': 25})), \
                patch('update_market_data.get_disclosure_updates', return_value=(updates, {'complete': True})):
            count, failures = update_market_data(now=datetime(2026, 11, 14, tzinfo=timezone.utc))
            output = json.loads((Path(tmp) / 'market.json').read_text())
        self.assertEqual(count, 25)
        self.assertEqual(failures, [])
        self.assertEqual(output['stocks']['MQG.AX']['annualOrdinaryCashDps'], 7.0)
        self.assertEqual(output['stocks']['AFI.AX']['annualOrdinaryCashDps'], 0.27)
        self.assertEqual(output['stocks']['BHP.AX']['dividendBasis']['fx']['rate'], 1.5)

    def test_price_changes_do_not_invent_history_and_leap_day_uses_february_28(self):
        stamp = lambda y, m, d: int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())
        payload = {"chart": {"result": [{
            "meta": {"regularMarketPrice": 110, "regularMarketTime": stamp(2024, 2, 29)},
            "timestamp": [stamp(2023, 2, 28), stamp(2024, 2, 28), stamp(2024, 2, 29)],
            "indicators": {"quote": [{"close": [100, 108, 110]}]},
        }]}}
        result = summarize_chart(payload, now=datetime(2024, 3, 1, tzinfo=timezone.utc))
        self.assertEqual(result['priceChanges']['year']['targetDate'], '2023-02-28')
        self.assertEqual(result['priceChanges']['year']['baselineDate'], '2023-02-28')
        self.assertIsNone(result['priceChanges']['week']['percent'])
        self.assertIsNone(result['priceChanges']['week']['baselinePrice'])

    def test_australian_session_dates_cross_utc_midnight_without_merging_days(self):
        stamp = lambda d: int(datetime(2026, 11, d, 23, tzinfo=timezone.utc).timestamp())
        payload = {"chart": {"result": [{
            "meta": {"regularMarketPrice": 110, "regularMarketTime": stamp(12), 'gmtoffset': 39600},
            "timestamp": [stamp(11), stamp(12), stamp(12) + 3600],
            "indicators": {"quote": [{"close": [100, 110, 110]}]},
        }]}}
        result = summarize_chart(payload, now=datetime(2026, 11, 14, tzinfo=timezone.utc))
        self.assertEqual(result['marketDate'], '2026-11-13')
        self.assertEqual(result['priceChanges']['day']['baselineDate'], '2026-11-12')
        self.assertAlmostEqual(result['priceChanges']['day']['percent'], 0.1)

    def test_missing_annual_disclosure_never_infers_income_from_dividend_events(self):
        payload = {"chart": {"result": [{
            "meta": {"regularMarketPrice": 10, "regularMarketTime": 1794524400},
            "events": {"dividends": {'a': {'date': 1794265200, 'amount': 0.5}}},
        }]}}
        result = summarize_chart(payload, now=datetime(2026, 11, 14, tzinfo=timezone.utc))
        self.assertIsNone(result['annualOrdinaryCashDps'])
        self.assertEqual(result['dividendBasis']['status'], 'missing')

    def test_price_periods_use_quote_date_and_prior_close_before_weekend_anniversary(self):
        stamp = lambda y, m, d: int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())
        payload = {"chart": {"result": [{
            "meta": {"regularMarketPrice": 110, "regularMarketTime": stamp(2026, 11, 16)},
            "timestamp": [stamp(2025, 11, 14), stamp(2025, 11, 17),
                          stamp(2026, 11, 9), stamp(2026, 11, 13), stamp(2026, 11, 16)],
            "indicators": {"quote": [{"close": [100, 105, 108, 109, 110]}]},
        }]}}
        result = summarize_chart(payload, now=datetime(2026, 11, 18, tzinfo=timezone.utc))
        changes = result.get("priceChanges", {})
        self.assertEqual(changes.get("week", {}).get("baselineDate"), "2026-11-09")
        self.assertEqual(changes.get("year", {}).get("baselineDate"), "2025-11-14")
        self.assertAlmostEqual(changes["day"]["percent"], 110 / 109 - 1)
        self.assertAlmostEqual(changes["week"]["percent"], 110 / 108 - 1)
        self.assertAlmostEqual(changes["year"]["percent"], 0.10)

    def test_special_dividend_is_cash_but_not_sustainable_ordinary_income(self):
        stamp = lambda m, d: int(datetime(2026, m, d, tzinfo=timezone.utc).timestamp())
        payload = {"chart": {"result": [{
            "meta": {"regularMarketPrice": 20, "regularMarketTime": stamp(11, 13)},
            "events": {"dividends": {
                "interim": {"date": stamp(2, 23), "amount": 0.17},
                "final_with_special": {"date": stamp(8, 17), "amount": 0.62},
            }},
        }]}}

        result = summarize_chart(payload, now=datetime(2026, 11, 14, tzinfo=timezone.utc),
                                 dividend_disclosure={
                                     'kind': 'reported', 'periodEnd': '2026-06-30',
                                     'announcedOn': '2026-08-01', 'validUntil': '2027-08-01',
                                     'dps': 0.69, 'currency': 'AUD',
                                     'sources': ['https://company.example/fy26'],
                                     'components': [{'label': 'FY26 interim ordinary', 'amount': 0.17},
                                                    {'label': 'FY26 final ordinary', 'amount': 0.52}],
                                 })

        self.assertAlmostEqual(result["trailingCashDps"], 0.79)
        self.assertAlmostEqual(result["annualOrdinaryCashDps"], 0.69)

    def test_annual_model_uses_disclosed_fiscal_year_even_when_ex_dates_shift(self):
        stamp = lambda y, m, d: int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())
        payload = {"chart": {"result": [{
            "meta": {"regularMarketPrice": 40, "regularMarketTime": stamp(2026, 11, 10)},
            "events": {"dividends": {
                "previous_final": {"date": stamp(2025, 11, 11), "amount": 0.85},
                "interim": {"date": stamp(2026, 5, 7), "amount": 0.85},
                "final": {"date": stamp(2026, 11, 10), "amount": 0.85},
            }},
        }]}}

        result = summarize_chart(payload, now=datetime(2026, 11, 10, tzinfo=timezone.utc),
                                 dividend_disclosure={
                                     'kind': 'reported', 'periodEnd': '2026-09-30',
                                     'announcedOn': '2026-11-01', 'validUntil': '2027-11-01',
                                     'dps': 1.70, 'currency': 'AUD',
                                     'sources': ['https://company.example/fy26'],
                                 })

        self.assertAlmostEqual(result["trailingCashDps"], 2.55)
        self.assertAlmostEqual(result.get("annualOrdinaryCashDps", 0), 1.70)

    def test_trailing_dividends_use_twelve_calendar_months_and_ignore_future_events(self):
        stamp = lambda y, m, d: int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())
        payload = {"chart": {"result": [{
            "meta": {"regularMarketPrice": 38.86, "regularMarketTime": stamp(2026, 11, 13)},
            "events": {"dividends": {
                "old": {"date": stamp(2025, 11, 11), "amount": 0.85},
                "interim": {"date": stamp(2026, 5, 7), "amount": 0.85},
                "final": {"date": stamp(2026, 11, 10), "amount": 0.85},
                "future": {"date": stamp(2026, 12, 1), "amount": 0.85},
            }},
        }]}}

        result = summarize_chart(payload, now=datetime(2026, 11, 14, tzinfo=timezone.utc))

        self.assertAlmostEqual(result["trailingCashDps"], 1.70)

    def test_daily_change_uses_previous_session_not_range_start_or_duplicate_bar(self):
        day = lambda d: int(datetime(2026, 11, d, tzinfo=timezone.utc).timestamp())
        payload = {"chart": {"result": [{
            "meta": {"regularMarketPrice": 38.86, "regularMarketTime": day(13),
                     "chartPreviousClose": 38.30},
            "timestamp": [day(11), day(12), day(13), day(13) + 3600],
            "indicators": {"quote": [{"close": [38.56, 38.77, 38.86, 38.86]}]},
        }]}}

        result = summarize_chart(payload, now=datetime(2026, 11, 14, tzinfo=timezone.utc))

        self.assertAlmostEqual(result.get("previousClose", 0), 38.77)
        self.assertAlmostEqual(result.get("dailyChange", 0), 0.09)
        self.assertAlmostEqual(result.get("dailyChangePercent", 0), 38.86 / 38.77 - 1)

    def test_builds_current_price_range_and_trailing_dividend(self):
        now = datetime(2026, 11, 8, tzinfo=timezone.utc)
        payload = {
            "chart": {
                "result": [{
                    "meta": {
                        "regularMarketPrice": 10.5,
                        "regularMarketTime": int(datetime(2026, 11, 6, tzinfo=timezone.utc).timestamp()),
                        "currency": "AUD",
                    },
                    "timestamp": [
                        int(datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp()),
                        int(datetime(2026, 11, 6, tzinfo=timezone.utc).timestamp()),
                    ],
                    "indicators": {"quote": [{"high": [12.0, 11.0], "low": [8.0, 9.5], "close": [9.0, 10.5]}]},
                    "events": {"dividends": {
                        "a": {"date": int(datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp()), "amount": 0.30},
                        "b": {"date": int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp()), "amount": 0.40},
                        "old": {"date": int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()), "amount": 1.00},
                    }},
                }],
                "error": None,
            }
        }

        result = summarize_chart(payload, now=now)

        self.assertEqual(result["price"], 10.5)
        self.assertEqual(result["high52w"], 12.0)
        self.assertEqual(result["low52w"], 8.0)
        self.assertAlmostEqual(result["trailingCashDps"], 0.70)
        self.assertEqual(result["marketDate"], "2026-11-06")
        self.assertEqual(result["dataAgeDays"], 2)


if __name__ == "__main__":
    unittest.main()
