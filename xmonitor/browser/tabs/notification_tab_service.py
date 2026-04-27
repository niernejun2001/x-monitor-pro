import random
import time

from xmonitor.services.notify.scan_logging import format_notify_error
from xmonitor.services.notify.schedule_state import update_notification_refresh_schedule


def _stabilize_notification_tab_after_open(tab, deps, *, article_timeout=10.0):
    deps._wait_document_ready(tab, timeout=5.5)
    try:
        tab.wait.ele_displayed('tag:article', timeout=article_timeout)
    except Exception:
        pass
    time.sleep(random.uniform(1.0, 1.8))
    try:
        tab.run_js('window.scrollTo(0, 0);')
    except Exception:
        pass
    try:
        tabs = tab.eles('css:[role="tab"]', timeout=2)
        for tab_btn in tabs:
            tab_text = (tab_btn.text or '').strip().lower()
            if tab_text in ['全部', 'all']:
                if tab_btn.attr('aria-selected') != 'true':
                    tab_btn.click()
                    deps.log_to_ui('info', '📬 已切换到"全部"通知')
                    time.sleep(random.uniform(0.6, 1.2))
                break
    except Exception as e:
        deps.log_to_ui('debug', f'切换全部标签失败: {e}')
    deps._wait_document_ready(tab, timeout=3.0)
    time.sleep(random.uniform(0.4, 0.9))


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
            _stabilize_notification_tab_after_open(deps.notification_tab, deps)
            deps.log_to_ui('success', '✅ 通知标签页已创建并保持打开')
            update_notification_refresh_schedule(
                deps,
                last_refresh_at=0.0,
                interval=deps._schedule_next_notification_refresh_interval(deps.notification_refresh_interval),
            )
            deps._set_runtime_attr('notification_tab_ready_at', time.time() + random.uniform(1.8, 3.4))
            deps._set_runtime_attr('notification_empty_article_streak', 0)
        except Exception as e:
            deps.log_to_ui('error', f'创建通知标签页失败: {format_notify_error(e)}')
            deps._set_runtime_attr('notification_tab', None)


def close_notification_tab(deps):
    with deps.notification_tab_lock:
        if deps.notification_tab:
            try:
                deps.notification_tab.close()
            except Exception:
                pass
            deps._set_runtime_attr('notification_tab', None)
            update_notification_refresh_schedule(deps, last_refresh_at=0.0)
            deps._set_runtime_attr('notification_tab_ready_at', 0.0)
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
