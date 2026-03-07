import hashlib
import random
import re
import time
import unicodedata
import urllib.error


def reorder_articles_for_scan(articles, deps):
    """对文章进行分块随机重排，打散读取顺序但不丢数据。"""
    if not articles:
        return []
    reordered = []
    chunk_low = max(1, deps.ARTICLE_REORDER_CHUNK_MIN)
    chunk_high = max(chunk_low, deps.ARTICLE_REORDER_CHUNK_MAX)
    idx = 0
    items = list(articles)
    while idx < len(items):
        chunk_size = random.randint(chunk_low, chunk_high)
        chunk = items[idx: idx + chunk_size]
        if len(chunk) > 1 and random.random() < 0.75:
            random.shuffle(chunk)
        reordered.extend(chunk)
        idx += chunk_size
    return reordered


def normalize_content_for_filter(content):
    text = str(content or '')
    text = text.replace('＠', '@')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def contains_emoji_char(ch, deps):
    cp = ord(ch)
    for low, high in deps.EMOJI_UNICODE_RANGES:
        if low <= cp <= high:
            return True
    return False


def is_emoji_only_content(content, deps):
    text = normalize_content_for_filter(content)
    if not text:
        return False
    has_emoji = False
    for ch in text:
        if ch.isspace() or ch in deps.EMOJI_JOINER_CHARS:
            continue
        if contains_emoji_char(ch, deps):
            has_emoji = True
            continue
        cat = unicodedata.category(ch)
        if cat.startswith('P') or cat.startswith('S'):
            continue
        return False
    return has_emoji


def llm_filter_endpoint(deps, base_url=None):
    base = str(base_url if base_url is not None else deps.LLM_FILTER_BASE_URL or '').strip()
    if not base:
        return ''
    base = base.rstrip('/')
    if base.endswith('/chat/completions'):
        return base
    if base.endswith('/v1'):
        return f'{base}/chat/completions'
    if base.endswith('/v1/'):
        return f'{base}chat/completions'
    return f'{base}/chat/completions'


def llm_runtime_ready(deps, base_url=None, model=None):
    model_name = str(model if model is not None else deps.LLM_FILTER_MODEL or '').strip()
    return bool(model_name and llm_filter_endpoint(deps, base_url=base_url))


def llm_filter_is_ready(deps, base_url=None, model=None, enabled=None):
    enabled_flag = deps.LLM_FILTER_ENABLED if enabled is None else bool(enabled)
    return bool(enabled_flag and llm_runtime_ready(deps, base_url=base_url, model=model))


def prune_llm_filter_cache(deps, now_ts=None):
    if now_ts is None:
        now_ts = time.time()
    expire_before = now_ts - max(60, deps.LLM_FILTER_CACHE_TTL_SEC)
    expired = [key for key, value in deps.llm_filter_cache.items() if float(value.get('ts', 0)) < expire_before]
    for key in expired:
        deps.llm_filter_cache.pop(key, None)
    if len(deps.llm_filter_cache) > max(100, deps.LLM_FILTER_CACHE_MAX_ENTRIES):
        overflow = len(deps.llm_filter_cache) - max(100, deps.LLM_FILTER_CACHE_MAX_ENTRIES)
        old_items = sorted(deps.llm_filter_cache.items(), key=lambda item: float(item[1].get('ts', 0)))[:overflow]
        for key, _ in old_items:
            deps.llm_filter_cache.pop(key, None)


def normalize_content_for_dedupe(content):
    """标准化内容用于重复检测。"""
    text = re.sub(r'\s+', ' ', content or '').strip().lower()
    text = re.sub(r'https?://\S+', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'www\.\S+', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def make_content_signature(handle, content, deps):
    handle_norm = deps.normalize_handle(handle)
    content_norm = normalize_content_for_dedupe(content)
    if not handle_norm or not content_norm:
        return ''
    raw = f'{handle_norm}|{content_norm}'
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def prune_content_dedupe(deps, now_ts=None):
    if now_ts is None:
        now_ts = time.time()
    expire_before = now_ts - deps.CONTENT_DEDUPE_TTL_SEC
    expired_keys = [k for k, ts in deps.content_dedupe.items() if ts < expire_before]
    for key in expired_keys:
        deps.content_dedupe.pop(key, None)
    if len(deps.content_dedupe) > deps.CONTENT_DEDUPE_MAX_ENTRIES:
        overflow = len(deps.content_dedupe) - deps.CONTENT_DEDUPE_MAX_ENTRIES
        old_keys = sorted(deps.content_dedupe.items(), key=lambda item: item[1])[:overflow]
        for key, _ in old_keys:
            deps.content_dedupe.pop(key, None)


def should_skip_duplicate_content(handle, content, deps, now_ts=None):
    if now_ts is None:
        now_ts = time.time()
    if len(deps.content_dedupe) > deps.CONTENT_DEDUPE_MAX_ENTRIES:
        prune_content_dedupe(deps, now_ts=now_ts)
    signature = make_content_signature(handle, content, deps)
    if not signature:
        return False
    last_seen = deps.content_dedupe.get(signature)
    if last_seen and (now_ts - last_seen) <= deps.CONTENT_DEDUPE_TTL_SEC:
        return True
    deps.content_dedupe[signature] = now_ts
    return False


def should_skip_by_llm_filter(content, deps):
    if not deps._llm_filter_is_ready():
        return False, ''
    text = deps._normalize_content_for_filter(content)
    if not text:
        return False, ''
    sig_raw = normalize_content_for_dedupe(text)
    if not sig_raw:
        return False, ''
    sig = hashlib.md5(sig_raw.encode('utf-8')).hexdigest()
    now_ts = time.time()
    with deps.llm_filter_cache_lock:
        cached = deps.llm_filter_cache.get(sig)
        if cached and (now_ts - float(cached.get('ts', 0))) <= deps.LLM_FILTER_CACHE_TTL_SEC:
            return bool(cached.get('skip', False)), str(cached.get('reason', '') or '')
    try:
        skip, reason = deps._call_openai_compatible_filter_api(text)
    except urllib.error.URLError as e:
        deps.log_to_ui('debug', f'🤖 [LLMFilter] 接口不可达，已回退规则过滤: {e}')
        skip, reason = False, ''
    except Exception as e:
        deps.log_to_ui('debug', f'🤖 [LLMFilter] 调用异常，已回退规则过滤: {e}')
        skip, reason = False, ''
    with deps.llm_filter_cache_lock:
        deps.llm_filter_cache[sig] = {'ts': now_ts, 'skip': bool(skip), 'reason': str(reason or '')}
        if len(deps.llm_filter_cache) > deps.LLM_FILTER_CACHE_MAX_ENTRIES:
            prune_llm_filter_cache(deps, now_ts)
    return bool(skip), str(reason or '')


def should_skip_content_by_policy(content, deps, allow_llm_hard_filter=None):
    text = deps._normalize_content_for_filter(content)
    if not text:
        return False, ''
    lower_text = text.lower()
    for mention in deps.CONTENT_FILTER_BLOCKED_MENTIONS:
        mention_norm = str(mention or '').strip().lower()
        if mention_norm and mention_norm in lower_text:
            return True, 'blocked_mention'
    if deps._is_emoji_only_content(text):
        return True, 'emoji_only'
    if allow_llm_hard_filter is None:
        allow_llm_hard_filter = bool(deps.LLM_HARD_FILTER_ENABLED)
    if allow_llm_hard_filter:
        llm_skip, llm_reason = should_skip_by_llm_filter(text, deps)
        if llm_skip:
            return True, llm_reason or 'llm_filter'
    return False, ''
