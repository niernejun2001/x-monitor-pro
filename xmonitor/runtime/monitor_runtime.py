import concurrent.futures
import random
import threading
import time
import traceback


def monitoring_loop(deps):
    """
    主监控循环 - 单浏览器多标签页模式
    - 所有任务同时并行（每个任务一个标签页）
    - 通知标签页始终保持打开
    """

    def is_active():
        return bool(deps._get_runtime_attr('monitor_active', False))

    log_to_ui = deps.log_to_ui
    blocked_users = ['@manateelazycat', '@X', '@Twitter']
    last_save_time = time.time()
    save_interval = 60
    last_maintenance_time = time.time()
    maintenance_interval = deps.get_random_maintenance_interval()

    log_to_ui('info', f">>> 🚀 引擎启动 ({deps.ENGINE_VERSION} 全并行标签页版)...")
    log_to_ui('info', '🧩 build: 2026-02-27-headless-stability-suite')
    if deps.is_headless_verbose_logging_enabled():
        log_to_ui('info', '🧪 [HEADLESS] 已启用超详细诊断日志')
    if deps.headless_mode:
        profile_strategy = '临时Profile优先' if deps.HEADLESS_FORCE_TEMP_PROFILE else '允许固定Profile'
        log_to_ui('info', f'🧪 [HEADLESS] Profile策略: {profile_strategy}')
    else:
        maint_mode = '允许自动重启' if deps.HEADFUL_MAINTENANCE_RESTART else '默认仅轻量保活(不重启浏览器)'
        disconnect_mode = '允许断线后重启' if deps.HEADFUL_NOTIFY_DISCONNECT_RESTART else '断线仅重建通知标签页'
        log_to_ui('info', f'🖥️ [HEADFUL] 维护策略: {maint_mode}')
        log_to_ui('info', f'🖥️ [HEADFUL] 断线恢复策略: {disconnect_mode}')

    if deps._llm_filter_is_ready():
        log_to_ui('info', f'🤖 [LLMFilter] 已启用模型过滤: model={deps.LLM_FILTER_MODEL}, endpoint={deps._llm_filter_endpoint()}')
    elif deps.LLM_FILTER_ENABLED:
        log_to_ui('warn', '⚠️ [LLMFilter] 已开启但配置不完整（需设置 XMONITOR_LLM_BASE_URL 与 XMONITOR_LLM_MODEL）')

    log_to_ui(
        'info',
        f'🛠️ 浏览器维护策略：每 {int(deps.MAINTENANCE_INTERVAL_MIN_SEC)}-{int(deps.MAINTENANCE_INTERVAL_MAX_SEC)}s 随机维护（当前{int(maintenance_interval)}s）',
    )

    try:
        browser = deps.init_global_browser()
        log_to_ui('success', '✅ 浏览器已初始化')

        delegated = deps.get_effective_delegated_account()
        if delegated:
            log_to_ui('info', '🔄 检测到委派账户配置已启用')
            log_to_ui('info', '🔄 正在切换到委派账户...')
            with deps.browser_lock:
                browser.get('https://x.com/home')
                time.sleep(2)
                switch_success = deps.ensure_delegated_account_session(browser, delegated)
            if switch_success:
                log_to_ui('success', '✅ 已切换到委派账户，所有监控将使用委派账户身份')
            else:
                log_to_ui('warn', '⚠️ 委派账户切换失败，将使用主账户进行监控')
            time.sleep(2)
        else:
            log_to_ui('info', 'ℹ️ 未配置委派账户，使用主账户进行监控')

        with deps.data_lock:
            notify_enabled = bool(deps.notification_monitoring)
        if notify_enabled:
            deps.init_notification_tab(blocked_users)

        last_notification_scan = 0.0
        notification_interval = deps.get_random_notification_interval()
        recent_window_minutes = deps.NOTIFICATION_RECENT_WINDOW_MINUTES
        log_to_ui(
            'info',
            f'📬 通知刷新策略：每{deps.NOTIFICATION_SCAN_INTERVAL_MIN_SEC}-{deps.NOTIFICATION_SCAN_INTERVAL_MAX_SEC}秒随机拉取过去{recent_window_minutes}分钟内产生的通知（当前{notification_interval:.1f}s）',
        )
        log_to_ui(
            'info',
            f'🧭 行为随机化策略：任务并发{deps.TASK_PARALLEL_MIN}-{deps.TASK_PARALLEL_MAX}随机、提交抖动{deps.TASK_SUBMIT_JITTER_MIN_SEC}-{deps.TASK_SUBMIT_JITTER_MAX_SEC}s、标签页创建抖动{deps.TAB_OPEN_JITTER_MIN_SEC}-{deps.TAB_OPEN_JITTER_MAX_SEC}s',
        )

        while is_active():
            current_tasks = deps.monitor_tasks_repo.snapshot()
            with deps.data_lock:
                notify_enabled = bool(deps.notification_monitoring)

            current_time = time.time()

            if not deps._is_dm_critical_active():
                retry_done = deps.notify_state_facade.process_retry_queue(max_items=1)
                if retry_done > 0:
                    log_to_ui('debug', f'🔁 已自动处理到期重试任务: {retry_done} 条')

            if notify_enabled and is_active() and (current_time - last_notification_scan >= notification_interval):
                if deps._is_dm_critical_active():
                    deps._maybe_log_dm_critical_skip()
                else:
                    deps.ensure_notification_tab(blocked_users)
                    deps.scan_persistent_notification_tab(blocked_users, max_recent_minutes=recent_window_minutes)
                    last_notification_scan = current_time
                    notification_interval = deps.get_random_notification_interval()
                    log_to_ui('debug', f'📬 下次通知扫描间隔: {notification_interval:.1f}s')

            if current_tasks:
                log_to_ui('info', '=' * 60)
                log_to_ui('info', '🔄 开始推文扫描周期')
                task_queue = list(current_tasks)
                random.shuffle(task_queue)
                parallel_limit = deps.get_random_task_parallel(len(task_queue))
                log_to_ui('info', f'📊 推文监控: 共 {len(task_queue)} 个任务 (本轮并发≈{parallel_limit})')

                for start_idx in range(0, len(task_queue), parallel_limit):
                    if not is_active():
                        break
                    batch = task_queue[start_idx:start_idx + parallel_limit]
                    batch_futures = []
                    for i, task in enumerate(batch):
                        future = deps.task_executor.submit(deps.scan_task_with_tab, task, blocked_users)
                        batch_futures.append(future)
                        if i < len(batch) - 1:
                            time.sleep(random.uniform(deps.TASK_SUBMIT_JITTER_MIN_SEC, deps.TASK_SUBMIT_JITTER_MAX_SEC))

                    for future in concurrent.futures.as_completed(batch_futures):
                        try:
                            future.result()
                        except Exception as e:
                            log_to_ui('error', f'任务执行错误: {e}')

                    if start_idx + parallel_limit < len(task_queue):
                        gap = random.uniform(deps.TASK_BATCH_GAP_MIN_SEC, deps.TASK_BATCH_GAP_MAX_SEC)
                        log_to_ui('debug', f'⏱️ 批次间隔: {gap:.1f}s')
                        time.sleep(gap)

                rest = random.randint(20, 40)
                log_to_ui('info', f'⏱️ 推文扫描结束，将在 {rest}s 后开始下一轮...')

                for second in range(rest):
                    if not is_active():
                        break

                    with deps.data_lock:
                        notify_enabled = bool(deps.notification_monitoring)
                    now_ts = time.time()
                    if notify_enabled and (now_ts - last_notification_scan >= notification_interval):
                        if deps._is_dm_critical_active():
                            deps._maybe_log_dm_critical_skip()
                        else:
                            deps.ensure_notification_tab(blocked_users)
                            deps.scan_persistent_notification_tab(blocked_users, max_recent_minutes=recent_window_minutes)
                            last_notification_scan = now_ts
                            notification_interval = deps.get_random_notification_interval()
                            log_to_ui('debug', f'📬 下次通知扫描间隔: {notification_interval:.1f}s')

                    if not deps._is_dm_critical_active():
                        retry_done = deps.notify_state_facade.process_retry_queue(max_items=1)
                        if retry_done > 0:
                            log_to_ui('debug', f'🔁 休息期已自动处理重试任务: {retry_done} 条')

                    if second % 10 == 0 and second > 0:
                        log_to_ui('info', f'⏳ 倒计时 {rest - second}s...')
                    time.sleep(1)

                log_to_ui('info', '=' * 60)
            elif not notify_enabled:
                log_to_ui('warn', '⏳ 无任务，等待中...')
                time.sleep(5)
            else:
                time.sleep(1)

            if (time.time() - last_maintenance_time) >= maintenance_interval:
                if deps._is_dm_critical_active():
                    deps._maybe_log_dm_critical_skip()
                    last_maintenance_time = time.time()
                    maintenance_interval = deps.get_random_maintenance_interval()
                    continue
                if (not deps.headless_mode) and (not deps.HEADFUL_MAINTENANCE_RESTART):
                    log_to_ui('info', '🛠️ 有头维护：执行轻量保活（不重启浏览器）')
                    deps.run_headful_soft_maintenance(blocked_users, notify_enabled)
                else:
                    deps.close_notification_tab()
                    delegated = deps.get_effective_delegated_account()
                    browser_ref = getattr(deps, 'global_browser', None)
                    if delegated and deps.delegated_switch_ok and browser_ref:
                        log_to_ui('info', '🔄 委派模式维护：仅刷新浏览器，避免重复登录')
                        try:
                            with deps.browser_lock:
                                browser_ref.get('https://x.com/home')
                                time.sleep(1.2)
                                browser_ref.refresh()
                                time.sleep(1.2)
                        except Exception as refresh_err:
                            log_to_ui('warn', f'⚠️ 轻量刷新失败，回退为完整重启: {refresh_err}')
                            deps.restart_global_browser()
                    else:
                        deps.restart_global_browser()
                    if notify_enabled:
                        deps.init_notification_tab(blocked_users)
                last_notification_scan = 0.0
                notification_interval = deps.get_random_notification_interval()
                last_maintenance_time = time.time()
                maintenance_interval = deps.get_random_maintenance_interval()
                log_to_ui('info', f'🛠️ 下次浏览器维护间隔: {int(maintenance_interval)}s')

            if time.time() - last_save_time >= save_interval:
                log_to_ui('info', '💾 执行定时数据保存...')
                deps.save_state()
                last_save_time = time.time()

                max_history_size = 10000
                with deps.data_lock:
                    if len(deps.history_ids) > max_history_size:
                        history_list = list(deps.history_ids)
                        deps.history_ids.clear()
                        deps.history_ids.update(history_list[-max_history_size:])
                        log_to_ui('info', f'🧹 历史记录已清理，保留最新 {max_history_size} 条')
                    before_dedupe = len(deps.content_dedupe)
                    deps.prune_content_dedupe()
                    after_dedupe = len(deps.content_dedupe)
                    if after_dedupe < before_dedupe:
                        log_to_ui('info', f'🧹 内容签名已清理: {before_dedupe} -> {after_dedupe}')

    except Exception as e:
        log_to_ui('error', f'💥 Fatal Error: {e}')
        traceback.print_exc()
    finally:
        deps._set_runtime_attr('monitor_active', False)
        log_to_ui('info', '>>> 引擎停止中，保存数据...')
        deps.save_state()
        log_to_ui('success', '💾 数据已保存，再见！')
        deps.cleanup_global_browser()
        with deps.monitor_thread_lock:
            if getattr(deps, 'monitor_thread', None) is threading.current_thread():
                deps._set_runtime_attr('monitor_thread', None)
