import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_alerts import build_alerts, evaluate_status


def basis(dps, valid_until='2099-01-01'):
    return {'status': 'verified', 'annualDpsAud': dps, 'currency': 'AUD',
            'announcedOn': '2026-08-01', 'validUntil': valid_until}


class BuildAlertsTests(unittest.TestCase):
    def setUp(self):
        clock = patch('check_alerts.datetime').start()
        self.addCleanup(patch.stopall)
        clock.now.return_value = datetime(2026, 11, 14, 1, tzinfo=timezone.utc)

    def test_cached_verified_foreign_basis_requires_current_positive_fx(self):
        stock = {'ticker': 'TEST.AX', 'name': 'Test', 'quality': 'A',
                 'requiredCashYield': 0.05, 'stabilityFactor': 1, 'payoutCoverage': 1.2}
        for currency in ('USD', 'EUR'):
            for label, fx in (
                ('expired', {'rate': 1.5, 'asOf': '2026-11-06'}),
                ('future', {'rate': 1.5, 'asOf': '2026-11-15'}),
                ('missing date', {'rate': 1.5}),
                ('empty date', {'rate': 1.5, 'asOf': ''}),
                ('invalid date', {'rate': 1.5, 'asOf': 'not-a-date'}),
                ('missing FX', None),
                ('missing rate', {'asOf': '2026-11-14'}),
                ('zero rate', {'rate': 0, 'asOf': '2026-11-14'}),
                ('negative rate', {'rate': -1.5, 'asOf': '2026-11-14'}),
                ('nonfinite rate', {'rate': float('inf'), 'asOf': '2026-11-14'}),
            ):
                with self.subTest(currency=currency, fx=label):
                    market = {'price': 10, 'dataAgeDays': 0, 'marketDate': '2026-11-14',
                              'dividendBasis': {**basis(5), 'currency': currency, 'fx': fx}}
                    self.assertEqual(evaluate_status(stock, market, date(2026, 11, 14)),
                                     ('UNVERIFIED', None, None))
                    alerts, statuses = build_alerts([stock], {'stocks': {'TEST.AX': market}}, {})
                    self.assertEqual(statuses, {'TEST.AX': 'UNVERIFIED'})
                    self.assertEqual(alerts, [])

    def test_foreign_fx_seven_days_old_is_valid_and_aud_needs_no_fx(self):
        stock = {'quality': 'A', 'requiredCashYield': 0.05, 'stabilityFactor': 1, 'payoutCoverage': 1.2}
        for currency in ('AUD', 'USD', 'EUR'):
            with self.subTest(currency=currency):
                dividend_basis = {**basis(5), 'currency': currency}
                if currency != 'AUD':
                    dividend_basis['fx'] = {'rate': 1.5, 'asOf': '2026-11-07'}
                market = {'price': 10, 'dataAgeDays': 0, 'marketDate': '2026-11-14',
                          'dividendBasis': dividend_basis}
                self.assertEqual(evaluate_status(stock, market, date(2026, 11, 14))[0], 'BUY')

    def test_future_market_date_is_stale_and_does_not_alert(self):
        stock = {'ticker': 'TEST.AX', 'name': 'Test', 'quality': 'A',
                 'requiredCashYield': 0.05, 'stabilityFactor': 1, 'payoutCoverage': 1.2}
        market = {'price': 10, 'dataAgeDays': 0, 'marketDate': '2026-11-15', 'dividendBasis': basis(5)}
        self.assertEqual(evaluate_status(stock, market, date(2026, 11, 14)), ('STALE', None, None))
        self.assertEqual(build_alerts([stock], {'stocks': {'TEST.AX': market}}, {}),
                         ([], {'TEST.AX': 'STALE'}))

    def test_missing_or_invalid_market_date_is_stale_and_does_not_alert(self):
        stock = {'ticker': 'TEST.AX', 'name': 'Test', 'quality': 'A',
                 'requiredCashYield': 0.05, 'stabilityFactor': 1, 'payoutCoverage': 1.2}
        for market_date in ({}, {'marketDate': None}, {'marketDate': ''}, {'marketDate': 'not-a-date'}):
            with self.subTest(market_date=market_date):
                market = {'price': 10, 'dataAgeDays': 0, 'dividendBasis': basis(5), **market_date}
                self.assertEqual(evaluate_status(stock, market, date(2026, 11, 14)), ('STALE', None, None))
                self.assertEqual(build_alerts([stock], {'stocks': {'TEST.AX': market}}, {}),
                                 ([], {'TEST.AX': 'STALE'}))

    def test_cached_price_age_is_rechecked_against_decision_date(self):
        stock = {'quality': 'A', 'requiredCashYield': 0.05, 'stabilityFactor': 1, 'payoutCoverage': 1.2}
        market = {'price': 10, 'dataAgeDays': 0, 'marketDate': '2026-11-01', 'dividendBasis': basis(5)}
        self.assertEqual(evaluate_status(stock, market, date(2026, 11, 14))[0], 'STALE')

    def test_expired_or_future_basis_cannot_trigger_an_alert(self):
        stock = {'quality': 'A', 'requiredCashYield': 0.05, 'stabilityFactor': 1, 'payoutCoverage': 1.2}
        market = {'price': 10, 'dataAgeDays': 0, 'marketDate': '2026-11-14', 'dividendBasis': basis(5, '2026-11-13')}
        self.assertEqual(evaluate_status(stock, market, date(2026, 11, 14))[0], 'UNVERIFIED')
        market['dividendBasis'] = {**basis(5), 'announcedOn': '2026-11-15'}
        self.assertEqual(evaluate_status(stock, market, date(2026, 11, 14))[0], 'UNVERIFIED')

    def test_missing_basis_ignores_legacy_override_and_rolling_events(self):
        stock = {'quality': 'A', 'requiredCashYield': 0.05, 'stabilityFactor': 1,
                 'payoutCoverage': 1.2, 'sustainableDpsOverride': 5}
        market = {'price': 10, 'dataAgeDays': 0, 'marketDate': '2026-11-14', 'trailingCashDps': 5, 'annualOrdinaryCashDps': 5}
        status, buy, cash_yield = evaluate_status(stock, market)
        self.assertEqual(status, 'UNVERIFIED')
        self.assertIsNone(buy)
        self.assertIsNone(cash_yield)

    def test_three_rolling_payments_cannot_create_a_false_buy_alert(self):
        stock = {"quality": "A", "requiredCashYield": 0.052,
                 "stabilityFactor": 0.97, "payoutCoverage": 1.15}
        market = {"price": 38.86, "dataAgeDays": 1, 'marketDate': '2026-11-13',
                  "trailingCashDps": 2.55, "annualOrdinaryCashDps": 1.70, 'dividendBasis': basis(1.70)}

        status, buy_price, cash_yield = evaluate_status(stock, market)

        self.assertEqual(status, "WAIT")
        self.assertAlmostEqual(buy_price, 1.70 * 0.97 / 0.052)
        self.assertAlmostEqual(cash_yield, 1.70 * 0.97 / 38.86)

    def test_alerts_when_a_stock_enters_watch_zone(self):
        universe = [{
            "ticker": "TLS.AX",
            "name": "Telstra",
            "quality": "A",
            "requiredCashYield": 0.043,
            "stabilityFactor": 1,
            "payoutCoverage": 1.2,
        }]
        market = {"stocks": {"TLS.AX": {"price": 5.1, "trailingCashDps": 0.21, "dataAgeDays": 1, 'marketDate': '2026-11-13',
                                       'dividendBasis': basis(0.21)}}}

        alerts, statuses = build_alerts(universe, market, {"TLS.AX": "WAIT"})

        self.assertEqual(statuses["TLS.AX"], "WATCH")
        self.assertEqual(len(alerts), 1)
        self.assertIn("TLS", alerts[0])
        self.assertIn("接近买点", alerts[0])


if __name__ == "__main__":
    unittest.main()
