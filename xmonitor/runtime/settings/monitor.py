def _safe_float(raw, default_val):
    try:
        return float(raw)
    except Exception:
        return float(default_val)


def _safe_int(raw, default_val):
    try:
        return int(raw)
    except Exception:
        return int(default_val)


def _bool_not_off(raw, default='0'):
    return str(raw if raw is not None else default).strip().lower() not in {'0', 'false', 'no', 'off'}


def load_monitor_runtime_settings(env):
    env = env or {}
    updates_event_buffer_max = _safe_int(env.get('XMONITOR_UPDATES_EVENT_BUFFER_MAX', '5000'), 5000)
    updates_event_buffer_max = max(200, min(50000, int(updates_event_buffer_max)))
    return {
        'UPDATES_EVENT_BUFFER_MAX': updates_event_buffer_max,
        'NOTIFICATION_SCAN_INTERVAL_MIN_SEC': _safe_float(env.get('XMONITOR_NOTIFY_SCAN_MIN_SEC', '6'), 6.0),
        'NOTIFICATION_SCAN_INTERVAL_MAX_SEC': _safe_float(env.get('XMONITOR_NOTIFY_SCAN_MAX_SEC', '14'), 14.0),
        'NOTIFICATION_RECENT_WINDOW_MINUTES': _safe_int(env.get('XMONITOR_NOTIFY_RECENT_WINDOW_MIN', '45'), 45),
        'NOTIFICATION_MAX_SCAN_ARTICLES': _safe_int(env.get('XMONITOR_NOTIFY_MAX_ARTICLES', '180'), 180),
        'NOTIFICATION_VERBOSE_TRACE': _bool_not_off(env.get('XMONITOR_NOTIFY_VERBOSE_TRACE', '1'), '1'),
        'NOTIFICATION_TRACE_MAX_ARTICLES': _safe_int(env.get('XMONITOR_NOTIFY_TRACE_MAX_ARTICLES', '12'), 12),
        'NOTIFICATION_TRACE_TEXT_LEN': _safe_int(env.get('XMONITOR_NOTIFY_TRACE_TEXT_LEN', '120'), 120),
        'NOTIFICATION_REFRESH_INTERVAL_MIN_SEC': _safe_float(env.get('XMONITOR_NOTIFY_REFRESH_MIN_SEC', '55'), 55.0),
        'NOTIFICATION_REFRESH_INTERVAL_MAX_SEC': _safe_float(env.get('XMONITOR_NOTIFY_REFRESH_MAX_SEC', '135'), 135.0),
        'NOTIFICATION_REFRESH_SKIP_PROB': _safe_float(env.get('XMONITOR_NOTIFY_REFRESH_SKIP_PROB', '0.22'), 0.22),
        'NOTIFICATION_REFRESH_SOFT_NAV_PROB': _safe_float(env.get('XMONITOR_NOTIFY_REFRESH_SOFT_NAV_PROB', '0.24'), 0.24),
        'NOTIFICATION_REFRESH_COOLDOWN_PROB': _safe_float(env.get('XMONITOR_NOTIFY_REFRESH_COOLDOWN_PROB', '0.20'), 0.20),
        'NOTIFICATION_REFRESH_COOLDOWN_MIN_SEC': _safe_float(env.get('XMONITOR_NOTIFY_REFRESH_COOLDOWN_MIN_SEC', '16'), 16.0),
        'NOTIFICATION_REFRESH_COOLDOWN_MAX_SEC': _safe_float(env.get('XMONITOR_NOTIFY_REFRESH_COOLDOWN_MAX_SEC', '48'), 48.0),
        'NOTIFICATION_ACTIVE_HOURS_START': _safe_int(env.get('XMONITOR_NOTIFY_ACTIVE_HOURS_START', '8'), 8),
        'NOTIFICATION_ACTIVE_HOURS_END': _safe_int(env.get('XMONITOR_NOTIFY_ACTIVE_HOURS_END', '23'), 23),
        'NOTIFICATION_ACTIVE_SCAN_MULTIPLIER': _safe_float(env.get('XMONITOR_NOTIFY_ACTIVE_SCAN_MULTIPLIER', '0.92'), 0.92),
        'NOTIFICATION_ACTIVE_REFRESH_MULTIPLIER': _safe_float(env.get('XMONITOR_NOTIFY_ACTIVE_REFRESH_MULTIPLIER', '0.94'), 0.94),
        'NOTIFICATION_ACTIVE_COOLDOWN_MULTIPLIER': _safe_float(env.get('XMONITOR_NOTIFY_ACTIVE_COOLDOWN_MULTIPLIER', '0.90'), 0.90),
        'NOTIFICATION_QUIET_SCAN_MULTIPLIER': _safe_float(env.get('XMONITOR_NOTIFY_QUIET_SCAN_MULTIPLIER', '1.28'), 1.28),
        'NOTIFICATION_QUIET_REFRESH_MULTIPLIER': _safe_float(env.get('XMONITOR_NOTIFY_QUIET_REFRESH_MULTIPLIER', '1.36'), 1.36),
        'NOTIFICATION_QUIET_COOLDOWN_MULTIPLIER': _safe_float(env.get('XMONITOR_NOTIFY_QUIET_COOLDOWN_MULTIPLIER', '1.22'), 1.22),
        'NOTIFICATION_ADAPTIVE_BOOST_WINDOW_SEC': _safe_float(env.get('XMONITOR_NOTIFY_ADAPTIVE_BOOST_WINDOW_SEC', '210'), 210.0),
        'NOTIFICATION_ADAPTIVE_SCAN_BOOST_MULTIPLIER': _safe_float(env.get('XMONITOR_NOTIFY_ADAPTIVE_SCAN_BOOST_MULTIPLIER', '0.78'), 0.78),
        'NOTIFICATION_ADAPTIVE_REFRESH_BOOST_MULTIPLIER': _safe_float(env.get('XMONITOR_NOTIFY_ADAPTIVE_REFRESH_BOOST_MULTIPLIER', '0.84'), 0.84),
        'NOTIFICATION_ADAPTIVE_IDLE_THRESHOLD': _safe_int(env.get('XMONITOR_NOTIFY_ADAPTIVE_IDLE_THRESHOLD', '4'), 4),
        'NOTIFICATION_ADAPTIVE_IDLE_SCAN_MULTIPLIER': _safe_float(env.get('XMONITOR_NOTIFY_ADAPTIVE_IDLE_SCAN_MULTIPLIER', '1.18'), 1.18),
        'NOTIFICATION_ADAPTIVE_IDLE_REFRESH_MULTIPLIER': _safe_float(env.get('XMONITOR_NOTIFY_ADAPTIVE_IDLE_REFRESH_MULTIPLIER', '1.24'), 1.24),
        'NOTIFICATION_EMPTY_RECOVER_SOFT_THRESHOLD': _safe_int(env.get('XMONITOR_NOTIFY_EMPTY_RECOVER_SOFT_THRESHOLD', '3'), 3),
        'NOTIFICATION_EMPTY_RECOVER_HARD_THRESHOLD': _safe_int(env.get('XMONITOR_NOTIFY_EMPTY_RECOVER_HARD_THRESHOLD', '6'), 6),
        'NOTIFICATION_REPLY_ONLY_MODE': _bool_not_off(env.get('XMONITOR_NOTIFY_REPLY_ONLY', '1'), '1'),
        'TWITTER_CLI_ENABLED': _bool_not_off(env.get('XMONITOR_TWITTER_CLI_ENABLED', '1'), '1'),
        'TWITTER_CLI_NOTIFY_ENRICH': _bool_not_off(env.get('XMONITOR_TWITTER_CLI_NOTIFY_ENRICH', '1'), '1'),
        'TWITTER_CLI_TWEET_CACHE_TTL_SEC': _safe_float(env.get('XMONITOR_TWITTER_CLI_TWEET_CACHE_TTL_SEC', '300'), 300.0),
        'TWITTER_CLI_USER_CACHE_TTL_SEC': _safe_float(env.get('XMONITOR_TWITTER_CLI_USER_CACHE_TTL_SEC', '600'), 600.0),
    }
