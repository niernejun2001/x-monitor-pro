import time


def set_reply_flow_active(active, *, state_lock, state_setter):
    with state_lock:
        state_setter(bool(active))


def is_reply_flow_active(*, state_lock, state_getter):
    with state_lock:
        return bool(state_getter())


def record_reply_outcome(
    handle,
    ok,
    err,
    *,
    normalize_handle_fn,
    metrics_lock,
    outcome_recent,
    failure_streak_getter,
    failure_streak_setter,
    handle_failures,
    failure_window_sec,
    failure_budget_max,
    failure_cooldown_sec,
):
    handle_norm = normalize_handle_fn(handle)
    now = time.time()
    err_text = str(err or '')
    with metrics_lock:
        outcome_recent.append(1 if ok else 0)
        if ok:
            failure_streak_setter(0)
            if handle_norm and handle_norm in handle_failures:
                handle_failures.pop(handle_norm, None)
            return

        next_streak = int(failure_streak_getter()) + 1
        failure_streak_setter(next_streak)
        if not handle_norm:
            return
        record = handle_failures.get(handle_norm, {})
        first_ts = float(record.get('first_ts', now))
        count = int(record.get('count', 0))
        if (now - first_ts) > failure_window_sec:
            first_ts = now
            count = 0
        count += 1
        cooldown_until = float(record.get('cooldown_until', 0.0))
        if count >= max(1, failure_budget_max):
            cooldown_until = now + max(60, failure_cooldown_sec)
        handle_failures[handle_norm] = {
            'count': count,
            'first_ts': first_ts,
            'cooldown_until': cooldown_until,
            'last_err': err_text[:260],
        }
