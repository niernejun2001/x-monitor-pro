from xmonitor.browser.dom.interaction import (
    click_first_actionable_by_selectors as _click_first_actionable_by_selectors_impl,
    click_share_copy_link as _click_share_copy_link_impl,
    click_with_prompt_guard as _click_with_prompt_guard_impl,
    confirm_dm_closed_dual_stage as _confirm_dm_closed_dual_stage_impl,
    dismiss_pending_browser_prompt as _dismiss_pending_browser_prompt_impl,
    install_headless_dialog_guard as _install_headless_dialog_guard_impl,
)
from xmonitor.runtime.browser_guard import (
    is_cross_world_click_error as _is_cross_world_click_error_impl,
    is_unhandled_prompt_error as _is_unhandled_prompt_error_impl,
    prepare_reply_prompt_guard as _prepare_reply_prompt_guard_impl,
)
from xmonitor.services.dm.passcode_service import (
    handle_dm_passcode_prompt as _handle_dm_passcode_prompt_impl,
    warmup_dm_passcode_if_needed as _warmup_dm_passcode_if_needed_impl,
)
from xmonitor.services.dm.state_service import (
    clear_dm_unavailable_cache as _clear_dm_unavailable_cache_impl,
    get_status_link_from_item as _get_status_link_from_item_impl,
    is_dm_unavailable_cached as _is_dm_unavailable_cached_impl,
    mark_dm_unavailable as _mark_dm_unavailable_impl,
)


def build_dm_interaction_exports(deps, *, headless_mode_getter, log_to_ui_fn):
    def _is_unhandled_prompt_error(err):
        return _is_unhandled_prompt_error_impl(err)

    def _dismiss_pending_browser_prompt(tab, max_rounds=2):
        return _dismiss_pending_browser_prompt_impl(tab, deps, max_rounds=max_rounds)

    def _install_headless_dialog_guard(tab):
        return _install_headless_dialog_guard_impl(tab, deps)

    def _prepare_reply_prompt_guard(tab, stage=''):
        return _prepare_reply_prompt_guard_impl(
            tab,
            stage=stage,
            headless_mode=headless_mode_getter(),
            dismiss_pending_prompt_fn=_dismiss_pending_browser_prompt,
            install_headless_dialog_guard_fn=_install_headless_dialog_guard,
            log_to_ui_fn=log_to_ui_fn,
        )

    def _is_cross_world_click_error(err):
        return _is_cross_world_click_error_impl(err)

    def _click_first_actionable_by_selectors(tab, selectors):
        return _click_first_actionable_by_selectors_impl(tab, selectors)

    def _click_with_prompt_guard(tab, element, action_name, refetch_selectors=None):
        return _click_with_prompt_guard_impl(
            tab,
            element,
            action_name,
            deps,
            refetch_selectors=refetch_selectors,
        )

    def _is_dm_unavailable_cached(handle):
        return _is_dm_unavailable_cached_impl(handle, deps)

    def _mark_dm_unavailable(handle):
        return _mark_dm_unavailable_impl(handle, deps)

    def _clear_dm_unavailable_cache(handle):
        return _clear_dm_unavailable_cache_impl(handle, deps)

    def _get_status_link_from_item(item, matched_status_handle=None, matched_status_id=None):
        return _get_status_link_from_item_impl(
            item,
            deps,
            matched_status_handle=matched_status_handle,
            matched_status_id=matched_status_id,
        )

    def _click_share_copy_link(tab, target_article, fallback_link):
        return _click_share_copy_link_impl(tab, target_article, fallback_link, deps)

    def _handle_dm_passcode_prompt(tab):
        return _handle_dm_passcode_prompt_impl(tab, deps)

    def _warmup_dm_passcode_if_needed(tab, force=False):
        return _warmup_dm_passcode_if_needed_impl(tab, deps, force=force)

    def _confirm_dm_closed_dual_stage(tab, handle):
        return _confirm_dm_closed_dual_stage_impl(tab, handle, deps)

    return {
        '_is_unhandled_prompt_error': _is_unhandled_prompt_error,
        '_dismiss_pending_browser_prompt': _dismiss_pending_browser_prompt,
        '_install_headless_dialog_guard': _install_headless_dialog_guard,
        '_prepare_reply_prompt_guard': _prepare_reply_prompt_guard,
        '_is_cross_world_click_error': _is_cross_world_click_error,
        '_click_first_actionable_by_selectors': _click_first_actionable_by_selectors,
        '_click_with_prompt_guard': _click_with_prompt_guard,
        '_is_dm_unavailable_cached': _is_dm_unavailable_cached,
        '_mark_dm_unavailable': _mark_dm_unavailable,
        '_clear_dm_unavailable_cache': _clear_dm_unavailable_cache,
        '_get_status_link_from_item': _get_status_link_from_item,
        '_click_share_copy_link': _click_share_copy_link,
        '_handle_dm_passcode_prompt': _handle_dm_passcode_prompt,
        '_warmup_dm_passcode_if_needed': _warmup_dm_passcode_if_needed,
        '_confirm_dm_closed_dual_stage': _confirm_dm_closed_dual_stage,
    }
