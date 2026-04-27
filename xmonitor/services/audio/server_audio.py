import base64
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time

from xmonitor.services.support.error_format import format_runtime_error


def _safe_log(deps, level, message):
    logger = getattr(deps, 'log_to_ui', None)
    if callable(logger):
        try:
            logger(level, message)
        except Exception:
            pass


def _find_executable(name):
    path = shutil.which(str(name or '').strip())
    return str(path or '').strip()


def detect_server_audio_player():
    ffplay = _find_executable('ffplay')
    if ffplay:
        return {
            'name': 'ffplay',
            'path': ffplay,
            'builder': lambda audio_path: [ffplay, '-nodisp', '-autoexit', '-loglevel', 'error', '-hide_banner', audio_path],
        }
    mpv = _find_executable('mpv')
    if mpv:
        return {
            'name': 'mpv',
            'path': mpv,
            'builder': lambda audio_path: [mpv, '--no-video', '--really-quiet', '--audio-display=no', audio_path],
        }
    mpg123 = _find_executable('mpg123')
    if mpg123:
        return {
            'name': 'mpg123',
            'path': mpg123,
            'builder': lambda audio_path: [mpg123, '-q', audio_path],
        }
    return None


def build_notify_server_audio_runtime_payload(deps):
    player = getattr(deps, 'NOTIFY_SERVER_AUDIO_PLAYER_INFO', None)
    enabled = bool(getattr(deps, 'NOTIFY_SERVER_AUDIO_ENABLED', False))
    return {
        'notify_server_audio_enabled': enabled,
        'notify_server_audio_ready': bool(enabled and player and player.get('path')),
        'notify_server_audio_player': str((player or {}).get('name', '') or ''),
        'notify_server_audio_last_error': str(getattr(deps, 'notify_server_audio_last_error', '') or ''),
        'notify_server_audio_last_ok_at': float(getattr(deps, 'notify_server_audio_last_ok_at', 0.0) or 0.0),
        'notify_server_audio_queue_size': int(getattr(deps, 'notify_server_audio_queue_size', 0) or 0),
    }


def build_notify_voice_text_for_server(content_text, deps):
    raw = str(content_text or '').replace('\r', ' ').replace('\n', ' ').strip()
    if not raw:
        raw = '收到一条新评论'
    text = f'评论内容：{raw}'
    return deps._truncate_text_for_tts(text)


def _write_audio_temp_file(audio_b64, deps):
    encoding = str(getattr(deps, 'DOUBAO_TTS_ENCODING', 'mp3') or 'mp3').strip().lower()
    suffix = '.wav' if encoding == 'wav' else ('.ogg' if encoding in {'ogg', 'opus'} else '.mp3')
    audio_bytes = base64.b64decode(str(audio_b64 or '').strip())
    fd, path = tempfile.mkstemp(prefix='xmonitor-notify-', suffix=suffix)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(audio_bytes)
    except Exception:
        try:
            os.unlink(path)
        except Exception:
            pass
        raise
    return path


def _play_file_with_system_player(audio_path, deps):
    player = getattr(deps, 'NOTIFY_SERVER_AUDIO_PLAYER_INFO', None)
    if not player or not player.get('builder'):
        raise RuntimeError('未找到可用系统播放器')
    cmd = list(player['builder'](audio_path))
    if not cmd:
        raise RuntimeError('系统播放器命令为空')
    proc = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
        timeout=max(5.0, float(getattr(deps, 'DOUBAO_TTS_TIMEOUT_SEC', 12.0) or 12.0) + 20.0),
    )
    if int(proc.returncode or 0) != 0:
        err = ''
        try:
            err = (proc.stderr or b'').decode('utf-8', errors='ignore').strip()
        except Exception:
            err = ''
        raise RuntimeError(f"播放器执行失败(code={proc.returncode}): {err[:240]}")


def _server_audio_worker(deps):
    queue_obj = getattr(deps, 'notify_server_audio_queue', None)
    if queue_obj is None:
        return
    while True:
        try:
            payload = queue_obj.get(timeout=1.0)
        except queue.Empty:
            continue
        if payload is None:
            queue_obj.task_done()
            break
        try:
            text = build_notify_voice_text_for_server(payload.get('content', ''), deps)
            audio_b64 = deps._synthesize_doubao_tts_audio_base64(text)
            audio_path = _write_audio_temp_file(audio_b64, deps)
            try:
                _play_file_with_system_player(audio_path, deps)
            finally:
                try:
                    os.unlink(audio_path)
                except Exception:
                    pass
            deps.notify_server_audio_last_ok_at = time.time()
            deps.notify_server_audio_last_error = ''
            _safe_log(
                deps,
                'debug',
                f"🔊 [ServerAudio] 已播报通知: {payload.get('handle', '') or '-'} {str(payload.get('content', '') or '')[:36]}"
            )
        except Exception as exc:
            err_text = format_runtime_error(exc)
            deps.notify_server_audio_last_error = err_text
            _safe_log(deps, 'warn', f'🔊 [ServerAudio] 播报失败: {err_text}')
        finally:
            try:
                deps.notify_server_audio_queue_size = max(0, int(queue_obj.qsize()))
            except Exception:
                deps.notify_server_audio_queue_size = 0
            queue_obj.task_done()


def ensure_notify_server_audio_worker(deps):
    if not bool(getattr(deps, 'NOTIFY_SERVER_AUDIO_ENABLED', False)):
        return False
    if not getattr(deps, 'NOTIFY_SERVER_AUDIO_PLAYER_INFO', None):
        return False
    lock = getattr(deps, 'notify_server_audio_thread_lock', None)
    if lock is None:
        return False
    with lock:
        thread = getattr(deps, 'notify_server_audio_thread', None)
        if thread and getattr(thread, 'is_alive', lambda: False)():
            return True
        worker = threading.Thread(
            target=_server_audio_worker,
            args=(deps,),
            name='notify-server-audio',
            daemon=True,
        )
        deps.notify_server_audio_thread = worker
        worker.start()
        return True


def enqueue_notify_server_audio(item, deps):
    if not isinstance(item, dict):
        return False
    if not bool(getattr(deps, 'NOTIFY_SERVER_AUDIO_ENABLED', False)):
        return False
    if not bool(item.get('voice_should_notify', False)):
        return False
    if not deps._doubao_tts_is_ready():
        return False
    if not getattr(deps, 'NOTIFY_SERVER_AUDIO_PLAYER_INFO', None):
        return False
    if not ensure_notify_server_audio_worker(deps):
        return False
    queue_obj = getattr(deps, 'notify_server_audio_queue', None)
    if queue_obj is None:
        return False
    payload = {
        'key': str(item.get('key', '') or '').strip(),
        'handle': str(item.get('handle', '') or '').strip(),
        'content': str(item.get('content', '') or '').strip(),
    }
    if not payload['content']:
        return False
    queue_obj.put(payload)
    try:
        deps.notify_server_audio_queue_size = int(queue_obj.qsize())
    except Exception:
        deps.notify_server_audio_queue_size = 0
    return True
