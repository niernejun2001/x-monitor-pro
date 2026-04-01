from xmonitor.runtime.event_bus import (
    drain_msg_queue as _drain_msg_queue_impl,
    publish_new_data_event as _publish_new_data_event_impl,
)
from xmonitor.runtime.logging_support import (
    is_headless_verbose_logging_enabled as _is_headless_verbose_logging_enabled_impl,
    log_headless_debug as _log_headless_debug_impl,
    log_headless_exception as _log_headless_exception_impl,
    log_to_ui as _log_to_ui_impl,
)
from xmonitor.runtime.timing_helpers import (
    get_random_maintenance_interval as _get_random_maintenance_interval_impl,
    get_random_notification_interval as _get_random_notification_interval_impl,
    get_random_notification_refresh_interval as _get_random_notification_refresh_interval_impl,
    get_random_task_parallel as _get_random_task_parallel_impl,
    schedule_next_notification_refresh_interval as _schedule_next_notification_refresh_interval_impl,
)
from xmonitor.services.analysis.filter import reorder_articles_for_scan as _reorder_articles_for_scan_impl
from xmonitor.services.support.diagnostics import (
    as_json_safe as _as_json_safe_impl,
    capture_runtime_diagnostic as _capture_runtime_diagnostic_impl,
    probe_selectors_snapshot as _probe_selectors_snapshot_impl,
)


def build_core_event_exports(
    deps,
    *,
    runtime_log_file,
    msg_queue,
    headless_mode_getter,
    verbose_flag_getter,
    traceback_module,
):
    def log_to_ui(level, msg):
        return _log_to_ui_impl(level, msg, runtime_log_file=runtime_log_file, msg_queue=msg_queue)

    def publish_new_data_event(item):
        return _publish_new_data_event_impl(item, deps)

    def enqueue_new_data(item):
        publish_new_data_event(item)

    def drain_msg_queue(collect_new_data=False):
        return _drain_msg_queue_impl(deps, collect_new_data=collect_new_data)

    def is_headless_verbose_logging_enabled():
        return _is_headless_verbose_logging_enabled_impl(
            headless_mode=headless_mode_getter(),
            verbose_flag=verbose_flag_getter(),
        )

    def log_headless_debug(msg):
        return _log_headless_debug_impl(
            msg,
            enabled=is_headless_verbose_logging_enabled(),
            logger_fn=log_to_ui,
        )

    def log_headless_exception(context, err):
        return _log_headless_exception_impl(
            context,
            err,
            enabled=is_headless_verbose_logging_enabled(),
            logger_fn=log_to_ui,
            traceback_module=traceback_module,
        )

    def _as_json_safe(obj):
        return _as_json_safe_impl(obj)

    def _probe_selectors_snapshot(tab, selectors):
        return _probe_selectors_snapshot_impl(tab, selectors)

    def _capture_runtime_diagnostic(tab, stage, err=None, selectors=None, extra=None):
        return _capture_runtime_diagnostic_impl(
            tab,
            stage,
            deps,
            err=err,
            selectors=selectors,
            extra=extra,
        )

    def get_random_notification_interval():
        return _get_random_notification_interval_impl(deps)

    def get_random_notification_refresh_interval():
        return _get_random_notification_refresh_interval_impl(deps)

    def _schedule_next_notification_refresh_interval(previous_interval=None):
        return _schedule_next_notification_refresh_interval_impl(previous_interval, deps)

    def get_random_maintenance_interval():
        return _get_random_maintenance_interval_impl(deps)

    def get_random_task_parallel(task_count):
        return _get_random_task_parallel_impl(task_count, deps)

    def reorder_articles_for_scan(articles):
        return _reorder_articles_for_scan_impl(articles, deps)

    return {
        'log_to_ui': log_to_ui,
        'publish_new_data_event': publish_new_data_event,
        'enqueue_new_data': enqueue_new_data,
        'drain_msg_queue': drain_msg_queue,
        'is_headless_verbose_logging_enabled': is_headless_verbose_logging_enabled,
        'log_headless_debug': log_headless_debug,
        'log_headless_exception': log_headless_exception,
        '_as_json_safe': _as_json_safe,
        '_probe_selectors_snapshot': _probe_selectors_snapshot,
        '_capture_runtime_diagnostic': _capture_runtime_diagnostic,
        'get_random_notification_interval': get_random_notification_interval,
        'get_random_notification_refresh_interval': get_random_notification_refresh_interval,
        '_schedule_next_notification_refresh_interval': _schedule_next_notification_refresh_interval,
        'get_random_maintenance_interval': get_random_maintenance_interval,
        'get_random_task_parallel': get_random_task_parallel,
        'reorder_articles_for_scan': reorder_articles_for_scan,
    }
