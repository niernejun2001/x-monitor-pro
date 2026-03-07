import threading


def start_monitor_thread(deps):
    with deps.monitor_thread_lock:
        if deps.monitor_thread and deps.monitor_thread.is_alive():
            deps._set_runtime_attr('monitor_active', True)
            return False

        deps._set_runtime_attr('monitor_active', True)
        deps._set_runtime_attr('monitor_thread', threading.Thread(target=deps.monitoring_loop, daemon=True, name='monitoring_loop'))
        deps.monitor_thread.start()
        return True


def stop_monitor_thread(deps, wait_timeout=15):
    """停止监控线程并等待退出，防止重启时竞态。"""
    deps._set_runtime_attr('monitor_active', False)

    with deps.monitor_thread_lock:
        thread_ref = deps.monitor_thread

    if thread_ref and thread_ref.is_alive():
        thread_ref.join(timeout=wait_timeout)
        if thread_ref.is_alive():
            deps.log_to_ui('warn', '⚠️ 监控线程未在超时内退出，执行强制浏览器清理')
            deps.close_notification_tab()
            deps.cleanup_global_browser()
            return False

    with deps.monitor_thread_lock:
        if deps.monitor_thread and not deps.monitor_thread.is_alive():
            deps._set_runtime_attr('monitor_thread', None)

    return True
