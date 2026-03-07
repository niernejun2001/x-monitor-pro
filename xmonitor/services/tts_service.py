import base64
import json
import urllib.error
import urllib.request
import uuid


def doubao_tts_is_ready(deps):
    return bool(
        deps.DOUBAO_TTS_ENABLED
        and str(deps.DOUBAO_TTS_APP_ID or '').strip()
        and str(deps.DOUBAO_TTS_ACCESS_TOKEN or '').strip()
        and str(deps.DOUBAO_TTS_VOICE_TYPE or '').strip()
    )


def doubao_tts_mime_by_encoding(encoding):
    enc = str(encoding or '').strip().lower()
    if enc == 'wav':
        return 'audio/wav'
    if enc in {'ogg', 'opus'}:
        return 'audio/ogg'
    return 'audio/mpeg'


def truncate_text_for_tts(text, deps):
    content = str(text or '').strip()
    max_chars = max(20, int(deps.DOUBAO_TTS_TEXT_MAX_CHARS))
    if len(content) <= max_chars:
        return content
    return f'{content[:max_chars]}...'


def synthesize_doubao_tts_audio_base64(text, deps):
    if not doubao_tts_is_ready(deps):
        raise RuntimeError('豆包TTS未就绪：请配置 AppID/AccessToken/音色')

    text_payload = truncate_text_for_tts(text, deps)
    if not text_payload:
        raise RuntimeError('语音文本为空')

    req_obj = {
        'app': {
            'appid': str(deps.DOUBAO_TTS_APP_ID),
            'token': str(deps.DOUBAO_TTS_ACCESS_TOKEN),
            'cluster': str(deps.DOUBAO_TTS_CLUSTER),
        },
        'user': {'uid': str(deps.DOUBAO_TTS_UID or 'xmonitor-notify')},
        'audio': {
            'voice_type': str(deps.DOUBAO_TTS_VOICE_TYPE),
            'encoding': str(deps.DOUBAO_TTS_ENCODING or 'mp3'),
            'speed_ratio': float(deps.DOUBAO_TTS_SPEED_RATIO),
            'volume_ratio': float(deps.DOUBAO_TTS_VOLUME_RATIO),
            'pitch_ratio': float(deps.DOUBAO_TTS_PITCH_RATIO),
        },
        'request': {
            'reqid': str(uuid.uuid4()),
            'text': text_payload,
            'text_type': 'plain',
            'operation': 'query',
        },
    }
    body = json.dumps(req_obj, ensure_ascii=False).encode('utf-8')

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer;{deps.DOUBAO_TTS_ACCESS_TOKEN}',
    }
    req = urllib.request.Request(deps.DOUBAO_TTS_ENDPOINT, data=body, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=max(3.0, float(deps.DOUBAO_TTS_TIMEOUT_SEC))) as resp:
            raw_bytes = resp.read() or b''
    except urllib.error.HTTPError as e:
        detail = ''
        try:
            detail = (e.read() or b'').decode('utf-8', errors='ignore')
        except Exception:
            detail = ''
        raise RuntimeError(f'豆包TTS HTTP错误: {e.code} {detail[:200]}') from e
    except urllib.error.URLError as e:
        raise RuntimeError(f'豆包TTS网络错误: {e}') from e

    try:
        resp_obj = json.loads(raw_bytes.decode('utf-8', errors='ignore'))
    except Exception as e:
        raise RuntimeError(f'豆包TTS响应解析失败: {e}') from e

    code = int(resp_obj.get('code', 0) or 0)
    if code not in {0, 3000}:
        msg = str(resp_obj.get('message', '') or '').strip()
        raise RuntimeError(f'豆包TTS返回失败 code={code} msg={msg}')

    audio_b64 = resp_obj.get('data', '')
    if isinstance(audio_b64, dict):
        audio_b64 = audio_b64.get('audio', '')
    audio_b64 = str(audio_b64 or '').strip()
    if not audio_b64:
        raise RuntimeError('豆包TTS返回音频为空')

    try:
        base64.b64decode(audio_b64, validate=True)
    except Exception as e:
        raise RuntimeError(f'豆包TTS音频base64无效: {e}') from e

    return audio_b64
