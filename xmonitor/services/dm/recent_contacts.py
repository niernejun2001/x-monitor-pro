import datetime
import json
import random
import re
import threading
import time
import urllib.request
from urllib.parse import urlparse

CHAT_URL = 'https://x.com/i/chat'
DEFAULT_SCAN_LIMIT = 24
DEFAULT_DAILY_HOUR = 9
DEFAULT_DAILY_MINUTE = 0
ENTERPRISE_WECHAT_WEBHOOK_PREFIX = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key='

_RELATIVE_TIME_RE = re.compile(r'(\d+)\s*(秒|分钟|分|小时|天|s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)', re.I)
_HANDLE_RE = re.compile(r'@([A-Za-z0-9_]{1,20})')
_AVATAR_TESTID_PREFIX = 'UserAvatar-Container-'
_RESERVED_PROFILE_PATHS = {
    'compose',
    'explore',
    'home',
    'i',
    'jobs',
    'messages',
    'notifications',
    'search',
    'settings',
}
_CHINESE_CLOCK_RE = re.compile(r'(上午|下午|早上|晚上|中午)?\s*(\d{1,2})[:：](\d{2})')
_EN_CLOCK_RE = re.compile(r'\b(\d{1,2}):(\d{2})\s*(am|pm)?\b', re.I)
_CHINESE_DATE_RE = re.compile(r'(\d{1,2})月(\d{1,2})日')
_MONTH_DATE_RE = re.compile(
    r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+(\d{1,2})\b',
    re.I,
)
_MONTH_MAP = {
    'jan': 1,
    'feb': 2,
    'mar': 3,
    'apr': 4,
    'may': 5,
    'jun': 6,
    'jul': 7,
    'aug': 8,
    'sep': 9,
    'sept': 9,
    'oct': 10,
    'nov': 11,
    'dec': 12,
}


def _normalize_spaces(text):
    return re.sub(r'\s+', ' ', str(text or '').replace('\u200f', ' ').replace('\u200e', ' ')).strip()


def _normalize_handle_value(raw):
    value = str(raw or '').strip()
    if not value:
        return ''
    if value.startswith(_AVATAR_TESTID_PREFIX):
        value = value[len(_AVATAR_TESTID_PREFIX):]
    value = value.strip().lstrip('@')
    if re.fullmatch(r'[A-Za-z0-9_]{1,20}', value):
        return f'@{value}'
    return ''


def _href_path(raw_href):
    href = str(raw_href or '').strip()
    if not href:
        return ''
    try:
        if href.startswith('http://') or href.startswith('https://'):
            parsed = urlparse(href)
            if parsed.netloc and not parsed.netloc.endswith('x.com') and not parsed.netloc.endswith('twitter.com'):
                return ''
            return parsed.path or ''
        return href.split('?', 1)[0].split('#', 1)[0]
    except Exception:
        return ''


def _is_chat_conversation_href(raw_href):
    path = _href_path(raw_href)
    if path.startswith('/messages/'):
        return True
    return bool(re.match(r'^/i/chat/[^/?#]+', path))


def _extract_profile_handle_from_href(raw_href):
    path = _href_path(raw_href)
    if not path or not path.startswith('/'):
        return ''
    parts = [part for part in path.split('/') if part]
    if not parts:
        return ''
    first = parts[0]
    if first.lower() in _RESERVED_PROFILE_PATHS:
        return ''
    return _normalize_handle_value(first)


def _now_text(now_fn=None):
    return (now_fn or datetime.datetime.now)().strftime('%Y-%m-%d %H:%M:%S')


def _empty_result(status='ok', msg='', *, window_hours=24):
    return {
        'status': status,
        'msg': msg,
        'contacts': [],
        'count': 0,
        'copy_text': '',
        'scanned_rows': 0,
        'stale_rows': 0,
        'unknown_time_rows': 0,
        'window_hours': window_hours,
        'source_url': CHAT_URL,
        'captured_at': _now_text(),
    }


def _parse_relative_age_seconds(text):
    raw = _normalize_spaces(text).lower()
    if not raw:
        return None
    if any(word in raw for word in ('刚刚', '刚才', 'now', 'just now')):
        return 0
    if any(word in raw for word in ('昨天', '昨日', 'yesterday')):
        return 24 * 3600
    best = None
    for match in _RELATIVE_TIME_RE.finditer(raw):
        try:
            amount = int(match.group(1))
        except Exception:
            continue
        unit = match.group(2).lower()
        if unit in {'秒', 's', 'sec', 'secs', 'second', 'seconds'}:
            seconds = amount
        elif unit in {'分钟', '分', 'm', 'min', 'mins', 'minute', 'minutes'}:
            seconds = amount * 60
        elif unit in {'小时', 'h', 'hr', 'hrs', 'hour', 'hours'}:
            seconds = amount * 3600
        elif unit in {'天', 'd', 'day', 'days'}:
            seconds = amount * 86400
        else:
            continue
        best = seconds if best is None else min(best, seconds)
    return best


