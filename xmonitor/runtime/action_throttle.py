import random
import time


def throttle_reply_action_if_needed(deps):
    now = time.time()
    jitter_gap = random.uniform(deps.REPLY_ACTION_GAP_MIN_SEC, deps.REPLY_ACTION_GAP_MAX_SEC)
    jitter_gap *= deps._get_adaptive_reply_gap_factor()
    jitter_gap *= deps._get_humanize_multiplier()
    wait_sec = 0.0
    with deps.reply_rate_limit_lock:
        getter = getattr(deps, '_get_runtime_attr', None)
        last_ts = getter('last_reply_action_ts', getattr(deps, 'last_reply_action_ts', 0.0)) if callable(getter) else getattr(deps, 'last_reply_action_ts', 0.0)
        elapsed = now - last_ts
        if elapsed < jitter_gap:
            wait_sec = jitter_gap - elapsed
        if wait_sec > 0:
            time.sleep(wait_sec)
        setter = getattr(deps, '_set_runtime_attr', None)
        if callable(setter):
            setter('last_reply_action_ts', time.time())
        else:
            deps.last_reply_action_ts = time.time()
    if wait_sec > 0.25:
        deps.log_to_ui('debug', f'🕒 发送前节流等待 {wait_sec:.2f}s（风控保护）')


def throttle_dm_action_if_needed(deps, stage_text='私信发送'):
    now = time.time()
    human_mult = deps._get_humanize_multiplier()
    jitter_gap = random.uniform(deps.DM_ACTION_GAP_MIN_SEC, deps.DM_ACTION_GAP_MAX_SEC) * human_mult
    wait_sec = 0.0
    with deps.dm_rate_limit_lock:
        getter = getattr(deps, '_get_runtime_attr', None)
        last_ts = getter('last_dm_action_ts', getattr(deps, 'last_dm_action_ts', 0.0)) if callable(getter) else getattr(deps, 'last_dm_action_ts', 0.0)
        elapsed = now - last_ts
        if elapsed < jitter_gap:
            wait_sec = jitter_gap - elapsed
        if wait_sec > 0:
            time.sleep(wait_sec)
        setter = getattr(deps, '_set_runtime_attr', None)
        if callable(setter):
            setter('last_dm_action_ts', time.time())
        else:
            deps.last_dm_action_ts = time.time()
    if wait_sec > 0.15:
        deps.log_to_ui('debug', f'📨 {stage_text}前防抖等待 {wait_sec:.2f}s')
        deps.log_headless_debug(f'{stage_text}节流完成，等待={wait_sec:.2f}s')
