#!/usr/bin/env python3
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_PATH = ROOT / "data" / "stock-universe.json"
OUTPUT_PATH = ROOT / "public" / "data" / "market.json"


def summarize_chart(payload, now=None, payments_per_year=2, special_dividends=None):
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
    special_dividends = special_dividends or {}
    ordinary_events = []
    for event in trailing_events:
        ex_date = datetime.fromtimestamp(event["date"], tz=exchange_tz).date().isoformat()
        amount = float(event.get("amount", 0)) - special_dividends.get(ex_date, 0)
        if amount < 0:
            raise ValueError(f"Special dividend exceeds cash amount on {ex_date}")
        if amount > 0:
            ordinary_events.append(amount)
    annual_dps = sum(ordinary_events[-payments_per_year:])

    previous_close = previous_sessions[max(previous_sessions)] if previous_sessions else None
    daily_change = price - previous_close if previous_close else None

    return {
        "price": price,
        "previousClose": previous_close,
        "dailyChange": daily_change,
        "dailyChangePercent": daily_change / previous_close if previous_close else None,
        "currency": meta.get("currency", "AUD"),
        "marketDate": market_date.isoformat(),
        "dataAgeDays": max(0, (now.astimezone(exchange_tz).date() - market_date).days),
        "high52w": max(highs) if highs else None,
        "low52w": min(lows) if lows else None,
        "firstClose52w": closes[0] if closes else None,
        "trailingCashDps": round(trailing_dps, 6),
        "annualOrdinaryCashDps": round(annual_dps, 6),
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


def update_market_data():
    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    stocks = {}
    failures = []
    for stock in universe:
        ticker = stock["ticker"]
        try:
            stocks[ticker] = summarize_chart(
                fetch_chart(ticker), now=now,
                payments_per_year=stock.get("paymentsPerYear", 2),
                special_dividends=stock.get("specialDividends", {}),
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
