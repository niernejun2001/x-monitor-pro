from xmonitor.services.notify.scan import scan_notifications_page as _scan_notifications_page_impl
from xmonitor.services.notify.tab_runtime import scan_persistent_notification_tab as _scan_persistent_notification_tab_impl
from xmonitor.services.scan.page_scan import (
    scan_page_content_with_tab as _scan_page_content_with_tab_impl,
    scan_task_with_tab as _scan_task_with_tab_impl,
    scan_task_worker as _scan_task_worker_impl,
)
from xmonitor.services.scan.tweet_scan import scan_page_content as _scan_page_content_impl


def build_notify_scan_exports(deps):
    def scan_page_content(page, url, blocked_list):
        return _scan_page_content_impl(page, url, blocked_list, deps)

    def scan_notifications_page(page, blocked_list, max_recent_minutes=None, allow_navigation=True):
        return _scan_notifications_page_impl(
            page,
            blocked_list,
            max_recent_minutes,
            deps,
            allow_navigation=allow_navigation,
        )

    def scan_persistent_notification_tab(blocked_users, max_recent_minutes=None, allow_refresh=True):
        return _scan_persistent_notification_tab_impl(
            blocked_users,
            deps,
            max_recent_minutes=max_recent_minutes,
            allow_refresh=allow_refresh,
        )

    def scan_task_worker(task, page, blocked_users):
        return _scan_task_worker_impl(task, page, blocked_users, deps)

    def scan_task_with_tab(task, blocked_users):
        return _scan_task_with_tab_impl(task, blocked_users, deps)

    def scan_page_content_with_tab(tab, url, blocked_list):
        return _scan_page_content_with_tab_impl(tab, url, blocked_list, deps)

    return {
        'scan_page_content': scan_page_content,
        'scan_notifications_page': scan_notifications_page,
        'scan_persistent_notification_tab': scan_persistent_notification_tab,
        'scan_task_worker': scan_task_worker,
        'scan_task_with_tab': scan_task_with_tab,
        'scan_page_content_with_tab': scan_page_content_with_tab,
    }
