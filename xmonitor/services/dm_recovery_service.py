import os


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
              conversationOk: !!(conversationOk || editor),
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
        dm_err_text = str(dm_err or '')
        if deps._is_dm_closed_error_text(dm_err_text):
            confirmed_closed, close_reason = deps._confirm_dm_closed_dual_stage(tab, dm_handle)
            if confirmed_closed:
                deps.log_to_ui('info', f"📨 私信关闭已确认: @{deps.normalize_handle(dm_handle)} ({close_reason})")
                return False, dm_err_text, True
            deps.log_to_ui(
                'warn',
                f"⚠️ 私信关闭判定未通过二次确认，改为重试队列: @{deps.normalize_handle(dm_handle)} ({close_reason})"
            )
            return False, f"E_DM_EDITOR_NOT_FOUND: 二次确认未判定关闭 ({close_reason})", False
        return False, f"打开私信失败: {dm_err}", False
    if callable(mark_func):
        mark_func('open_dm')

    if not progress.get('link_sent'):
        ok_dm_1, err_dm_1 = deps._send_dm_message_with_retry(tab, share_link, handle=dm_handle)
        if not ok_dm_1:
            return False, f"发送私信链接失败: {err_dm_1}", False
        progress['link_sent'] = True
        if callable(mark_func):
            mark_func('send_dm_link')
        deps.log_to_ui('debug', '📨 已发送私信链接')
    else:
        deps.log_to_ui('debug', '📨 跳过重复发送私信链接（本流程已成功发送）')

    if not progress.get('text_sent'):
        dm_text_final = deps._sanitize_dm_message_text(dm_text)
        llm_fallback_used = False
        if callable(dm_text_supplier):
            ok_gen, dm_text_generated, gen_meta = dm_text_supplier()
            if not ok_gen:
                err_code = str((gen_meta or {}).get('error_code', 'E_DM_LLM_GENERATE_FAILED') or 'E_DM_LLM_GENERATE_FAILED')
                err_detail = str((gen_meta or {}).get('error_detail', '') or '第二条私信文案生成失败')
                if deps.DM_LLM_DOWN_FALLBACK_TEMPLATE and dm_text_final and deps._is_dm_llm_fallback_allowed(err_code, err_detail):
                    llm_fallback_used = True
                    deps.log_to_ui('warn', f'⚠️ 二条私信LLM不可用，已降级发送模板文案: {err_code}')
                else:
                    return False, f'{err_code}: {err_detail}', False
            else:
                dm_text_final = deps._sanitize_dm_message_text(dm_text_generated)
        if not dm_text_final:
            return False, 'E_DM_TEXT_EMPTY: 第二条私信文案为空', False
        deps._prepare_reply_prompt_guard(tab, '第二条私信前')
        deps._humanized_gap_between_dm_messages(tab)
        ok_dm_2, err_dm_2 = deps._send_dm_message_with_retry(tab, dm_text_final, handle=dm_handle)
        if not ok_dm_2:
            return False, f'发送私信文案失败: {err_dm_2}', False
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
        for idx, (label, tab_provider) in enumerate(strategies, start=1):
            try:
                work_tab = tab_provider()
            except Exception as e:
                last_err = f'{label}失败: {e}'
                deps.log_to_ui('warn', f'⚠️ 私信恢复步骤失败({idx}/{len(strategies)}): {last_err}')
                continue

            ok, err, dm_closed = run_dm_send_sequence_once(
                work_tab,
                handle_norm,
                share_link,
                dm_text,
                deps,
                mark_func=mark_func,
                progress=progress,
                dm_text_supplier=dm_text_supplier,
            )
            if ok:
                if idx > 1:
                    deps.log_to_ui('success', f'✅ 私信发送已通过恢复策略成功: {label}')
                return True, '', False, work_tab
            if dm_closed:
                return False, err, True, work_tab

            last_err = str(err or last_err)
            err_class = deps._classify_dm_error_text(last_err)
            if err_class == 'context':
                context_failure_count += 1
            else:
                context_failure_count = 0

            deps.log_to_ui('warn', f'⚠️ 私信发送失败({label}): {last_err}')
            if deps._is_dm_soft_send_error_text(last_err):
                deps.log_to_ui('debug', f'📨 软错误快速返回（跳过慢恢复）: {last_err[:80]}')
                return False, last_err, False, work_tab
            deps._capture_runtime_diagnostic(
                work_tab,
                f'dm_recovery_{idx}',
                err=last_err,
                selectors=[
                    'css:[data-testid="sendDMFromProfile"]',
                    'css:[data-testid="sendDM"]',
                    'css:textarea[data-testid="dm-composer-textarea"]',
                    'css:[data-testid="dmComposerTextInput"]',
                    'css:[data-testid="dm-composer-send-button"]',
                ],
                extra={
                    'strategy': label,
                    'strategy_idx': idx,
                    'headless_mode': _get_headless_mode(deps),
                    'handle': handle_norm,
                    'message_len': len(str(dm_text or '')),
                    'progress': dict(progress),
                    'dm_error_class': err_class,
                    'dm_context_failure_count': context_failure_count,
                },
            )

        if (
            (not best_effort)
            and deps.DM_RECOVERY_ENABLE_RESTART_BROWSER
            and context_failure_count >= deps.DM_CONTEXT_RESTART_THRESHOLD
        ):
            try:
                deps.log_to_ui('warn', f'⚠️ 触发上下文阈值恢复：重启浏览器并重建标签页（count={context_failure_count}）')
                deps.restart_global_browser()
                work_tab = deps.ensure_reply_work_tab(force_recreate=True)
                ok, err, dm_closed = run_dm_send_sequence_once(
                    work_tab,
                    handle_norm,
                    share_link,
                    dm_text,
                    deps,
                    mark_func=mark_func,
                    progress=progress,
                    dm_text_supplier=dm_text_supplier,
                )
                if ok:
                    return True, '', False, work_tab
                if dm_closed:
                    return False, err, True, work_tab
                last_err = str(err or last_err)
                deps._capture_runtime_diagnostic(
                    work_tab,
                    'dm_recovery_restart_failed',
                    err=last_err,
                    selectors=[
                        'css:[data-testid="sendDMFromProfile"]',
                        'css:textarea[data-testid="dm-composer-textarea"]',
                        'css:[data-testid="dm-composer-send-button"]',
                    ],
                    extra={
                        'headless_mode': _get_headless_mode(deps),
                        'handle': handle_norm,
                        'dm_error_class': deps._classify_dm_error_text(last_err),
                        'dm_context_failure_count': context_failure_count,
                    },
                )
            except Exception as e:
                last_err = f'重启浏览器恢复异常: {e}'

        if (not best_effort) and _get_headless_mode(deps) and deps.DM_RECOVERY_ENABLE_HEADFUL_FALLBACK:
            display_ok = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
            if deps.DM_RECOVERY_HEADFUL_REQUIRE_DISPLAY and not display_ok:
                deps.log_to_ui('warn', '⚠️ 有头兜底已启用但未检测到 DISPLAY，跳过本次有头兜底')
            else:
                prev_headless = _get_headless_mode(deps)
                switched = False
                try:
                    if prev_headless:
                        _set_headless_mode(deps, False)
                        switched = True
                        deps.log_to_ui('warn', '⚠️ 无头私信多次失败，临时切换有头模式执行本条私信兜底')
                        deps.restart_global_browser()
                    work_tab = deps.ensure_reply_work_tab(force_recreate=True)
                    ok, err, dm_closed = run_dm_send_sequence_once(
                        work_tab,
                        handle_norm,
                        share_link,
                        dm_text,
                        deps,
                        mark_func=mark_func,
                        progress=progress,
                        dm_text_supplier=dm_text_supplier,
                    )
                    if ok:
                        deps.log_to_ui('success', '✅ 有头兜底私信发送成功')
                        return True, '', False, work_tab
                    if dm_closed:
                        return False, err, True, work_tab
                    last_err = str(err or last_err)
                    deps._capture_runtime_diagnostic(
                        work_tab,
                        'dm_recovery_headful_fallback_failed',
                        err=last_err,
                        selectors=[
                            'css:[data-testid="sendDMFromProfile"]',
                            'css:textarea[data-testid="dm-composer-textarea"]',
                            'css:[data-testid="dm-composer-send-button"]',
                        ],
                        extra={'headless_mode': _get_headless_mode(deps), 'handle': handle_norm},
                    )
                except Exception as e:
                    last_err = f'有头兜底异常: {e}'
                    deps.log_to_ui('warn', f'⚠️ {last_err}')
                finally:
                    if switched:
                        _set_headless_mode(deps, prev_headless)
                        try:
                            deps.restart_global_browser()
                            deps.log_to_ui('info', '🔄 私信兜底结束，已恢复无头浏览器运行')
                        except Exception as restore_err:
                            deps.log_to_ui('warn', f'⚠️ 恢复无头浏览器失败，请手动重启: {restore_err}')
        return False, last_err, False, work_tab
    finally:
        if entered_critical:
            deps._leave_dm_critical()
