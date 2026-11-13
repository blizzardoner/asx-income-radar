import json
import unittest
from datetime import date
from pathlib import Path
from dividend_basis import resolve_dividend_basis

ROOT = Path(__file__).resolve().parents[1]


class DisclosureSnapshotTests(unittest.TestCase):
    def test_every_security_has_a_reconciled_source_backed_period_not_a_frequency_default(self):
        universe = json.loads((ROOT / 'data/stock-universe.json').read_text(encoding='utf-8'))
        snapshot = json.loads((ROOT / 'data/dividend-disclosures.json').read_text(encoding='utf-8'))
        records = snapshot['records']
        self.assertEqual(len(records), 25)
        self.assertEqual(set(records), {stock['ticker'] for stock in universe})
        for stock in universe:
            for legacy in ['paymentsPerYear', 'sustainableDpsOverride', 'specialDividends']:
                self.assertNotIn(legacy, stock)
        reviewed = date.fromisoformat(snapshot['reviewedOn'])
        fx = {'USD/AUD': {'rate': 1.5, 'asOf': snapshot['reviewedOn'],
                          'source': 'https://finance.yahoo.com/quote/AUD=X/'}}
        for ticker, record in records.items():
            with self.subTest(ticker=ticker):
                self.assertIn(record['currency'], ['AUD', 'USD'])
                self.assertTrue(record['evidence'])
                self.assertTrue(record['sources'])
                self.assertAlmostEqual(sum(c['amount'] for c in record['components']), record['dps'], places=6)
                self.assertTrue(all(c.get('currency', record['currency']) == record['currency'] for c in record['components']))
                self.assertEqual(resolve_dividend_basis(record, reviewed, fx)['status'], 'verified')
        self.assertEqual(records['AFI.AX']['kind'], 'guidance')
        self.assertEqual(records['MQG.AX']['periodEnd'], '2026-03-31')
        self.assertEqual(records['COL.AX']['periodEnd'], '2026-06-28')


if __name__ == '__main__':
    unittest.main()
