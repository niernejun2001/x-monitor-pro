def build_notify_tts_runtime_payload(deps, include_secrets=True):
    payload = {
        'notify_tts_enabled': bool(deps.DOUBAO_TTS_ENABLED),
        'notify_tts_ready': bool(deps._doubao_tts_is_ready()),
        'notify_tts_provider': ('doubao' if deps._doubao_tts_is_ready() else 'browser'),
        'notify_tts_app_id': str(deps.DOUBAO_TTS_APP_ID or ''),
        'notify_tts_voice_type': str(deps.DOUBAO_TTS_VOICE_TYPE or ''),
        'notify_tts_cluster': str(deps.DOUBAO_TTS_CLUSTER or 'volcano_tts'),
        'notify_tts_endpoint': str(deps.DOUBAO_TTS_ENDPOINT or 'https://openspeech.bytedance.com/api/v1/tts'),
        'notify_tts_uid': str(deps.DOUBAO_TTS_UID or 'xmonitor-notify'),
        'notify_tts_encoding': str(deps.DOUBAO_TTS_ENCODING or 'mp3'),
        'notify_tts_speed_ratio': float(deps.DOUBAO_TTS_SPEED_RATIO),
        'notify_tts_volume_ratio': float(deps.DOUBAO_TTS_VOLUME_RATIO),
        'notify_tts_pitch_ratio': float(deps.DOUBAO_TTS_PITCH_RATIO),
        'notify_tts_timeout_sec': float(deps.DOUBAO_TTS_TIMEOUT_SEC),
        'notify_tts_text_max_chars': int(deps.DOUBAO_TTS_TEXT_MAX_CHARS),
    }
    if include_secrets:
        payload['notify_tts_access_token'] = str(deps.DOUBAO_TTS_ACCESS_TOKEN or '')
        payload['notify_tts_secret_key'] = str(deps.DOUBAO_TTS_SECRET_KEY or '')
    return payload


def normalize_notify_tts_config_from_payload(payload, deps):
    payload = payload or {}
    enabled = bool(payload.get('enabled', deps.DOUBAO_TTS_ENABLED))
    app_id = str(payload.get('app_id', deps.DOUBAO_TTS_APP_ID) or '').strip()
    access_token = str(payload.get('access_token', deps.DOUBAO_TTS_ACCESS_TOKEN) or '').strip()
    secret_key = str(payload.get('secret_key', deps.DOUBAO_TTS_SECRET_KEY) or '').strip()
    voice_type = str(payload.get('voice_type', deps.DOUBAO_TTS_VOICE_TYPE or 'zh_female_vv_uranus_bigtts') or 'zh_female_vv_uranus_bigtts').strip()
    cluster = str(payload.get('cluster', deps.DOUBAO_TTS_CLUSTER or 'volcano_tts') or 'volcano_tts').strip()
    endpoint = str(payload.get('endpoint', deps.DOUBAO_TTS_ENDPOINT or 'https://openspeech.bytedance.com/api/v1/tts') or 'https://openspeech.bytedance.com/api/v1/tts').strip()
    uid = str(payload.get('uid', deps.DOUBAO_TTS_UID or 'xmonitor-notify') or 'xmonitor-notify').strip()
    encoding = str(payload.get('encoding', deps.DOUBAO_TTS_ENCODING or 'mp3') or 'mp3').strip().lower()
    if encoding == 'opus':
        encoding = 'ogg'
    if encoding not in {'mp3', 'wav', 'ogg'}:
        encoding = 'mp3'
    speed_ratio = max(0.5, min(2.0, deps._safe_float(payload.get('speed_ratio', deps.DOUBAO_TTS_SPEED_RATIO), deps.DOUBAO_TTS_SPEED_RATIO)))
    volume_ratio = max(0.2, min(3.0, deps._safe_float(payload.get('volume_ratio', deps.DOUBAO_TTS_VOLUME_RATIO), deps.DOUBAO_TTS_VOLUME_RATIO)))
    pitch_ratio = max(0.5, min(2.0, deps._safe_float(payload.get('pitch_ratio', deps.DOUBAO_TTS_PITCH_RATIO), deps.DOUBAO_TTS_PITCH_RATIO)))
    timeout_sec = max(3.0, min(30.0, deps._safe_float(payload.get('timeout_sec', deps.DOUBAO_TTS_TIMEOUT_SEC), deps.DOUBAO_TTS_TIMEOUT_SEC)))
    text_max_chars = max(20, min(500, deps._safe_int(payload.get('text_max_chars', deps.DOUBAO_TTS_TEXT_MAX_CHARS), deps.DOUBAO_TTS_TEXT_MAX_CHARS)))
    return {
        'enabled': bool(enabled),
        'app_id': app_id,
        'access_token': access_token,
        'secret_key': secret_key,
        'voice_type': voice_type,
        'cluster': cluster or 'volcano_tts',
        'endpoint': endpoint or 'https://openspeech.bytedance.com/api/v1/tts',
        'uid': uid or 'xmonitor-notify',
        'encoding': encoding,
        'speed_ratio': float(speed_ratio),
        'volume_ratio': float(volume_ratio),
        'pitch_ratio': float(pitch_ratio),
        'timeout_sec': float(timeout_sec),
        'text_max_chars': int(text_max_chars),
    }


