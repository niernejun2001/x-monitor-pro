import random
import time


def _clamp_hour(raw_value, default_value):
    try:
        hour = int(raw_value)
    except Exception:
        hour = int(default_value)
    return max(0, min(23, hour))


def _resolve_notification_schedule_profile(deps, now_struct=None):
    now_struct = now_struct or time.localtime()
    hour = _clamp_hour(getattr(now_struct, 'tm_hour', 12), 12)
    active_start = _clamp_hour(getattr(deps, 'NOTIFICATION_ACTIVE_HOURS_START', 8), 8)
    active_end = _clamp_hour(getattr(deps, 'NOTIFICATION_ACTIVE_HOURS_END', 23), 23)

    if active_start == active_end:
        is_active = True
    elif active_start < active_end:
        is_active = active_start <= hour < active_end
    else:
        is_active = hour >= active_start or hour < active_end

    if is_active:
        return {
            'label': 'active',
            'scan_multiplier': max(0.65, float(getattr(deps, 'NOTIFICATION_ACTIVE_SCAN_MULTIPLIER', 0.92))),
            'refresh_multiplier': max(0.7, float(getattr(deps, 'NOTIFICATION_ACTIVE_REFRESH_MULTIPLIER', 0.94))),
            'cooldown_multiplier': max(0.6, float(getattr(deps, 'NOTIFICATION_ACTIVE_COOLDOWN_MULTIPLIER', 0.9))),
        }

    return {
        'label': 'quiet',
        'scan_multiplier': max(1.0, float(getattr(deps, 'NOTIFICATION_QUIET_SCAN_MULTIPLIER', 1.28))),
        'refresh_multiplier': max(1.0, float(getattr(deps, 'NOTIFICATION_QUIET_REFRESH_MULTIPLIER', 1.36))),
        'cooldown_multiplier': max(1.0, float(getattr(deps, 'NOTIFICATION_QUIET_COOLDOWN_MULTIPLIER', 1.22))),
    }


def _resolve_notification_adaptive_profile(deps, now_ts=None):
    now_ts = float(now_ts if now_ts is not None else time.time())
    last_new_item_at = float(getattr(deps, 'notification_last_new_item_at', 0.0) or 0.0)
    idle_scan_streak = max(0, int(getattr(deps, 'notification_idle_scan_streak', 0) or 0))
    boost_window_sec = max(30.0, float(getattr(deps, 'NOTIFICATION_ADAPTIVE_BOOST_WINDOW_SEC', 210.0)))
    idle_threshold = max(1, int(getattr(deps, 'NOTIFICATION_ADAPTIVE_IDLE_THRESHOLD', 4) or 4))

    scan_multiplier = 1.0
    refresh_multiplier = 1.0
    boost_active = False
    idle_active = False

    if last_new_item_at > 0 and (now_ts - last_new_item_at) <= boost_window_sec:
        scan_multiplier *= min(1.0, max(0.5, float(getattr(deps, 'NOTIFICATION_ADAPTIVE_SCAN_BOOST_MULTIPLIER', 0.78))))
        refresh_multiplier *= min(1.0, max(0.55, float(getattr(deps, 'NOTIFICATION_ADAPTIVE_REFRESH_BOOST_MULTIPLIER', 0.84))))
        boost_active = True

    if idle_scan_streak >= idle_threshold:
        extra_idle_steps = min(5, idle_scan_streak - idle_threshold)
        scan_multiplier *= max(1.0, float(getattr(deps, 'NOTIFICATION_ADAPTIVE_IDLE_SCAN_MULTIPLIER', 1.18))) + (extra_idle_steps * 0.06)
        refresh_multiplier *= max(1.0, float(getattr(deps, 'NOTIFICATION_ADAPTIVE_IDLE_REFRESH_MULTIPLIER', 1.24))) + (extra_idle_steps * 0.08)
        idle_active = True

    return {
        'scan_multiplier': scan_multiplier,
        'refresh_multiplier': refresh_multiplier,
        'boost_active': boost_active,
        'idle_active': idle_active,
        'idle_scan_streak': idle_scan_streak,
        'last_new_item_at': last_new_item_at,
    }


def get_notification_schedule_snapshot(deps, now_ts=None, now_struct=None):
    now_ts = float(now_ts if now_ts is not None else time.time())
    schedule = _resolve_notification_schedule_profile(deps, now_struct=now_struct)
    adaptive = _resolve_notification_adaptive_profile(deps, now_ts=now_ts)
    boost_age_sec = None
    last_new_item_at = float(adaptive.get('last_new_item_at') or 0.0)
    if last_new_item_at > 0:
        boost_age_sec = max(0.0, now_ts - last_new_item_at)

    return {
        'period_label': str(schedule.get('label') or 'active'),
        'boost_active': bool(adaptive.get('boost_active')),
        'idle_active': bool(adaptive.get('idle_active')),
        'scan_multiplier': round(float(schedule.get('scan_multiplier', 1.0)) * float(adaptive.get('scan_multiplier', 1.0)), 3),
        'refresh_multiplier': round(float(schedule.get('refresh_multiplier', 1.0)) * float(adaptive.get('refresh_multiplier', 1.0)), 3),
        'idle_scan_streak': int(adaptive.get('idle_scan_streak', 0) or 0),
        'boost_age_sec': None if boost_age_sec is None else round(float(boost_age_sec), 1),
    }


