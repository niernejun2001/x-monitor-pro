import time

from flask import jsonify, request

from xmonitor.services.support.error_format import format_runtime_error


def register_tts_routes(app, deps):
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
        resp.update(deps._build_notify_tts_runtime_payload(include_secrets=False))
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
            return jsonify({'status': 'err', 'msg': f'豆包TTS测试失败: {format_runtime_error(e)}', 'latency_ms': elapsed_ms, **deps._build_notify_tts_runtime_payload(include_secrets=False)}), 500

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
            err_msg = format_runtime_error(e)
            deps.log_to_ui('warn', f'🔊 豆包TTS合成失败: {err_msg}')
            return jsonify({'status': 'err', 'msg': err_msg, 'provider': 'doubao'}), 500
