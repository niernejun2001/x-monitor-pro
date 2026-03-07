import time


def clamp(value, low, high):
    return max(low, min(high, value))


def get_pending_notify_count(pending_results, data_lock):
    try:
        with data_lock:
            return sum(1 for row in pending_results if row.get('source') == '通知页面')
    except Exception:
        return 0


def get_humanize_multiplier(
    *,
    headless_mode,
    base_multiplier,
    headless_extra_multiplier,
    reply_metrics_lock,
    reply_failure_streak,
):
    base = max(0.85, float(base_multiplier))
    if headless_mode:
        base *= (1.0 + max(0.0, float(headless_extra_multiplier)))
    try:
        with reply_metrics_lock:
            streak = int(reply_failure_streak())
    except Exception:
        streak = 0
    if streak > 0:
        base *= min(1.45, 1.0 + 0.07 * streak)
    return clamp(base, 0.85, 2.8)


def get_adaptive_reply_gap_factor(
    *,
    adaptive_enabled,
    acceleration_enabled,
    reply_metrics_lock,
    reply_outcome_recent,
    reply_failure_streak,
    queue_depth,
    queue_accel_factor,
):
    if not adaptive_enabled:
        return 1.0
    with reply_metrics_lock:
        outcomes = list(reply_outcome_recent)
        streak = int(reply_failure_streak())
    success_rate = (sum(outcomes) / len(outcomes)) if outcomes else 1.0
    factor = 1.0
    if streak > 0:
        factor *= min(2.0, 1.0 + 0.16 * streak)
    if acceleration_enabled and len(outcomes) >= 8 and success_rate >= 0.9 and queue_depth >= 30 and streak == 0:
        accel = clamp(float(queue_accel_factor), 0.92, 1.0)
        factor *= accel
    return clamp(factor, 0.92, 2.2)


def reserve_notify_dm_user_slot(handle, task_key, *, normalize_handle_fn, cooldown_dict, cooldown_lock, cooldown_sec):
    handle_norm = normalize_handle_fn(handle)
    if not handle_norm or cooldown_sec <= 0:
        return True, 0.0
    now = time.time()
    task_key_text = str(task_key or '').strip()
    with cooldown_lock:
        record = cooldown_dict.get(handle_norm, {})
        next_ts = float(record.get('until', 0.0) or 0.0)
        owner_task = str(record.get('task_key', '') or '').strip()
        if next_ts > now and owner_task and owner_task != task_key_text:
            return False, max(0.0, next_ts - now)
        cooldown_dict[handle_norm] = {
            'until': now + float(cooldown_sec),
            'task_key': task_key_text,
        }
        if len(cooldown_dict) > 2048:
            expired = [
                h for h, meta in cooldown_dict.items()
                if float((meta or {}).get('until', 0.0) or 0.0) <= now
            ]
            for handle_item in expired[:1024]:
                cooldown_dict.pop(handle_item, None)
    return True, 0.0
