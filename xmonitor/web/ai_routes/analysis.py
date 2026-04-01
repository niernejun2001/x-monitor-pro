import time

from flask import jsonify, request

from .helpers import extract_llm_runtime_from_payload


def register_analysis_routes(app, deps):
    @app.route('/api/llm_filter/test', methods=['POST'])
    def llm_filter_test():
        payload = request.get_json(silent=True) or {}
        runtime = extract_llm_runtime_from_payload(payload, deps)
        if not runtime['base_url'] or not runtime['model']:
            return jsonify({'status': 'err', 'msg': '请先填写 Base URL 和模型名'}), 400
        start_ts = time.perf_counter()
        try:
            result_obj, raw_text = deps._call_openai_compatible_json(
                'You are a strict JSON classifier.',
                '请返回JSON: {"ok":true,"message":"pong"}',
                base_url=runtime['base_url'],
                api_key=runtime['api_key'],
                model=runtime['model'],
                timeout_sec=runtime['timeout_sec'],
                max_tokens=48,
            )
            latency_ms = int((time.perf_counter() - start_ts) * 1000)
            ok_flag = True
            if isinstance(result_obj, dict) and 'ok' in result_obj:
                ok_raw = result_obj.get('ok')
                if isinstance(ok_raw, str):
                    ok_flag = ok_raw.strip().lower() in {'1', 'true', 'yes', 'y'}
                else:
                    ok_flag = bool(ok_raw)
            return jsonify({
                'status': 'ok' if ok_flag else 'err',
                'model': runtime['model'],
                'endpoint': deps._llm_filter_endpoint(base_url=runtime['base_url']),
                'latency_ms': latency_ms,
                'result': result_obj if isinstance(result_obj, dict) else {},
                'raw': str(raw_text or '')[:180],
                'msg': '模型可用' if ok_flag else '模型返回异常',
            })
        except Exception as e:
            return jsonify({
                'status': 'err',
                'model': runtime['model'],
                'endpoint': deps._llm_filter_endpoint(base_url=runtime['base_url']),
                'msg': f'模型不可用: {e}',
            }), 500

    @app.route('/api/llm_filter/analyze', methods=['POST'])
    def llm_filter_analyze():
        payload = request.get_json(silent=True) or {}
        content = str(payload.get('content', '') or '').strip()
        analyze_source = str(payload.get('analyze_source', '') or '').strip() or 'unknown'
        if not content:
            return jsonify({'status': 'err', 'msg': '评论内容不能为空'}), 400
        runtime = extract_llm_runtime_from_payload(payload, deps)
        deps.log_to_ui('debug', f"🤖 [IntentAPI] request source={analyze_source} content={deps._normalize_one_line(content, 120)}")
        analysis = deps.analyze_comment_intent(
            content,
            base_url=runtime['base_url'],
            api_key=runtime['api_key'],
            model=runtime['model'],
            timeout_sec=runtime['timeout_sec'],
        )
        analysis['voice_should_notify'] = bool(deps._should_notify_voice_by_intent(analysis))
        deps.log_to_ui('debug', f"🤖 [IntentAPI] result source={analyze_source} score={analysis.get('intent_score', 0)} level={analysis.get('intent_level', '')} intent={bool(analysis.get('is_intent_user', False))} voice={bool(analysis.get('voice_should_notify', False))} llm_used={bool(analysis.get('llm_used', False))} reason={analysis.get('reason', '') or '-'}")
        deps.log_to_ui('info', f"🤖 AI意向分析[{analyze_source}] score={analysis.get('intent_score', 0)} level={analysis.get('intent_level', '')} intent={bool(analysis.get('is_intent_user', False))} voice={bool(analysis.get('voice_should_notify', False))} llm_used={bool(analysis.get('llm_used', False))}")
        return jsonify({'status': 'ok', 'analysis': analysis})
