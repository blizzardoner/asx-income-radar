#!/usr/bin/env python3
import json
import sys
import urllib.parse
import urllib.request
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path
from dividend_basis import resolve_dividend_basis
from stock_universe import fetch_vas_universe
from screening_metrics import build_screening_metrics
from franking import resolve_franking

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_PATH = ROOT / "data" / "stock-universe.json"
DIVIDEND_PATH = ROOT / "data" / "dividend-disclosures.json"
FRANKING_PATH = ROOT / 'data' / 'franking-disclosures.json'
OUTPUT_PATH = ROOT / "public" / "data" / "market.json"
CACHE_DIR = ROOT / '.cache' / 'asx-income-radar'
_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST = 0.0


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
    if not isfinite(price) or price <= 0 or meta.get('currency', 'AUD') != 'AUD':
        raise ValueError('Invalid price or non-AUD equity quote')
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
        "franking": resolve_franking(basis, as_of),
        "screening": build_screening_metrics(payload, now),
    }


def validate_chart(payload, ticker):
    try:
        chart = payload['chart']
        results = chart['result']
        if chart.get('error') is not None or not isinstance(results, list) or len(results) != 1:
            raise ValueError('Invalid Yahoo chart result')
        result = results[0]
        meta = result['meta']
        symbol = meta.get('symbol')
        if not isinstance(symbol, str) or symbol.upper() != ticker.upper():
            raise ValueError('Yahoo ticker identity mismatch')
        for field in ('regularMarketPrice', 'regularMarketTime'):
            value = meta[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
                raise ValueError('Invalid Yahoo quote metadata')
        timestamps = result['timestamp']
        quotes = result['indicators']['quote']
        if not isinstance(timestamps, list) or not isinstance(quotes, list) or len(quotes) != 1 or not isinstance(quotes[0], dict):
            raise ValueError('Invalid Yahoo chart history')
        for stamp in timestamps:
            if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not isfinite(stamp):
                raise ValueError('Invalid Yahoo chart timestamp')
        for field in ('close', 'high', 'low', 'volume'):
            values = quotes[0].get(field)
            if values is None and field != 'close':
                continue
            if not isinstance(values, list) or len(values) != len(timestamps):
                raise ValueError('Invalid Yahoo chart series')
            if any(value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                         or not isfinite(value)) for value in values):
                raise ValueError('Invalid Yahoo chart observation')
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError('Malformed Yahoo chart payload') from exc


def fetch_chart(ticker):
    global _LAST_REQUEST
    cache_path = CACHE_DIR / 'charts' / (urllib.parse.quote(ticker, safe='') + '.json')
    try:
        cached = json.loads(cache_path.read_text(encoding='utf-8'))
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached['retrievedAt'])).total_seconds()
        if 0 <= age < 7200:
            validate_chart(cached['payload'], ticker)
            return cached['payload']
    except (OSError, ValueError, KeyError, TypeError):
        pass
    query = urllib.parse.urlencode({
        "range": "10y",
        "interval": "1d",
        "events": "div,splits",
    })
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ASX-Income-Radar/1.0"})
    for attempt in range(3):
        try:
            with _REQUEST_LOCK:
                time.sleep(max(0, .2 - (time.monotonic() - _LAST_REQUEST)))
                _LAST_REQUEST = time.monotonic()
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            validate_chart(payload, ticker)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({'retrievedAt': datetime.now(timezone.utc).isoformat(),
                                             'payload': payload}, allow_nan=False), encoding='utf-8')
            return payload
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def get_disclosure_updates(universe, disclosures, now):
    from asx_disclosures import discover_updates
    return discover_updates(universe, disclosures, now, CACHE_DIR / 'disclosures')


def apply_disclosure_update(market, update):
    market['disclosureUpdate'] = update
    if update.get('status') != 'current':
        market['dividendBasis'] = {**market['dividendBasis'], 'status': 'needs_review',
                                   'annualDpsAud': None,
                                   'reason': update.get('reason') or '公告更新待复核；不再沿用旧年度买入依据'}
        market['annualOrdinaryCashDps'] = None
        market['franking'] = {'status': 'unknown', 'rate': None, 'sources': [],
                              'reason': '公告更新尚未复核，不能沿用旧年度抵税比例'}
    return market


def update_market_data(now=None):
    core = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    disclosures = json.loads(DIVIDEND_PATH.read_text(encoding='utf-8'))['records']
    taxes = json.loads(FRANKING_PATH.read_text(encoding='utf-8'))['records']
    disclosures = {ticker: {**record, 'franking': taxes.get(ticker)} for ticker, record in disclosures.items()}
    now = now or datetime.now(timezone.utc)
    universe, universe_meta = fetch_vas_universe(core, now)
    updates, announcement_meta = get_disclosure_updates(universe, disclosures, now)
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
    def collect(stock):
        ticker = stock['ticker']
        market = summarize_chart(fetch_chart(ticker), now=now,
                                 dividend_disclosure=disclosures.get(ticker), fx_rates=fx_rates)
        update = updates.get(ticker, {'status': 'unavailable', 'checkedAt': now.isoformat(),
                                      'reason': '公告查询没有返回该证券的完整覆盖状态'})
        return apply_disclosure_update(market, update)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(collect, stock): stock['ticker'] for stock in universe}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                stocks[ticker] = future.result()
            except Exception as exc:
                failures.append({'ticker': ticker, 'error': str(exc)})

    proxy_tickers = [s['ticker'] for s in universe if s.get('isProxyHolding')]
    coverage = sum(t in stocks for t in proxy_tickers) / len(proxy_tickers) if proxy_tickers else 0
    if coverage < .95:
        raise ValueError(f'Proxy price coverage {coverage:.1%} is below 95%; old artifact not overwritten')

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output = {'schemaVersion': 2, 'updatedAt': now.isoformat(), 'universe': universe_meta,
              'universeStocks': universe, 'announcementDiscovery': announcement_meta,
              'stocks': dict(sorted(stocks.items())), 'failures': sorted(failures, key=lambda x: x['ticker'])}
    temporary = OUTPUT_PATH.with_suffix('.tmp')
    temporary.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(OUTPUT_PATH)
    return len(stocks), failures


if __name__ == "__main__":
    try:
        count, failures = update_market_data()
        print(json.dumps({"updated": count, "failures": failures}, ensure_ascii=False))
        raise SystemExit(1 if failures and count == 0 else 0)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
