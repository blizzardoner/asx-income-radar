"""Observed market statistics for screening, never a forecast of ordinary income."""
from datetime import date, datetime, timedelta, timezone
from math import isfinite


def build_screening_metrics(payload, now):
    result = payload['chart']['result'][0]
    meta = result['meta']
    tz = timezone(timedelta(seconds=meta.get('gmtoffset', 0)))
    as_of = now.astimezone(tz).date()
    market_date = datetime.fromtimestamp(meta['regularMarketTime'], tz).date()
    price = float(meta['regularMarketPrice'])
    if not isfinite(price) or price <= 0:
        raise ValueError('Invalid price for cash-yield screening')
    try:
        cutoff = as_of.replace(year=as_of.year - 1)
    except ValueError:
        cutoff = as_of.replace(year=as_of.year - 1, day=28)
    dividends = result.get('events', {}).get('dividends', {}).values()
    cash = sum(float(d['amount']) for d in dividends
               if cutoff < datetime.fromtimestamp(d['date'], tz).date() <= as_of)
    quote = (result.get('indicators', {}).get('quote') or [{}])[0]
    sessions = {}
    history = {}
    for i, timestamp in enumerate(result.get('timestamp') or []):
        day = datetime.fromtimestamp(timestamp, tz).date()
        close = (quote.get('close') or [])[i] if i < len(quote.get('close') or []) else None
        volume = (quote.get('volume') or [])[i] if i < len(quote.get('volume') or []) else None
        if day <= market_date and close is not None and isfinite(close) and close > 0:
            history[day] = close
        if (0 <= (as_of - day).days <= 90 and day <= market_date
                and close is not None and volume is not None
                and isfinite(close) and isfinite(volume) and close > 0 and volume >= 0):
            sessions[day] = float(close) * float(volume)
    recent = [sessions[day] for day in sorted(sessions)[-60:]]
    annual = []
    all_dividends = result.get('events', {}).get('dividends', {}).values()
    for year in range(as_of.year - 5, as_of.year):
        bars = sorted(day for day in history if day.year == year)
        complete = (len(bars) >= 180 and bars[0] <= date(year, 1, 8)
                    and bars[-1] >= date(year, 12, 24)) if bars else False
        dps = sum(float(d['amount']) for d in all_dividends
                  if datetime.fromtimestamp(d['date'], tz).year == year)
        annual.append({'year': year, 'dps': round(dps, 6), 'complete': complete})
    return {
        'historicalCashYield': cash / price,
        'averageDailyValue': sum(recent) / len(recent) if len(recent) >= 20 else None,
        'liquiditySessions': len(recent),
        'paidYears': sum(row['complete'] and row['dps'] > 0 for row in annual),
        'coveredYears': sum(row['complete'] for row in annual),
        'annualCashDividends': annual,
    }