def _parse_iso_age_seconds(raw_value, now):
    value = str(raw_value or '').strip()
    if not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except Exception:
        return None
    try:
        if parsed.tzinfo is not None:
            current = datetime.datetime.now(parsed.tzinfo) if now.tzinfo is None else now.astimezone(parsed.tzinfo)
        else:
            current = now.replace(tzinfo=None)
        return max(0, int((current - parsed).total_seconds()))
    except Exception:
        return None


def _parse_clock_age_seconds(raw_text, now):
    text = _normalize_spaces(raw_text)
    if not text:
        return None

    def _candidate_age(hour, minute):
        try:
            candidate = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
        except Exception:
            return None
        if candidate > now + datetime.timedelta(minutes=5):
            candidate -= datetime.timedelta(days=1)
        return max(0, int((now - candidate).total_seconds()))

    for match in _CHINESE_CLOCK_RE.finditer(text):
        prefix = str(match.group(1) or '')
        hour = int(match.group(2))
        minute = int(match.group(3))
        if prefix in {'下午', '晚上'} and hour < 12:
            hour += 12
        if prefix == '上午' and hour == 12:
            hour = 0
        if prefix == '中午' and hour < 11:
            hour += 12
        age = _candidate_age(hour, minute)
        if age is not None:
            return age

    for match in _EN_CLOCK_RE.finditer(text):
        hour = int(match.group(1))
        minute = int(match.group(2))
        suffix = str(match.group(3) or '').lower()
        if suffix == 'pm' and hour < 12:
            hour += 12
        if suffix == 'am' and hour == 12:
            hour = 0
        age = _candidate_age(hour, minute)
        if age is not None:
            return age
    return None


def _parse_date_age_seconds(raw_text, now):
    text = _normalize_spaces(raw_text)
    if not text:
        return None
    month = day = None
    match = _CHINESE_DATE_RE.search(text)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
    else:
        match = _MONTH_DATE_RE.search(text)
        if match:
            month_key = str(match.group(1) or '').lower()
            month = _MONTH_MAP.get(month_key[:4]) or _MONTH_MAP.get(month_key[:3])
            day = int(match.group(2))
    if not month or not day:
        return None
    try:
        candidate = now.replace(month=month, day=day, hour=0, minute=0, second=0, microsecond=0)
    except Exception:
        return None
    if candidate > now + datetime.timedelta(days=1):
        try:
            candidate = candidate.replace(year=candidate.year - 1)
        except Exception:
            return None
    return max(0, int((now - candidate).total_seconds()))


def _parse_snapshot_age_seconds(snapshot, now_fn=None):
    now = (now_fn or datetime.datetime.now)()
    candidates = []
    if isinstance(snapshot, dict):
        for raw_dt in list(snapshot.get('datetime_attrs') or []):
            age = _parse_iso_age_seconds(raw_dt, now)
            if age is not None:
                candidates.append(age)
        texts = list(snapshot.get('time_texts') or [])
        raw_text = snapshot.get('raw_text', '')
    else:
        texts = []
        raw_text = str(snapshot or '')

    for raw_text_item in [raw_text] + texts:
        rel_age = _parse_relative_age_seconds(raw_text_item)
        if rel_age is not None:
            candidates.append(rel_age)
        clock_age = _parse_clock_age_seconds(raw_text_item, now)
        if clock_age is not None:
            candidates.append(clock_age)
        date_age = _parse_date_age_seconds(raw_text_item, now)
        if date_age is not None:
            candidates.append(date_age)
    if not candidates:
        return None
    return min(candidates)


def _is_within_window(snapshot, *, window_hours=24, now_fn=None):
    age = _parse_snapshot_age_seconds(snapshot, now_fn=now_fn)
    if age is None:
        # X sometimes shows only clock/date text in chat rows. Keep unknown rows so users can inspect them.
        return True, None
    try:
        max_age = max(1, float(window_hours or 24)) * 3600
    except Exception:
        max_age = 24 * 3600
    return age <= max_age, age


def _is_within_24h(text):
    return _is_within_window(text, window_hours=24)


