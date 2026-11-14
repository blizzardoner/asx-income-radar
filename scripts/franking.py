"""Unknown franking is not 0%; only reviewed, matching annual evidence is usable."""
from datetime import date
from math import isfinite, isclose
from urllib.parse import urlparse


def resolve_franking(basis, as_of):
    unknown = {'status': 'unknown', 'rate': None, 'sources': [],
               'reason': '未核实该普通年度股息的加权franking rate；未知不等于0%'}
    try:
        tax = basis['franking']
        rate = tax['rate']
        sources = tax['sources']
        if (basis.get('status') != 'verified'
                or not date.fromisoformat(basis['announcedOn']) <= as_of <= date.fromisoformat(basis['validUntil'])
                or date.fromisoformat(tax['reviewedOn']) > as_of
                or date.fromisoformat(tax['announcedOn']) > as_of
                or tax['currency'] != basis['currency']
                or tax['basisKind'] != basis['kind']
                or tax['kind'] != 'annual_ordinary' or tax['periodEnd'] != basis['periodEnd']
                or isinstance(rate, bool) or not isinstance(rate, (int, float)) or not isfinite(rate) or not 0 <= rate <= 1
                or not tax.get('evidence') or not sources
                or any(urlparse(url).scheme != 'https' or not urlparse(url).netloc for url in sources)):
            return unknown
    except (KeyError, TypeError, ValueError):
        return unknown
    try:
        parts = tax['components']
        total, franked = 0.0, 0.0
        if not parts:
            return unknown
        for component in parts:
            cash, creditable, fraction = (component['cashDps'], component['frankedCashDps'], component['frankingFraction'])
            if (component['currency'] != tax['currency']
                    or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x)
                    for x in (cash, creditable, fraction))
                    or cash < 0 or not 0 <= creditable <= cash or not 0 <= fraction <= 1
                    or not isclose(cash * fraction, creditable, abs_tol=.000001)):
                return unknown
            total += cash
            franked += creditable
        if total <= 0 or not isclose(total, basis['dps'], abs_tol=.000001) or not isclose(franked / total, rate, abs_tol=.000001):
            return unknown
    except (KeyError, TypeError, ValueError):
        return unknown
    return {**tax, 'status': 'verified'}
