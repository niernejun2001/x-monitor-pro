import time
from DrissionPage import ChromiumPage

from xmonitor.services.support.error_format import format_runtime_error


def _format_browser_error(err):
    return format_runtime_error(err)


def _read_browser_cookie_value(browser, cookie_name):
    if browser is None or not cookie_name:
        return ''
    try:
        rows = browser.cookies(all_domains=True, all_info=True)
    except TypeError:
        try:
            rows = browser.cookies(all_domains=True)
        except Exception:
            return ''
    except Exception:
        return ''
    for row in list(rows or []):
        if not isinstance(row, dict):
            try:
                name = getattr(row, 'name', '')
                value = getattr(row, 'value', '')
            except Exception:
                continue
        else:
            name = row.get('name', '')
            value = row.get('value', '')
        if str(name or '').strip() == str(cookie_name or '').strip():
            return str(value or '').strip()
    return ''


def _resolve_auth_bootstrap_strategy(saved_token, profile_token):
    saved = str(saved_token or '').strip()
    profile = str(profile_token or '').strip()
    if profile:
        return {
            'mode': 'reuse_profile',
            'token': profile,
            'has_profile_token': True,
            'saved_token_present': bool(saved),
            'tokens_match': bool(saved and saved == profile),
        }
    if saved:
        return {
            'mode': 'inject_saved',
            'token': saved,
            'has_profile_token': False,
            'saved_token_present': True,
            'tokens_match': False,
        }
    return {
        'mode': 'no_token',
        'token': '',
        'has_profile_token': False,
        'saved_token_present': False,
        'tokens_match': False,
    }


