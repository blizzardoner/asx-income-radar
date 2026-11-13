"""Source-backed annual income; never infer a fiscal year from ex-date counts."""
from datetime import date
from math import isfinite, isclose
from urllib.parse import urlparse


def resolve_dividend_basis(disclosure, as_of, fx_rates=None):
    if not disclosure:
        return {'status': 'missing', 'annualDpsAud': None,
                'reason': '尚无已核实的普通年度股息披露'}
    try:
        announced = date.fromisoformat(disclosure['announcedOn'])
        period_end = date.fromisoformat(disclosure['periodEnd'])
        valid_until = date.fromisoformat(disclosure['validUntil'])
        dps = disclosure['dps']
        sources = disclosure.get('sources', [])
        if (disclosure.get('kind') not in ('reported', 'guidance')
                or not isinstance(dps, (int, float)) or isinstance(dps, bool)
                or not isfinite(dps) or dps < 0
                or not sources or any(urlparse(url).scheme != 'https' or not urlparse(url).netloc for url in sources)
                or valid_until < announced
                or (disclosure['kind'] == 'reported' and period_end > announced)):
            raise ValueError('Incomplete ordinary annual disclosure')
        components = disclosure.get('components')
        if components is not None and not isclose(sum(c['amount'] for c in components), dps, abs_tol=0.000001):
            raise ValueError('Components do not reconcile to annual DPS')
    except (KeyError, ValueError, TypeError):
        return {**disclosure, 'status': 'invalid', 'annualDpsAud': None,
                'reason': '普通年度股息披露缺失、金额或期间无法核实'}
    if valid_until < as_of:
        return {**disclosure, 'status': 'stale', 'annualDpsAud': None,
                'reason': '普通年度股息依据已超过复核有效期'}
    if announced > as_of:
        return {**disclosure, 'status': 'invalid', 'annualDpsAud': None,
                'reason': '披露尚未公布'}
    currency = disclosure.get('currency')
    if currency == 'AUD':
        return {**disclosure, 'status': 'verified', 'annualDpsAud': dps}
    fx = (fx_rates or {}).get(f'{currency}/AUD')
    try:
        age = (as_of - date.fromisoformat(fx['asOf'])).days
        rate = fx['rate']
        if age < 0 or age > 7 or not isfinite(rate) or rate <= 0:
            raise ValueError('Invalid or stale FX quote')
    except (TypeError, KeyError, ValueError):
        return {**disclosure, 'status': 'missing_fx', 'annualDpsAud': None,
                'reason': f'{currency}股息缺少有效澳元汇率，不能直接当作AUD'}
    return {**disclosure, 'status': 'verified', 'annualDpsAud': round(dps * rate, 6), 'fx': fx}
