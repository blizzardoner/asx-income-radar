import unittest
from datetime import date
from dividend_basis import resolve_dividend_basis


class DividendBasisTests(unittest.TestCase):
    def test_usd_disclosure_requires_a_fresh_aud_conversion_not_a_dollar_label_change(self):
        record = {'kind': 'reported', 'periodEnd': '2025-12-31',
                  'announcedOn': '2026-02-01', 'validUntil': '2027-02-01',
                  'dps': 2, 'currency': 'USD', 'sources': ['https://company.example/results']}
        missing = resolve_dividend_basis(record, date(2026, 11, 14))
        self.assertIsNone(missing['annualDpsAud'])
        fx = {'USD/AUD': {'rate': 1.5, 'asOf': '2026-11-13',
                          'source': 'https://finance.yahoo.com/quote/AUD=X/'}}
        result = resolve_dividend_basis(record, date(2026, 11, 14), fx)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['annualDpsAud'], 3)
        self.assertEqual(result['fx']['rate'], 1.5)
        fx['USD/AUD']['asOf'] = '2026-10-01'
        self.assertIsNone(resolve_dividend_basis(record, date(2026, 11, 14), fx)['annualDpsAud'])

    def test_incomplete_or_inconsistent_disclosures_fail_closed(self):
        base = {'kind': 'reported', 'periodEnd': '2026-06-30',
                'announcedOn': '2026-08-01', 'validUntil': '2027-08-01',
                'dps': 1.2, 'currency': 'AUD', 'sources': ['https://company.example/results']}
        for override in [{'sources': []}, {'dps': None}, {'dps': -1}, {'dps': float('nan')},
                         {'kind': 'rolling'}, {'periodEnd': '2027-06-30'},
                         {'announcedOn': 'bad-date'},
                         {'components': [{'label': 'FY26', 'amount': 2}]}]:
            with self.subTest(override=override):
                result = resolve_dividend_basis({**base, **override}, date(2026, 11, 14))
                self.assertNotEqual(result['status'], 'verified')
                self.assertIsNone(result['annualDpsAud'])

    def test_expired_or_not_yet_announced_disclosure_cannot_supply_a_model_yield(self):
        record = {'kind': 'reported', 'periodEnd': '2026-06-30',
                  'announcedOn': '2026-08-01', 'validUntil': '2026-11-13',
                  'dps': 1.2, 'currency': 'AUD', 'sources': ['https://company.example/results']}
        result = resolve_dividend_basis(record, date(2026, 11, 14))
        self.assertEqual(result['status'], 'stale')
        self.assertIsNone(result['annualDpsAud'])
        record['announcedOn'] = '2026-11-15'
        record['validUntil'] = '2027-11-15'
        result = resolve_dividend_basis(record, date(2026, 11, 14))
        self.assertNotEqual(result['status'], 'verified')
        self.assertIsNone(result['annualDpsAud'])

    def test_complete_annual_disclosure_does_not_depend_on_payment_count(self):
        disclosure = {
            'kind': 'reported', 'periodEnd': '2026-06-30',
            'announcedOn': '2026-08-01', 'validUntil': '2027-08-01',
            'dps': 1.20, 'currency': 'AUD', 'sources': ['https://company.example/results'],
            'components': [{'label': f'FY26 Q{n}', 'amount': 0.30} for n in range(1, 5)],
        }
        result = resolve_dividend_basis(disclosure, date(2026, 11, 14))
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['annualDpsAud'], 1.20)

    def test_missing_disclosure_does_not_fall_back_to_rolling_cash(self):
        result = resolve_dividend_basis(None, date(2026, 11, 14))
        self.assertEqual(result['status'], 'missing')
        self.assertIsNone(result['annualDpsAud'])


if __name__ == '__main__':
    unittest.main()
