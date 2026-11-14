import unittest
from datetime import datetime, timezone, timedelta
from screening_metrics import build_screening_metrics


class ScreeningMetricsTests(unittest.TestCase):
    def liquidity_payload(self, days, quote_day):
        return {'chart': {'result': [{
            'meta': {'symbol': 'MFG.AX', 'currency': 'AUD', 'gmtoffset': 39600,
                     'regularMarketPrice': 10, 'regularMarketTime': int(quote_day.timestamp())},
            'timestamp': [int(day.timestamp()) for day in days],
            'indicators': {'quote': [{'close': [10] * len(days), 'volume': [1000] * len(days)}]},
        }]}}

    def test_old_quote_cannot_make_old_turnover_recent(self):
        days = [datetime(2020, 9, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(60)]
        result = build_screening_metrics(self.liquidity_payload(days, days[-1]),
                                         datetime(2026, 11, 14, tzinfo=timezone.utc))
        self.assertIsNone(result['averageDailyValue'])
        self.assertEqual(result['liquiditySessions'], 0)

    def test_liquidity_90_day_boundary_and_20_session_minimum_use_as_of(self):
        now = datetime(2026, 11, 14, tzinfo=timezone.utc)
        quote_day = now - timedelta(days=15)
        # Nineteen recent sessions plus the inclusive 90-day boundary.
        days = [now - timedelta(days=i) for i in range(15, 34)] + [now - timedelta(days=90)]
        result = build_screening_metrics(self.liquidity_payload(days, quote_day), now)
        self.assertEqual(result['liquiditySessions'], 20)
        self.assertEqual(result['averageDailyValue'], 10000)
        days[-1] = now - timedelta(days=91)
        result = build_screening_metrics(self.liquidity_payload(days, quote_day), now)
        self.assertEqual(result['liquiditySessions'], 19)
        self.assertIsNone(result['averageDailyValue'])

    def test_future_bars_cannot_inflate_liquidity_past_as_of_or_actual_quote(self):
        now = datetime(2026, 11, 14, tzinfo=timezone.utc)
        for quote_day in (now - timedelta(days=15), now + timedelta(days=2)):
            with self.subTest(quote_day=quote_day):
                end = min(now, quote_day)
                days = [end - timedelta(days=i) for i in range(19)]
                # Neither after-quote bars nor future bars may qualify session 20.
                days += [end + timedelta(days=i) for i in (1, 2)]
                result = build_screening_metrics(self.liquidity_payload(days, quote_day), now)
                self.assertEqual(result['liquiditySessions'], 19)
                self.assertIsNone(result['averageDailyValue'])

    def test_recent_stale_mfg_quote_retains_only_recent_sessions(self):
        now = datetime(2026, 11, 14, tzinfo=timezone.utc)
        quote_day = datetime(2026, 10, 30, tzinfo=timezone.utc)
        days = []
        day = quote_day
        while len(days) < 60:
            if day.weekday() < 5:
                days.append(day)
            day -= timedelta(days=1)
        result = build_screening_metrics(self.liquidity_payload(days, quote_day), now)
        self.assertEqual(result['liquiditySessions'], 55)
        self.assertEqual(result['averageDailyValue'], 10000)

    def test_old_or_nonfinite_turnover_is_not_presented_as_recent_liquidity(self):
        days = [int((datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)).timestamp()) for i in range(60)]
        payload = {'chart': {'result': [{
            'meta': {'regularMarketPrice': 10, 'regularMarketTime': 1794524400},
            'timestamp': days, 'indicators': {'quote': [{'close': [10] * 60, 'volume': [100] * 60}]},
        }]}}
        result = build_screening_metrics(payload, datetime(2026, 11, 14, tzinfo=timezone.utc))
        self.assertIsNone(result['averageDailyValue'])

    def test_paid_years_count_complete_calendar_history_not_quarterly_payment_count(self):
        days = []
        day = datetime(2021, 7, 1, tzinfo=timezone.utc)
        while day.year <= 2025:
            if day.weekday() < 5:
                days.append(int(day.timestamp()))
            day += timedelta(days=1)
        day = datetime(2026, 9, 1, tzinfo=timezone.utc)
        while day <= datetime(2026, 11, 13, tzinfo=timezone.utc):
            if day.weekday() < 5:
                days.append(int(day.timestamp()))
            day += timedelta(days=1)
        dividends = {str(y): {'date': int(datetime(y, 12, 15, tzinfo=timezone.utc).timestamp()), 'amount': 0.3}
                     for y in range(2021, 2025)}
        for m in [3, 6, 9, 12]:
            stamp = int(datetime(2025, m, 15, tzinfo=timezone.utc).timestamp())
            dividends[str(stamp)] = {'date': stamp, 'amount': 0.075}
        payload = {'chart': {'result': [{
            'meta': {'regularMarketPrice': 10, 'regularMarketTime': 1794524400},
            'timestamp': days, 'indicators': {'quote': [{'close': [10] * len(days), 'volume': [100] * len(days)}]},
            'events': {'dividends': dividends},
        }]}}
        result = build_screening_metrics(payload, datetime(2026, 11, 14, tzinfo=timezone.utc))
        self.assertEqual(result.get('paidYears'), 4)
        self.assertEqual(result['coveredYears'], 4)
        self.assertFalse(result['annualCashDividends'][0]['complete'])
        self.assertAlmostEqual(result['annualCashDividends'][-1]['dps'], 0.30)
        self.assertEqual(result['averageDailyValue'], 1000)

    def test_history_yield_is_labelled_cash_observed_not_ordinary_or_sustainable(self):
        payload = {'chart': {'result': [{
            'meta': {'regularMarketPrice': 10, 'regularMarketTime': 1794524400},
            'timestamp': [1794438000, 1794524400, 1794528000],
            'indicators': {'quote': [{'close': [9, 10, 10], 'volume': [100, 200, 200]}]},
            'events': {'dividends': {'ordinary': {'date': 1778112000, 'amount': 0.5},
                                     'special': {'date': 1794265200, 'amount': 1.0}}},
        }]}}
        metrics = build_screening_metrics(payload, datetime(2026, 11, 14, tzinfo=timezone.utc))
        self.assertAlmostEqual(metrics['historicalCashYield'], 0.15)
        self.assertNotIn('sustainableDps', metrics)
        self.assertNotIn('ordinaryDps', metrics)
        self.assertEqual(metrics['liquiditySessions'], 2)
        self.assertIsNone(metrics['averageDailyValue'])


if __name__ == '__main__':
    unittest.main()
