import random


def get_random_notification_interval(deps):
    low = max(1.0, float(deps.NOTIFICATION_SCAN_INTERVAL_MIN_SEC))
    high = max(low, float(deps.NOTIFICATION_SCAN_INTERVAL_MAX_SEC))
    base = random.uniform(low, high)
    if random.random() < 0.12:
        base += random.uniform(high * 0.6, high * 1.8)
    if random.random() < 0.06:
        base *= random.uniform(0.72, 0.92)
    upper = max(high * 3.2, high + 2.0)
    base = max(low * 0.85, min(base, upper))
    return round(base, 2)


def get_random_notification_refresh_interval(deps):
    low = max(5.0, float(deps.NOTIFICATION_REFRESH_INTERVAL_MIN_SEC))
    high = max(low, float(deps.NOTIFICATION_REFRESH_INTERVAL_MAX_SEC))
    base = random.uniform(low, high)
    if random.random() < 0.18:
        base += random.uniform(6.0, 22.0)
    if random.random() < 0.08:
        base *= random.uniform(0.82, 0.95)
    upper = max(high * 2.2, high + 8.0)
    base = max(low * 0.9, min(base, upper))
    return round(base, 2)


def schedule_next_notification_refresh_interval(previous_interval, deps):
    interval = float(get_random_notification_refresh_interval(deps))
    if previous_interval is not None:
        try:
            prev = max(5.0, float(previous_interval))
        except Exception:
            prev = 0.0
        if prev > 0 and random.random() < 0.35:
            mix = random.uniform(0.35, 0.75)
            interval = (prev * mix) + (interval * (1 - mix))

    cooldown_prob = max(0.0, min(1.0, float(deps.NOTIFICATION_REFRESH_COOLDOWN_PROB)))
    if random.random() < cooldown_prob:
        low = max(0.5, float(deps.NOTIFICATION_REFRESH_COOLDOWN_MIN_SEC))
        high = max(low, float(deps.NOTIFICATION_REFRESH_COOLDOWN_MAX_SEC))
        interval += random.uniform(low, high)

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
