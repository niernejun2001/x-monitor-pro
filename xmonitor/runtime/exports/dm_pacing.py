from xmonitor.runtime.action_throttle import (
    throttle_dm_action_if_needed as _throttle_dm_action_if_needed_impl,
    throttle_reply_action_if_needed as _throttle_reply_action_if_needed_impl,
)
from xmonitor.runtime.reply_metrics import record_reply_outcome_deps as _record_reply_outcome_deps_impl
from xmonitor.runtime.runtime_flow import (
    get_adaptive_reply_gap_factor as _get_adaptive_reply_gap_factor_impl,
    get_humanize_multiplier as _get_humanize_multiplier_impl,
    reserve_notify_dm_user_slot as _reserve_notify_dm_user_slot_impl,
)
from xmonitor.services.dm.flow_service import dm_humanized_idle as _dm_humanized_idle_impl
from xmonitor.services.dm.runtime import (
    humanized_gap_between_dm_messages as _humanized_gap_between_dm_messages_impl,
    humanized_type_dm_text as _humanized_type_dm_text_impl,
    paste_dm_text_exact as _paste_dm_text_exact_impl,
    poke_dm_editor_events as _poke_dm_editor_events_impl,
    refresh_dm_editor_state as _refresh_dm_editor_state_impl,
)
from xmonitor.services.dm.state_service import reply_humanized_idle as _reply_humanized_idle_impl


def build_dm_pacing_exports(
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
    def _get_humanize_multiplier():
        return _get_humanize_multiplier_impl(
            headless_mode=headless_mode_getter(),
            base_multiplier=base_multiplier,
            headless_extra_multiplier=headless_extra_multiplier,
            reply_metrics_lock=reply_metrics_lock,
            reply_failure_streak=reply_failure_streak_fn,
        )

    def _get_adaptive_reply_gap_factor():
        return _get_adaptive_reply_gap_factor_impl(
            adaptive_enabled=adaptive_enabled,
            acceleration_enabled=acceleration_enabled,
            reply_metrics_lock=reply_metrics_lock,
            reply_outcome_recent=reply_outcome_recent,
            reply_failure_streak=reply_failure_streak_fn,
            queue_depth=queue_depth_fn(),
            queue_accel_factor=queue_accel_factor,
        )

    def _check_reply_failure_budget(handle):
        return True, ''

    def _reserve_notify_dm_user_slot(handle, task_key=''):
        return _reserve_notify_dm_user_slot_impl(
            handle,
            task_key,
            normalize_handle_fn=normalize_handle_fn,
            cooldown_dict=notify_dm_user_cooldown,
            cooldown_lock=notify_dm_user_cooldown_lock,
            cooldown_sec=dm_user_cooldown_sec,
        )

    def _record_reply_outcome(handle, ok, err=''):
        return _record_reply_outcome_deps_impl(handle, ok, err, deps)

    def _throttle_reply_action_if_needed():
        return _throttle_reply_action_if_needed_impl(deps)

    def _throttle_dm_action_if_needed(stage_text='私信发送'):
        return _throttle_dm_action_if_needed_impl(deps, stage_text=stage_text)

    def _dm_humanized_idle(tab, low=0.08, high=0.28, stage_text='私信动作'):
        return _dm_humanized_idle_impl(tab, deps, low=low, high=high, stage_text=stage_text)

    def _humanized_type_dm_text(tab, editor, dm_text):
        return _humanized_type_dm_text_impl(
            tab,
            editor,
            dm_text,
            idle_func=_dm_humanized_idle,
            log_debug=log_headless_debug_fn,
        )

    def _paste_dm_text_exact(tab, editor, dm_text):
        return _paste_dm_text_exact_impl(
            tab,
            editor,
            dm_text,
            idle_func=_dm_humanized_idle,
            log_debug=log_headless_debug_fn,
        )

    def _refresh_dm_editor_state(tab, editor, dm_text):
        return _refresh_dm_editor_state_impl(tab, editor, dm_text)

    def _poke_dm_editor_events(tab, editor):
        return _poke_dm_editor_events_impl(tab, editor)

    def _humanized_gap_between_dm_messages(tab):
        return _humanized_gap_between_dm_messages_impl(
            tab,
            idle_func=_dm_humanized_idle,
            humanize_multiplier_fn=_get_humanize_multiplier,
            min_sec=dm_between_messages_min_sec,
            max_sec=dm_between_messages_max_sec,
            log_ui=log_to_ui_fn,
            log_debug=log_headless_debug_fn,
        )

    def _reply_humanized_idle(tab, low=0.16, high=0.46, stage_text='回复步骤'):
        return _reply_humanized_idle_impl(tab, deps, low=low, high=high, stage_text=stage_text)

    return {
        '_get_humanize_multiplier': _get_humanize_multiplier,
        '_get_adaptive_reply_gap_factor': _get_adaptive_reply_gap_factor,
        '_check_reply_failure_budget': _check_reply_failure_budget,
        '_reserve_notify_dm_user_slot': _reserve_notify_dm_user_slot,
        '_record_reply_outcome': _record_reply_outcome,
        '_throttle_reply_action_if_needed': _throttle_reply_action_if_needed,
        '_throttle_dm_action_if_needed': _throttle_dm_action_if_needed,
        '_dm_humanized_idle': _dm_humanized_idle,
        '_humanized_type_dm_text': _humanized_type_dm_text,
        '_paste_dm_text_exact': _paste_dm_text_exact,
        '_refresh_dm_editor_state': _refresh_dm_editor_state,
        '_poke_dm_editor_events': _poke_dm_editor_events,
        '_humanized_gap_between_dm_messages': _humanized_gap_between_dm_messages,
        '_reply_humanized_idle': _reply_humanized_idle,
    }
