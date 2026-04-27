def update_notification_refresh_schedule(deps, *, last_refresh_at=None, interval=None):
    if last_refresh_at is None:
        last_refresh_at = float(getattr(deps, 'notification_last_refresh_at', 0.0) or 0.0)
    if interval is None:
        interval = float(getattr(deps, 'notification_refresh_interval', 0.0) or 0.0)

    last_refresh_at = float(last_refresh_at or 0.0)
    interval = float(interval or 0.0)
    next_refresh_at = last_refresh_at + interval if last_refresh_at > 0 and interval > 0 else 0.0

    deps._set_runtime_attr('notification_last_refresh_at', last_refresh_at)
    deps._set_runtime_attr('notification_refresh_interval', interval)
    deps._set_runtime_attr('notification_next_refresh_at', next_refresh_at)
    return next_refresh_at
