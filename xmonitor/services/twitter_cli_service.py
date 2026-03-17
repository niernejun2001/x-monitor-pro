import importlib
import re
import threading
import time


_IMPORT_LOCK = threading.Lock()
_IMPORT_STATE = {
    'checked': False,
    'ok': False,
    'error': '',
    'client_cls': None,
    'auth_mod': None,
}
_CALL_LOCK = threading.Lock()
_TWEET_CACHE = {}
_USER_CACHE = {}
_RUNTIME_META = {
    'last_error': '',
    'last_ok_at': 0.0,
    'last_verify_ok': False,
    'last_verify_at': 0.0,
    'last_auth_source': '',
    'last_cookie_source': '',
}


def _log(deps, level, message):
    logger = getattr(deps, 'log_to_ui', None)
    if callable(logger):
        try:
            logger(level, message)
        except Exception:
            pass


def _normalize_handle(raw_handle):
    return str(raw_handle or '').strip().lstrip('@').lower()


def _pick_status_id(raw_value):
    text = str(raw_value or '').strip()
    if not text:
        return ''
    match = re.search(r'(?<!\d)(\d{8,80})(?!\d)', text)
    return match.group(1) if match else ''


def _runtime_enabled(deps):
    return bool(getattr(deps, 'TWITTER_CLI_ENABLED', True))


def _tweet_cache_ttl(deps):
    try:
        ttl = float(getattr(deps, 'TWITTER_CLI_TWEET_CACHE_TTL_SEC', 300.0) or 300.0)
    except Exception:
        ttl = 300.0
    return max(30.0, ttl)


def _user_cache_ttl(deps):
    try:
        ttl = float(getattr(deps, 'TWITTER_CLI_USER_CACHE_TTL_SEC', 600.0) or 600.0)
    except Exception:
        ttl = 600.0
    return max(30.0, ttl)


def _load_twitter_cli_modules():
    with _IMPORT_LOCK:
        if _IMPORT_STATE['checked']:
            return _IMPORT_STATE
        try:
            client_mod = importlib.import_module('twitter_cli.client')
            auth_mod = importlib.import_module('twitter_cli.auth')
            _IMPORT_STATE.update({
                'checked': True,
                'ok': True,
                'error': '',
                'client_cls': getattr(client_mod, 'TwitterClient', None),
                'auth_mod': auth_mod,
            })
        except Exception as exc:
            _IMPORT_STATE.update({
                'checked': True,
                'ok': False,
                'error': str(exc),
                'client_cls': None,
                'auth_mod': None,
            })
        return _IMPORT_STATE


def _coerce_cookie_dicts(raw_cookies):
    cookies = []
    for item in list(raw_cookies or []):
        if isinstance(item, dict):
            cookies.append(item)
            continue
        cookie_dict = {}
        for key in ('name', 'value', 'domain'):
            try:
                cookie_dict[key] = getattr(item, key)
            except Exception:
                cookie_dict[key] = ''
        cookies.append(cookie_dict)
    return cookies


def _extract_browser_cookie_payload(cookie_holder):
    if cookie_holder is None or not hasattr(cookie_holder, 'cookies'):
        return None
    try:
        raw_cookies = cookie_holder.cookies(all_domains=True, all_info=True)
    except TypeError:
        raw_cookies = cookie_holder.cookies(all_domains=True)
    except Exception:
        return None

    cookies = _coerce_cookie_dicts(raw_cookies)
    all_cookies = {}
    auth_token = ''
    ct0 = ''
    for cookie in cookies:
        name = str(cookie.get('name', '') or '').strip()
        value = str(cookie.get('value', '') or '')
        domain = str(cookie.get('domain', '') or '').lower()
        if not name or not value:
            continue
        if domain and ('x.com' not in domain) and ('twitter.com' not in domain):
            continue
        all_cookies[name] = value
        if name == 'auth_token':
            auth_token = value
        elif name == 'ct0':
            ct0 = value
    if not auth_token or not ct0:
        return None
    cookie_string = '; '.join(f'{name}={all_cookies[name]}' for name in sorted(all_cookies.keys()))
    return {
        'auth_token': auth_token,
        'ct0': ct0,
        'cookie_string': cookie_string,
        'cookie_source': 'drission_browser',
    }


