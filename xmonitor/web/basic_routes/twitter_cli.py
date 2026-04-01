from flask import jsonify, request


def _twitter_cli_http_status(payload):
    return 200 if payload.get('status') == 'ok' else 500


def register_twitter_cli_routes(app, deps):
    @app.route('/api/twitter_cli/status')
    def twitter_cli_status():
        verify = str(request.args.get('verify', '') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
        getter = getattr(deps, '_get_twitter_cli_status', None)
        if not callable(getter):
            return jsonify({'status': 'err', 'msg': 'twitter-cli 未接入'}), 501
        payload = dict(getter(verify=verify) or {})
        return jsonify(payload), _twitter_cli_http_status(payload)

    @app.route('/api/twitter_cli/tweet_detail', methods=['POST'])
    def twitter_cli_tweet_detail():
        payload = request.get_json(silent=True) or {}
        tweet_id = str(payload.get('tweet_id', payload.get('status_id', '')) or '').strip()
        if not tweet_id:
            return jsonify({'status': 'err', 'msg': 'tweet_id 不能为空'}), 400
        fetcher = getattr(deps, '_fetch_twitter_cli_tweet_detail', None)
        if not callable(fetcher):
            return jsonify({'status': 'err', 'msg': 'twitter-cli 未接入'}), 501
        result = dict(fetcher(tweet_id, max_count=payload.get('max_count', 8), force_refresh=bool(payload.get('force_refresh', False))) or {})
        return jsonify(result), _twitter_cli_http_status(result)

    @app.route('/api/twitter_cli/user')
    def twitter_cli_user():
        raw_handle = str(request.args.get('handle', '') or '').strip()
        if not raw_handle:
            return jsonify({'status': 'err', 'msg': 'handle 不能为空'}), 400
        fetcher = getattr(deps, '_fetch_twitter_cli_user', None)
        if not callable(fetcher):
            return jsonify({'status': 'err', 'msg': 'twitter-cli 未接入'}), 501
        force_refresh = str(request.args.get('force_refresh', '') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
        result = dict(fetcher(raw_handle, force_refresh=force_refresh) or {})
        return jsonify(result), _twitter_cli_http_status(result)
