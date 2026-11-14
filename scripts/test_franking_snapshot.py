import json
from datetime import date
from pathlib import Path
import unittest
from franking import resolve_franking

ROOT = Path(__file__).resolve().parents[1]


class FrankingSnapshotTests(unittest.TestCase):
    def test_every_reviewed_annual_basis_has_explicit_known_or_unknown_tax_evidence(self):
        annual = json.loads((ROOT / 'data/dividend-disclosures.json').read_text(encoding='utf-8'))['records']
        taxes = json.loads((ROOT / 'data/franking-disclosures.json').read_text(encoding='utf-8'))['records']
        self.assertEqual(set(annual), set(taxes))
        self.assertEqual(len(taxes), 25)
        self.assertEqual(sum(tax['rate'] is not None for tax in taxes.values()), 20)
        self.assertEqual(sum(tax['rate'] is None for tax in taxes.values()), 5)
        for ticker, tax in taxes.items():
            with self.subTest(ticker=ticker):
                self.assertEqual(tax['periodEnd'], annual[ticker]['periodEnd'])
                self.assertTrue(tax['evidence'])
                result = resolve_franking({**annual[ticker], 'franking': tax, 'status': 'verified'},
                                          date.fromisoformat(tax['reviewedOn']))
                self.assertEqual(result['status'], 'unknown' if tax['rate'] is None else 'verified')
                self.assertEqual(result['rate'], tax['rate'])

    def test_corrected_partial_rates_and_actual_zero_are_preserved(self):
        taxes = json.loads((ROOT / 'data/franking-disclosures.json').read_text(encoding='utf-8'))['records']
        self.assertAlmostEqual(taxes['TLS.AX']['rate'], 19 / 21)
        self.assertAlmostEqual(taxes['ANZ.AX']['rate'], .775)
        self.assertEqual(taxes['AGL.AX']['rate'], 1)
        self.assertEqual(taxes['TCL.AX']['rate'], 0)
        self.assertIsNone(taxes['SCG.AX']['rate'])
