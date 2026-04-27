import re


USER_STATUS_URL_RE = re.compile(
    r'(?:https?://)?(?:www\.|mobile\.)?(?:x|twitter)\.com/([A-Za-z0-9_]+)/(?:status|statuses)/(\d{6,80})',
    flags=re.IGNORECASE,
)
USER_STATUS_PATH_RE = re.compile(r'^/([A-Za-z0-9_]+)/(?:status|statuses)/(\d{6,80})', flags=re.IGNORECASE)
GENERIC_STATUS_RE = re.compile(r'/(?:i/(?:web/)?status|web/status)/(\d{6,80})', flags=re.IGNORECASE)
ANY_STATUS_PATH_RE = re.compile(r'/(?:status|statuses)/(\d{6,80})', flags=re.IGNORECASE)
QUERY_STATUS_ID_RE = re.compile(r'(?:status_id|conversation_id)=(\d{6,80})', flags=re.IGNORECASE)


def _safe_pick_status_id(pick_best_status_id_fn, *parts):
    try:
        return pick_best_status_id_fn(*parts)
    except TypeError:
        for part in parts:
            try:
                value = pick_best_status_id_fn(part)
            except TypeError:
                continue
            if value:
                return value
        raise


def extract_status_id_candidates(raw_text, *, normalize_status_id_digits_fn):
    raw = str(raw_text or '')
    if not raw:
        return []
    candidates = []
    patterns = (
        ANY_STATUS_PATH_RE,
        QUERY_STATUS_ID_RE,
        re.compile(r'(?<!\d)(\d{15,80})(?!\d)'),
    )
    for pattern in patterns:
        for match in pattern.findall(raw):
            sid = normalize_status_id_digits_fn(match)
            if sid:
                candidates.append(sid)
    return candidates


def extract_status_link_parts(raw_url, *, pick_best_status_id_fn):
    raw = str(raw_url or '').strip()
    if not raw:
        return None, None
    match = GENERIC_STATUS_RE.search(raw)
    if match:
        sid = _safe_pick_status_id(pick_best_status_id_fn, match.group(1), raw)
        if sid:
            return None, sid
    user_matches = list(USER_STATUS_URL_RE.finditer(raw))
    if not user_matches:
        path_match = USER_STATUS_PATH_RE.search(raw)
        if path_match:
            user_matches = [path_match]
    if user_matches:
        best = None
        best_len = -1
        for match in user_matches:
            uname = str(match.group(1) or '').strip().lower()
            if uname in {'i', 'web'}:
                continue
            sid = _safe_pick_status_id(pick_best_status_id_fn, match.group(2), raw)
            if sid and len(sid) > best_len:
                best = (match.group(1), sid)
                best_len = len(sid)
        if best:
            return f'@{best[0]}', best[1]
    match = QUERY_STATUS_ID_RE.search(raw)
    if match:
        sid = _safe_pick_status_id(pick_best_status_id_fn, match.group(1), raw)
        if sid:
            return None, sid
    return None, None


def canonical_status_url(
    raw_url,
    *,
    status_id='',
    status_handle='',
    normalize_handle_fn,
    pick_best_status_id_fn,
):
    raw = str(raw_url or '').strip()
    sid = str(status_id or '').strip() or _safe_pick_status_id(pick_best_status_id_fn, raw)
    handle_norm = normalize_handle_fn(status_handle)
    raw_handle, raw_sid = extract_status_link_parts(raw, pick_best_status_id_fn=pick_best_status_id_fn)
    if raw_sid and not sid:
        sid = raw_sid
    raw_handle_norm = normalize_handle_fn(raw_handle)
    if raw_handle_norm and sid:
        return f'https://x.com/{raw_handle_norm}/status/{sid}'
    if sid and handle_norm:
        return f'https://x.com/{handle_norm}/status/{sid}'
    if sid:
        return f'https://x.com/i/status/{sid}'
    return raw


def status_identity(raw_url, *, pick_best_status_id_fn):
    sid = _safe_pick_status_id(pick_best_status_id_fn, raw_url)
    if sid:
        return f'status:{sid}'
    return str(raw_url or '')


def status_url_quality(raw_url):
    low = str(raw_url or '').lower()
    if re.search(r'https://x\.com/(?!i/)(?!web/)[a-z0-9_]+/status/\d+', low):
        return 2
    if '/i/status/' in low:
        return 1
    return 0


def status_url_priority(raw_url):
    low = str(raw_url or '').lower()
    score = 0
    if '/status/' in low:
        score += 100
    if '/i/status/' in low:
        score += 15
    if '/i/web/status/' in low or '/i/status/' in low or '/web/status/' in low:
        score += 20
    if 'conversation_id=' in low or 'status_id=' in low:
        score += 15
    if low.startswith('https://x.com/') or low.startswith('https://twitter.com/') or low.startswith('https://mobile.twitter.com/'):
        score += 5
    return score
