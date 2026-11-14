import unittest
from datetime import date
from stock_universe import parse_vas_holdings


class StockUniverseTests(unittest.TestCase):
    def test_proxy_keeps_real_count_symbols_and_core_watch_only_separate(self):
        rows = [dict(ticker=t, name=t, sectorName='Banks', marketValPercent=w,
                     effectiveDate='2026-09-30')
                for t, w in [('BHP', 10), ('NAB', 3), ('SGLLV', .02), ('ZERO', 0), (None, 0)]]
        core = [{'ticker': 'NAB.AX', 'name': 'NAB', 'quality': 'A', 'frankingFraction': 1},
                {'ticker': 'AFI.AX', 'name': 'AFI', 'quality': 'A'}]
        stocks, meta = parse_vas_holdings({'data': rows}, core, date(2026, 11, 14), 'raw-sha')
        self.assertEqual(len(stocks), 4)
        self.assertEqual(meta['holdingCount'], 3)
        self.assertEqual(meta['watchOnlyCount'], 1)
        self.assertEqual(meta['excludedRows'], 2)
        self.assertEqual(meta['asOf'], '2026-09-30')
        self.assertEqual(meta['kind'], 'vas_proxy')
        self.assertEqual(meta['sourceSha256'], 'raw-sha')
        self.assertEqual(stocks[2]['ticker'], 'SGLLV.AX')
        self.assertEqual(stocks[2]['sourceTicker'], 'SGLLV')
        self.assertTrue(stocks[1]['isCore'])
        self.assertFalse(stocks[-1]['isProxyHolding'])
        self.assertNotIn('frankingFraction', stocks[1])

    def test_ambiguous_stale_future_or_duplicate_holdings_fail_closed(self):
        row = dict(ticker='BHP', name='BHP', marketValPercent=1, effectiveDate='2026-09-30')
        for rows in ([row, row], [dict(row, effectiveDate='2027-01-01')],
                     [dict(row, effectiveDate='2025-01-01')],
                     [row, dict(row, ticker='NAB', effectiveDate='2026-08-31')],
                     [dict(row, ticker=None)], [dict(row, marketValPercent=float('nan'))]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                parse_vas_holdings({'data': rows}, [], date(2026, 11, 14), 'sha')