def _iter_cookie_holders(deps):
    seen = set()
    for attr_name in ('notification_tab', 'reply_work_tab', 'global_browser'):
        holder = getattr(deps, attr_name, None)
        if holder is None:
            continue
        holder_id = id(holder)
        if holder_id in seen:
            continue
        seen.add(holder_id)
        yield attr_name, holder


def _resolve_cookie_payload(deps):
    for source_name, holder in _iter_cookie_holders(deps):
        payload = _extract_browser_cookie_payload(holder)
        if payload:
            payload['cookie_source'] = f'drission_{source_name}'
            return payload

    modules = _load_twitter_cli_modules()
    if not modules.get('ok'):
        raise RuntimeError(modules.get('error') or 'twitter-cli 模块不可用')
    auth_mod = modules.get('auth_mod')
    if auth_mod is None or not hasattr(auth_mod, 'get_cookies'):
        raise RuntimeError('twitter-cli.auth.get_cookies 不可用')
    cookies = auth_mod.get_cookies()
    if not isinstance(cookies, dict):
        raise RuntimeError('twitter-cli cookies 返回格式异常')
    auth_token = str(cookies.get('auth_token', '') or '').strip()
    ct0 = str(cookies.get('ct0', '') or '').strip()
    if not auth_token or not ct0:
        raise RuntimeError('twitter-cli 未获取到 auth_token / ct0')
    return {
        'auth_token': auth_token,
        'ct0': ct0,
        'cookie_string': str(cookies.get('cookie_string', '') or '').strip(),
        'cookie_source': 'twitter_cli_auth',
    }


def _create_client_and_meta(deps):
    modules = _load_twitter_cli_modules()
    if not modules.get('ok'):
        raise RuntimeError(modules.get('error') or 'twitter-cli 模块不可用')
    client_cls = modules.get('client_cls')
    if client_cls is None:
        raise RuntimeError('twitter-cli.TwitterClient 不可用')
    cookie_payload = _resolve_cookie_payload(deps)
    client = client_cls(
        cookie_payload['auth_token'],
        cookie_payload['ct0'],
        cookie_string=(cookie_payload.get('cookie_string') or None),
    )
    _RUNTIME_META['last_auth_source'] = 'cookie_session'
    _RUNTIME_META['last_cookie_source'] = str(cookie_payload.get('cookie_source', '') or '')
    _RUNTIME_META['last_error'] = ''
    return client, cookie_payload


def _tweet_to_payload(tweet):
    author = getattr(tweet, 'author', None)
    screen_name = str(getattr(author, 'screen_name', '') or '').strip()
    tweet_id = str(getattr(tweet, 'id', '') or '').strip()
    return {
        'id': tweet_id,
        'text': str(getattr(tweet, 'text', '') or '').strip(),
        'created_at': str(getattr(tweet, 'created_at', '') or '').strip(),
        'url': (
            f'https://x.com/{screen_name}/status/{tweet_id}'
            if screen_name and tweet_id else
            (f'https://x.com/i/status/{tweet_id}' if tweet_id else '')
        ),
        'author': {
            'id': str(getattr(author, 'id', '') or '').strip(),
            'name': str(getattr(author, 'name', '') or '').strip(),
            'screen_name': screen_name,
            'verified': bool(getattr(author, 'verified', False)),
        },
    }


def _user_to_payload(profile):
    return {
        'id': str(getattr(profile, 'id', '') or '').strip(),
        'name': str(getattr(profile, 'name', '') or '').strip(),
        'screen_name': str(getattr(profile, 'screen_name', '') or '').strip(),
        'bio': str(getattr(profile, 'bio', '') or '').strip(),
        'location': str(getattr(profile, 'location', '') or '').strip(),
        'url': str(getattr(profile, 'url', '') or '').strip(),
        'followers_count': int(getattr(profile, 'followers_count', 0) or 0),
        'following_count': int(getattr(profile, 'following_count', 0) or 0),
        'tweets_count': int(getattr(profile, 'tweets_count', 0) or 0),
        'likes_count': int(getattr(profile, 'likes_count', 0) or 0),
        'verified': bool(getattr(profile, 'verified', False)),
    }


