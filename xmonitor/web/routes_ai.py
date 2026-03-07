import time
from collections import deque
from flask import jsonify, request


def _extract_llm_runtime_from_payload(payload, deps):
    payload = payload or {}
    base_url = str(payload.get('base_url', deps.LLM_FILTER_BASE_URL) or '').strip()
    api_key = str(payload.get('api_key', deps.LLM_FILTER_API_KEY) or '').strip() or 'EMPTY'
    model = str(payload.get('model', deps.LLM_FILTER_MODEL) or '').strip()
    timeout_sec = deps.clamp_llm_timeout(payload.get('timeout_sec', deps.LLM_FILTER_TIMEOUT_SEC))
    return {
        'base_url': base_url,
        'api_key': api_key,
        'model': model,
        'timeout_sec': timeout_sec,
    }


def register_ai_routes(app, deps):
    @app.route('/api/llm_filter/test', methods=['POST'])
    def llm_filter_test():
        payload = request.get_json(silent=True) or {}
        runtime = _extract_llm_runtime_from_payload(payload, deps)
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
        runtime = _extract_llm_runtime_from_payload(payload, deps)
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

    @app.route('/api/set_llm_filter_config', methods=['POST'])
    def set_llm_filter_config():
        payload = request.get_json(silent=True) or {}
        enabled = bool(payload.get('enabled', False))
        base_url = str(payload.get('base_url', '') or '').strip()
        api_key = str(payload.get('api_key', '') or '').strip()
        model = str(payload.get('model', '') or '').strip()
        filter_prompt_template = str(payload.get('llm_filter_prompt_template', deps.LLM_FILTER_PROMPT_TEMPLATE) or '').strip()
        intent_prompt_template = str(payload.get('llm_intent_prompt_template', deps.LLM_INTENT_PROMPT_TEMPLATE) or '').strip()
        notify_voice_block_keywords_text = str(payload.get('notify_voice_block_keywords_text', deps.NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT) or '').strip()
        dm_llm_rewrite_enabled = bool(payload.get('dm_llm_rewrite_enabled', deps.DM_LLM_REWRITE_ENABLED))
        dm_llm_rewrite_prompt_template = str(payload.get('dm_llm_rewrite_prompt_template', deps.DM_LLM_REWRITE_PROMPT_TEMPLATE) or '').strip() or deps.DM_LLM_REWRITE_DEFAULT_PROMPT
        try:
            dm_llm_rewrite_max_chars = int(payload.get('dm_llm_rewrite_max_chars', deps.DM_LLM_REWRITE_MAX_CHARS))
        except Exception:
            dm_llm_rewrite_max_chars = deps.DM_LLM_REWRITE_MAX_CHARS
        dm_llm_rewrite_max_chars = max(80, min(1200, int(dm_llm_rewrite_max_chars)))
        try:
            dm_llm_rewrite_temperature = float(payload.get('dm_llm_rewrite_temperature', deps.DM_LLM_REWRITE_TEMPERATURE))
        except Exception:
            dm_llm_rewrite_temperature = deps.DM_LLM_REWRITE_TEMPERATURE
        dm_llm_rewrite_temperature = max(0.0, min(1.2, float(dm_llm_rewrite_temperature)))
        try:
            dm_llm_rewrite_max_regen = int(payload.get('dm_llm_rewrite_max_regen', deps.DM_LLM_REWRITE_MAX_REGEN))
        except Exception:
            dm_llm_rewrite_max_regen = deps.DM_LLM_REWRITE_MAX_REGEN
        dm_llm_rewrite_max_regen = max(0, min(5, int(dm_llm_rewrite_max_regen)))
        try:
            dm_llm_rewrite_dedupe_size = int(payload.get('dm_llm_rewrite_dedupe_size', deps.DM_LLM_REWRITE_DEDUPE_SIZE))
        except Exception:
            dm_llm_rewrite_dedupe_size = deps.DM_LLM_REWRITE_DEDUPE_SIZE
        dm_llm_rewrite_dedupe_size = max(50, min(1000, int(dm_llm_rewrite_dedupe_size)))
        try:
            timeout_sec = deps.clamp_llm_timeout(payload.get('timeout_sec', deps.LLM_FILTER_TIMEOUT_SEC))
        except Exception:
            timeout_sec = deps.LLM_FILTER_TIMEOUT_SEC
        if enabled and (not base_url or not model):
            return jsonify({'status': 'err', 'msg': '启用 LLM 过滤时，Base URL 和模型名不能为空'}), 400
        notify_voice_block_keywords = deps._normalize_keyword_lines(notify_voice_block_keywords_text)
        with deps.data_lock:
            deps.LLM_FILTER_ENABLED = enabled
            deps.LLM_FILTER_BASE_URL = base_url
            deps.LLM_FILTER_API_KEY = api_key
            deps.LLM_FILTER_MODEL = model
            deps.LLM_FILTER_TIMEOUT_SEC = timeout_sec
            deps.LLM_FILTER_PROMPT_TEMPLATE = filter_prompt_template
            deps.LLM_INTENT_PROMPT_TEMPLATE = intent_prompt_template
            deps.DM_LLM_REWRITE_ENABLED = dm_llm_rewrite_enabled
            deps.DM_LLM_REWRITE_PROMPT_TEMPLATE = dm_llm_rewrite_prompt_template
            deps.DM_LLM_REWRITE_MAX_CHARS = dm_llm_rewrite_max_chars
            deps.DM_LLM_REWRITE_TEMPERATURE = dm_llm_rewrite_temperature
            deps.DM_LLM_REWRITE_MAX_REGEN = dm_llm_rewrite_max_regen
            if deps.DM_LLM_REWRITE_DEDUPE_SIZE != dm_llm_rewrite_dedupe_size:
                deps.DM_LLM_REWRITE_DEDUPE_SIZE = dm_llm_rewrite_dedupe_size
                deps.dm_llm_rewrite_history = deque(list(deps.dm_llm_rewrite_history), maxlen=deps.DM_LLM_REWRITE_DEDUPE_SIZE)
            else:
                deps.DM_LLM_REWRITE_DEDUPE_SIZE = dm_llm_rewrite_dedupe_size
            deps.NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT = notify_voice_block_keywords_text
            deps.NOTIFY_VOICE_BLOCK_KEYWORDS = notify_voice_block_keywords
        with deps.llm_filter_cache_lock:
            deps.llm_filter_cache.clear()
        deps.save_state()
        if deps.LLM_FILTER_ENABLED and deps._llm_filter_is_ready():
            deps.log_to_ui('info', f'🤖 [LLMFilter] 配置已更新并启用: model={deps.LLM_FILTER_MODEL}')
        elif deps.LLM_FILTER_ENABLED:
            deps.log_to_ui('warn', '⚠️ [LLMFilter] 已启用但配置不完整')
        else:
            deps.log_to_ui('info', '🤖 [LLMFilter] 已禁用')
        deps.log_to_ui('info', f'🔇 [NotifyVoice] 不播报关键词已更新: {len(deps.NOTIFY_VOICE_BLOCK_KEYWORDS)} 条')
        return jsonify({
            'status': 'ok',
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
            'notify_voice_block_keywords': list(deps.NOTIFY_VOICE_BLOCK_KEYWORDS),
        })

    @app.route('/api/set_notify_tts_config', methods=['POST'])
    def set_notify_tts_config():
        payload = request.get_json(silent=True) or {}
        cfg = deps._normalize_notify_tts_config_from_payload(payload)
        if cfg['enabled'] and (not cfg['app_id'] or not cfg['access_token'] or not cfg['voice_type']):
            return jsonify({'status': 'err', 'msg': '启用豆包TTS时必须填写 AppID / Access Token / 音色'}), 400
        with deps.data_lock:
            deps._apply_notify_tts_config(cfg)
            save_ok, save_err = deps._save_local_tts_config(deps.LOCAL_TTS_CONFIG)
        deps.save_state()
        if deps._doubao_tts_is_ready():
            deps.log_to_ui('info', f'🔊 [NotifyTTS] 配置已更新并生效: voice={deps.DOUBAO_TTS_VOICE_TYPE} encoding={deps.DOUBAO_TTS_ENCODING}')
        else:
            deps.log_to_ui('warn', '⚠️ [NotifyTTS] 配置已保存，但当前仍未就绪（请检查必填项）')
        if not save_ok:
            deps.log_to_ui('warn', f'⚠️ [NotifyTTS] 本地配置落盘失败: {save_err}')
        resp = {'status': 'ok', 'saved_to_local_file': bool(save_ok), 'save_error': str(save_err or '')}
        resp.update(deps._build_notify_tts_runtime_payload(include_secrets=True))
        return jsonify(resp)

    @app.route('/api/notify_tts/test', methods=['POST'])
    def notify_tts_test():
        payload = request.get_json(silent=True) or {}
        text = str(payload.get('text', '') or '').strip() or '这是一条豆包语音测试'
        if not deps._doubao_tts_is_ready():
            return jsonify({'status': 'err', 'msg': '豆包TTS未就绪，请先保存有效配置', **deps._build_notify_tts_runtime_payload(include_secrets=False)}), 400
        started_at = time.perf_counter()
        try:
            audio_b64 = deps._synthesize_doubao_tts_audio_base64(text)
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            return jsonify({'status': 'ok', 'msg': '豆包TTS测试通过', 'latency_ms': elapsed_ms, 'audio_b64_len': len(str(audio_b64 or '')), **deps._build_notify_tts_runtime_payload(include_secrets=False)})
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            return jsonify({'status': 'err', 'msg': f'豆包TTS测试失败: {e}', 'latency_ms': elapsed_ms, **deps._build_notify_tts_runtime_payload(include_secrets=False)}), 500

    @app.route('/api/tts/synthesize', methods=['POST'])
    def tts_synthesize():
        payload = request.get_json(silent=True) or {}
        text = str(payload.get('text', '') or '').strip()
        if not text:
            return jsonify({'status': 'err', 'msg': 'text不能为空'}), 400
        if not deps._doubao_tts_is_ready():
            return jsonify({'status': 'err', 'msg': '豆包TTS未配置或未启用', 'provider': 'browser'}), 503
        try:
            audio_b64 = deps._synthesize_doubao_tts_audio_base64(text)
            return jsonify({
                'status': 'ok',
                'provider': 'doubao',
                'voice_type': str(deps.DOUBAO_TTS_VOICE_TYPE or ''),
                'encoding': str(deps.DOUBAO_TTS_ENCODING or 'mp3'),
                'mime': deps._doubao_tts_mime_by_encoding(deps.DOUBAO_TTS_ENCODING),
                'audio_base64': audio_b64,
            })
        except Exception as e:
            err_msg = str(e)
            deps.log_to_ui('warn', f'🔊 豆包TTS合成失败: {err_msg}')
            return jsonify({'status': 'err', 'msg': err_msg, 'provider': 'doubao'}), 500