def _extract_contact_from_row_text(text):
    clean = _normalize_spaces(text)
    if not clean:
        return None
    handles = _HANDLE_RE.findall(clean)
    handle = f'@{handles[0]}' if handles else ''
    name = ''
    if handle:
        prefix = clean.split(handle, 1)[0].strip(' ·-–—:：')
        if prefix:
            name = prefix.split('  ')[0].strip()
    if not name:
        parts = re.split(r'\s+[·•]\s+|\s+-\s+|\s+–\s+', clean)
        name = (parts[0] if parts else clean).strip()
        if handle and handle in name:
            name = name.split(handle, 1)[0].strip()
    if not handle:
        return None
    return {'name': name or handle, 'handle': handle, 'raw_text': clean}


def _strip_leading_name_from_chat_text(raw_text):
    lines = [line.strip() for line in str(raw_text or '').splitlines() if line and line.strip()]
    if not lines:
        return ''
    first = _normalize_spaces(lines[0]).strip(' ·-–—:：')
    if not first:
        return ''
    relative_tokens = [
        r'\d+\s*(秒|分钟|分|小时|天|s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)',
        r'刚刚',
        r'刚才',
        r'now',
        r'just now',
        r'昨天',
        r'yesterday',
    ]
    token_re = re.compile(rf'\s+(?:{"|".join(relative_tokens)})(?:\b|(?=\s|$|You:|你:|您:))', re.I)
    match = token_re.search(first)
    if match:
        return first[:match.start()].strip(' ·-–—:：')
    return ''


def _extract_contact_from_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        return _extract_contact_from_row_text(snapshot)

    raw_text = str(snapshot.get('raw_text', '') or '')
    clean = _normalize_spaces(raw_text)
    handles = []
    for href in list(snapshot.get('hrefs') or []):
        handle = _extract_profile_handle_from_href(href)
        if handle and handle not in handles:
            handles.append(handle)
    for raw in list(snapshot.get('avatar_handles') or []):
        handle = _normalize_handle_value(raw)
        if handle and handle not in handles:
            handles.append(handle)
    for match in _HANDLE_RE.findall(clean):
        handle = _normalize_handle_value(match)
        if handle and handle not in handles:
            handles.append(handle)
    handle = handles[0] if handles else ''
    if not handle:
        return None

    name = _strip_leading_name_from_chat_text(raw_text)
    lines = [line.strip() for line in raw_text.splitlines() if line and line.strip()]
    now = datetime.datetime.now()
    if not name:
        for line in lines[:5]:
            normalized_line = _normalize_spaces(line).strip(' ·-–—:：')
            if not normalized_line:
                continue
            if normalized_line == handle:
                continue
            if _parse_relative_age_seconds(normalized_line) is not None:
                continue
            if _parse_clock_age_seconds(normalized_line, now) is not None:
                continue
            name = normalized_line
            break

    if not name and handle in clean:
        prefix = clean.split(handle, 1)[0].strip(' ·-–—:：')
        if prefix:
            name = prefix
    if not name:
        parsed = _extract_contact_from_row_text(clean)
        if parsed:
            name = parsed.get('name') or ''
    return {'name': name or handle, 'handle': handle, 'raw_text': clean}


def _row_identity(row):
    handle = str(row.get('handle', '') or '').strip().lower()
    if handle:
        return handle
    return str(row.get('name', '') or '').strip().lower()


def _collect_dm_rows(tab):
    selectors = [
        'css:[data-testid="conversation"]',
        'css:[data-testid^="dm-conversation-item-"]',
        'css:a[href^="/messages/"]',
        'css:a[href^="/i/chat/"]',
        'css:div[role="link"][data-testid]',
        'css:div[role="button"][data-testid]',
    ]
    rows = []
    for selector in selectors:
        try:
            rows.extend(tab.eles(selector, timeout=0.5) or [])
        except Exception:
            continue
    return rows