def build_twitter_cli_runtime_payload(deps):
    modules = _load_twitter_cli_modules()
    return {
        'twitter_cli_enabled': _runtime_enabled(deps),
        'twitter_cli_available': bool(modules.get('ok')),
        'twitter_cli_import_error': str(modules.get('error', '') or ''),
        'twitter_cli_last_error': str(_RUNTIME_META.get('last_error', '') or ''),
        'twitter_cli_last_ok_at': float(_RUNTIME_META.get('last_ok_at', 0.0) or 0.0),
        'twitter_cli_last_verify_at': float(_RUNTIME_META.get('last_verify_at', 0.0) or 0.0),
        'twitter_cli_last_verify_ok': bool(_RUNTIME_META.get('last_verify_ok', False)),
        'twitter_cli_last_auth_source': str(_RUNTIME_META.get('last_auth_source', '') or ''),
        'twitter_cli_last_cookie_source': str(_RUNTIME_META.get('last_cookie_source', '') or ''),
    }


def get_twitter_cli_status(deps, verify=False):
    payload = build_twitter_cli_runtime_payload(deps)
    payload.update({
        'status': 'ok',
        'authenticated': False,
        'screen_name': '',
        'msg': '',
    })
    if not payload['twitter_cli_enabled']:
        payload['msg'] = 'twitter-cli 已禁用'
        return payload
    if not payload['twitter_cli_available']:
        payload['status'] = 'err'
        payload['msg'] = payload['twitter_cli_import_error'] or 'twitter-cli 未安装'
        return payload
    if not verify:
        payload['msg'] = 'twitter-cli 已接入'
        return payload

    try:
        with _CALL_LOCK:
            client, _ = _create_client_and_meta(deps)
            me = client.fetch_me()
        payload['authenticated'] = True
        payload['screen_name'] = str(getattr(me, 'screen_name', '') or '').strip()
        payload['msg'] = 'twitter-cli 认证可用'
        _RUNTIME_META['last_ok_at'] = time.time()
        _RUNTIME_META['last_verify_at'] = _RUNTIME_META['last_ok_at']
        _RUNTIME_META['last_verify_ok'] = True
        _RUNTIME_META['last_error'] = ''
        return payload
    except Exception as exc:
        _RUNTIME_META['last_verify_at'] = time.time()
        _RUNTIME_META['last_verify_ok'] = False
        _RUNTIME_META['last_error'] = str(exc)
        payload.update({
            'status': 'err',
            'authenticated': False,
            'msg': str(exc),
            'twitter_cli_last_error': str(exc),
            'twitter_cli_last_verify_at': float(_RUNTIME_META['last_verify_at']),
            'twitter_cli_last_verify_ok': False,
        })
        return payload


def fetch_twitter_cli_tweet_detail(deps, tweet_id, max_count=8, force_refresh=False):
    result = {
        'status': 'err',
        'tweet_id': '',
        'tweet': {},
        'replies': [],
        'reply_count': 0,
        'msg': '',
        'auth_source': '',
        'cookie_source': '',
        **build_twitter_cli_runtime_payload(deps),
    }
    if not _runtime_enabled(deps):
        result['msg'] = 'twitter-cli 已禁用'
        return result
    if not result['twitter_cli_available']:
        result['msg'] = result['twitter_cli_import_error'] or 'twitter-cli 未安装'
        return result

    tweet_id = _pick_status_id(tweet_id)
    result['tweet_id'] = tweet_id
    if not tweet_id:
        result['msg'] = 'tweet_id 无效'
        return result

    now = time.time()
    cache_key = str(tweet_id)
    cache_ttl = _tweet_cache_ttl(deps)
    cached = _TWEET_CACHE.get(cache_key)
    if (not force_refresh) and cached and float(cached.get('expire_at', 0.0) or 0.0) > now:
        cached_payload = dict(cached.get('payload', {}) or {})
        cached_payload['cache_hit'] = True
        return cached_payload

    try:
        with _CALL_LOCK:
            client, meta = _create_client_and_meta(deps)
            tweets = client.fetch_tweet_detail(tweet_id, max_count=max(2, min(int(max_count or 8), 40)))
        focal = tweets[0] if tweets else None
        focal_payload = _tweet_to_payload(focal) if focal else {}
        replies = [_tweet_to_payload(tweet) for tweet in list(tweets[1:])[:10]]
        payload = {
            'status': 'ok',
            'tweet_id': tweet_id,
            'tweet': focal_payload,
            'replies': replies,
            'reply_count': max(0, len(tweets) - 1),
            'msg': 'ok',
            'auth_source': 'cookie_session',
            'cookie_source': str(meta.get('cookie_source', '') or ''),
            'cache_hit': False,
            **build_twitter_cli_runtime_payload(deps),
        }
        _TWEET_CACHE[cache_key] = {'expire_at': now + cache_ttl, 'payload': dict(payload)}
        _RUNTIME_META['last_ok_at'] = now
        _RUNTIME_META['last_error'] = ''
        return payload
    except Exception as exc:
        _RUNTIME_META['last_error'] = str(exc)
        result['msg'] = str(exc)
        result['twitter_cli_last_error'] = str(exc)
        return result


