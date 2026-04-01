from xmonitor.browser.core.options import init_browser_options as _init_browser_options_impl
from xmonitor.browser.tabs.notification_tab_service import (
    close_notification_tab as _close_notification_tab_impl,
    ensure_notification_tab as _ensure_notification_tab_impl,
    init_notification_tab as _init_notification_tab_impl,
)
from xmonitor.browser.tabs.work_tab_service import ensure_reply_work_tab as _ensure_reply_work_tab_impl
from xmonitor.runtime.reply_metrics import (
    is_reply_flow_active_deps as _is_reply_flow_active_deps_impl,
    set_reply_flow_active_deps as _set_reply_flow_active_deps_impl,
)
from xmonitor.runtime.runtime_control import (
    start_monitor_thread as _start_monitor_thread_impl,
    stop_monitor_thread as _stop_monitor_thread_impl,
)
from xmonitor.services.platform.delegation import (
    ensure_delegated_account_session as _ensure_delegated_account_session_impl,
    get_current_account_handle as _get_current_account_handle_impl,
    switch_to_delegated_account as _switch_to_delegated_account_impl,
)


def build_notify_browser_exports(deps):
    def init_browser_options(port, user_data_path, force_headless=None, safe_mode=False):
        return _init_browser_options_impl(
            port,
            user_data_path,
            deps,
            force_headless=force_headless,
            safe_mode=safe_mode,
        )

    def get_effective_delegated_account():
        if not deps.delegated_enabled:
            return ''
        return str(deps.delegated_account or '').strip()

    def get_current_account_handle(page):
        return _get_current_account_handle_impl(page)

    def ensure_delegated_account_session(page, target_account):
        return _ensure_delegated_account_session_impl(page, target_account, deps)

    def switch_to_delegated_account(page, target_account):
        return _switch_to_delegated_account_impl(page, target_account, deps)

    def init_notification_tab(blocked_users):
        return _init_notification_tab_impl(blocked_users, deps)

    def close_notification_tab():
        return _close_notification_tab_impl(deps)

    def ensure_notification_tab(blocked_users):
        return _ensure_notification_tab_impl(blocked_users, deps)

    def start_monitor_thread():
        return _start_monitor_thread_impl(deps)

    def stop_monitor_thread(wait_timeout=15):
        return _stop_monitor_thread_impl(deps, wait_timeout=wait_timeout)

    def ensure_reply_work_tab(force_recreate=False):
        return _ensure_reply_work_tab_impl(deps, force_recreate=force_recreate)

    def _set_reply_flow_active(active):
        return _set_reply_flow_active_deps_impl(active, deps)

    def _is_reply_flow_active():
        return _is_reply_flow_active_deps_impl(deps)

    return {
        'init_browser_options': init_browser_options,
        'get_effective_delegated_account': get_effective_delegated_account,
        'get_current_account_handle': get_current_account_handle,
        'ensure_delegated_account_session': ensure_delegated_account_session,
        'switch_to_delegated_account': switch_to_delegated_account,
        'init_notification_tab': init_notification_tab,
        'close_notification_tab': close_notification_tab,
        'ensure_notification_tab': ensure_notification_tab,
        'start_monitor_thread': start_monitor_thread,
        'stop_monitor_thread': stop_monitor_thread,
        'ensure_reply_work_tab': ensure_reply_work_tab,
        '_set_reply_flow_active': _set_reply_flow_active,
        '_is_reply_flow_active': _is_reply_flow_active,
    }
