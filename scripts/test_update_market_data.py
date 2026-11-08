import unittest
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_market_data import summarize_chart


class SummarizeChartTests(unittest.TestCase):
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
