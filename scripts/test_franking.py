import unittest
from datetime import date
from franking import resolve_franking


class FrankingTests(unittest.TestCase):
    def basis(self, **tax):
        return {'status': 'verified', 'kind': 'reported', 'currency': 'AUD', 'periodEnd': '2026-06-30', 'dps': 1.0,
                'announcedOn': '2026-08-01', 'validUntil': '2027-08-01',
                'franking': {'rate': 0, 'periodEnd': '2026-06-30', 'kind': 'annual_ordinary',
                             'sources': ['https://issuer.example/fy26'], 'evidence': 'Both ordinary payments unfranked',
                             'reviewedOn': '2026-11-14', 'announcedOn': '2026-08-01',
                             'basisKind': 'reported', 'currency': 'AUD',
                             'components': [{'cashDps': 1, 'frankedCashDps': 0, 'frankingFraction': 0,
                                             'currency': 'AUD'}], **tax}}

    def test_real_cba_tax_must_match_annual_currency_kind_and_available_date(self):
        import json
        from copy import deepcopy
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        annual = json.loads((root / 'data/dividend-disclosures.json').read_text(encoding='utf-8'))['records']['CBA.AX']
        tax = json.loads((root / 'data/franking-disclosures.json').read_text(encoding='utf-8'))['records']['CBA.AX']
        for fields in ({'currency': 'USD'}, {'basisKind': 'guidance'}, {'announcedOn': '2027-01-01'},
                       {'currency': None}, {'basisKind': None}, {'announcedOn': None}):
            with self.subTest(fields=fields):
                changed = {**deepcopy(tax), **fields}
                if fields.get('currency') == 'USD':
                    for component in changed['components']:
                        component['currency'] = 'USD'
                result = resolve_franking({**annual, 'status': 'verified', 'franking': changed}, date(2026, 11, 14))
                self.assertEqual(result['status'], 'unknown')
        self.assertEqual(resolve_franking({**annual, 'status': 'verified', 'franking': tax},
                                          date(2026, 11, 14))['status'], 'verified')
        self.assertEqual(resolve_franking(self.basis(announcedOn='2026-11-14'),
                                          date(2026, 11, 14))['status'], 'verified')

    def test_components_require_explicit_matching_currency(self):
        for currency in ('USD', None):
            with self.subTest(currency=currency):
                component = {'cashDps': 1, 'frankedCashDps': 0, 'frankingFraction': 0}
                if currency is not None:
                    component['currency'] = currency
                result = resolve_franking(self.basis(components=[component]), date(2026, 11, 14))
                self.assertEqual(result['status'], 'unknown')

    def test_components_must_reconcile_to_same_annual_cash_and_weighted_franking(self):
        for tax in ({'rate': 1}, {'components': []},
                    {'components': [{'cashDps': .5, 'frankedCashDps': 0, 'frankingFraction': 0, 'currency': 'AUD'}]},
                    {'components': [{'cashDps': 1, 'frankedCashDps': .5, 'frankingFraction': 0, 'currency': 'AUD'}]}):
            with self.subTest(tax=tax):
                self.assertEqual(resolve_franking(self.basis(**tax), date(2026, 11, 14))['status'], 'unknown')

    def test_explicit_verified_zero_is_not_unknown(self):
        result = resolve_franking(self.basis(), date(2026, 11, 14))
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['rate'], 0)

    def test_missing_legacy_latest_period_mismatch_or_invalid_fraction_is_unknown(self):
        cases = [{'status': 'verified', 'frankingFraction': 1},
                 self.basis(kind='latest_payment'), self.basis(periodEnd='2025-06-30'),
                 self.basis(rate=None), self.basis(rate=True), self.basis(rate=float('nan')),
                 self.basis(rate=1.1), self.basis(sources=[]), self.basis(evidence=''),
                 self.basis(reviewedOn='2026-11-15'), self.basis(sources=['javascript:alert(1)'])]
        for basis in cases:
            with self.subTest(basis=basis):
                self.assertEqual(resolve_franking(basis, date(2026, 11, 14))['rate'], None)

    def test_unverified_or_expired_annual_basis_cannot_claim_current_tax_rate(self):
        for fields in ({'status': 'needs_review'}, {'validUntil': '2026-11-13'}, {'announcedOn': '2026-11-15'}):
            with self.subTest(fields=fields):
                result = resolve_franking({**self.basis(rate=.9), **fields}, date(2026, 11, 14))
                self.assertEqual(result['status'], 'unknown')
