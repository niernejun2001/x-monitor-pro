import time


def enter_dm_critical(deps, section='dm_send'):
    """进入私信关键区，期间尽量避免通知页刷新/切换。"""
    if not deps.DM_CRITICAL_LOCK_ENABLED:
        return False
    deps.dm_critical_lock.acquire()
    with deps.dm_critical_state_lock:
        deps.dm_critical_depth += 1
        if deps.dm_critical_depth == 1:
            deps.dm_critical_started_at = time.time()
    return True


def leave_dm_critical(deps):
    """退出私信关键区。"""
    if not deps.DM_CRITICAL_LOCK_ENABLED:
        return
    with deps.dm_critical_state_lock:
        deps.dm_critical_depth = max(0, int(deps.dm_critical_depth) - 1)
        if deps.dm_critical_depth == 0:
            deps.dm_critical_started_at = 0.0
    try:
        deps.dm_critical_lock.release()
    except Exception:
        pass


def is_dm_critical_active(deps):
    with deps.dm_critical_state_lock:
        active = int(deps.dm_critical_depth) > 0
        started = float(deps.dm_critical_started_at or 0.0)
    if not active:
        return False
    if started > 0 and (time.time() - started) > float(deps.DM_CRITICAL_MAX_HOLD_SEC):
        now = time.time()
        if (now - float(deps.dm_critical_last_timeout_warn_ts or 0.0)) >= 15.0:
            deps.dm_critical_last_timeout_warn_ts = now
            deps.log_to_ui(
                'warn',
                f'⚠️ 私信关键区占用超过{int(deps.DM_CRITICAL_MAX_HOLD_SEC)}s，临时放行通知扫描（不影响当前私信任务继续）'
            )
        return False
    return True


def maybe_log_dm_critical_skip(deps):
    """限频输出因私信关键区跳过通知刷新的日志。"""
    now = time.time()
    if (now - deps.dm_critical_last_skip_log_ts) >= 3.0:
        deps.dm_critical_last_skip_log_ts = now
        deps.log_to_ui('debug', '📨 私信关键区进行中，已延后通知扫描/刷新')
