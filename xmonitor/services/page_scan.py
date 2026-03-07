import datetime
import random
import re
import time


def scan_task_worker(task, page, blocked_users, deps):
    log_to_ui = deps.log_to_ui
    scan_page_content = deps.scan_page_content
    should_skip_content_by_policy = deps.should_skip_content_by_policy
    should_skip_duplicate_content = deps.should_skip_duplicate_content
    enqueue_new_data = deps.enqueue_new_data
    save_state = deps.save_state
    monitor_tasks = deps.monitor_tasks
    pending_results = deps.pending_results
    history_ids = deps.history_ids
    data_lock = deps.data_lock

    return _scan_task_worker_impl(task, page, blocked_users, sys.modules[__name__])


def scan_task_with_tab(task, blocked_users, deps):
    global_browser = deps.global_browser
    browser_initialized = deps.browser_initialized
    log_to_ui = deps.log_to_ui
    scan_page_content_with_tab = deps.scan_page_content_with_tab
    should_skip_content_by_policy = deps.should_skip_content_by_policy
    should_skip_duplicate_content = deps.should_skip_duplicate_content
    enqueue_new_data = deps.enqueue_new_data
    save_state = deps.save_state
    monitor_tasks = deps.monitor_tasks
    pending_results = deps.pending_results
    history_ids = deps.history_ids
    data_lock = deps.data_lock
    tab_lock = deps.tab_lock
    TAB_OPEN_JITTER_MIN_SEC = deps.TAB_OPEN_JITTER_MIN_SEC
    TAB_OPEN_JITTER_MAX_SEC = deps.TAB_OPEN_JITTER_MAX_SEC

    return _scan_task_with_tab_impl(task, blocked_users, sys.modules[__name__])


def scan_page_content_with_tab(tab, url, blocked_list, deps):
    reorder_articles_for_scan = deps.reorder_articles_for_scan
    should_skip_content_by_policy = deps.should_skip_content_by_policy
    get_effective_delegated_account = deps.get_effective_delegated_account
    log_to_ui = deps.log_to_ui
    history_ids = deps.history_ids
    normalize_handle = deps.normalize_handle

    return _scan_page_content_with_tab_impl(tab, url, blocked_list, sys.modules[__name__])

