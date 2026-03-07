import datetime
from flask import jsonify, render_template, request


def register_basic_routes(app, deps):
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/state')
    def state():
        with deps.data_lock:
            return jsonify({
                'token': deps.global_token,
                'tasks': list(deps.monitor_tasks),
                'is_running': deps.monitor_active,
                'pending': list(deps.pending_results),
                'updates_last_seq': int(deps.updates_event_seq),
                'updates_buffer_size': len(deps.updates_event_buffer),
                'notification_monitoring': deps.notification_monitoring,
                'delegated_account': deps.delegated_account,
                'delegated_enabled': deps.delegated_enabled,
                'headless_mode': deps.headless_mode,
                'notify_reply_templates': list(deps.notify_reply_templates),
                'dm_message_templates': list(deps.dm_message_templates),
                'llm_filter_enabled': bool(deps.LLM_FILTER_ENABLED),
                'llm_filter_base_url': str(deps.LLM_FILTER_BASE_URL or ''),
                'llm_filter_api_key': str(deps.LLM_FILTER_API_KEY or ''),
                'llm_filter_model': str(deps.LLM_FILTER_MODEL or ''),
                'llm_filter_timeout_sec': float(deps.LLM_FILTER_TIMEOUT_SEC),
                'llm_filter_timeout_max_sec': float(deps.LLM_FILTER_TIMEOUT_MAX_SEC),
                'llm_filter_prompt_template': str(deps.LLM_FILTER_PROMPT_TEMPLATE or ''),
                'llm_intent_prompt_template': str(deps.LLM_INTENT_PROMPT_TEMPLATE or ''),
                'dm_llm_rewrite_enabled': bool(deps.DM_LLM_REWRITE_ENABLED),
                'dm_llm_rewrite_prompt_template': str(deps.DM_LLM_REWRITE_PROMPT_TEMPLATE or ''),
                'dm_llm_rewrite_max_chars': int(deps.DM_LLM_REWRITE_MAX_CHARS),
                'dm_llm_rewrite_temperature': float(deps.DM_LLM_REWRITE_TEMPERATURE),
                'dm_llm_rewrite_max_regen': int(deps.DM_LLM_REWRITE_MAX_REGEN),
                'dm_llm_rewrite_dedupe_size': int(deps.DM_LLM_REWRITE_DEDUPE_SIZE),
                'notify_voice_block_keywords_text': str(deps.NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT or ''),
                'notification_reply_only_mode': bool(deps.NOTIFICATION_REPLY_ONLY_MODE),
                **deps._build_notify_tts_runtime_payload(include_secrets=True),
            })

    @app.route('/api/task/add', methods=['POST'])
    def add_t():
        url = request.json['url']
        deps.monitor_tasks_repo.add(url)
        deps.save_state()
        return jsonify({'status': 'ok', 'tasks': deps.monitor_tasks_repo.snapshot()})

    @app.route('/api/task/remove', methods=['POST'])
    def rem_t():
        url = request.json['url']
        deps.monitor_tasks_repo.remove(url)
        deps.save_state()
        return jsonify({'status': 'ok', 'tasks': deps.monitor_tasks_repo.snapshot()})

    @app.route('/api/mark_done', methods=['POST'])
    def mark_done():
        key = request.json.get('key')
        handle = request.json.get('handle', '')
        removed = deps.pending_results_repo.remove_matching(key=key, handle=handle)
        deps.save_state()
        if key:
            deps.log_to_ui('info', f'✅ 记录已处理: key={key}（移除{removed}条）')
        else:
            deps.log_to_ui('info', f'✅ 记录已处理: handle={handle}（兼容模式移除{removed}条）')
        return jsonify({'status': 'ok', 'removed': removed})

    @app.route('/api/clear_results', methods=['POST'])
    def clear_results():
        result_type = request.json.get('type', 'all')
        deps.pending_results_repo.clear_results(result_type)
        if result_type == 'notify':
            deps.log_to_ui('info', '🗑️ 已清空通知捕获结果')
        elif result_type == 'tweet':
            deps.log_to_ui('info', '🗑️ 已清空推文捕获结果')
        else:
            deps.log_to_ui('info', '🗑️ 已清空所有捕获结果')
        deps.save_state()
        return jsonify({'status': 'ok'})

    @app.route('/api/clear_blocklist', methods=['POST'])
    def clear_blocklist():
        deps.processed_users_repo.clear()
        deps.save_processed_users()
        deps.log_to_ui('info', '⛔ 已清空黑名单（当前抓取不再按用户屏蔽）')
        return jsonify({'status': 'ok'})

    @app.route('/api/notify_replies')
    def get_notify_replies():
        try:
            limit = int(request.args.get('limit', 200))
        except Exception:
            limit = 200
        reply_items = deps.pending_results_repo.list_reply_items(deps.is_reply_to_me_notification_item, limit=limit)
        return jsonify({
            'status': 'ok',
            'count': len(reply_items),
            'reply_only_mode': bool(deps.NOTIFICATION_REPLY_ONLY_MODE),
            'items': reply_items,
        })

    @app.route('/api/toggle_notification', methods=['POST'])
    def toggle_notification():
        enabled = request.json.get('enabled', False)
        with deps.data_lock:
            deps.notification_monitoring = enabled
        deps.save_state()
        status_text = '启用' if enabled else '禁用'
        deps.log_to_ui('info', f'📬 通知监控已{status_text}')
        return jsonify({'status': 'ok', 'notification_monitoring': deps.notification_monitoring})

    @app.route('/api/set_delegated_account', methods=['POST'])
    def set_delegated_account():
        payload = request.get_json(silent=True) or {}
        account = str(payload.get('account', '') or '').strip()
        old_norm = deps.normalize_handle(deps.delegated_account)
        new_norm = deps.normalize_handle(account)
        with deps.data_lock:
            deps.delegated_account = account
            deps.delegated_enabled = bool(account)
            if (old_norm != new_norm) or (not deps.delegated_enabled):
                deps._set_runtime_attr('delegated_account_active', '')
                deps._set_runtime_attr('delegated_switch_ok', False)
        deps.save_state()
        if deps.delegated_enabled:
            deps.log_to_ui('info', f'👤 已设置委派账户: {account}')
        else:
            deps.log_to_ui('info', '👤 已清除委派账户')
        return jsonify({'status': 'ok', 'delegated_account': deps.delegated_account, 'delegated_enabled': deps.delegated_enabled})

    @app.route('/api/open_user_replies_page', methods=['POST'])
    def open_user_replies_page():
        payload = request.get_json(silent=True) or {}
        raw_handle = str(payload.get('handle', '') or '').strip()
        handle = deps.normalize_handle(raw_handle)
        if not handle:
            return jsonify({'status': 'err', 'msg': '请输入有效的推特 @ID'}), 400
        if not deps.re.fullmatch(r'[a-z0-9_]{1,30}', handle):
            return jsonify({'status': 'err', 'msg': '推特ID格式不合法'}), 400
        target_url = f'https://x.com/{handle}/with_replies'
        try:
            with deps.browser_lock:
                browser = deps.global_browser if (deps.browser_initialized and deps.global_browser) else None
            if browser is None:
                if not deps.global_token.strip():
                    return jsonify({'status': 'err', 'msg': '请先配置 Token 并启动监控后再跳转'}), 400
                browser = deps.init_global_browser()
            with deps.browser_lock:
                tab = browser.new_tab()
                tab.get(target_url)
            deps.log_to_ui('info', f'🔗 已打开用户回复页: @{handle}')
            return jsonify({'status': 'ok', 'handle': f'@{handle}', 'url': target_url})
        except Exception as e:
            deps.log_to_ui('warn', f'⚠️ 打开用户回复页失败 @{handle}: {e}')
            return jsonify({'status': 'err', 'msg': f'打开失败: {e}'}), 500

    @app.route('/api/toggle_headless', methods=['POST'])
    def toggle_headless():
        payload = request.get_json(silent=True) or {}
        enabled = bool(payload.get('enabled', True))
        mode_text = '无头模式' if enabled else '有头模式(调试)'
        was_running = bool(deps.monitor_active)
        with deps.data_lock:
            deps.headless_mode = enabled
        deps.save_state()
        deps.log_to_ui('info', f'🖥️ 浏览器模式已切换为: {mode_text}')
        if not was_running:
            return jsonify({'status': 'ok', 'headless_mode': deps.headless_mode, 'auto_restarted': False})
        deps.log_to_ui('info', '🔄 监控运行中，正在自动重启以应用新浏览器模式...')
        stopped = deps.stop_monitor_thread(wait_timeout=20)
        started = deps.start_monitor_thread()
        deps.save_state()
        if started:
            deps.log_to_ui('success', f'✅ 已应用{mode_text}并自动重启监控')
            return jsonify({'status': 'ok', 'headless_mode': deps.headless_mode, 'auto_restarted': True, 'stopped': bool(stopped)})
        msg = '浏览器模式已切换，但监控自动重启失败，请手动点击启动监控'
        deps.log_to_ui('error', f'❌ {msg}')
        return jsonify({'status': 'err', 'msg': msg, 'headless_mode': deps.headless_mode, 'auto_restarted': False, 'stopped': bool(stopped)})

    @app.route('/api/start', methods=['POST'])
    def start_rt():
        if deps.monitor_active:
            return jsonify({'status': 'err', 'msg': '监控已在运行'})
        deps.global_token = request.json['token']
        started = deps.start_monitor_thread()
        if not started:
            return jsonify({'status': 'err', 'msg': '监控线程正在运行'})
        deps.save_state()
        return jsonify({'status': 'ok'})

    @app.route('/api/stop', methods=['POST'])
    def stop_rt():
        deps.log_to_ui('info', '🛑 停止监控，保存数据...')
        stopped = deps.stop_monitor_thread(wait_timeout=15)
        deps.save_state()
        deps.save_processed_users()
        deps.log_to_ui('success', '💾 数据已保存')
        return jsonify({'status': 'ok', 'stopped': stopped})

    @app.route('/api/updates')
    def up():
        raw_since = str(request.args.get('since_seq', '') or '').strip()
        has_since = raw_since != ''
        if not has_since:
            new_items = deps.drain_msg_queue(collect_new_data=True)
            with deps.data_lock:
                tasks_copy = list(deps.monitor_tasks)
                last_seq = int(deps.updates_event_seq)
                if (not new_items) and deps.updates_event_buffer:
                    new_items = [evt.get('data') for evt in list(deps.updates_event_buffer)[-120:] if isinstance(evt.get('data'), dict)]
            return jsonify({'new_items': new_items, 'tasks': tasks_copy, 'last_seq': last_seq, 'dropped': False})
        try:
            since_seq = max(0, int(raw_since))
        except Exception:
            since_seq = 0
        deps.drain_msg_queue(collect_new_data=False)
        with deps.data_lock:
            tasks_copy = list(deps.monitor_tasks)
            last_seq = int(deps.updates_event_seq)
            buffer_snapshot = list(deps.updates_event_buffer)
        dropped = False
        if buffer_snapshot:
            oldest_seq = int(buffer_snapshot[0].get('seq', 0) or 0)
            if since_seq > 0 and oldest_seq > (since_seq + 1):
                dropped = True
        new_items = [evt.get('data') for evt in buffer_snapshot if int(evt.get('seq', 0) or 0) > since_seq and isinstance(evt.get('data'), dict)]
        return jsonify({'new_items': new_items, 'tasks': tasks_copy, 'last_seq': last_seq, 'dropped': dropped})
