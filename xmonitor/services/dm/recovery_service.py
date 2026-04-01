from xmonitor.services.dm.recovery_support import (
    attempt_headful_dm_fallback,
    attempt_restart_recovery,
    execute_dm_recovery_strategies,
    prepare_second_dm_text,
    resolve_dm_send_failure,
    resolve_open_dm_failure,
)


def _get_headless_mode(deps):
    return bool(getattr(deps, 'headless_mode', False))


def _set_headless_mode(deps, value):
    deps.headless_mode = bool(value)


def read_dm_session_state(tab, handle='', deps=None):
    """读取当前私信会话状态，用于发送前闸门判断。"""
    handle_norm = deps.normalize_handle(handle)
    try:
        url = str(tab.url or '')
    except Exception:
        url = ''
    url_ok = deps._is_dm_context_url(url)
    out = {
        'url': url,
        'url_ok': bool(url_ok),
        'conversation_ok': bool(not handle_norm),
        'editor_ok': False,
        'send_button_present': False,
        'send_button_enabled': False,
        'ready': False,
    }
    try:
        state = tab.run_js(
            """
            const target = String(arguments[0] || '').toLowerCase();
            const lower = (v) => String(v || '').toLowerCase();
            const text = lower((document.body && document.body.innerText) ? document.body.innerText : '');
            const conversationOk = !target || text.includes('@' + target) || text.includes(target);
            const editor = document.querySelector(
              'textarea[data-testid="dm-composer-textarea"],textarea[placeholder="Message"],textarea[placeholder*="消息"],[data-testid="dmComposerTextInput"] [contenteditable]:not([contenteditable="false"]),div[role="textbox"][contenteditable]:not([contenteditable="false"]),[data-testid="dmComposerTextInput"] [contenteditable="true"],div[role="textbox"][contenteditable="true"]'
            );
            const sendBtn = document.querySelector(
              'button[data-testid="dm-composer-send-button"],[data-testid="dm-composer-send-button"],button[data-testid*="dm-composer-send"],[data-testid*="dm-composer-send"],[data-testid="dmComposerSendButton"],button[data-testid="dmComposerSendButton"],button[aria-label*="发送"],button[aria-label*="Send"]'
            );
            const sendDisabled = !!(sendBtn && (sendBtn.disabled || sendBtn.getAttribute('aria-disabled') === 'true'));
            return {
              conversationOk: !!conversationOk,
              editorOk: !!editor,
              sendPresent: !!sendBtn,
              sendEnabled: !!(sendBtn && !sendDisabled),
            };
            """,
            handle_norm,
        ) or {}
        out['conversation_ok'] = bool(state.get('conversationOk', out['conversation_ok']))
        out['editor_ok'] = bool(state.get('editorOk'))
        out['send_button_present'] = bool(state.get('sendPresent'))
        out['send_button_enabled'] = bool(state.get('sendEnabled'))
    except Exception:
        pass
    out['ready'] = bool(out['url_ok'] and out['editor_ok'] and out['conversation_ok'])
    return out


def run_dm_send_sequence_once(
    tab,
    dm_handle,
    share_link,
    dm_text,
    deps,
    mark_func=None,
    progress=None,
    dm_text_supplier=None,
):
    """执行一次完整私信发送（开私信 -> 发链接 -> 发文案）。"""
    if progress is None:
        progress = {'link_sent': False, 'text_sent': False}
    dm_editor, dm_err = deps._open_dm_editor_for_handle(tab, dm_handle)
    if not dm_editor:
        err_text, dm_closed = resolve_open_dm_failure(tab, dm_handle, dm_err, deps)
        return False, err_text, dm_closed
    if callable(mark_func):
        mark_func('open_dm')

    if not progress.get('link_sent'):
        ok_dm_1, err_dm_1 = deps._send_dm_message_with_retry(tab, share_link, handle=dm_handle)
        if not ok_dm_1:
            err_text, dm_closed = resolve_dm_send_failure(
                tab,
                dm_handle,
                err_dm_1,
                deps,
                prefix='发送私信链接失败',
            )
            return False, err_text, dm_closed
        progress['link_sent'] = True
        if callable(mark_func):
            mark_func('send_dm_link')
        deps.log_to_ui('debug', '📨 已发送私信链接')
    else:
        deps.log_to_ui('debug', '📨 跳过重复发送私信链接（本流程已成功发送）')

    if not progress.get('text_sent'):
        ok_text, dm_text_final, llm_fallback_used, text_state = prepare_second_dm_text(
            tab,
            dm_text,
            deps,
            dm_text_supplier=dm_text_supplier,
        )
        if not ok_text:
            return False, text_state, False
        if text_state == 'already_exists':
            progress['text_sent'] = True
            if callable(mark_func):
                mark_func('send_dm_text')
            deps.log_to_ui('debug', '📨 检测到第二条私信文案已存在当前会话，跳过重复发送')
            return True, '', False
        deps._prepare_reply_prompt_guard(tab, '第二条私信前')
        deps._humanized_gap_between_dm_messages(tab)
        ok_dm_2, err_dm_2 = deps._send_dm_message_with_retry(tab, dm_text_final, handle=dm_handle)
        if not ok_dm_2:
            err_text, dm_closed = resolve_dm_send_failure(
                tab,
                dm_handle,
                err_dm_2,
                deps,
                prefix='发送私信文案失败',
            )
            return False, err_text, dm_closed
        progress['text_sent'] = True
        if callable(mark_func):
            mark_func('send_dm_text')
        if llm_fallback_used:
            deps.log_to_ui('debug', '📨 已发送私信文案（模板降级）')
        else:
            deps.log_to_ui('debug', '📨 已发送私信文案')
    else:
        deps.log_to_ui('debug', '📨 跳过重复发送私信文案（本流程已成功发送）')
    return True, '', False