def _collect_dm_row_snapshots_from_dom(tab):
    script = r"""
    const isVisible = (el) => {
      if (!el) return false;
      const st = window.getComputedStyle(el);
      if (!st || st.display === 'none' || st.visibility === 'hidden') return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    };
    const avatarPrefix = 'UserAvatar-Container-';
    const roots = [];
    const seenRoots = new Set();
    const isSideNavNode = (el) => {
      return !!(el && el.closest && el.closest('nav, [role="navigation"], [data-testid="SideNav_AccountSwitcher_Button"]'));
    };
    const isMainNode = (el) => {
      return !!(el && el.closest && el.closest('main, [data-testid="primaryColumn"]'));
    };
    const findRowRoot = (el) => {
      if (!isMainNode(el) || isSideNavNode(el)) return null;
      let best = null;
      let node = el;
      for (let depth = 0; depth < 9 && node; depth += 1) {
        if (!isMainNode(node) || isSideNavNode(node)) break;
        if (!isVisible(node)) {
          node = node.parentElement;
          continue;
        }
        const text = String(node.innerText || node.textContent || '').trim();
        const hrefs = Array.from(node.querySelectorAll ? node.querySelectorAll('a[href]') : []).map((a) => String(a.getAttribute('href') || ''));
        const ownHref = String(node.getAttribute ? node.getAttribute('href') || '' : '');
        const avatarCount = node.querySelectorAll ? node.querySelectorAll('[data-testid^="UserAvatar-Container-"]').length : 0;
        const hasMessageLink = ownHref.startsWith('/messages/') || ownHref.startsWith('/i/chat/') || hrefs.some((h) => h.startsWith('/messages/') || h.includes('/messages/') || h.startsWith('/i/chat/') || h.includes('/i/chat/'));
        const isConversation = node.matches && node.matches('[data-testid="conversation"], [data-testid^="dm-conversation-item-"], a[href^="/messages/"], a[href^="/i/chat/"]');
        if (hasMessageLink || isConversation) {
          const textLen = text.length;
          const score =
            (hasMessageLink ? 1000 : 0) +
            (isConversation ? 800 : 0) +
            (avatarCount ? 260 : 0) +
            Math.min(360, textLen) -
            (textLen > 1600 ? 900 : 0);
          if (!best || score > best.score) best = { node, score };
        }
        node = node.parentElement;
      }
      return best ? best.node : el;
    };
    const seeds = Array.from(document.querySelectorAll('main [data-testid="conversation"], main [data-testid^="dm-conversation-item-"], main a[href^="/messages/"], main a[href^="/i/chat/"], [data-testid="primaryColumn"] [data-testid="conversation"], [data-testid="primaryColumn"] [data-testid^="dm-conversation-item-"], [data-testid="primaryColumn"] a[href^="/messages/"], [data-testid="primaryColumn"] a[href^="/i/chat/"]'));
    for (const seed of seeds) {
      const root = findRowRoot(seed);
      if (!root || seenRoots.has(root) || !isVisible(root) || !isMainNode(root) || isSideNavNode(root)) continue;
      seenRoots.add(root);
      roots.push(root);
    }
    const out = [];
    const seenKeys = new Set();
    for (const root of roots) {
      const text = String(root.innerText || root.textContent || '').trim();
      const links = Array.from(root.querySelectorAll ? root.querySelectorAll('a[href]') : []);
      const hrefs = links.map((a) => String(a.getAttribute('href') || '')).filter(Boolean);
      const ownHref = String(root.getAttribute ? root.getAttribute('href') || '' : '');
      if (ownHref) hrefs.unshift(ownHref);
      const avatarHandles = Array.from(root.querySelectorAll ? root.querySelectorAll('[data-testid^="UserAvatar-Container-"]') : [])
        .map((el) => String(el.getAttribute('data-testid') || '').replace(avatarPrefix, ''))
        .filter(Boolean);
      const isConversation = root.matches && root.matches('[data-testid="conversation"], [data-testid^="dm-conversation-item-"], a[href^="/messages/"], a[href^="/i/chat/"]');
      const hasMessageSignal = Boolean(isConversation || hrefs.some((h) => h.startsWith('/messages/') || h.includes('/messages/') || h.startsWith('/i/chat/') || h.includes('/i/chat/')));
      if (!hasMessageSignal) continue;
      if (!text && !avatarHandles.length) continue;
      const times = Array.from(root.querySelectorAll ? root.querySelectorAll('time') : []);
      const timeTexts = times.map((t) => String(t.innerText || t.textContent || '').trim()).filter(Boolean);
      const datetimeAttrs = times.map((t) => String(t.getAttribute('datetime') || '')).filter(Boolean);
      const key = `${avatarHandles.join(',')}|${hrefs.slice(0, 4).join(',')}|${text.slice(0, 180)}`;
      if (seenKeys.has(key)) continue;
      seenKeys.add(key);
      out.push({
        raw_text: text,
        hrefs,
        avatar_handles: avatarHandles,
        is_conversation: hasMessageSignal,
        time_texts: timeTexts,
        datetime_attrs: datetimeAttrs,
      });
      if (out.length >= 120) break;
    }
    return out;
    """
    try:
        rows = tab.run_js(script)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    except Exception:
        return None
    return []


