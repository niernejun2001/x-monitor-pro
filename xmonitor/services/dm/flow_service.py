import random
import time


def should_use_share_link_quick_path(deps):
    mode = str(deps.SHARE_LINK_QUICK_PATH_MODE or 'always').strip().lower()
    if mode == 'off':
        return False
    if mode == 'always':
        return True
    if not deps.SHARE_LINK_QUICK_PATH:
        return False
    queue_depth = deps.notify_state_facade.get_pending_notify_count()
    if queue_depth < 16:
        return False
    with deps.reply_metrics_lock:
        outcomes = list(deps.reply_outcome_recent)
        streak = int(deps.reply_failure_streak)
    if streak > 0:
        return False
    if len(outcomes) < 8:
        return False
    success_rate = sum(outcomes) / len(outcomes)
    return success_rate >= 0.9


def dm_humanized_idle(tab, deps, low=0.08, high=0.28, stage_text='私信动作'):
    mult = deps._get_humanize_multiplier()
    low_v = max(0.02, float(low) * mult)
    high_v = max(low_v, float(high) * mult)
    if tab and random.random() < deps.DM_HUMAN_SCROLL_CHANCE:
        delta = random.randint(-220, 220)
        if abs(delta) < 40:
            delta = 80 if delta >= 0 else -80
        try:
            tab.run_js('window.scrollBy(0, arguments[0]);', delta)
            time.sleep(random.uniform(0.04, 0.16))
            if random.random() < 0.35:
                tab.run_js('window.scrollBy(0, arguments[0]);', -int(delta * random.uniform(0.2, 0.6)))
        except Exception:
            pass
    pause = random.uniform(low_v, high_v)
    time.sleep(pause)
    deps.log_headless_debug(f'{stage_text}随机停顿 {pause:.2f}s')


def ensure_dm_context_for_handle(tab, handle, deps):
    handle_norm = deps.normalize_handle(handle)
    try:
        current_url = str(tab.url or '')
    except Exception:
        current_url = ''
    if deps._is_dm_context_url(current_url):
        return True
    if not handle_norm:
        return False
    editor, dm_err = deps._open_dm_editor_for_handle(tab, handle_norm)
    if editor:
        return True
    deps.log_to_ui('debug', f'📨 DM上下文守卫未恢复会话: handle=@{handle_norm}, err={dm_err or "-"}, url={current_url or "-"}')
    return False
