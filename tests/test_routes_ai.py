import threading
import types
import unittest

from flask import Flask

from xmonitor.web.ai_routes import register_ai_routes


class RoutesAITests(unittest.TestCase):
    def _make_deps(self):
        deps = types.SimpleNamespace()
        deps.data_lock = threading.Lock()
        deps.llm_filter_cache_lock = threading.Lock()
        deps.llm_filter_cache = {'cached': {'ts': 1}}
        deps.DM_LLM_REWRITE_DEFAULT_PROMPT = 'default rewrite prompt'
        deps.DM_LLM_REWRITE_PROMPT_TEMPLATE = 'rewrite prompt'
        deps.DM_LLM_REWRITE_ENABLED = False
        deps.DM_LLM_REWRITE_MAX_CHARS = 260
        deps.DM_LLM_REWRITE_TEMPERATURE = 0.35
        deps.DM_LLM_REWRITE_MAX_REGEN = 1
        deps.DM_LLM_REWRITE_DEDUPE_SIZE = 200
        deps.dm_llm_rewrite_history = []
        deps.LLM_FILTER_ENABLED = False
        deps.LLM_FILTER_BASE_URL = ''
        deps.LLM_FILTER_API_KEY = 'EMPTY'
        deps.LLM_FILTER_MODEL = ''
        deps.LLM_FILTER_TIMEOUT_SEC = 8.0
        deps.LLM_FILTER_TIMEOUT_MAX_SEC = 120.0
        deps.LLM_FILTER_RETRY_COUNT = 2
        deps.LLM_FILTER_RETRY_BACKOFF_SEC = 0.35
        deps.LLM_FILTER_PROMPT_TEMPLATE = ''
        deps.LLM_INTENT_PROMPT_TEMPLATE = ''
        deps.NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT = ''
        deps.NOTIFY_VOICE_BLOCK_KEYWORDS = ()
        deps.DOUBAO_TTS_ENABLED = True
        deps.DOUBAO_TTS_APP_ID = 'app-id'
        deps.DOUBAO_TTS_ACCESS_TOKEN = 'token'
        deps.DOUBAO_TTS_SECRET_KEY = 'secret'
        deps.DOUBAO_TTS_VOICE_TYPE = 'voice-type'
        deps.DOUBAO_TTS_CLUSTER = 'volcano_tts'
        deps.DOUBAO_TTS_ENDPOINT = 'https://example.com/tts'
        deps.DOUBAO_TTS_UID = 'uid'
        deps.DOUBAO_TTS_ENCODING = 'mp3'
        deps.DOUBAO_TTS_SPEED_RATIO = 1.0
        deps.DOUBAO_TTS_VOLUME_RATIO = 1.0
        deps.DOUBAO_TTS_PITCH_RATIO = 1.0
        deps.DOUBAO_TTS_TIMEOUT_SEC = 12.0
        deps.DOUBAO_TTS_TEXT_MAX_CHARS = 160
        deps.LOCAL_TTS_CONFIG = {}
        deps._normalize_one_line = lambda text, limit=120: str(text or '')[:limit]
        deps._should_notify_voice_by_intent = lambda analysis: bool(analysis.get('is_intent_user'))
        deps.analyze_comment_intent = lambda content, **kwargs: {
            'intent_score': 88,
            'intent_level': 'high',
            'is_intent_user': True,
            'llm_used': True,
            'reason': '询价',
        }
        deps._call_openai_compatible_json = lambda *args, **kwargs: ({'ok': True, 'message': 'pong'}, '{"ok":true}')
        deps._llm_filter_endpoint = lambda base_url=None: f"{str(base_url or deps.LLM_FILTER_BASE_URL).rstrip('/')}/chat/completions"
        deps.clamp_llm_timeout = lambda raw: max(2.0, min(float(deps.LLM_FILTER_TIMEOUT_MAX_SEC), float(raw)))
        deps._normalize_keyword_lines = lambda text: [x.strip().lower() for x in str(text or '').replace(',', '\n').splitlines() if x.strip()]
        deps._llm_filter_is_ready = lambda: bool(deps.LLM_FILTER_BASE_URL and deps.LLM_FILTER_MODEL)
        deps._normalize_notify_tts_config_from_payload = lambda payload: {
            'enabled': bool(payload.get('enabled', False)),
            'app_id': str(payload.get('app_id', '') or '').strip(),
            'access_token': str(payload.get('access_token', '') or '').strip(),
            'secret_key': str(payload.get('secret_key', '') or '').strip(),
            'voice_type': str(payload.get('voice_type', 'voice-type') or 'voice-type').strip(),
            'cluster': 'volcano_tts',
            'endpoint': 'https://example.com/tts',
            'uid': 'uid',
            'encoding': 'mp3',
            'speed_ratio': 1.0,
            'volume_ratio': 1.0,
            'pitch_ratio': 1.0,
            'timeout_sec': 12.0,
            'text_max_chars': 160,
        }
        deps._apply_notify_tts_config = lambda cfg: deps.__dict__.update({
            'DOUBAO_TTS_ENABLED': cfg['enabled'],
            'DOUBAO_TTS_APP_ID': cfg['app_id'],
            'DOUBAO_TTS_ACCESS_TOKEN': cfg['access_token'],
            'DOUBAO_TTS_SECRET_KEY': cfg['secret_key'],
            'DOUBAO_TTS_VOICE_TYPE': cfg['voice_type'],
            'LOCAL_TTS_CONFIG': dict(cfg),
        })
        deps._save_local_tts_config = lambda cfg: (True, '')
        deps._doubao_tts_is_ready = lambda: bool(deps.DOUBAO_TTS_ENABLED and deps.DOUBAO_TTS_APP_ID and deps.DOUBAO_TTS_ACCESS_TOKEN and deps.DOUBAO_TTS_VOICE_TYPE)
        deps._build_notify_tts_runtime_payload = lambda include_secrets=True: {
            'notify_tts_enabled': bool(deps.DOUBAO_TTS_ENABLED),
            'notify_tts_ready': bool(deps._doubao_tts_is_ready()),
            'notify_tts_provider': 'doubao' if deps._doubao_tts_is_ready() else 'browser',
            'notify_tts_app_id': deps.DOUBAO_TTS_APP_ID,
            'notify_tts_access_token_configured': bool(deps.DOUBAO_TTS_ACCESS_TOKEN),
            'notify_tts_secret_key_configured': bool(deps.DOUBAO_TTS_SECRET_KEY),
            'notify_tts_voice_type': deps.DOUBAO_TTS_VOICE_TYPE,
            'notify_tts_cluster': deps.DOUBAO_TTS_CLUSTER,
            'notify_tts_endpoint': deps.DOUBAO_TTS_ENDPOINT,
            'notify_tts_uid': deps.DOUBAO_TTS_UID,
            'notify_tts_encoding': deps.DOUBAO_TTS_ENCODING,
            'notify_tts_speed_ratio': deps.DOUBAO_TTS_SPEED_RATIO,
            'notify_tts_volume_ratio': deps.DOUBAO_TTS_VOLUME_RATIO,
            'notify_tts_pitch_ratio': deps.DOUBAO_TTS_PITCH_RATIO,
            'notify_tts_timeout_sec': deps.DOUBAO_TTS_TIMEOUT_SEC,
            'notify_tts_text_max_chars': deps.DOUBAO_TTS_TEXT_MAX_CHARS,
            **({'notify_tts_access_token': deps.DOUBAO_TTS_ACCESS_TOKEN, 'notify_tts_secret_key': deps.DOUBAO_TTS_SECRET_KEY} if include_secrets else {}),
        }
        deps._synthesize_doubao_tts_audio_base64 = lambda text: 'QUJD'
        deps._doubao_tts_mime_by_encoding = lambda encoding: 'audio/mpeg'
        deps.save_state = lambda: None
        deps.log_to_ui = lambda level, msg: None
        return deps

    def _client(self):
        deps = self._make_deps()
        app = Flask(__name__)
        register_ai_routes(app, deps)
        return app.test_client(), deps

    def test_llm_filter_test_requires_runtime(self):
        client, _ = self._client()
        resp = client.post('/api/llm_filter/test', json={'base_url': '', 'model': ''})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()['status'], 'err')

    def test_llm_filter_test_success(self):
        client, _ = self._client()
        resp = client.post('/api/llm_filter/test', json={'base_url': 'http://127.0.0.1:11434/v1', 'model': 'qwen3'})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['model'], 'qwen3')
        self.assertIn('/chat/completions', data['endpoint'])

    def test_llm_filter_analyze_returns_analysis(self):
        client, _ = self._client()
        resp = client.post('/api/llm_filter/analyze', json={'content': '老板 咨询一下价格'})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(data['analysis']['voice_should_notify'])
        self.assertEqual(data['analysis']['intent_level'], 'high')

    def test_set_llm_filter_config_updates_runtime(self):
        client, deps = self._client()
        resp = client.post('/api/set_llm_filter_config', json={
            'enabled': True,
            'base_url': 'http://127.0.0.1:11434/v1',
            'api_key': 'EMPTY',
            'model': 'qwen3',
            'timeout_sec': 9,
            'retry_count': 3,
            'retry_backoff_sec': 0.5,
            'notify_voice_block_keywords_text': 'foo\nbar',
            'dm_llm_rewrite_enabled': True,
            'dm_llm_rewrite_prompt_template': 'rewrite me',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['llm_filter_enabled'])
        self.assertEqual(deps.LLM_FILTER_MODEL, 'qwen3')
        self.assertEqual(deps.LLM_FILTER_RETRY_COUNT, 3)
        self.assertEqual(deps.LLM_FILTER_RETRY_BACKOFF_SEC, 0.5)
        self.assertEqual(deps.NOTIFY_VOICE_BLOCK_KEYWORDS, ['foo', 'bar'])
        self.assertEqual(deps.llm_filter_cache, {})
        self.assertTrue(deps.DM_LLM_REWRITE_ENABLED)
        self.assertTrue(data['llm_filter_api_key_configured'])
        self.assertEqual(data['llm_filter_retry_count'], 3)
        self.assertEqual(data['llm_filter_retry_backoff_sec'], 0.5)

    def test_set_llm_filter_config_preserves_api_key_when_omitted(self):
        client, deps = self._client()
        deps.LLM_FILTER_API_KEY = 'keep-me'
        resp = client.post('/api/set_llm_filter_config', json={
            'enabled': True,
            'base_url': 'http://127.0.0.1:11434/v1',
            'model': 'qwen3',
            'timeout_sec': 9,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(deps.LLM_FILTER_API_KEY, 'keep-me')
        self.assertTrue(resp.get_json()['llm_filter_api_key_configured'])

    def test_set_notify_tts_config_updates_runtime(self):
        client, deps = self._client()
        resp = client.post('/api/set_notify_tts_config', json={
            'enabled': True,
            'app_id': 'new-app',
            'access_token': 'new-token',
            'secret_key': 'new-secret',
            'voice_type': 'new-voice',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(deps.DOUBAO_TTS_APP_ID, 'new-app')
        self.assertEqual(deps.DOUBAO_TTS_VOICE_TYPE, 'new-voice')
        self.assertTrue(data['notify_tts_ready'])
        self.assertTrue(data['notify_tts_access_token_configured'])
        self.assertNotIn('notify_tts_access_token', data)

    def test_tts_synthesize_success(self):
        client, _ = self._client()
        resp = client.post('/api/tts/synthesize', json={'text': '测试播报'})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['audio_base64'], 'QUJD')
        self.assertEqual(data['mime'], 'audio/mpeg')

    def test_tts_synthesize_formats_blank_error(self):
        class _BlankError(Exception):
            def __str__(self):
                return ''

        client, deps = self._client()
        deps._synthesize_doubao_tts_audio_base64 = lambda text: (_ for _ in ()).throw(_BlankError())
        logs = []
        deps.log_to_ui = lambda level, msg: logs.append((level, msg))

        resp = client.post('/api/tts/synthesize', json={'text': '测试播报'})

        self.assertEqual(resp.status_code, 500)
        data = resp.get_json()
        self.assertEqual(data['status'], 'err')
        self.assertEqual(data['msg'], '_BlankError')
        self.assertTrue(any('_BlankError' in msg for _, msg in logs))


if __name__ == '__main__':
    unittest.main()
