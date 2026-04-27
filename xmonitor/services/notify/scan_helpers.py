import datetime
import re

HANDLE_TOKEN_RE = re.compile(r'(?<![\w.])@([A-Za-z0-9_]{1,30})\b')
RESERVED_PROFILE_ROUTES = {'home', 'notifications', 'explore', 'messages', 'compose', 'i'}
PROFILE_STATUS_HREF_RE = re.compile(
    r'^(?:https?://(?:www\.|mobile\.)?(?:x|twitter)\.com)?/([A-Za-z0-9_]+)(?:/((?:status|statuses)/\d+|photo|media|likes|with_replies))?\b',
    flags=re.IGNORECASE,
)
_MONTH_NAME_TO_NUMBER = {
    'jan': 1, 'january': 1,
    'feb': 2, 'february': 2,
    'mar': 3, 'march': 3,
    'apr': 4, 'april': 4,
    'may': 5,
    'jun': 6, 'june': 6,
    'jul': 7, 'july': 7,
    'aug': 8, 'august': 8,
    'sep': 9, 'sept': 9, 'september': 9,
    'oct': 10, 'october': 10,
    'nov': 11, 'november': 11,
    'dec': 12, 'december': 12,
}


def _extract_handle_token(text):
    match = HANDLE_TOKEN_RE.search(str(text or ''))
    return f"@{match.group(1)}" if match else None


def _extract_handle_from_href(href):
    raw = str(href or '').strip()
    if not raw:
        return None
    match = PROFILE_STATUS_HREF_RE.match(raw)
    if not match:
        return None
    username = str(match.group(1) or '').strip()
    if not username or username.lower() in RESERVED_PROFILE_ROUTES:
        return None
    return f'@{username}'


def _age_minutes_from_absolute_date(dt, now_utc):
    age = (now_utc - dt.astimezone(datetime.timezone.utc)).total_seconds() / 60
    return max(age, 0)


def _parse_absolute_notification_date(time_text, now_utc):
    text = str(time_text or '').strip()
    if not text:
        return None

    cn_match = re.search(r'(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日', text)
    if cn_match:
        year = int(cn_match.group(1) or now_utc.year)
        month = int(cn_match.group(2))
        day = int(cn_match.group(3))
        try:
            dt = datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc)
            if cn_match.group(1) is None and dt > now_utc + datetime.timedelta(days=1):
                dt = datetime.datetime(year - 1, month, day, tzinfo=datetime.timezone.utc)
            return _age_minutes_from_absolute_date(dt, now_utc)
        except Exception:
            return None

    en_patterns = (
        r'([A-Za-z]{3,9})\s+(\d{1,2})(?:,\s*(\d{4}))?',
        r'(\d{1,2})\s+([A-Za-z]{3,9})(?:\s+(\d{4}))?',
    )
    for pattern in en_patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        if pattern.startswith('([A-Za-z]'):
            month_name = str(match.group(1) or '').strip().lower()
            day = int(match.group(2))
            year = int(match.group(3) or now_utc.year)
        else:
            day = int(match.group(1))
            month_name = str(match.group(2) or '').strip().lower()
            year = int(match.group(3) or now_utc.year)
        month = _MONTH_NAME_TO_NUMBER.get(month_name, 0)
        if month <= 0:
            continue
        try:
            dt = datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc)
            if match.group(3) is None and dt > now_utc + datetime.timedelta(days=1):
                dt = datetime.datetime(year - 1, month, day, tzinfo=datetime.timezone.utc)
            return _age_minutes_from_absolute_date(dt, now_utc)
        except Exception:
            return None

    numeric_patterns = (
        ('ymd', r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})'),
        ('mdy', r'(\d{1,2})[-/](\d{1,2})(?:[-/](\d{4}))?'),
    )
    for pattern_type, pattern in numeric_patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        if pattern_type == 'ymd':
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            has_year = True
        else:
            month = int(match.group(1))
            day = int(match.group(2))
            year = int(match.group(3) or now_utc.year)
            has_year = bool(match.group(3))
        try:
            dt = datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc)
            if (not has_year) and dt > now_utc + datetime.timedelta(days=1):
                dt = datetime.datetime(year - 1, month, day, tzinfo=datetime.timezone.utc)
            return _age_minutes_from_absolute_date(dt, now_utc)
        except Exception:
            return None
    return None


def parse_notification_age_minutes(article):
    try:
        time_ele = article.ele('tag:time', timeout=0)
        if not time_ele:
            return None
        dt_attr = (time_ele.attr('datetime') or '').strip()
        if dt_attr:
            dt_text = dt_attr.replace('Z', '+00:00')
            dt = datetime.datetime.fromisoformat(dt_text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            age = (now_utc - dt.astimezone(datetime.timezone.utc)).total_seconds() / 60
            return max(age, 0)
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        time_text = (time_ele.text or '').strip().lower()
        if not time_text:
            return None
        if any(k in time_text for k in ['刚刚', 'just now', 'now']):
            return 0
        if any(k in time_text for k in ['昨天', 'yesterday']):
            return 1440
        relative_patterns = (
            (r'(\d+)\s*(?:秒|sec|secs|second|seconds|s)\b', 0),
            (r'(\d+)\s*(?:分|分钟|min|mins|minute|minutes|m)\b', 1),
            (r'(\d+)\s*(?:小时|hr|hrs|hour|hours|h)\b', 60),
            (r'(\d+)\s*(?:天|day|days|d)\b', 1440),
            (r'(\d+)\s*(?:周|week|weeks|w)\b', 10080),
            (r'(\d+)\s*(?:月|个月|month|months|mo)\b', 43200),
            (r'(\d+)\s*(?:年|year|years|y)\b', 525600),
        )
        for pattern, multiplier in relative_patterns:
            match = re.search(pattern, time_text, flags=re.IGNORECASE)
            if not match:
                continue
            num = int(match.group(1)) if match.group(1) else 0
            if multiplier == 0:
                return 0
            return (num if num > 0 else 1) * multiplier
        absolute_age = _parse_absolute_notification_date(time_text, now_utc)
        if absolute_age is not None:
            return absolute_age
    except Exception:
        return None
    return None


def extract_notification_handle(article, article_text):
    try:
        user_ele = article.ele('css:[data-testid="User-Name"]', timeout=0)
        if user_ele:
            user_text = (user_ele.text or '').strip()
            handle = _extract_handle_token(user_text)
            if handle:
                return handle
    except Exception:
        pass
    try:
        links = article.eles('tag:a', timeout=0)
        for link in links:
            href = (link.attr('href') or '').strip()
            handle = _extract_handle_from_href(href)
            if handle:
                return handle
    except Exception:
        pass
    try:
        raw_html = str(article.html or '')
        if raw_html:
            hrefs = re.findall(r'href=[\'"]([^\'"]+)[\'"]', raw_html, flags=re.IGNORECASE)
            for href in hrefs:
                handle = _extract_handle_from_href(href)
                if handle:
                    return handle
    except Exception:
        pass
    return _extract_handle_token(article_text or '')
