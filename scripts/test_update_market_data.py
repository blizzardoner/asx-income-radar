import unittest
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_market_data import summarize_chart


class SummarizeChartTests(unittest.TestCase):
    def test_universe_separates_verified_specials_and_quarterly_ordinary_guidance(self):
        stocks = {stock["ticker"]: stock for stock in json.loads(
            (Path(__file__).resolve().parents[1] / "data" / "stock-universe.json").read_text())}

        self.assertEqual(stocks["SUN.AX"].get("specialDividends", {}).get("2026-08-17"), 0.10)
        self.assertEqual(stocks["AFI.AX"].get("paymentsPerYear"), 4)
        self.assertEqual(stocks["AFI.AX"]["sustainableDpsOverride"], 0.27)

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
                                 special_dividends={"2026-08-17": 0.10})

        self.assertAlmostEqual(result["trailingCashDps"], 0.79)
        self.assertAlmostEqual(result["annualOrdinaryCashDps"], 0.69)

    def test_annual_model_uses_latest_two_payments_even_when_ex_dates_shift(self):
        stamp = lambda y, m, d: int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())
        payload = {"chart": {"result": [{
            "meta": {"regularMarketPrice": 40, "regularMarketTime": stamp(2026, 11, 10)},
            "events": {"dividends": {
                "previous_final": {"date": stamp(2025, 11, 11), "amount": 0.85},
                "interim": {"date": stamp(2026, 5, 7), "amount": 0.85},
                "final": {"date": stamp(2026, 11, 10), "amount": 0.85},
            }},
        }]}}

        result = summarize_chart(payload, now=datetime(2026, 11, 10, tzinfo=timezone.utc))

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
