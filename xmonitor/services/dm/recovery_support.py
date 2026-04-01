import os


def resolve_open_dm_failure(tab, dm_handle, dm_err, deps):
    dm_err_text = str(dm_err or '')
    if deps._is_dm_closed_error_text(dm_err_text):
        confirmed_closed, close_reason = deps._confirm_dm_closed_dual_stage(tab, dm_handle)
        if confirmed_closed:
            deps.log_to_ui('info', f"📨 私信关闭已确认: @{deps.normalize_handle(dm_handle)} ({close_reason})")
            return dm_err_text, True
        deps.log_to_ui(
            'warn',
            f"⚠️ 私信关闭判定未通过二次确认，改为重试队列: @{deps.normalize_handle(dm_handle)} ({close_reason})"
        )
        return f"E_DM_EDITOR_NOT_FOUND: 二次确认未判定关闭 ({close_reason})", False
    return f"打开私信失败: {dm_err}", False


def resolve_dm_send_failure(tab, dm_handle, err_text, deps, *, prefix):
    err_text = str(err_text or '')
    if deps._is_dm_closed_error_text(err_text):
        confirmed_closed, close_reason = deps._confirm_dm_closed_dual_stage(tab, dm_handle)
        if confirmed_closed:
            deps.log_to_ui('info', f"📨 私信关闭已确认: @{deps.normalize_handle(dm_handle)} ({close_reason})")
            return err_text, True
    return f'{prefix}: {err_text}', False


def prepare_second_dm_text(tab, dm_text, deps, dm_text_supplier=None):
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
                return False, '', False, f'{err_code}: {err_detail}'
        else:
            dm_text_final = deps._sanitize_dm_message_text(dm_text_generated)
    if not dm_text_final:
        return False, '', False, 'E_DM_TEXT_EMPTY: 第二条私信文案为空'
    if deps._conversation_contains_dm_text(tab, dm_text_final):
        return True, dm_text_final, llm_fallback_used, 'already_exists'
    return True, dm_text_final, llm_fallback_used, ''


def execute_dm_recovery_strategies(
    *,
    strategies,
    work_tab,
    handle_norm,
    share_link,
    dm_text,
    deps,
    mark_func,
    progress,
    dm_text_supplier,
    get_headless_mode_fn,
    run_sequence_fn,
):
    last_err = '发送私信失败'
    context_failure_count = 0
    is_continuable_error = getattr(deps, '_is_dm_send_fallback_continuable_error', None)
    if not callable(is_continuable_error):
        is_continuable_error = lambda err_text: False

    for idx, (label, tab_provider) in enumerate(strategies, start=1):
        try:
            work_tab = tab_provider()
        except Exception as e:
            last_err = f'{label}失败: {e}'
            deps.log_to_ui('warn', f'⚠️ 私信恢复步骤失败({idx}/{len(strategies)}): {last_err}')
            continue

        ok, err, dm_closed = run_sequence_fn(
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
            return 'ok', work_tab, '', context_failure_count, False
        if dm_closed:
            return 'dm_closed', work_tab, err, context_failure_count, True

        last_err = str(err or last_err)
        err_class = deps._classify_dm_error_text(last_err)
        context_failure_count = (context_failure_count + 1) if err_class == 'context' else 0

        deps.log_to_ui('warn', f'⚠️ 私信发送失败({label}): {last_err}')
        if is_continuable_error(last_err):
            deps.log_to_ui('debug', f'📨 当前错误允许进入下一恢复策略: {last_err[:120]}')
            continue
        if deps._is_dm_soft_send_error_text(last_err):
            deps.log_to_ui('debug', f'📨 软错误快速返回（跳过慢恢复）: {last_err[:80]}')
            return 'stop', work_tab, last_err, context_failure_count, False
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
                'headless_mode': get_headless_mode_fn(deps),
                'handle': handle_norm,
                'message_len': len(str(dm_text or '')),
                'progress': dict(progress),
                'dm_error_class': err_class,
                'dm_context_failure_count': context_failure_count,
            },
        )

    return 'continue', work_tab, last_err, context_failure_count, False


def attempt_restart_recovery(
    *,
    work_tab,
    handle_norm,
    share_link,
    dm_text,
    deps,
    mark_func,
    progress,
    dm_text_supplier,
    context_failure_count,
    get_headless_mode_fn,
    run_sequence_fn,
):
    try:
        deps.log_to_ui('warn', f'⚠️ 触发上下文阈值恢复：重启浏览器并重建标签页（count={context_failure_count}）')
        deps.restart_global_browser()
        work_tab = deps.ensure_reply_work_tab(force_recreate=True)
        ok, err, dm_closed = run_sequence_fn(
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
            return 'ok', work_tab, '', False
        if dm_closed:
            return 'dm_closed', work_tab, err, True
        last_err = str(err or '发送私信失败')
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
                'headless_mode': get_headless_mode_fn(deps),
                'handle': handle_norm,
                'dm_error_class': deps._classify_dm_error_text(last_err),
                'dm_context_failure_count': context_failure_count,
            },
        )
        return 'continue', work_tab, last_err, False
    except Exception as e:
        return 'continue', work_tab, f'重启浏览器恢复异常: {e}', False


def attempt_headful_dm_fallback(
    *,
    work_tab,
    handle_norm,
    share_link,
    dm_text,
    deps,
    mark_func,
    progress,
    dm_text_supplier,
    get_headless_mode_fn,
    set_headless_mode_fn,
    run_sequence_fn,
):
    display_ok = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
    if deps.DM_RECOVERY_HEADFUL_REQUIRE_DISPLAY and not display_ok:
        deps.log_to_ui('warn', '⚠️ 有头兜底已启用但未检测到 DISPLAY，跳过本次有头兜底')
        return 'continue', work_tab, '', False

    prev_headless = get_headless_mode_fn(deps)
    switched = False
    last_err = ''
    try:
        if prev_headless:
            set_headless_mode_fn(deps, False)
            switched = True
            deps.log_to_ui('warn', '⚠️ 无头私信多次失败，临时切换有头模式执行本条私信兜底')
            deps.restart_global_browser()
        work_tab = deps.ensure_reply_work_tab(force_recreate=True)
        ok, err, dm_closed = run_sequence_fn(
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
            return 'ok', work_tab, '', False
        if dm_closed:
            return 'dm_closed', work_tab, err, True
        last_err = str(err or '发送私信失败')
        deps._capture_runtime_diagnostic(
            work_tab,
            'dm_recovery_headful_fallback_failed',
            err=last_err,
            selectors=[
                'css:[data-testid="sendDMFromProfile"]',
                'css:textarea[data-testid="dm-composer-textarea"]',
                'css:[data-testid="dm-composer-send-button"]',
            ],
            extra={'headless_mode': get_headless_mode_fn(deps), 'handle': handle_norm},
        )
        return 'continue', work_tab, last_err, False
    except Exception as e:
        last_err = f'有头兜底异常: {e}'
        deps.log_to_ui('warn', f'⚠️ {last_err}')
        return 'continue', work_tab, last_err, False
    finally:
        if switched:
            set_headless_mode_fn(deps, prev_headless)
            try:
                deps.restart_global_browser()
                deps.log_to_ui('info', '🔄 私信兜底结束，已恢复无头浏览器运行')
            except Exception as restore_err:
                deps.log_to_ui('warn', f'⚠️ 恢复无头浏览器失败，请手动重启: {restore_err}')