def _collect_dm_row_snapshots_from_elements(tab):
    snapshots = []
    for row in _collect_dm_rows(tab):
        try:
            raw_text = str(getattr(row, 'text', '') or '')
        except Exception:
            raw_text = ''
        avatar_handles = []
        hrefs = []
        time_texts = []
        datetime_attrs = []
        try:
            testid = row.attr('data-testid') or ''
            is_conversation = str(testid or '') == 'conversation' or str(testid or '').startswith('dm-conversation-item-')
            handle = _normalize_handle_value(testid)
            if handle:
                avatar_handles.append(handle.lstrip('@'))
        except Exception:
            is_conversation = False
            pass
        try:
            for avatar in row.eles('css:[data-testid^="UserAvatar-Container-"]', timeout=0):
                testid = avatar.attr('data-testid') or ''
                handle = _normalize_handle_value(testid)
                if handle:
                    avatar_handles.append(handle.lstrip('@'))
        except Exception:
            pass
        try:
            for anchor in row.eles('tag:a', timeout=0):
                href = str(anchor.attr('href') or '').strip()
                if href:
                    hrefs.append(href)
                    if _is_chat_conversation_href(href):
                        is_conversation = True
        except Exception:
            pass
        try:
            for time_el in row.eles('tag:time', timeout=0):
                time_text = str(getattr(time_el, 'text', '') or '').strip()
                dt_attr = str(time_el.attr('datetime') or '').strip()
                if time_text:
                    time_texts.append(time_text)
                if dt_attr:
                    datetime_attrs.append(dt_attr)
        except Exception:
            pass
        if raw_text or avatar_handles:
            snapshots.append({
                'raw_text': raw_text,
                'hrefs': hrefs,
                'avatar_handles': list(dict.fromkeys(avatar_handles)),
                'is_conversation': bool(is_conversation),
                'time_texts': time_texts,
                'datetime_attrs': datetime_attrs,
            })
    return snapshots


def _collect_dm_row_snapshots(tab):
    rows = _collect_dm_row_snapshots_from_dom(tab)
    if rows is not None:
        return rows
    return _collect_dm_row_snapshots_from_elements(tab)


def _snapshot_has_message_signal(snapshot):
    if not isinstance(snapshot, dict):
        return True
    if bool(snapshot.get('is_conversation', False)):
        return True
    for href in list(snapshot.get('hrefs') or []):
        if _is_chat_conversation_href(href):
            return True
    return False


def _is_passcode_blocking_page(tab):
    try:
        url = str(getattr(tab, 'url', '') or '').lower()
    except Exception:
        url = ''
    if '/i/chat/pin/recovery' in url or '/i/chat/pin' in url:
        return True
    try:
        text = str(tab.run_js(
            """
            const main = document.querySelector('main') || document.body;
            return String(main && (main.innerText || main.textContent) || '').slice(0, 1200).toLowerCase();
            """
        ) or '').lower()
    except Exception:
        return False
    return bool('enter passcode' in text and ('forgot passcode' in text or 'recover your encryption keys' in text))


def scan_recent_dm_contacts(tab, *, window_hours=24, max_scrolls=8, idle_after=2, sleep_fn=time.sleep, now_fn=None, passcode_handler=None):
    """Scan X chat list and return contacts with recent DM activity.

    The function intentionally reads only the conversation list. It does not open conversations or send anything.
    """
    now_fn = now_fn or datetime.datetime.now
    contacts = []
    seen = set()
    scanned_rows = 0
    stale_rows = 0
    unknown_time_rows = 0
    errors = []

    try:
        tab.get(CHAT_URL)
    except Exception as err:
        result = _empty_result('err', f'打开私信页面失败: {err}', window_hours=window_hours)
        return result

    try:
        sleep_fn(2.0)
    except Exception:
        pass

    if _is_passcode_blocking_page(tab):
        handled = False
        if callable(passcode_handler):
            try:
                handled = bool(passcode_handler(tab))
            except Exception:
                handled = False
        if handled:
            try:
                sleep_fn(2.0)
            except Exception:
                pass
        if _is_passcode_blocking_page(tab):
            result = _empty_result('err', '私信页被 Enter Passcode 拦截，未进入会话列表，请先配置/输入私信口令', window_hours=window_hours)
            result['last_error'] = result['msg']
            return result

    consecutive_idle = 0
    for _ in range(max(1, int(max_scrolls or 1))):
        before_count = len(contacts)
        rows = _collect_dm_row_snapshots(tab)
        scanned_rows += len(rows)
        for row in rows:
            if not _snapshot_has_message_signal(row):
                continue
            parsed = _extract_contact_from_snapshot(row)
            if not parsed:
                continue
            within, age_seconds = _is_within_window(row, window_hours=window_hours, now_fn=now_fn)
            if age_seconds is None:
                unknown_time_rows += 1
            elif not within:
                stale_rows += 1
                continue
            identity = _row_identity(parsed)
            if not identity or identity in seen:
                continue
            seen.add(identity)
            parsed.update({
                'age_seconds': age_seconds,
                'age_text': '' if age_seconds is None else _format_age(age_seconds),
                'captured_at': now_fn().strftime('%Y-%m-%d %H:%M:%S'),
            })
            contacts.append(parsed)

        if len(contacts) == before_count:
            consecutive_idle += 1
        else:
            consecutive_idle = 0
        if consecutive_idle >= max(1, int(idle_after or 1)):
            break
        try:
            tab.run_js('window.scrollBy(0, 760); void(0);')
        except Exception as err:
            errors.append(str(err))
            break
        try:
            sleep_fn(0.75)
        except Exception:
            pass

    result = {
        'status': 'ok',
        'msg': f'已统计最近 {window_hours} 小时私信联系人 {len(contacts)} 个',
        'contacts': contacts,
        'count': len(contacts),
        'scanned_rows': scanned_rows,
        'stale_rows': stale_rows,
        'unknown_time_rows': unknown_time_rows,
        'window_hours': window_hours,
        'source_url': CHAT_URL,
        'captured_at': now_fn().strftime('%Y-%m-%d %H:%M:%S'),
        'errors': errors[-5:],
    }
    result['copy_text'] = format_contacts_for_copy(contacts)
    return result