def apply_notify_tts_config(cfg, deps):
    deps.DOUBAO_TTS_ENABLED = bool(cfg.get('enabled', False))
    deps.DOUBAO_TTS_APP_ID = str(cfg.get('app_id', '') or '').strip()
    deps.DOUBAO_TTS_ACCESS_TOKEN = str(cfg.get('access_token', '') or '').strip()
    deps.DOUBAO_TTS_SECRET_KEY = str(cfg.get('secret_key', '') or '').strip()
    deps.DOUBAO_TTS_VOICE_TYPE = str(cfg.get('voice_type', 'zh_female_vv_uranus_bigtts') or 'zh_female_vv_uranus_bigtts').strip()
    deps.DOUBAO_TTS_CLUSTER = str(cfg.get('cluster', 'volcano_tts') or 'volcano_tts').strip()
    deps.DOUBAO_TTS_ENDPOINT = str(cfg.get('endpoint', 'https://openspeech.bytedance.com/api/v1/tts') or 'https://openspeech.bytedance.com/api/v1/tts').strip()
    deps.DOUBAO_TTS_UID = str(cfg.get('uid', 'xmonitor-notify') or 'xmonitor-notify').strip()
    deps.DOUBAO_TTS_ENCODING = str(cfg.get('encoding', 'mp3') or 'mp3').strip().lower()
    deps.DOUBAO_TTS_SPEED_RATIO = max(0.5, min(2.0, deps._safe_float(cfg.get('speed_ratio', 1.0), 1.0)))
    deps.DOUBAO_TTS_VOLUME_RATIO = max(0.2, min(3.0, deps._safe_float(cfg.get('volume_ratio', 1.35), 1.35)))
    deps.DOUBAO_TTS_PITCH_RATIO = max(0.5, min(2.0, deps._safe_float(cfg.get('pitch_ratio', 1.0), 1.0)))
    deps.DOUBAO_TTS_TIMEOUT_SEC = max(3.0, min(30.0, deps._safe_float(cfg.get('timeout_sec', 12.0), 12.0)))
    deps.DOUBAO_TTS_TEXT_MAX_CHARS = max(20, min(500, deps._safe_int(cfg.get('text_max_chars', 160), 160)))
    deps.LOCAL_TTS_CONFIG = {
        'enabled': '1' if deps.DOUBAO_TTS_ENABLED else '0',
        'app_id': deps.DOUBAO_TTS_APP_ID,
        'access_token': deps.DOUBAO_TTS_ACCESS_TOKEN,
        'secret_key': deps.DOUBAO_TTS_SECRET_KEY,
        'voice_type': deps.DOUBAO_TTS_VOICE_TYPE,
        'cluster': deps.DOUBAO_TTS_CLUSTER,
        'endpoint': deps.DOUBAO_TTS_ENDPOINT,
        'uid': deps.DOUBAO_TTS_UID,
        'encoding': deps.DOUBAO_TTS_ENCODING,
        'speed_ratio': deps.DOUBAO_TTS_SPEED_RATIO,
        'volume_ratio': deps.DOUBAO_TTS_VOLUME_RATIO,
        'pitch_ratio': deps.DOUBAO_TTS_PITCH_RATIO,
        'timeout_sec': deps.DOUBAO_TTS_TIMEOUT_SEC,
        'text_max_chars': deps.DOUBAO_TTS_TEXT_MAX_CHARS,
    }
