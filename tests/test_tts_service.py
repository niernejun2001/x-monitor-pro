import io
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from xmonitor.services.audio.tts import (
    _is_retryable_tts_error_message,
    synthesize_doubao_tts_audio_base64,
)


class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TTSServiceTests(unittest.TestCase):
    def _make_deps(self):
        return SimpleNamespace(
            DOUBAO_TTS_ENABLED=True,
            DOUBAO_TTS_APP_ID='app',
            DOUBAO_TTS_ACCESS_TOKEN='token',
            DOUBAO_TTS_VOICE_TYPE='voice',
            DOUBAO_TTS_CLUSTER='volcano_tts',
            DOUBAO_TTS_UID='xmonitor-notify',
            DOUBAO_TTS_ENCODING='mp3',
            DOUBAO_TTS_SPEED_RATIO=1.0,
            DOUBAO_TTS_VOLUME_RATIO=1.0,
            DOUBAO_TTS_PITCH_RATIO=1.0,
            DOUBAO_TTS_ENDPOINT='https://example.com/tts',
            DOUBAO_TTS_TIMEOUT_SEC=3.0,
            DOUBAO_TTS_TEXT_MAX_CHARS=160,
            DOUBAO_TTS_RETRY_COUNT=1,
            DOUBAO_TTS_RETRY_BACKOFF_SEC=0.01,
        )

    def test_retryable_eof_error_detected(self):
        self.assertTrue(_is_retryable_tts_error_message('豆包TTS网络错误: [SSL: UNEXPECTED_EOF_WHILE_READING]'))

    def test_synthesize_retries_once_on_transient_error(self):
        deps = self._make_deps()
        good_payload = json.dumps({'code': 3000, 'data': 'QUJD'}).encode()
        calls = {'count': 0}

        def fake_urlopen(req, timeout=0):
            calls['count'] += 1
            if calls['count'] == 1:
                raise OSError('[SSL: UNEXPECTED_EOF_WHILE_READING]')
            return _Resp(good_payload)

        with mock.patch('urllib.request.urlopen', side_effect=fake_urlopen):
            with mock.patch('time.sleep', lambda *_: None):
                audio = synthesize_doubao_tts_audio_base64('测试播报', deps)

        self.assertEqual(audio, 'QUJD')
        self.assertEqual(calls['count'], 2)


if __name__ == '__main__':
    unittest.main()