def _format_age(seconds):
    try:
        seconds = int(seconds)
    except Exception:
        return ''
    if seconds < 60:
        return f'{seconds}秒内'
    if seconds < 3600:
        return f'{seconds // 60}分钟内'
    if seconds < 86400:
        return f'{seconds // 3600}小时内'
    return f'{seconds // 86400}天内'


def format_contacts_for_copy(contacts):
    lines = []
    for row in list(contacts or []):
        handle = _normalize_spaces(row.get('handle', ''))
        if not handle:
            continue
        lines.append(handle)
    return '\n'.join(lines)


def _normalize_copy_text_to_handles(raw_text):
    handles = []
    for match in _HANDLE_RE.findall(str(raw_text or '')):
        handle = _normalize_handle_value(match)
        if handle and handle not in handles:
            handles.append(handle)
    return '\n'.join(handles)


def _normalize_result_payload(raw, *, window_hours=24, now_fn=None):
    result = dict(raw or {}) if isinstance(raw, dict) else {}
    contacts = [dict(row) for row in list(result.get('contacts') or []) if isinstance(row, dict)]
    copy_text = format_contacts_for_copy(contacts) if contacts else _normalize_copy_text_to_handles(result.get('copy_text'))
    result.update({
        'status': str(result.get('status') or 'ok'),
        'msg': str(result.get('msg') or ''),
        'contacts': contacts,
        'count': int(result.get('count', len(contacts)) or 0),
        'copy_text': copy_text,
        'scanned_rows': int(result.get('scanned_rows', 0) or 0),
        'stale_rows': int(result.get('stale_rows', 0) or 0),
        'unknown_time_rows': int(result.get('unknown_time_rows', 0) or 0),
        'window_hours': int(result.get('window_hours', window_hours) or window_hours),
        'source_url': str(result.get('source_url') or CHAT_URL),
        'captured_at': str(result.get('captured_at') or _now_text(now_fn)),
        'next_run_at': float(result.get('next_run_at', 0.0) or 0.0),
        'last_error': str(result.get('last_error') or ''),
        'last_run_type': str(result.get('last_run_type') or ''),
    })
    return result


def set_recent_dm_contacts_result(deps, result, *, save=True):
    normalized = _normalize_result_payload(result)
    lock = getattr(deps, 'data_lock', None)
    if lock:
        with lock:
            if callable(getattr(deps, '_set_runtime_attr', None)):
                deps._set_runtime_attr('dm_recent_contacts_result', normalized)
            else:
                deps.dm_recent_contacts_result = normalized
    else:
        deps.dm_recent_contacts_result = normalized
    if save:
        save_fn = getattr(deps, 'save_state', None)
        if callable(save_fn):
            try:
                save_fn()
            except Exception:
                pass
    return normalized


def get_recent_dm_contacts_result(deps):
    raw = getattr(deps, 'dm_recent_contacts_result', None)
    return _normalize_result_payload(raw) if isinstance(raw, dict) else _empty_result('ok', '还没有执行过私信联系人统计')


