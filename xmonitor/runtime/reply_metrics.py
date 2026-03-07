from xmonitor.services.reply_runtime import is_reply_flow_active, record_reply_outcome, set_reply_flow_active


def set_reply_flow_active_deps(active, deps):
    return set_reply_flow_active(
        active,
        state_lock=deps.reply_flow_state_lock,
        state_setter=lambda value: deps._set_runtime_attr('reply_flow_active', bool(value)),
    )


def is_reply_flow_active_deps(deps):
    return is_reply_flow_active(
        state_lock=deps.reply_flow_state_lock,
        state_getter=lambda: deps._get_runtime_attr('reply_flow_active', False),
    )


def record_reply_outcome_deps(handle, ok, err, deps):
    return record_reply_outcome(
        handle,
        ok,
        err,
        normalize_handle_fn=deps.normalize_handle,
        metrics_lock=deps.reply_metrics_lock,
        outcome_recent=deps.reply_outcome_recent,
        failure_streak_getter=lambda: deps._get_runtime_attr('reply_failure_streak', 0),
        failure_streak_setter=lambda value: deps._set_runtime_attr('reply_failure_streak', int(value)),
        handle_failures=deps.reply_handle_failures,
        failure_window_sec=deps.REPLY_FAILURE_WINDOW_SEC,
        failure_budget_max=deps.REPLY_FAILURE_BUDGET_MAX,
        failure_cooldown_sec=deps.REPLY_FAILURE_COOLDOWN_SEC,
    )
