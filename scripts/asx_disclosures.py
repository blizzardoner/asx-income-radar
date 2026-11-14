"""Official ASX headline discovery (not PDF interpretation or annual renewal).

The anonymous endpoint is used by ASX's own announcements page. Public access
is for personal/noncommercial use; no PDF bodies are downloaded or republished.
"""


from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import random
import re
import tempfile
import threading
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

SYDNEY = ZoneInfo('Australia/Sydney')
API_BASE = 'https://asx.api.cmfyapp.com/asx-research/1.0/'
LOOKBACK_DAYS = 60
BATCH_SIZE = 40
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36',
    'Accept': 'application/json', 'Referer': 'https://www.asx.com.au/',
}
_REQUEST_LOCK = threading.Lock()
_last_request = 0.0


class DiscoveryError(ValueError):
    """The source cannot establish complete, unambiguous coverage."""


class ASXClient:
    """Sequential urllib transport: shared 150ms spacing, 20s timeout, 2 retries."""

    def __init__(self):
        self.request_count = 0

    def get_json(self, path, params):
        global _last_request
        request = Request(API_BASE + path + '?' + urlencode(params), headers=HEADERS)
        for attempt in range(3):
            try:
                # Serialize starts across all clients, including retries.
                with _REQUEST_LOCK:
                    delay = 0.15 - (time.monotonic() - _last_request)
                    if delay > 0:
                        time.sleep(delay)
                    _last_request = time.monotonic()
                    self.request_count += 1
                    response = urlopen(request, timeout=20)
                with response:
                    if response.status != 200:
                        raise OSError('ASX HTTP status ' + str(response.status))
                    raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise DiscoveryError('ASX JSON response exceeds bounded size')
                try:
                    payload = json.loads(raw)
                    if not isinstance(payload, dict) or not isinstance(payload.get('data'), dict):
                        raise ValueError('missing data object')
                except (ValueError, UnicodeError) as exc:
                    raise DiscoveryError('Invalid ASX JSON: ' + str(exc)) from exc
                return payload
            except OSError as exc:
                if attempt == 2:
                    raise DiscoveryError('ASX request failed after 3 attempts: ' + str(exc)) from exc
                time.sleep(0.3 * (2 ** attempt) + random.uniform(0, 0.1))
        raise DiscoveryError('ASX request exhausted')  # defensive; loop raises

    def lookup_entity(self, code):
        try:
            items = self.get_json('search/predictive', {
                'searchText': code, 'useBondsLookup': 'true'})['data']['items']
            if not isinstance(items, list):
                raise DiscoveryError('Missing predictive items list')
            matches = {item['xidEntity'] for item in items
                       if item.get('symbol') == code}
        except (KeyError, TypeError, AttributeError) as exc:
            raise DiscoveryError('Malformed exact symbol lookup: ' + code) from exc
        if len(matches) != 1:
            raise DiscoveryError('Missing or ambiguous exact ASX symbol: ' + code)
        entity = matches.pop()
        if type(entity) is not int or entity <= 0:
            raise DiscoveryError('Invalid ASX entity identity')
        return entity

    def announcements(self, entities, date_start, date_end, page_size=100):
        """Return only a reconciled complete batch; never return partial rows."""
        rows, seen, expected = [], set(), None
        for index in range(200):
            payload = self.get_json('markets/announcements', {
                'entityXids': ','.join(map(str, entities)), 'page': index,
                'itemsPerPage': page_size, 'dateStart': date_start,
                'dateEnd': date_end})
            try:
                data = payload['data']
                count, items = data['count'], data['items']
                if type(count) is not int or count < 0 or not isinstance(items, list):
                    raise DiscoveryError('Invalid announcement count/items')
                if expected is not None and count != expected:
                    raise DiscoveryError('Announcement total changed during pagination')
                expected = count
                if len(items) > page_size:
                    raise DiscoveryError('Announcement page exceeds requested size')
                for item in items:
                    key = item['documentKey']
                    if not isinstance(key, str) or not key or key in seen:
                        raise DiscoveryError('Duplicate or missing announcement documentKey')
                    seen.add(key)
                    rows.append(item)
            except (KeyError, TypeError) as exc:
                raise DiscoveryError('Malformed announcement page') from exc
            if len(rows) > expected:
                raise DiscoveryError('Announcement rows exceed declared total')
            if len(rows) == expected:
                return rows
            if len(items) < page_size:
                raise DiscoveryError('Incomplete announcement page/count mismatch')
        raise DiscoveryError('Announcement pagination exceeds bounded page limit')


def _datetime(value):
    if not isinstance(value, (str, datetime)):
        raise ValueError('Expected ISO timestamp or datetime')
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
    return (parsed.replace(tzinfo=SYDNEY) if parsed.tzinfo is None else parsed).astimezone(SYDNEY)


def _material(item):
    text = ' '.join([item['headline']] + item.get('announcementTypes', [])).lower()
    return bool(item.get('isPriceSensitive') or re.search(
        r'dividend|distribution|guidance|outlook|earnings|profit|results|annual report|financial report|'
        r'half.year|full.year|preliminary final|appendix 4[de]|return.of.capital|'
        r'capital.return|capital.reduction|buy.?back|update|cancel|amend|correct|withdraw|revis', text))


