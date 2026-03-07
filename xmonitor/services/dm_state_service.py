import time


def is_dm_unavailable_cached(handle, deps):
    """检查某用户私信不可达缓存。"""
    handle_norm = deps.normalize_handle(handle)
    if not handle_norm:
        return False
    now = time.time()
    with deps.dm_unavailable_cache_lock:
        expire_ts = deps.dm_unavailable_cache.get(handle_norm, 0.0)
        if expire_ts > now:
            return True
        if handle_norm in deps.dm_unavailable_cache:
            deps.dm_unavailable_cache.pop(handle_norm, None)
    return False


def mark_dm_unavailable(handle, deps):
    handle_norm = deps.normalize_handle(handle)
    if not handle_norm:
        return
    with deps.dm_unavailable_cache_lock:
        deps.dm_unavailable_cache[handle_norm] = time.time() + deps.DM_UNAVAILABLE_CACHE_TTL_SEC


def clear_dm_unavailable_cache(handle, deps):
    handle_norm = deps.normalize_handle(handle)
    if not handle_norm:
        return
    with deps.dm_unavailable_cache_lock:
        deps.dm_unavailable_cache.pop(handle_norm, None)


def get_status_link_from_item(item, deps, matched_status_handle=None, matched_status_id=None):
    status_handle = deps.normalize_handle(
        matched_status_handle or item.get('status_handle') or item.get('handle') or ''
    )
    status_id = deps._pick_best_status_id(
        matched_status_id or '',
        item.get('status_id', ''),
        item.get('status_url', ''),
        item.get('key', ''),
    )
    raw_url = str(item.get('status_url', '')).strip()
    return deps._normalize_dm_share_link(raw_url, status_id=status_id, status_handle=status_handle, fallback_url=raw_url)


def reply_humanized_idle(tab, deps, low=0.16, high=0.46, stage_text='回复步骤'):
    deps._prepare_reply_prompt_guard(tab, f'{stage_text}前')
    mult = deps._get_humanize_multiplier()
    low_v = max(0.05, float(low) * mult)
    high_v = max(low_v, float(high) * mult)
    pause = deps.random.uniform(low_v, high_v)
    if deps.headless_mode:
        pause += deps.random.uniform(0.08, 0.26)
    time.sleep(pause)
    deps._prepare_reply_prompt_guard(tab, f'{stage_text}后')
    deps.log_headless_debug(f'{stage_text}等待 {pause:.2f}s')
