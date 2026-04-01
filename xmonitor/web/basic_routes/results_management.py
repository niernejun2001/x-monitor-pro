from flask import jsonify, request


def register_results_management_routes(app, deps):
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
        for row in reply_items:
            deps._ensure_notify_flow_fields(row)
        return jsonify({
            'status': 'ok',
            'count': len(reply_items),
            'reply_only_mode': bool(deps.NOTIFICATION_REPLY_ONLY_MODE),
            'items': reply_items,
        })
