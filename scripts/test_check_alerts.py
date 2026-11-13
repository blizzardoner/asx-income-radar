import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_alerts import build_alerts, evaluate_status


class BuildAlertsTests(unittest.TestCase):
    def test_three_rolling_payments_cannot_create_a_false_buy_alert(self):
        stock = {"quality": "A", "requiredCashYield": 0.052,
                 "stabilityFactor": 0.97, "payoutCoverage": 1.15}
        market = {"price": 38.86, "dataAgeDays": 1,
                  "trailingCashDps": 2.55, "annualOrdinaryCashDps": 1.70}

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
        market = {"stocks": {"TLS.AX": {"price": 5.1, "trailingCashDps": 0.21, "dataAgeDays": 1}}}

        alerts, statuses = build_alerts(universe, market, {"TLS.AX": "WAIT"})

        self.assertEqual(statuses["TLS.AX"], "WATCH")
        self.assertEqual(len(alerts), 1)
        self.assertIn("TLS", alerts[0])
        self.assertIn("接近买点", alerts[0])


if __name__ == "__main__":
    unittest.main()
