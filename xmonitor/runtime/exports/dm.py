from xmonitor.runtime.exports.dm_common import build_dm_common_exports
from xmonitor.runtime.exports.dm_errors import build_dm_error_exports
from xmonitor.runtime.exports.dm_interaction import build_dm_interaction_exports
from xmonitor.runtime.exports.dm_pacing import build_dm_pacing_exports
from xmonitor.runtime.exports.dm_session import build_dm_session_exports


def build_dm_runtime_exports(
    deps,
    *,
    headless_mode_getter,
    base_multiplier,
    headless_extra_multiplier,
    reply_metrics_lock,
    reply_failure_streak_fn,
    adaptive_enabled,
    acceleration_enabled,
    reply_outcome_recent,
    queue_depth_fn,
    queue_accel_factor,
    normalize_handle_fn,
    notify_dm_user_cooldown,
    notify_dm_user_cooldown_lock,
    dm_user_cooldown_sec,
    dm_between_messages_min_sec,
    dm_between_messages_max_sec,
    log_to_ui_fn,
    log_headless_debug_fn,
):
    exports = {}
    exports.update(build_dm_common_exports())
    exports.update(build_dm_error_exports())
    exports.update(
        build_dm_pacing_exports(
            deps,
            headless_mode_getter=headless_mode_getter,
            base_multiplier=base_multiplier,
            headless_extra_multiplier=headless_extra_multiplier,
            reply_metrics_lock=reply_metrics_lock,
            reply_failure_streak_fn=reply_failure_streak_fn,
            adaptive_enabled=adaptive_enabled,
            acceleration_enabled=acceleration_enabled,
            reply_outcome_recent=reply_outcome_recent,
            queue_depth_fn=queue_depth_fn,
            queue_accel_factor=queue_accel_factor,
            normalize_handle_fn=normalize_handle_fn,
            notify_dm_user_cooldown=notify_dm_user_cooldown,
            notify_dm_user_cooldown_lock=notify_dm_user_cooldown_lock,
            dm_user_cooldown_sec=dm_user_cooldown_sec,
            dm_between_messages_min_sec=dm_between_messages_min_sec,
            dm_between_messages_max_sec=dm_between_messages_max_sec,
            log_to_ui_fn=log_to_ui_fn,
            log_headless_debug_fn=log_headless_debug_fn,
        )
    )
    exports.update(
        build_dm_interaction_exports(
            deps,
            headless_mode_getter=headless_mode_getter,
            log_to_ui_fn=log_to_ui_fn,
        )
    )
    exports.update(build_dm_session_exports(deps))
    return exports
