from flask import jsonify, request


def register_runtime_control_routes(app, deps):
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
        payload = request.get_json(silent=True) or {}
        token = str(payload.get('token', '') or '').strip()
        if token:
            deps.global_token = token
        elif not str(deps.global_token or '').strip():
            return jsonify({'status': 'err', 'msg': '请先配置 Token'}), 400
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