def scan_recent_dm_contacts_with_browser(deps, *, window_hours=24, max_scrolls=8, run_type='manual', log_label=''):
    tab = None
    result = None
    try:
        browser = deps.init_global_browser()
        tab_lock = getattr(deps, 'tab_lock', None)
        if tab_lock:
            with tab_lock:
                tab = browser.new_tab()
        else:
            tab = browser.new_tab()
        logger = getattr(deps, 'log_to_ui', None)
        if callable(logger):
            if log_label:
                logger('info', f'📨 开始统计{log_label}')
            else:
                logger('info', f'📨 开始统计最近 {window_hours} 小时私信联系人')
        result = scan_recent_dm_contacts(
            tab,
            window_hours=window_hours,
            max_scrolls=max_scrolls,
            passcode_handler=getattr(deps, '_handle_dm_passcode_prompt', None),
        )
        result['last_run_type'] = run_type
        result['last_error'] = '' if result.get('status') == 'ok' else str(result.get('msg') or '')
        if callable(logger):
            if result.get('status') == 'ok':
                logger('success', f"📨 私信联系人统计完成: {result.get('count', 0)} 个")
            else:
                logger('warn', f"📨 私信联系人统计失败: {result.get('msg', '')}")
        return set_recent_dm_contacts_result(deps, result, save=True)
    except Exception as err:
        msg = str(err) or err.__class__.__name__
        logger = getattr(deps, 'log_to_ui', None)
        if callable(logger):
            logger('error', f'📨 私信联系人统计异常: {msg}')
        result = _empty_result('err', msg, window_hours=window_hours)
        result['last_run_type'] = run_type
        result['last_error'] = msg
        return set_recent_dm_contacts_result(deps, result, save=True)
    finally:
        if tab is not None:
            try:
                tab.close()
            except Exception:
                pass