def fetch_twitter_cli_user(deps, screen_name, force_refresh=False):
    result = {
        'status': 'err',
        'handle': '',
        'user': {},
        'msg': '',
        'auth_source': '',
        'cookie_source': '',
        **build_twitter_cli_runtime_payload(deps),
    }
    if not _runtime_enabled(deps):
        result['msg'] = 'twitter-cli 已禁用'
        return result
    if not result['twitter_cli_available']:
        result['msg'] = result['twitter_cli_import_error'] or 'twitter-cli 未安装'
        return result

    handle = _normalize_handle(screen_name)
    result['handle'] = f'@{handle}' if handle else ''
    if not handle:
        result['msg'] = 'handle 无效'
        return result

    now = time.time()
    cache_key = handle
    cache_ttl = _user_cache_ttl(deps)
    cached = _USER_CACHE.get(cache_key)
    if (not force_refresh) and cached and float(cached.get('expire_at', 0.0) or 0.0) > now:
        cached_payload = dict(cached.get('payload', {}) or {})
        cached_payload['cache_hit'] = True
        return cached_payload

    try:
        with _CALL_LOCK:
            client, meta = _create_client_and_meta(deps)
            profile = client.fetch_user(handle)
        payload = {
            'status': 'ok',
            'handle': f'@{handle}',
            'user': _user_to_payload(profile),
            'msg': 'ok',
            'auth_source': 'cookie_session',
            'cookie_source': str(meta.get('cookie_source', '') or ''),
            'cache_hit': False,
            **build_twitter_cli_runtime_payload(deps),
        }
        _USER_CACHE[cache_key] = {'expire_at': now + cache_ttl, 'payload': dict(payload)}
        _RUNTIME_META['last_ok_at'] = now
        _RUNTIME_META['last_error'] = ''
        return payload
    except Exception as exc:
        _RUNTIME_META['last_error'] = str(exc)
        result['msg'] = str(exc)
        result['twitter_cli_last_error'] = str(exc)
        return result


def enrich_notification_from_twitter_cli(deps, status_id, handle_hint='', content_hint=''):
    out = {
        'status': 'err',
        'content': '',
        'status_handle': '',
        'status_url': '',
        'source': '',
        'msg': '',
    }
    tweet_id = _pick_status_id(status_id)
    if not tweet_id:
        out['msg'] = 'status_id 无效'
        return out
    detail = fetch_twitter_cli_tweet_detail(deps, tweet_id, max_count=6)
    if detail.get('status') != 'ok':
        out['msg'] = str(detail.get('msg', '') or 'twitter-cli 获取推文详情失败')
        return out
    tweet = detail.get('tweet') or {}
    text = str(tweet.get('text', '') or '').strip()
    author = tweet.get('author') or {}
    screen_name = _normalize_handle(author.get('screen_name', '') or handle_hint)
    status_url = str(tweet.get('url', '') or '').strip()
    if not status_url and tweet_id:
        status_url = (
            f'https://x.com/{screen_name}/status/{tweet_id}'
            if screen_name else
            f'https://x.com/i/status/{tweet_id}'
        )
    out.update({
        'status': 'ok',
        'content': text[:280] if text else str(content_hint or '').strip()[:280],
        'status_handle': f'@{screen_name}' if screen_name else '',
        'status_url': status_url,
        'source': 'twitter_cli_tweet_detail',
        'msg': 'ok',
    })
    return out
