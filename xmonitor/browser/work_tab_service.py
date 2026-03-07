from xmonitor.browser.tab_manager import ensure_worker_tab


def ensure_reply_work_tab(deps, force_recreate=False):
    """确保回复专用工作标签页可用（复用同一标签页）。"""
    holder = [deps.reply_work_tab]
    tab = ensure_worker_tab(
        current_tab=holder,
        tab_lock_obj=deps.reply_work_tab_lock,
        browser_factory=deps.init_global_browser,
        warmup_func=deps._warmup_dm_passcode_if_needed,
        force_recreate=force_recreate,
        reuse_log=lambda: deps.log_to_ui('debug', '💬 复用已有回复工作标签页'),
        create_log=lambda: deps.log_to_ui('debug', '💬 已创建回复工作标签页（将持续复用）'),
    )
    deps._set_runtime_attr('reply_work_tab', holder[0])
    return tab