def _batch_rows(rows, batch, start, end, now):
    """Attribute to issuer identities, not secondary mentions (e.g. NAB holdings)."""
    attributed = {ticker: [] for ticker, _, _ in batch}
    for item in rows:
        try:
            if not isinstance(item['headline'], str) or not item['headline'].strip():
                raise DiscoveryError('Missing announcement headline')
            if not isinstance(item['documentKey'], str) or not item['documentKey']:
                raise DiscoveryError('Missing announcement documentKey')
            raw_date = item['date']
            if (not isinstance(raw_date, str)
                    or datetime.fromisoformat(raw_date.replace('Z', '+00:00')).tzinfo is None):
                raise DiscoveryError('Source announcement timestamp must have timezone')
            when = _datetime(raw_date)
            if not start <= when.date() <= end or when > now:
                raise DiscoveryError('Announcement outside requested Sydney date window')
            symbol = item.get('symbol')
            info = item.get('companyInfo', [])
            if not isinstance(info, list) or not all(isinstance(i, dict) for i in info):
                raise DiscoveryError('Invalid announcement companyInfo')
            if not symbol and not any(i.get('symbol') or i.get('xidEntity') for i in info):
                raise DiscoveryError('Announcement issuer identity unavailable')
            for ticker, code, entity in batch:
                if symbol == code or any(i.get('symbol') == code or i.get('xidEntity') == entity for i in info):
                    attributed[ticker].append((when, item))
        except (KeyError, TypeError, ValueError) as exc:
            raise DiscoveryError('Invalid announcement record: ' + str(exc)) from exc
    return attributed


def _status(rows, record, now, start, checked_at):
    relevant = sorted(((when, item) for when, item in rows if _material(item)),
                      key=lambda pair: (pair[0], pair[1]['documentKey']), reverse=True)
    latest = None
    if relevant:
        when, item = relevant[0]
        latest = {'headline': item['headline'], 'date': when.isoformat(),
                  'url': API_BASE + 'file/' + quote(item['documentKey'], safe='') + '&v=undefined',
                  'documentKey': item['documentKey']}
    result = {'status': 'needs_review', 'checkedAt': checked_at,
              'latestRelevant': latest, 'announcementCount': len(rows),
              'reason': 'No reviewed annual disclosure; headline discovery is not verification'}
    if not record or not record.get('reviewedOn'):
        return result
    try:
        reviewed = _datetime(record['reviewedOn'])
        if reviewed > now:
            raise ValueError('review timestamp is in the future')
    except (ValueError, TypeError, AttributeError) as exc:
        return {**result, 'status': 'unavailable', 'reason': 'Invalid reviewedOn: ' + str(exc)}
    date_only = isinstance(record['reviewedOn'], str) and len(record['reviewedOn']) == 10
    if any(when > reviewed or (date_only and when.date() == reviewed.date()) for when, _ in relevant):
        return {**result, 'reason': 'Material ASX announcement after review; manual annual-basis review required'}
    if reviewed.date() < start:
        return {**result, 'status': 'unavailable',
                'reason': 'Review predates complete discovery window; historical gap cannot prove current'}
    return {**result, 'status': 'current',
            'reason': 'Complete ASX window: no material issuer announcement after review; annual expiry unchanged'}


