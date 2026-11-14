"""Official VAS physical holdings are an explicitly dated proxy, not index membership."""
import hashlib
import json
import re
import urllib.request
from datetime import date
from math import isfinite

VAS_URL = 'https://www.vanguard.com.au/personal/api/data/products/holdings-download/8205'


def parse_vas_holdings(payload, core, as_of, source_sha256):
    rows = payload['data']
    if not isinstance(rows, list) or not rows:
        raise ValueError('Missing VAS holdings data')
    dates = {row.get('effectiveDate') for row in rows}
    if len(dates) != 1:
        raise ValueError('VAS holdings have ambiguous effective dates')
    holding_date = date.fromisoformat(next(iter(dates)))
    if not 0 <= (as_of - holding_date).days <= 120:
        raise ValueError('VAS holdings date is future or over 120 days old')
    known = {row['ticker']: row for row in core}
    stocks, seen, excluded = [], set(), 0
    for row in rows:
        weight = row.get('marketValPercent')
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) or not isfinite(weight) or weight < 0:
            raise ValueError('Invalid VAS holding weight')
        if weight == 0:
            excluded += 1
            continue
        symbol = row.get('ticker')
        if not isinstance(symbol, str) or not re.fullmatch(r'[A-Z0-9]{3,8}', symbol):
            raise ValueError('Positive VAS holding has unsupported/missing ticker')
        if symbol in seen:
            raise ValueError('Duplicate VAS ticker')
        seen.add(symbol)
        ticker = symbol + '.AX'
        stock = {**known.get(ticker, {}), 'ticker': ticker, 'sourceTicker': symbol,
                 'name': row.get('name') or symbol, 'sector': row.get('sectorName') or 'Unknown',
                 'type': known.get(ticker, {}).get('type', 'ASX listed'),
                 'isCore': ticker in known, 'isProxyHolding': True, 'holdingWeight': weight}
        stock.pop('frankingFraction', None)  # Legacy assumptions are not tax evidence.
        stocks.append(stock)
    if not stocks:
        raise ValueError('No positive VAS holdings')
    for ticker, original in known.items():
        if ticker.removesuffix('.AX') not in seen:
            stock = {**original, 'isCore': True, 'isProxyHolding': False, 'holdingWeight': None}
            stock.pop('frankingFraction', None)
            stocks.append(stock)
    holding_count = len(seen)
    return stocks, {'kind': 'vas_proxy', 'name': 'Vanguard VAS 官方持仓代理',
                    'sourceUrl': VAS_URL, 'asOf': holding_date.isoformat(),
                    'sourceSha256': source_sha256, 'rawRows': len(rows),
                    'holdingCount': holding_count, 'watchOnlyCount': len(stocks) - holding_count,
                    'excludedRows': excluded,
                    'difference': 'VAS基金实物持仓并非S&P/ASX 300官方成分；日期、数量及公司行动处理可能不同。仅保留正权重具名持仓，不裁成300只；保留原始代码，不猜别名。'}


def fetch_vas_universe(core, now):
    request = urllib.request.Request(VAS_URL, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    stocks, meta = parse_vas_holdings(json.loads(raw), core, now.date(), hashlib.sha256(raw).hexdigest())
    if not 200 <= meta['holdingCount'] <= 450:
        raise ValueError('Unexpected VAS proxy size; source review required')
    meta['retrievedAt'] = now.isoformat()
    return stocks, meta
