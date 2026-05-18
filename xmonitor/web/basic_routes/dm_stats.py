from flask import jsonify, request


def register_dm_stats_routes(app, deps):
    @app.route('/api/dm/recent_contacts', methods=['GET'])
    def dm_recent_contacts_state():
        return jsonify(deps.get_recent_dm_contacts_result())

    @app.route('/api/dm/recent_contacts', methods=['POST'])
    def dm_recent_contacts():
        payload = request.get_json(silent=True) or {}
        try:
            window_hours = max(1, min(72, int(payload.get('window_hours', 24) or 24)))
        except Exception:
            window_hours = 24
        try:
            max_scrolls = max(1, min(30, int(payload.get('max_scrolls', 8) or 8)))
        except Exception:
            max_scrolls = 8

        result = deps.scan_recent_dm_contacts_with_browser(
            window_hours=window_hours,
            max_scrolls=max_scrolls,
            run_type='manual',
        )
        return jsonify(result), 200 if result.get('status') == 'ok' else 500

    @app.route('/api/dm/recent_contacts/push_daily_test', methods=['POST'])
    def dm_recent_contacts_push_daily_test():
        result = deps.push_daily_dm_contacts_report(run_type='manual_test', title='测试')
        return jsonify(result), 200 if result.get('status') == 'ok' else 500