def _atomic_json(path, payload):
    """Same-directory replace; interruption cannot truncate the previous cache."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, allow_nan=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _cached_json(path, warnings):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        warnings.append('Ignoring unreadable cache ' + path.name + ': ' + str(exc))
        return None


def _save_cache(path, value, warnings):
    try:
        _atomic_json(path, value)
    except OSError as exc:
        warnings.append('Cache write failed ' + path.name + ': ' + str(exc))


def discover_updates(universe, disclosures, now, cache_dir):
    """Return (ticker -> update, metadata), never mutate annual disclosure records.

    ``now`` accepts an ISO timestamp or datetime (naive means Sydney). ``code``
    overrides the ticker's .AX-stripped ASX symbol. A date-only reviewedOn has no
    known review time: same-day relevant announcements conservatively need review.
    ``current`` proves discovery coverage only, NOT unexpired annual-model validity.
    Entity cache v2 stores {code: {xidEntity, verifiedAt}}. Only timezone-aware
    verification instants aged 0 through 24 hours inclusive are reusable; legacy,
    invalid, future or expired mappings require a successful exact-symbol lookup.
    Cache reuse never extends verifiedAt, and failed lookup never uses an old ID.
    """
    now = _datetime(now)
    checked = now.isoformat()
    start, end = now.date() - timedelta(days=LOOKBACK_DAYS), now.date()
    # A still-usable annual review can predate the normal discovery window.
    # Fetch back to that review rather than silently leaving a 60-day gap.
    for record in disclosures.values():
        try:
            reviewed_day = _datetime(record['reviewedOn']).date()
            if 0 <= (end - reviewed_day).days <= 400:
                start = min(start, reviewed_day)
        except (KeyError, TypeError, ValueError):
            pass  # The per-record status remains explicitly unavailable.
    client, updates, resolved = ASXClient(), {}, []
    cache = Path(cache_dir)
    warnings, cached_batches = [], 0
    mapping_path = cache / 'asx-entities.json'
    saved = _cached_json(mapping_path, warnings)
    entities_by_code = {}
    if saved is not None:
        try:
            if saved['version'] != 2 or not isinstance(saved['entities'], dict):
                raise ValueError('unsupported entity cache schema')
            for code, mapping in saved['entities'].items():
                try:
                    verified_at = mapping['verifiedAt']
                    if not isinstance(verified_at, str):
                        raise ValueError('missing identity verification timestamp')
                    verified = datetime.fromisoformat(verified_at.replace('Z', '+00:00'))
                    if (not re.fullmatch(r'[A-Z0-9]{1,12}', code)
                            or type(mapping['xidEntity']) is not int or mapping['xidEntity'] <= 0
                            or verified.utcoffset() is None
                            or not timedelta(0) <= now - verified <= timedelta(hours=24)):
                        raise ValueError('invalid or expired entity identity')
                    entities_by_code[code] = mapping
                except (KeyError, TypeError, ValueError, AttributeError):
                    warnings.append('Ignoring invalid or expired cached entity mapping: ' + str(code))
        except (KeyError, TypeError, ValueError):
            warnings.append('Ignoring invalid entity cache schema')
    for entry in universe:
        ticker = entry['ticker']
        code = entry.get('code') or ticker.removesuffix('.AX')
        try:
            if not isinstance(code, str) or not re.fullmatch(r'[A-Z0-9]{1,12}', code):
                raise DiscoveryError('Invalid ASX symbol; explicit code mapping required')
            mapping = entities_by_code.get(code)
            if mapping is None:
                entity = client.lookup_entity(code)
                mapping = {'xidEntity': entity, 'verifiedAt': checked}
                entities_by_code[code] = mapping
            resolved.append((ticker, code, mapping['xidEntity']))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            updates[ticker] = {'status': 'unavailable', 'checkedAt': checked,
                               'latestRelevant': None, 'reason': 'ASX entity lookup failed: ' + str(exc)}
    if entities_by_code:
        _save_cache(mapping_path, {'version': 2, 'entities': entities_by_code}, warnings)
    for offset in range(0, len(resolved), BATCH_SIZE):
        batch = resolved[offset:offset + BATCH_SIZE]
        try:
            entities = sorted(set(entity for _, _, entity in batch))
            identity = json.dumps([1, entities, start.isoformat(), end.isoformat()])
            digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]
            poll_path = cache / ('asx-announcements-' + digest + '.json')
            poll = _cached_json(poll_path, warnings)
            batch_checked, attributed = checked, None
            if poll is not None:
                try:
                    poll_time = _datetime(poll['checkedAt'])
                    rows = poll['rows']
                    if (poll['version'] != 1 or poll['identity'] != identity
                            or poll_time.date() != now.date() or poll_time > now
                            or (now - poll_time).total_seconds() > 1800
                            or type(poll['count']) is not int or poll['count'] != len(rows)
                            or len({r['documentKey'] for r in rows}) != len(rows)):
                        raise DiscoveryError('Invalid or noncurrent daily poll cache')
                    attributed = _batch_rows(rows, batch, start, end, poll_time)
                    batch_checked = poll_time.isoformat()
                    cached_batches += 1
                except (KeyError, ValueError, TypeError, AttributeError) as exc:
                    warnings.append('Ignoring invalid poll cache: ' + str(exc))
            if attributed is None:
                rows = client.announcements(entities, start.isoformat(), end.isoformat())
                attributed = _batch_rows(rows, batch, start, end, now)
                _save_cache(poll_path, {'version': 1, 'identity': identity, 'checkedAt': checked,
                                       'count': len(rows), 'rows': rows}, warnings)
            for ticker, _, _ in batch:
                updates[ticker] = _status(attributed[ticker], disclosures.get(ticker), now, start, batch_checked)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            for ticker, _, _ in batch:
                updates[ticker] = {'status': 'unavailable', 'checkedAt': checked,
                                   'latestRelevant': None, 'reason': 'ASX discovery failed: ' + str(exc)}
    counts = {status: sum(value['status'] == status for value in updates.values())
              for status in ('current', 'needs_review', 'unavailable')}
    oldest_check = min((value['checkedAt'] for value in updates.values()), key=_datetime, default=checked)
    return updates, {'checkedAt': oldest_check, 'queriedAt': checked,
                     'source': API_BASE + 'markets/announcements',
                     'windowStart': start.isoformat(), 'windowEnd': end.isoformat(),
                     'complete': counts['unavailable'] == 0, 'counts': counts,
                     'cachedBatches': cached_batches, 'cacheWarnings': warnings,
                     'requests': client.request_count,
                     'policy': 'Headline discovery only; does not renew or validate annual disclosure expiry'}