def _seconds_until_daily_run(now, *, hour=DEFAULT_DAILY_HOUR, minute=DEFAULT_DAILY_MINUTE):
    try:
        target = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
    except Exception:
        target = now.replace(hour=DEFAULT_DAILY_HOUR, minute=DEFAULT_DAILY_MINUTE, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def previous_daily_window(now, *, hour=DEFAULT_DAILY_HOUR, minute=DEFAULT_DAILY_MINUTE):
    try:
        end = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
    except Exception:
        end = now.replace(hour=DEFAULT_DAILY_HOUR, minute=DEFAULT_DAILY_MINUTE, second=0, microsecond=0)
    if now < end:
        end -= datetime.timedelta(days=1)
    start = end - datetime.timedelta(days=1)
    return start, end


def candidate_window_hours_for_daily_window(start, now, *, buffer_hours=1):
    seconds = max(1.0, (now - start).total_seconds())
    hours = int((seconds + 3599) // 3600) + max(0, int(buffer_hours or 0))
    return max(24, min(72, hours))


def filter_contacts_by_time_window(contacts, *, start, end, now_fn=None):
    now = (now_fn or datetime.datetime.now)()
    out = []
    seen = set()
    for row in list(contacts or []):
        if not isinstance(row, dict):
            continue
        handle = _normalize_spaces(row.get('handle', ''))
        if not handle:
            continue
        identity = handle.lower()
        if identity in seen:
            continue
        try:
            age_seconds = row.get('age_seconds')
            if age_seconds is None:
                continue
            event_time = now - datetime.timedelta(seconds=float(age_seconds))
        except Exception:
            continue
        if start <= event_time < end:
            item = dict(row)
            item['event_time'] = event_time.strftime('%Y-%m-%d %H:%M:%S')
            out.append(item)
            seen.add(identity)
    out.sort(key=lambda item: item.get('event_time', ''))
    return out


def build_daily_dm_contacts_message(contacts, *, start, end, title='推特私信统计'):
    handles = [str(row.get('handle') or '').strip() for row in list(contacts or []) if str(row.get('handle') or '').strip()]
    if handles:
        list_text = '\n'.join(f'{idx}. {handle}' for idx, handle in enumerate(handles, 1))
    else:
        list_text = '无'
    return (
        f'【{title}】昨日 9 点到今日 9 点推特私信统计\n'
        f'统计时间段：{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M}\n'
        f'私信人数：{len(handles)}\n'
        f'名单：\n{list_text}'
    )


def send_enterprise_wechat_text(webhook_url, content, *, timeout=20):
    webhook = str(webhook_url or '').strip()
    if not webhook:
        return {'status': 'err', 'msg': '未配置企业微信 Webhook'}
    if not webhook.startswith(ENTERPRISE_WECHAT_WEBHOOK_PREFIX):
        return {'status': 'err', 'msg': '企业微信 Webhook 地址格式不正确'}
    payload = json.dumps({'msgtype': 'text', 'text': {'content': str(content or '')}}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(webhook, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
        data = json.loads(raw) if raw else {}
    except Exception as err:
        return {'status': 'err', 'msg': f'企业微信推送失败: {err}'}
    try:
        errcode = int(data.get('errcode', -1))
    except Exception:
        errcode = -1
    if errcode == 0:
        return {'status': 'ok', 'msg': '企业微信推送成功', 'wecom': data}
    return {'status': 'err', 'msg': data.get('errmsg') or '企业微信推送失败', 'wecom': data}


def push_daily_dm_contacts_report(deps, *, now_fn=None, run_type='daily_09', title='推特私信统计'):
    now_fn = now_fn or datetime.datetime.now
    now = now_fn()
    start, end = previous_daily_window(now)
    candidate_window_hours = candidate_window_hours_for_daily_window(start, now)
    log_label = f'昨日 9 点到今日 9 点私信联系人（{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M}）'
    scan_result = scan_recent_dm_contacts_with_browser(
        deps,
        window_hours=candidate_window_hours,
        max_scrolls=12,
        run_type=run_type,
        log_label=log_label,
    )
    if scan_result.get('status') != 'ok':
        return {
            'status': 'err',
            'msg': scan_result.get('msg') or '私信统计失败',
            'scan_result': scan_result,
            'window_start': start.strftime('%Y-%m-%d %H:%M:%S'),
            'window_end': end.strftime('%Y-%m-%d %H:%M:%S'),
            'candidate_window_hours': candidate_window_hours,
        }
    contacts = filter_contacts_by_time_window(scan_result.get('contacts'), start=start, end=end, now_fn=now_fn)
    content = build_daily_dm_contacts_message(contacts, start=start, end=end, title=title)
    push_result = send_enterprise_wechat_text(getattr(deps, 'enterprise_wechat_webhook_url', ''), content)
    result = {
        **push_result,
        'count': len(contacts),
        'contacts': contacts,
        'copy_text': format_contacts_for_copy(contacts),
        'content': content,
        'window_start': start.strftime('%Y-%m-%d %H:%M:%S'),
        'window_end': end.strftime('%Y-%m-%d %H:%M:%S'),
        'candidate_window_hours': candidate_window_hours,
        'scan_count': int(scan_result.get('count', 0) or 0),
    }
    logger = getattr(deps, 'log_to_ui', None)
    if callable(logger):
        if result.get('status') == 'ok':
            logger('success', f"📣 企业微信私信日报已推送: {result.get('count', 0)} 人")
        else:
            logger('warn', f"📣 企业微信私信日报推送失败: {result.get('msg', '')}")
    return result


def _daily_dm_contacts_loop(deps, *, stop_event, sleep_fn=time.sleep, now_fn=datetime.datetime.now):
    while not stop_event.is_set():
        wait_sec = _seconds_until_daily_run(now_fn()) + random.uniform(0, 90)
        current = get_recent_dm_contacts_result(deps)
        current['next_run_at'] = time.time() + wait_sec
        set_recent_dm_contacts_result(deps, current, save=False)
        logger = getattr(deps, 'log_to_ui', None)
        if callable(logger):
            logger('debug', f'📨 私信联系人每日统计下次执行: {int(wait_sec)}s 后')
        if stop_event.wait(wait_sec):
            break
        push_daily_dm_contacts_report(deps, now_fn=now_fn, run_type='daily_09')


def start_daily_dm_contacts_scheduler(deps):
    thread = getattr(deps, 'dm_recent_contacts_thread', None)
    if thread is not None and thread.is_alive():
        return False
    stop_event = getattr(deps, 'dm_recent_contacts_stop_event', None)
    if stop_event is None:
        stop_event = threading.Event()
        deps.dm_recent_contacts_stop_event = stop_event
    else:
        stop_event.clear()
    thread = threading.Thread(
        target=_daily_dm_contacts_loop,
        args=(deps,),
        kwargs={'stop_event': stop_event},
        daemon=True,
        name='daily_dm_contacts_scheduler',
    )
    deps.dm_recent_contacts_thread = thread
    thread.start()
    return True


def stop_daily_dm_contacts_scheduler(deps, timeout=2.0):
    stop_event = getattr(deps, 'dm_recent_contacts_stop_event', None)
    if stop_event is not None:
        stop_event.set()
    thread = getattr(deps, 'dm_recent_contacts_thread', None)
    if thread is not None and thread.is_alive():
        thread.join(timeout=max(0.0, float(timeout or 0.0)))
    return True
