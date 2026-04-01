import os


def get_browser_path(candidate_paths=None):
    paths = candidate_paths or [
        '/usr/bin/chromium',
        '/usr/bin/google-chrome-stable',
        '/usr/bin/google-chrome',
        '/snap/bin/chromium',
    ]
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def is_unhandled_prompt_error(err):
    err_text = str(err or '').lower()
    keywords = [
        '存在未处理的提示框',
        '未处理的提示框',
        'unhandled prompt',
        'unexpected alert open',
        'unexpectedalertpresent',
        'alert open',
    ]
    return any(keyword in err_text for keyword in keywords)


def is_cross_world_click_error(err):
    msg = str(err or '').lower()
    return (
        'same javascript world' in msg
        or 'argument should belong to the same javascript world' in msg
        or 'object reference chain is too long' in msg
    )


def prepare_reply_prompt_guard(
    tab,
    *,
    stage='',
    headless_mode=False,
    dismiss_pending_prompt_fn=None,
    install_headless_dialog_guard_fn=None,
    log_to_ui_fn=None,
):
    handled = 0
    if callable(dismiss_pending_prompt_fn):
        handled = dismiss_pending_prompt_fn(tab, max_rounds=(4 if headless_mode else 2))
    if callable(install_headless_dialog_guard_fn):
        install_headless_dialog_guard_fn(tab)
    if handled > 0 and callable(log_to_ui_fn):
        stage_text = f'{stage} ' if stage else ''
        log_to_ui_fn('debug', f'🧯 {stage_text}已自动处理提示框 {handled} 次')
    return handled
