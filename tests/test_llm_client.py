import json
import types
import unittest
import urllib.error
from unittest import mock

from xmonitor.services.analysis.llm_client import call_openai_compatible_json


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class LlmClientTests(unittest.TestCase):
    def test_openai_client_tolerates_none_temperature_and_max_tokens(self):
        deps = types.SimpleNamespace(
            LLM_FILTER_MODEL='qwen',
            LLM_FILTER_API_KEY='token',
            LLM_FILTER_TIMEOUT_SEC=12.0,
            clamp_llm_timeout=lambda raw: 12.0,
            _llm_filter_endpoint=lambda base_url=None: 'http://127.0.0.1:11434/v1/chat/completions',
        )

        with mock.patch('urllib.request.urlopen', return_value=_FakeResponse({
            'choices': [{'message': {'content': '{"ok": true}'}}],
        })) as mocked_open:
            result, raw = call_openai_compatible_json(
                'system',
                'user',
                deps,
                max_tokens=None,
                temperature=None,
            )

        self.assertEqual(result, {'ok': True})
        self.assertEqual(raw, '{"ok": true}')
        request_obj = mocked_open.call_args.args[0]
        body = json.loads(request_obj.data.decode('utf-8'))
        self.assertEqual(body['max_tokens'], 120)
        self.assertEqual(body['temperature'], 0.0)

    def test_openai_client_retries_on_retryable_urlerror(self):
        deps = types.SimpleNamespace(
            LLM_FILTER_MODEL='qwen',
            LLM_FILTER_API_KEY='token',
            LLM_FILTER_TIMEOUT_SEC=12.0,
            LLM_FILTER_RETRY_COUNT=1,
            LLM_FILTER_RETRY_BACKOFF_SEC=0.01,
            clamp_llm_timeout=lambda raw: 12.0,
            _llm_filter_endpoint=lambda base_url=None: 'http://127.0.0.1:11434/v1/chat/completions',
        )
        calls = {'count': 0}

        def fake_urlopen(req, timeout=0):
            calls['count'] += 1
            if calls['count'] == 1:
                raise urllib.error.URLError('[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1081)')
            return _FakeResponse({'choices': [{'message': {'content': '{"ok": true}'}}]})

        with mock.patch('urllib.request.urlopen', side_effect=fake_urlopen):
            with mock.patch('time.sleep', lambda *_: None):
                result, raw = call_openai_compatible_json('system', 'user', deps)

        self.assertEqual(result, {'ok': True})
        self.assertEqual(raw, '{"ok": true}')
        self.assertEqual(calls['count'], 2)


if __name__ == '__main__':
    unittest.main()