def init_global_browser(deps):
    with deps.browser_init_lock:
        if deps.browser_initialized and deps.global_browser:
            return deps.global_browser

        max_attempts = 4
        last_error = None
        use_temp_profile_fallback = deps.browser_force_temp_profile or (deps.headless_mode and deps.HEADLESS_FORCE_TEMP_PROFILE)
        force_headless_retry = False
        safe_mode_retry = False

        for attempt in range(1, max_attempts + 1):
            with deps.browser_lock:
                if deps.browser_initialized and deps.global_browser:
                    return deps.global_browser

                if deps.global_browser:
                    try:
                        deps.global_browser.quit()
                    except Exception:
                        pass
                    deps._set_runtime_attr('global_browser', None)

                if deps.global_browser_dir:
                    deps.cleanup_browser_user_data_dir(deps.global_browser_dir)
                    deps._set_runtime_attr('global_browser_dir', None)

                try:
                    effective_headless = True if force_headless_retry else deps.headless_mode
                    if effective_headless and deps.HEADLESS_FORCE_TEMP_PROFILE:
                        use_temp_profile_fallback = True

                    if deps.BROWSER_PROFILE_PERSIST and not use_temp_profile_fallback:
                        locked, lock_pid = deps._is_profile_locked_by_alive_process(deps.BROWSER_PROFILE_DIR)
                        if locked:
                            cleanup_info = deps._auto_cleanup_profile_runtime(deps.BROWSER_PROFILE_DIR)
                            if cleanup_info['bound_total'] > 0:
                                deps.log_to_ui(
                                    'warn',
                                    f"⚠️ 固定Profile被占用(pid={lock_pid})，已自动清理残留进程 {cleanup_info['killed_total']}/{cleanup_info['bound_total']}"
                                )
                            use_temp_profile_fallback = True
                            deps._set_runtime_attr('browser_force_temp_profile', True)
                            deps.log_to_ui('warn', f'⚠️ 固定Profile被占用(pid={lock_pid})，本次直接切换临时Profile启动')
                        else:
                            deps._cleanup_stale_profile_singletons(deps.BROWSER_PROFILE_DIR)

                    prefer_persistent_profile = not use_temp_profile_fallback
                    deps._set_runtime_attr('global_browser_dir', deps.create_browser_user_data_dir(prefer_persistent=prefer_persistent_profile))
                    port = deps.get_free_port()
                    co = deps.init_browser_options(
                        port,
                        deps.global_browser_dir,
                        force_headless=True if force_headless_retry else None,
                        safe_mode=safe_mode_retry,
                    )
                    mode_text = '无头模式(连接失败自动兜底)' if force_headless_retry else ('无头模式' if effective_headless else '有头模式(调试)')
                    if safe_mode_retry:
                        mode_text = f'{mode_text}+安全参数'
                    profile_mode = '固定持久目录' if deps.is_persistent_browser_profile_dir(deps.global_browser_dir) else '临时目录'
                    deps.log_to_ui('info', f'🖥️ 正在初始化浏览器: {mode_text} | Profile: {profile_mode}')
                    deps.log_to_ui('debug', f'🗂️ 浏览器用户目录: {deps.global_browser_dir}')
                    deps.log_headless_debug(
                        f'init_attempt={attempt}/{max_attempts}, port={port}, '
                        f'profile_mode={profile_mode}, force_headless_retry={force_headless_retry}, safe_mode_retry={safe_mode_retry}, '
                        f'headless_force_temp_profile={deps.HEADLESS_FORCE_TEMP_PROFILE}'
                    )
                    deps._set_runtime_attr('global_browser', ChromiumPage(co))
                    deps.global_browser.get('https://x.com')
                    profile_auth_token = _read_browser_cookie_value(deps.global_browser, 'auth_token')
                    bootstrap = _resolve_auth_bootstrap_strategy(deps.global_token, profile_auth_token)
                    if bootstrap['mode'] == 'inject_saved':
                        cookie_dict = {'name': 'auth_token', 'value': bootstrap['token'], 'domain': '.x.com', 'path': '/', 'secure': True}
                        deps.global_browser.set.cookies(cookie_dict)
                        deps.log_to_ui('info', '🔐 未检测到 Profile 登录态，已注入保存的 auth_token')
                    elif bootstrap['mode'] == 'reuse_profile':
                        deps._set_runtime_attr('global_token', bootstrap['token'])
                        if bootstrap['saved_token_present'] and (not bootstrap['tokens_match']):
                            deps.log_to_ui('info', '🔐 检测到 Profile 内已有登录态，已优先复用浏览器会话，不覆盖为旧 auth_token')
                        else:
                            deps.log_to_ui('debug', '🔐 已复用固定 Profile 内的登录态')
                    else:
                        deps.log_to_ui('warn', '⚠️ 未检测到可用 auth_token，将以当前浏览器会话状态继续（如需使用请手动登录）')
                    deps.global_browser.refresh()
                    time.sleep(3)
                    deps._set_runtime_attr('browser_initialized', True)
                    deps.log_to_ui('success', '✅ 全局浏览器已初始化 (单浏览器多标签页模式)')
                    return deps.global_browser
                except Exception as e:
                    last_error = e
                    deps._set_runtime_attr('browser_initialized', False)
                    deps._set_runtime_attr('global_browser', None)
                    deps.log_headless_exception('浏览器初始化', e)
                    deps._capture_runtime_diagnostic(
                        None,
                        'init_global_browser_failed',
                        err=e,
                        extra={
                            'attempt': attempt,
                            'max_attempts': max_attempts,
                            'global_browser_dir': deps.global_browser_dir,
                            'headless_mode': bool(deps.headless_mode),
                            'force_headless_retry': bool(force_headless_retry),
                            'safe_mode_retry': bool(safe_mode_retry),
                            'use_temp_profile_fallback': bool(use_temp_profile_fallback),
                            'headless_force_temp_profile': bool(deps.HEADLESS_FORCE_TEMP_PROFILE),
                        },
                    )
                    display_error = _format_browser_error(e)
                    err_text = display_error.lower()
                    connection_failed = any(keyword in err_text for keyword in [
                        'cannot connect', '连接失败', 'disconnected', 'connection failed', 'timed out', 'timeout'
                    ])
                    if connection_failed and deps.global_browser_dir:
                        cleanup_info = deps._auto_cleanup_profile_runtime(deps.global_browser_dir)
                        if cleanup_info['bound_total'] > 0:
                            deps.log_to_ui('warn', f"⚠️ 检测到残留浏览器进程({cleanup_info['bound_total']})，已自动清理 {cleanup_info['killed_total']} 个并重试")
                    if connection_failed and not use_temp_profile_fallback:
                        use_temp_profile_fallback = True
                        deps._set_runtime_attr('browser_force_temp_profile', True)
                        deps.log_to_ui('warn', '⚠️ 连接浏览器失败，后续尝试将切换临时Profile重试')
                    if connection_failed and (not deps.headless_mode) and (not force_headless_retry):
                        force_headless_retry = True
                        deps.log_to_ui('warn', '⚠️ 当前有头模式连接失败，后续尝试将自动切换无头模式重试')
                    if connection_failed and not safe_mode_retry:
                        safe_mode_retry = True
                        deps.log_to_ui('warn', '⚠️ 启用浏览器安全参数集重试，降低参数兼容性风险')
                    if deps.global_browser_dir:
                        deps.cleanup_browser_user_data_dir(deps.global_browser_dir)
                        deps._set_runtime_attr('global_browser_dir', None)
                    deps.log_to_ui('warn', f'⚠️ 浏览器初始化失败({attempt}/{max_attempts}): {display_error}')
            if attempt < max_attempts:
                time.sleep(1.5 * attempt)

        raise RuntimeError(f'浏览器初始化失败，已重试 {max_attempts} 次: {_format_browser_error(last_error)}')


def cleanup_global_browser(deps):
    with deps.browser_lock:
        with deps.reply_work_tab_lock:
            if deps.reply_work_tab:
                try:
                    deps.reply_work_tab.close()
                except Exception:
                    pass
                deps._set_runtime_attr('reply_work_tab', None)
        with deps.dm_passcode_lock:
            deps.dm_passcode_warmed = False
        if deps.global_browser:
            try:
                deps.global_browser.quit()
            except Exception:
                pass
            deps._set_runtime_attr('global_browser', None)
        if deps.global_browser_dir:
            deps.cleanup_browser_user_data_dir(deps.global_browser_dir)
            deps._set_runtime_attr('global_browser_dir', None)
        deps._set_runtime_attr('browser_initialized', False)
        deps._set_runtime_attr('delegated_account_active', '')
        deps._set_runtime_attr('delegated_switch_ok', False)
        deps._set_runtime_attr('browser_force_temp_profile', False)
        deps._set_runtime_attr('last_dm_action_ts', 0.0)


def restart_global_browser(deps):
    deps.log_to_ui('info', '🔄 正在重启浏览器...')
    cleanup_global_browser(deps)
    time.sleep(1)
    browser = init_global_browser(deps)
    delegated = deps.get_effective_delegated_account()
    if delegated:
        browser.get('https://x.com/home')
        time.sleep(2)
        deps.ensure_delegated_account_session(browser, delegated)
        time.sleep(2)
    deps.log_to_ui('success', '✅ 浏览器已重启')
    return browser