def format_notification_schedule_snapshot(snapshot):
    snapshot = snapshot or {}
    period_label = str(snapshot.get('period_label') or 'active')
    if bool(snapshot.get('boost_active')):
        mode = 'boost'
    elif bool(snapshot.get('idle_active')):
        mode = 'idle'
    else:
        mode = 'steady'

    idle_scan_streak = int(snapshot.get('idle_scan_streak', 0) or 0)
    boost_age_sec = snapshot.get('boost_age_sec')
    boost_text = '-' if boost_age_sec is None else f'{float(boost_age_sec):.0f}s'
    return (
        f'period={period_label} mode={mode} '
        f'scanX={float(snapshot.get("scan_multiplier", 1.0)):.2f} '
        f'refreshX={float(snapshot.get("refresh_multiplier", 1.0)):.2f} '
        f'idleStreak={idle_scan_streak} boostAge={boost_text}'
    )


def get_random_notification_interval(deps):
    profile = _resolve_notification_schedule_profile(deps)
    adaptive = _resolve_notification_adaptive_profile(deps)
    low = max(1.0, float(deps.NOTIFICATION_SCAN_INTERVAL_MIN_SEC))
    high = max(low, float(deps.NOTIFICATION_SCAN_INTERVAL_MAX_SEC))
    span = max(0.0, high - low)
    base = low + (span * random.betavariate(2.4, 1.7))
    base *= float(profile['scan_multiplier'])
    base *= float(adaptive['scan_multiplier'])
    if span > 0 and random.random() < 0.16:
        base += random.uniform(span * 0.12, span * 0.55)
    if span > 0 and random.random() < 0.08:
        base -= random.uniform(span * 0.04, span * 0.18)
    upper = max(high * 1.85, high + max(span * 0.65, 2.0))
    lower = max(low * 0.96, low - max(span * 0.08, 0.25))
    base = max(lower, min(base, upper))
    return round(base, 2)


def get_random_notification_refresh_interval(deps):
    profile = _resolve_notification_schedule_profile(deps)
    adaptive = _resolve_notification_adaptive_profile(deps)
    low = max(5.0, float(deps.NOTIFICATION_REFRESH_INTERVAL_MIN_SEC))
    high = max(low, float(deps.NOTIFICATION_REFRESH_INTERVAL_MAX_SEC))
    span = max(0.0, high - low)
    base = low + (span * random.betavariate(2.9, 1.35))
    base *= float(profile['refresh_multiplier'])
    base *= float(adaptive['refresh_multiplier'])
    if span > 0 and random.random() < 0.24:
        base += random.uniform(max(6.0, span * 0.18), max(14.0, span * 0.72))
    if span > 0 and random.random() < 0.09:
        base -= random.uniform(span * 0.03, span * 0.12)
    upper = max(high * 1.9, high + max(18.0, span * 0.8))
    lower = max(low * 0.95, low - max(span * 0.06, 1.0))
    base = max(lower, min(base, upper))
    return round(base, 2)


def schedule_next_notification_refresh_interval(previous_interval, deps):
    profile = _resolve_notification_schedule_profile(deps)
    interval = float(get_random_notification_refresh_interval(deps))
    low = max(5.0, float(deps.NOTIFICATION_REFRESH_INTERVAL_MIN_SEC))
    high = max(low, float(deps.NOTIFICATION_REFRESH_INTERVAL_MAX_SEC))
    span = max(1.0, high - low)
    if previous_interval is not None:
        try:
            prev = max(5.0, float(previous_interval))
        except Exception:
            prev = 0.0
        if prev > 0:
            mix = random.uniform(0.45, 0.82)
            interval = (prev * mix) + (interval * (1 - mix))
            if random.random() < 0.22:
                interval += random.uniform(-span * 0.1, span * 0.22)

    cooldown_prob = max(0.0, min(1.0, float(deps.NOTIFICATION_REFRESH_COOLDOWN_PROB)))
    if random.random() < cooldown_prob:
        low = max(0.5, float(deps.NOTIFICATION_REFRESH_COOLDOWN_MIN_SEC))
        high = max(low, float(deps.NOTIFICATION_REFRESH_COOLDOWN_MAX_SEC))
        interval += random.uniform(low, high) * float(profile['cooldown_multiplier'])

    return round(max(5.0, interval), 2)


def get_random_maintenance_interval(deps):
    low = max(60.0, float(deps.MAINTENANCE_INTERVAL_MIN_SEC))
    high = max(low, float(deps.MAINTENANCE_INTERVAL_MAX_SEC))
    return round(random.uniform(low, high), 2)


def get_random_task_parallel(task_count, deps):
    if task_count <= 1:
        return 1
    low = max(1, min(deps.TASK_PARALLEL_MIN, task_count))
    high = max(low, min(deps.TASK_PARALLEL_MAX, task_count))
    return random.randint(low, high)
