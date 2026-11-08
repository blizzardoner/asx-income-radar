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


def summarize_chart(payload, now=None):
    now = now or datetime.now(timezone.utc)
    result = payload["chart"]["result"][0]
    meta = result["meta"]
    market_time = datetime.fromtimestamp(meta["regularMarketTime"], tz=timezone.utc)
    cutoff = now - timedelta(days=370)

    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    highs = []
    lows = []
    closes = []
    for index, timestamp in enumerate(timestamps):
        when = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        if when < now - timedelta(days=365):
            continue
        high = (quote.get("high") or [None] * len(timestamps))[index]
        low = (quote.get("low") or [None] * len(timestamps))[index]
        close = (quote.get("close") or [None] * len(timestamps))[index]
        if high is not None:
            highs.append(float(high))
        if low is not None:
            lows.append(float(low))
        if close is not None:
            closes.append(float(close))

    dividends = result.get("events", {}).get("dividends", {})
    trailing_dps = sum(
        float(event.get("amount", 0))
        for event in dividends.values()
        if datetime.fromtimestamp(event["date"], tz=timezone.utc) >= cutoff
    )

    return {
        "price": float(meta["regularMarketPrice"]),
        "currency": meta.get("currency", "AUD"),
        "marketDate": market_time.date().isoformat(),
        "dataAgeDays": max(0, (now.date() - market_time.date()).days),
        "high52w": max(highs) if highs else None,
        "low52w": min(lows) if lows else None,
        "firstClose52w": closes[0] if closes else None,
        "trailingCashDps": round(trailing_dps, 6),
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
            stocks[ticker] = summarize_chart(fetch_chart(ticker), now=now)
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
