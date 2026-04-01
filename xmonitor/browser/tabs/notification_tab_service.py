import random
import time


def init_notification_tab(blocked_users, deps):
    if not deps.global_browser or not deps.browser_initialized:
        return
    with deps.notification_tab_lock:
        if deps.notification_tab is not None:
            return
        try:
            deps.log_to_ui('info', '📬 创建持久通知标签页...')
            time.sleep(random.uniform(0.3, 1.1))
            deps._set_runtime_attr('notification_tab', deps.global_browser.new_tab())
            deps.notification_tab.get('https://x.com/notifications')
            try:
                deps.notification_tab.wait.ele_displayed('tag:article', timeout=10)
            except Exception:
                pass
            time.sleep(2)
            try:
                tabs = deps.notification_tab.eles('css:[role="tab"]', timeout=2)
                for tab in tabs:
                    tab_text = (tab.text or '').strip().lower()
                    if tab_text in ['全部', 'all']:
                        tab.click()
                        deps.log_to_ui('info', '📬 已切换到"全部"通知')
                        time.sleep(1)
                        break
            except Exception as e:
                deps.log_to_ui('debug', f'切换全部标签失败: {e}')
            deps.log_to_ui('success', '✅ 通知标签页已创建并保持打开')
            deps._set_runtime_attr('notification_last_refresh_at', 0.0)
            deps._set_runtime_attr('notification_refresh_interval', deps._schedule_next_notification_refresh_interval(deps.notification_refresh_interval))
            deps._set_runtime_attr('notification_empty_article_streak', 0)
        except Exception as e:
            deps.log_to_ui('error', f'创建通知标签页失败: {str(e)}')
            deps._set_runtime_attr('notification_tab', None)


def close_notification_tab(deps):
    with deps.notification_tab_lock:
        if deps.notification_tab:
            try:
                deps.notification_tab.close()
            except Exception:
                pass
            deps._set_runtime_attr('notification_tab', None)
            deps._set_runtime_attr('notification_last_refresh_at', 0.0)
            deps._set_runtime_attr('notification_empty_article_streak', 0)
            deps.log_to_ui('info', '📬 通知标签页已关闭')


def ensure_notification_tab(blocked_users, deps):
    with deps.notification_tab_lock:
        if deps.notification_tab is None:
            pass
        else:
            try:
                _ = deps.notification_tab.url
                return
            except Exception:
                deps._set_runtime_attr('notification_tab', None)
    init_notification_tab(blocked_users, deps)