def run_dm_send_with_recovery(
    tab,
    dm_handle,
    share_link,
    dm_text,
    deps,
    mark_func=None,
    best_effort=False,
    progress=None,
    dm_text_supplier=None,
):
    """私信发送恢复策略：原标签页 -> 重建标签页 -> 重启浏览器 -> 有头兜底。"""
    handle_norm = deps.normalize_handle(dm_handle)
    last_err = '发送私信失败'
    work_tab = tab
    entered_critical = deps._enter_dm_critical('dm_send_recovery')
    progress = dict(progress or {})
    progress.setdefault('link_sent', False)
    progress.setdefault('text_sent', False)
    context_failure_count = 0

    strategies = [('当前标签页', lambda: work_tab)]
    if (not best_effort) and deps.DM_RECOVERY_ENABLE_RECREATE_TAB:
        strategies.append(('重建回复标签页', lambda: deps.ensure_reply_work_tab(force_recreate=True)))

    try:
        status, work_tab, last_err, context_failure_count, dm_closed = execute_dm_recovery_strategies(
            strategies=strategies,
            work_tab=work_tab,
            handle_norm=handle_norm,
            share_link=share_link,
            dm_text=dm_text,
            deps=deps,
            mark_func=mark_func,
            progress=progress,
            dm_text_supplier=dm_text_supplier,
            get_headless_mode_fn=_get_headless_mode,
            run_sequence_fn=run_dm_send_sequence_once,
        )
        if status == 'ok':
            return True, '', False, work_tab
        if dm_closed:
            return False, last_err, True, work_tab
        if status == 'stop':
            return False, last_err, False, work_tab

        if (
            (not best_effort)
            and deps.DM_RECOVERY_ENABLE_RESTART_BROWSER
            and context_failure_count >= deps.DM_CONTEXT_RESTART_THRESHOLD
        ):
            status, work_tab, last_err, dm_closed = attempt_restart_recovery(
                work_tab=work_tab,
                handle_norm=handle_norm,
                share_link=share_link,
                dm_text=dm_text,
                deps=deps,
                mark_func=mark_func,
                progress=progress,
                dm_text_supplier=dm_text_supplier,
                context_failure_count=context_failure_count,
                get_headless_mode_fn=_get_headless_mode,
                run_sequence_fn=run_dm_send_sequence_once,
            )
            if status == 'ok':
                return True, '', False, work_tab
            if dm_closed:
                return False, last_err, True, work_tab

        if (not best_effort) and _get_headless_mode(deps) and deps.DM_RECOVERY_ENABLE_HEADFUL_FALLBACK:
            status, work_tab, fallback_err, dm_closed = attempt_headful_dm_fallback(
                work_tab=work_tab,
                handle_norm=handle_norm,
                share_link=share_link,
                dm_text=dm_text,
                deps=deps,
                mark_func=mark_func,
                progress=progress,
                dm_text_supplier=dm_text_supplier,
                get_headless_mode_fn=_get_headless_mode,
                set_headless_mode_fn=_set_headless_mode,
                run_sequence_fn=run_dm_send_sequence_once,
            )
            if fallback_err:
                last_err = fallback_err
            if status == 'ok':
                return True, '', False, work_tab
            if dm_closed:
                return False, last_err, True, work_tab
        return False, last_err, False, work_tab
    finally:
        if entered_critical:
            deps._leave_dm_critical()
