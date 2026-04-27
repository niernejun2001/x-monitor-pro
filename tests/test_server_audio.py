import queue
import types
import unittest

from xmonitor.services.audio.server_audio import _server_audio_worker


class ServerAudioTests(unittest.TestCase):
    def test_server_audio_worker_formats_blank_error(self):
        class _BlankError(Exception):
            def __str__(self):
                return ''

        q = queue.Queue()
        q.put({'handle': '@demo', 'content': 'hello'})
        q.put(None)
        logs = []
        deps = types.SimpleNamespace(
            notify_server_audio_queue=q,
            notify_server_audio_last_error='',
            notify_server_audio_last_ok_at=0.0,
            notify_server_audio_queue_size=0,
            DOUBAO_TTS_ENCODING='mp3',
            _truncate_text_for_tts=lambda text: text,
            _synthesize_doubao_tts_audio_base64=lambda text: (_ for _ in ()).throw(_BlankError()),
            log_to_ui=lambda level, msg: logs.append((level, msg)),
        )

        _server_audio_worker(deps)

        self.assertEqual(deps.notify_server_audio_last_error, '_BlankError')
        self.assertTrue(any('_BlankError' in msg for _, msg in logs))


if __name__ == '__main__':
    unittest.main()
