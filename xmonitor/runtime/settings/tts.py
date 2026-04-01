def safe_float(val, default_val):
    try:
        return float(val)
    except Exception:
        return float(default_val)


def safe_int(val, default_val):
    try:
        return int(val)
    except Exception:
        return int(default_val)


def load_tts_runtime_settings(env, local_cfg, *, detect_server_audio_player_fn):
    env = env or {}
    local_cfg = local_cfg or {}

    app_id = str(env.get('XMONITOR_DOUBAO_TTS_APP_ID', local_cfg.get('app_id', '')) or '').strip()
    access_token = str(env.get('XMONITOR_DOUBAO_TTS_ACCESS_TOKEN', local_cfg.get('access_token', '')) or '').strip()
    secret_key = str(env.get('XMONITOR_DOUBAO_TTS_SECRET_KEY', local_cfg.get('secret_key', '')) or '').strip()
    voice_type = str(
        env.get('XMONITOR_DOUBAO_TTS_VOICE_TYPE', local_cfg.get('voice_type', 'zh_female_vv_uranus_bigtts'))
        or 'zh_female_vv_uranus_bigtts'
    ).strip()
    cluster = str(env.get('XMONITOR_DOUBAO_TTS_CLUSTER', local_cfg.get('cluster', 'volcano_tts')) or 'volcano_tts').strip()
    endpoint = str(
        env.get('XMONITOR_DOUBAO_TTS_ENDPOINT', local_cfg.get('endpoint', 'https://openspeech.bytedance.com/api/v1/tts'))
        or 'https://openspeech.bytedance.com/api/v1/tts'
    ).strip()
    uid = str(env.get('XMONITOR_DOUBAO_TTS_UID', local_cfg.get('uid', 'xmonitor-notify')) or 'xmonitor-notify').strip()
    encoding = str(env.get('XMONITOR_DOUBAO_TTS_ENCODING', local_cfg.get('encoding', 'mp3')) or 'mp3').strip().lower()
    speed_ratio = safe_float(env.get('XMONITOR_DOUBAO_TTS_SPEED_RATIO', local_cfg.get('speed_ratio', 1.0)), 1.0)
    volume_ratio = safe_float(env.get('XMONITOR_DOUBAO_TTS_VOLUME_RATIO', local_cfg.get('volume_ratio', 1.35)), 1.35)
    volume_ratio = max(0.2, min(3.0, float(volume_ratio)))
    pitch_ratio = safe_float(env.get('XMONITOR_DOUBAO_TTS_PITCH_RATIO', local_cfg.get('pitch_ratio', 1.0)), 1.0)
    timeout_sec = safe_float(env.get('XMONITOR_DOUBAO_TTS_TIMEOUT_SEC', local_cfg.get('timeout_sec', 12.0)), 12.0)
    text_max_chars = safe_int(env.get('XMONITOR_DOUBAO_TTS_TEXT_MAX_CHARS', local_cfg.get('text_max_chars', 160)), 160)
    enabled = str(
        env.get(
            'XMONITOR_DOUBAO_TTS_ENABLED',
            local_cfg.get('enabled', '1' if (app_id and access_token) else '0'),
        )
        or ''
    ).strip().lower() in {'1', 'true', 'yes', 'on'}
    server_audio_enabled = str(env.get('XMONITOR_NOTIFY_SERVER_AUDIO_ENABLED', '1') or '').strip().lower() not in {
        '0', 'false', 'no', 'off'
    }

    return {
        'DOUBAO_TTS_APP_ID': app_id,
        'DOUBAO_TTS_ACCESS_TOKEN': access_token,
        'DOUBAO_TTS_SECRET_KEY': secret_key,
        'DOUBAO_TTS_VOICE_TYPE': voice_type,
        'DOUBAO_TTS_CLUSTER': cluster,
        'DOUBAO_TTS_ENDPOINT': endpoint,
        'DOUBAO_TTS_UID': uid,
        'DOUBAO_TTS_ENCODING': encoding,
        'DOUBAO_TTS_SPEED_RATIO': speed_ratio,
        'DOUBAO_TTS_VOLUME_RATIO': volume_ratio,
        'DOUBAO_TTS_PITCH_RATIO': pitch_ratio,
        'DOUBAO_TTS_TIMEOUT_SEC': timeout_sec,
        'DOUBAO_TTS_TEXT_MAX_CHARS': text_max_chars,
        'DOUBAO_TTS_ENABLED': enabled,
        'NOTIFY_SERVER_AUDIO_ENABLED': server_audio_enabled,
        'NOTIFY_SERVER_AUDIO_PLAYER_INFO': detect_server_audio_player_fn(),
    }
