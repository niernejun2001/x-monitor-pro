import datetime
import re


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
        time_text = (time_ele.text or '').strip().lower()
        if not time_text:
            return None
        num_match = re.search(r'(\d+)', time_text)
        num = int(num_match.group(1)) if num_match else 0
        if any(k in time_text for k in ['刚刚', 'now', '秒', ' sec', ' s']):
            return 0
        if any(k in time_text for k in ['分', ' min', 'm']):
            return num if num > 0 else 0
        if any(k in time_text for k in ['小时', ' hr', 'h']):
            return (num if num > 0 else 1) * 60
        if any(k in time_text for k in ['天', ' day', 'd']):
            return (num if num > 0 else 1) * 1440
    except Exception:
        return None
    return None


def extract_notification_handle(article, article_text):
    try:
        user_ele = article.ele('css:[data-testid="User-Name"]', timeout=0)
        if user_ele:
            user_text = (user_ele.text or '').strip()
            match = re.search(r'(@[\w_]+)', user_text)
            if match:
                return match.group(1)
    except Exception:
        pass
    try:
        links = article.eles('tag:a', timeout=0)
        for link in links:
            href = (link.attr('href') or '').strip()
            if not href.startswith('/'):
                continue
            status_match = re.match(r'^/([A-Za-z0-9_]+)/status/\d+', href)
            if status_match:
                return f"@{status_match.group(1)}"
            profile_match = re.match(r'^/([A-Za-z0-9_]+)$', href)
            if profile_match:
                username = profile_match.group(1).lower()
                if username not in {'home', 'notifications', 'explore', 'messages', 'compose', 'i'}:
                    return f"@{profile_match.group(1)}"
    except Exception:
        pass
    match = re.search(r'(@[\w_]+)', article_text or '')
    return match.group(1) if match else None
