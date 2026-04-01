import concurrent.futures
import queue
import random
import threading
import traceback
from collections import deque

from xmonitor.runtime.exports.analysis import build_analysis_runtime_exports
from xmonitor.runtime.exports.core import (
    build_core_runtime_exports,
    initialize_runtime_components,
)
from xmonitor.runtime.exports.dm import build_dm_runtime_exports
from xmonitor.runtime.exports.notify import build_notify_runtime_exports
from xmonitor.runtime.exports.support import build_support_runtime_exports
from xmonitor.runtime.state_defaults import build_initial_runtime_objects


def assemble_runtime_module(
    deps,
    *,
    safe_float_fn,
    safe_int_fn,
    clamp_llm_timeout_impl,
    llm_timeout_default,
    llm_timeout_max,
    env_port_getter,
    logging_module,
    is_noise_notification_text_fn,
    normalize_handle_fn,
    normalize_one_line_fn,
    pick_best_status_id_fn,
    reply_to_you_keywords,
    score_notification_candidate_fn,
):
    vars(deps).update(
        build_support_runtime_exports(
            deps,
            safe_float_fn=safe_float_fn,
            safe_int_fn=safe_int_fn,
            clamp_llm_timeout_fn=lambda raw_timeout: clamp_llm_timeout_impl(
                raw_timeout,
                default_timeout=llm_timeout_default,
                timeout_max=llm_timeout_max,
            ),
            env_port_getter=env_port_getter,
            logging_module=logging_module,
        )
    )

    deps.LLM_FILTER_TIMEOUT_SEC = deps.clamp_llm_timeout(llm_timeout_default)
    deps.LLM_FILTER_TIMEOUT_MAX_SEC = llm_timeout_max

    vars(deps).update(build_analysis_runtime_exports(deps))
    vars(deps).update(
        build_notify_runtime_exports(
            deps,
            is_noise_notification_text_fn=is_noise_notification_text_fn,
            normalize_content_for_dedupe_fn=deps.normalize_content_for_dedupe,
            normalize_handle_fn=normalize_handle_fn,
            normalize_one_line_fn=normalize_one_line_fn,
            pick_best_status_id_fn=pick_best_status_id_fn,
            reply_to_you_keywords=reply_to_you_keywords,
            score_notification_candidate_fn=score_notification_candidate_fn,
        )
    )

    vars(deps).update(
        build_initial_runtime_objects(
            queue_module=queue,
            threading_module=threading,
            deque_factory=deque,
            random_module=random,
            concurrent_futures_module=concurrent.futures,
            updates_event_buffer_max=deps.UPDATES_EVENT_BUFFER_MAX,
            default_notify_reply_templates=deps.DEFAULT_NOTIFY_REPLY_TEMPLATES,
            default_dm_templates=deps.DEFAULT_DM_TEMPLATES,
            dm_llm_rewrite_dedupe_size=deps.DM_LLM_REWRITE_DEDUPE_SIZE,
            notification_refresh_interval_min_sec=deps.NOTIFICATION_REFRESH_INTERVAL_MIN_SEC,
            notification_refresh_interval_max_sec=deps.NOTIFICATION_REFRESH_INTERVAL_MAX_SEC,
        )
    )

    runtime_components = initialize_runtime_components(deps)
    deps.runtime_components = runtime_components
    vars(deps).update(runtime_components)

    logging_module.basicConfig(level=logging_module.INFO)
    vars(deps).update(
        build_core_runtime_exports(
            deps,
            runtime_log_file=deps.RUNTIME_LOG_FILE,
            msg_queue=deps.msg_queue,
            headless_mode_getter=lambda: deps.headless_mode,
            verbose_flag_getter=lambda: deps.HEADLESS_VERBOSE_LOG,
            traceback_module=traceback,
        )
    )
    vars(deps).update(
        build_dm_runtime_exports(
            deps,
            headless_mode_getter=lambda: deps.headless_mode,
            base_multiplier=deps.HUMANIZE_BASE_MULTIPLIER,
            headless_extra_multiplier=deps.HUMANIZE_HEADLESS_EXTRA_MULTIPLIER,
            reply_metrics_lock=deps.reply_metrics_lock,
            reply_failure_streak_fn=lambda: deps.reply_failure_streak,
            adaptive_enabled=deps.REPLY_ADAPTIVE_THROTTLE,
            acceleration_enabled=deps.REPLY_ENABLE_ACCELERATION,
            reply_outcome_recent=deps.reply_outcome_recent,
            queue_depth_fn=deps.notify_state_facade.get_pending_notify_count,
            queue_accel_factor=deps.REPLY_QUEUE_ACCEL_FACTOR,
            normalize_handle_fn=normalize_handle_fn,
            notify_dm_user_cooldown=deps.notify_dm_user_cooldown,
            notify_dm_user_cooldown_lock=deps.notify_dm_user_cooldown_lock,
            dm_user_cooldown_sec=deps.DM_USER_COOLDOWN_SEC,
            dm_between_messages_min_sec=deps.DM_BETWEEN_MESSAGES_MIN_SEC,
            dm_between_messages_max_sec=deps.DM_BETWEEN_MESSAGES_MAX_SEC,
            log_to_ui_fn=deps.log_to_ui,
            log_headless_debug_fn=deps.log_headless_debug,
        )
    )
    return runtime_components
