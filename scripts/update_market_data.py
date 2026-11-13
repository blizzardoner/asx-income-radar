#!/usr/bin/env python3
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dividend_basis import resolve_dividend_basis

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_PATH = ROOT / "data" / "stock-universe.json"
DIVIDEND_PATH = ROOT / "data" / "dividend-disclosures.json"
OUTPUT_PATH = ROOT / "public" / "data" / "market.json"


def previous_anniversary(day):
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, day=28)


def price_change(price, sessions, target):
    candidates = [day for day in sessions if day <= target and (target - day).days <= 7]
    baseline_date = max(candidates) if candidates else None
    baseline = sessions[baseline_date] if baseline_date else None
    return {
        "targetDate": target.isoformat(),
        "baselineDate": baseline_date.isoformat() if baseline_date else None,
        "baselinePrice": baseline,
        "amount": price - baseline if baseline else None,
        "percent": price / baseline - 1 if baseline else None,
    }


def summarize_chart(payload, now=None, dividend_disclosure=None, fx_rates=None):
    now = now or datetime.now(timezone.utc)
    result = payload["chart"]["result"][0]
    meta = result["meta"]
    market_time = datetime.fromtimestamp(meta["regularMarketTime"], tz=timezone.utc)
    exchange_tz = timezone(timedelta(seconds=meta.get("gmtoffset", 0)))
    market_date = market_time.astimezone(exchange_tz).date()
    price = float(meta["regularMarketPrice"])
    previous_sessions = {}
    as_of = now.astimezone(exchange_tz).date()
    try:
        cutoff = as_of.replace(year=as_of.year - 1)
    except ValueError:  # February 29 has no anniversary in a non-leap year.
        cutoff = as_of.replace(year=as_of.year - 1, day=28)

    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    highs = []
    lows = []
    closes = []
    for index, timestamp in enumerate(timestamps):
        when = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        close = (quote.get("close") or [None] * len(timestamps))[index]
        session_date = when.astimezone(exchange_tz).date()
        if close is not None and session_date < market_date:
            previous_sessions[session_date] = float(close)
        if when < now - timedelta(days=365):
            continue
        high = (quote.get("high") or [None] * len(timestamps))[index]
        low = (quote.get("low") or [None] * len(timestamps))[index]
        if high is not None:
            highs.append(float(high))
        if low is not None:
            lows.append(float(low))
        if close is not None:
            closes.append(float(close))

    dividends = result.get("events", {}).get("dividends", {})
    trailing_events = sorted((
        event
        for event in dividends.values()
        if cutoff < datetime.fromtimestamp(event["date"], tz=exchange_tz).date() <= as_of
    ), key=lambda event: event["date"])
    trailing_dps = sum(float(event.get("amount", 0)) for event in trailing_events)
    basis = resolve_dividend_basis(dividend_disclosure, as_of, fx_rates)

    changes = {
        "day": price_change(price, previous_sessions, market_date - timedelta(days=1)),
        "week": price_change(price, previous_sessions, market_date - timedelta(days=7)),
        "year": price_change(price, previous_sessions, previous_anniversary(market_date)),
    }
    previous_close = changes["day"]["baselinePrice"]
    daily_change = changes["day"]["amount"]

    return {
        "price": price,
        "previousClose": previous_close,
        "dailyChange": daily_change,
        "dailyChangePercent": daily_change / previous_close if previous_close else None,
        "priceChanges": changes,
        "currency": meta.get("currency", "AUD"),
        "exchangeUtcOffset": meta.get("gmtoffset", 0),
        "marketDate": market_date.isoformat(),
        "dataAgeDays": max(0, (now.astimezone(exchange_tz).date() - market_date).days),
        "high52w": max(highs) if highs else None,
        "low52w": min(lows) if lows else None,
        "firstClose52w": closes[0] if closes else None,
        "trailingCashDps": round(trailing_dps, 6),
        "annualOrdinaryCashDps": basis["annualDpsAud"],
        "dividendBasis": basis,
    }


def fetch_chart(ticker):
    query = urllib.parse.urlencode({
        "range": "2y",
        "interval": "1d",
        "events": "div,splits",
    })
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ASX-Income-Radar/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def update_market_data(now=None):
    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    disclosures = json.loads(DIVIDEND_PATH.read_text(encoding='utf-8'))['records']
    now = now or datetime.now(timezone.utc)
    fx_rates = {}
    if any(r.get('currency') == 'USD' for r in disclosures.values()):
        try:
            meta = fetch_chart('AUD=X')['chart']['result'][0]['meta']
            if meta.get('currency') != 'AUD':
                raise ValueError('USD/AUD quote currency mismatch')
            fx_rates['USD/AUD'] = {
                'rate': float(meta['regularMarketPrice']),
                'asOf': datetime.fromtimestamp(meta['regularMarketTime'], timezone.utc).date().isoformat(),
                'source': 'https://finance.yahoo.com/quote/AUD=X/',
            }
        except Exception:
            pass  # Foreign-currency income is explicitly missing_fx, never guessed.
    stocks = {}
    failures = []
    for stock in universe:
        ticker = stock["ticker"]
        try:
            stocks[ticker] = summarize_chart(
                fetch_chart(ticker), now=now,
                dividend_disclosure=disclosures.get(ticker), fx_rates=fx_rates,
            )
        except Exception as exc:
            failures.append({"ticker": ticker, "error": str(exc)})

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps({"updatedAt": now.isoformat(), "stocks": stocks, "failures": failures}, indent=2),
        encoding="utf-8",
    )
    return len(stocks), failures


if __name__ == "__main__":
    try:
        count, failures = update_market_data()
        print(json.dumps({"updated": count, "failures": failures}, ensure_ascii=False))
        raise SystemExit(1 if failures and count == 0 else 0)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
