import random
import time

from xmonitor.services.dm.open_support import (
    DM_COMPOSE_NO_RESULT_MSG,
    DM_PLATFORM_CLOSED_MSG,
    DM_PROFILE_NO_BUTTON_MSG,
    capture_dm_open_failure,
    load_dm_profile_page,
    mark_dm_unavailable_and_return,
    try_open_dm_via_direct_compose,
    try_open_dm_via_profile_click,
)
from xmonitor.services.dm.open_probe import (
    direct_compose_state_indicates_closed,
    find_dm_editor,
    has_cannot_dm_hint,
    inspect_direct_compose_picker_state,
    page_mentions_handle,
    try_rescue_dm_popup,
    wait_dm_editor_or_closed,
)


def open_dm_editor_for_handle(tab, handle, deps, ignore_cached_unavailable=False):
    normalize_handle = deps.normalize_handle
    _is_dm_unavailable_cached = deps._is_dm_unavailable_cached
    DM_PROFILE_BUTTON_SELECTORS = deps.DM_PROFILE_BUTTON_SELECTORS
    DM_EDITOR_SELECTORS = deps.DM_EDITOR_SELECTORS
    DM_ENTRY_MODE = deps.DM_ENTRY_MODE
    DM_PROFILE_NO_BUTTON_AS_CLOSED = deps.DM_PROFILE_NO_BUTTON_AS_CLOSED
    DM_REJECT_NEW_MESSAGE_OVERLAY = deps.DM_REJECT_NEW_MESSAGE_OVERLAY
    DM_EDITOR_OPEN_RETRY_HEADLESS = deps.DM_EDITOR_OPEN_RETRY_HEADLESS
    DM_EDITOR_OPEN_RETRY_NORMAL = deps.DM_EDITOR_OPEN_RETRY_NORMAL
    _capture_runtime_diagnostic = deps._capture_runtime_diagnostic
    _click_with_prompt_guard = deps._click_with_prompt_guard
    _dm_humanized_idle = deps._dm_humanized_idle
    _handle_dm_passcode_prompt = deps._handle_dm_passcode_prompt
    _wait_document_ready = deps._wait_document_ready
    _wait_first_actionable = deps._wait_first_actionable
    _wait_first_visible = deps._wait_first_visible
    headless_mode = deps.headless_mode
    log_headless_debug = deps.log_headless_debug
    log_to_ui = deps.log_to_ui
    """打开某用户私信编辑框，返回编辑框元素。"""
    handle_norm = normalize_handle(handle)
    if not handle_norm:
        return None, "缺少目标用户handle"
    if (not ignore_cached_unavailable) and _is_dm_unavailable_cached(handle_norm):
        return None, "该用户当前不可私信（缓存命中）"
    entry_path = "init"
    entry_stage = "init"

    dm_btn_selectors = list(DM_PROFILE_BUTTON_SELECTORS)
    editor = None
    dm_btn_seen = False
    profile_opened_rounds = 0
    editor_selectors = list(DM_EDITOR_SELECTORS)
    cannot_dm_keywords = [
        "cannot send direct messages",
        "can't be messaged",
        "unable to message",
        "you can’t message this account",
        "该用户无法接收私信",
        "无法向该用户发送私信",
        "不能给该用户发私信",
        "无法发送私信",
    ]

    def _has_cannot_dm_hint():
        return has_cannot_dm_hint(tab, cannot_dm_keywords)

    def _find_dm_btn():
        return _wait_first_actionable(tab, dm_btn_selectors, timeout=1.8, poll=0.1)

    def _page_mentions_handle():
        return page_mentions_handle(tab, handle_norm)

    def _find_editor(timeout_each=2.5):
        return find_dm_editor(tab, editor_selectors, DM_REJECT_NEW_MESSAGE_OVERLAY, timeout_each=timeout_each)

    def _wait_editor_or_closed(timeout_sec=3.2):
        return wait_dm_editor_or_closed(
            tab,
            editor_selectors,
            DM_REJECT_NEW_MESSAGE_OVERLAY,
            cannot_dm_keywords,
            timeout_sec=timeout_sec,
        )

    if DM_PROFILE_NO_BUTTON_AS_CLOSED and DM_ENTRY_MODE in {"direct_compose_first", "dual_probe"}:
        entry_path = "profile_precheck"
        entry_stage = "profile_precheck_open"
        profile_opened_rounds += 1
        tab.get(f"https://x.com/{handle_norm}")
        _wait_document_ready(tab, timeout=5.5)
        try:
            tab.wait.ele_displayed('tag:main', timeout=8)
        except Exception:
            pass
        time.sleep(random.uniform(0.35, 0.7))
        if _has_cannot_dm_hint():
            return mark_dm_unavailable_and_return(deps, handle_norm, DM_PLATFORM_CLOSED_MSG)
        precheck_dm_btn = _find_dm_btn()
        if precheck_dm_btn:
            dm_btn_seen = True
        else:
            return mark_dm_unavailable_and_return(deps, handle_norm, DM_PROFILE_NO_BUTTON_MSG)

    if DM_ENTRY_MODE in {"direct_compose_first", "dual_probe"}:
        entry_path = "direct_compose"
        editor_direct, direct_state, entry_stage = try_open_dm_via_direct_compose(
            tab,
            handle_norm,
            wait_document_ready=_wait_document_ready,
            dm_humanized_idle=_dm_humanized_idle,
            handle_dm_passcode_prompt=_handle_dm_passcode_prompt,
            wait_editor_or_closed=_wait_editor_or_closed,
            page_mentions_handle=_page_mentions_handle,
            wait_first_actionable=_wait_first_actionable,
            wait_first_visible=_wait_first_visible,
            click_with_prompt_guard=_click_with_prompt_guard,
            try_rescue_dm_popup_func=try_rescue_dm_popup,
            inspect_direct_compose_picker_state_func=inspect_direct_compose_picker_state,
            direct_compose_state_indicates_closed_func=direct_compose_state_indicates_closed,
            log_headless_debug=log_headless_debug,
            log_to_ui=log_to_ui,
        )
        if editor_direct:
            return editor_direct, ""
        if direct_state == "closed":
            return mark_dm_unavailable_and_return(deps, handle_norm, DM_PLATFORM_CLOSED_MSG)

    entry_path = "profile_click"
    open_attempts = DM_EDITOR_OPEN_RETRY_HEADLESS if headless_mode else DM_EDITOR_OPEN_RETRY_NORMAL
    editor_profile, profile_err, opened_rounds_delta, dm_btn_seen_profile = try_open_dm_via_profile_click(
        tab,
        handle_norm,
        open_attempts=open_attempts,
        has_cannot_dm_hint=_has_cannot_dm_hint,
        find_dm_btn=_find_dm_btn,
        click_with_prompt_guard=lambda target_tab, element, action_name: _click_with_prompt_guard(
            target_tab,
            element,
            action_name,
            refetch_selectors=dm_btn_selectors,
        ),
        wait_editor_or_closed=_wait_editor_or_closed,
        page_mentions_handle=_page_mentions_handle,
        try_rescue_dm_popup_func=try_rescue_dm_popup,
        log_headless_debug=log_headless_debug,
        log_to_ui=log_to_ui,
        handle_dm_passcode_prompt=_handle_dm_passcode_prompt,
        wait_document_ready=_wait_document_ready,
        load_profile_page=lambda target_tab, target_handle, attempt: load_dm_profile_page(target_tab, target_handle, attempt, deps),
    )
    profile_opened_rounds += opened_rounds_delta
    dm_btn_seen = dm_btn_seen or dm_btn_seen_profile
    if editor_profile:
        return editor_profile, ""
    if profile_err == DM_PLATFORM_CLOSED_MSG:
        return mark_dm_unavailable_and_return(deps, handle_norm, DM_PLATFORM_CLOSED_MSG)

    if _has_cannot_dm_hint():
        return mark_dm_unavailable_and_return(deps, handle_norm, DM_PLATFORM_CLOSED_MSG)

    if (
        DM_PROFILE_NO_BUTTON_AS_CLOSED
        and profile_opened_rounds > 0
        and (not dm_btn_seen)
    ):
        return mark_dm_unavailable_and_return(deps, handle_norm, DM_PROFILE_NO_BUTTON_MSG)

    # profile_first 模式下，只有在资料页入口失败时才回退到直达私信搜索路径。
    if DM_ENTRY_MODE == "profile_first":
        entry_path = "direct_compose"
        editor_direct_fallback, direct_state, entry_stage = try_open_dm_via_direct_compose(
            tab,
            handle_norm,
            wait_document_ready=_wait_document_ready,
            dm_humanized_idle=_dm_humanized_idle,
            handle_dm_passcode_prompt=_handle_dm_passcode_prompt,
            wait_editor_or_closed=_wait_editor_or_closed,
            page_mentions_handle=_page_mentions_handle,
            wait_first_actionable=_wait_first_actionable,
            wait_first_visible=_wait_first_visible,
            click_with_prompt_guard=_click_with_prompt_guard,
            try_rescue_dm_popup_func=try_rescue_dm_popup,
            inspect_direct_compose_picker_state_func=inspect_direct_compose_picker_state,
            direct_compose_state_indicates_closed_func=direct_compose_state_indicates_closed,
            log_headless_debug=log_headless_debug,
            log_to_ui=log_to_ui,
        )
        if editor_direct_fallback:
            log_to_ui("debug", f"📨 资料页私信入口失败，已回退直达私信入口: @{handle_norm}")
            return editor_direct_fallback, ""
        if direct_state == "closed":
            return mark_dm_unavailable_and_return(deps, handle_norm, DM_PLATFORM_CLOSED_MSG)

    return capture_dm_open_failure(
        tab,
        handle_norm,
        dm_btn_selectors,
        editor_selectors,
        open_attempts=open_attempts,
        headless_mode=headless_mode,
        dm_entry_mode=DM_ENTRY_MODE,
        entry_path=entry_path,
        entry_stage=entry_stage,
        deps=deps,
    )
