import random
import time


def run_headful_soft_maintenance(blocked_users, notify_enabled, deps):
    """
    有头模式轻量维护：
    - 默认不重启整浏览器，避免打断人工操作
    - 优先在通知标签页做保活
    """
    if not notify_enabled:
        return True
    if deps._is_dm_critical_active():
        deps._maybe_log_dm_critical_skip()
        return True

    try:
        deps.ensure_notification_tab(blocked_users)
        with deps.notification_tab_lock:
            if not deps.notification_tab:
                return False
            deps.notification_tab.get('https://x.com/notifications')
            time.sleep(random.uniform(0.7, 1.6))
            try:
                tabs = deps.notification_tab.eles('css:[role="tab"]', timeout=1.2)
                for tab in tabs:
                    tab_text = (tab.text or '').strip().lower()
                    if tab_text in ['全部', 'all']:
                        is_selected = tab.attr('aria-selected') == 'true'
                        if not is_selected:
                            tab.click()
                            time.sleep(random.uniform(0.3, 0.8))
                        break
            except Exception:
                pass
        deps._set_runtime_attr('notification_last_refresh_at', time.time())
        deps._set_runtime_attr('notification_refresh_interval', deps._schedule_next_notification_refresh_interval(deps.notification_refresh_interval))
        return True
    except Exception as e:
        deps.log_to_ui('warn', f'⚠️ 有头轻量维护失败: {e}')
        return False
