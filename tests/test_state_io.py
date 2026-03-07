import json
import os
import tempfile
import time
import types
import unittest
from collections import deque

from xmonitor.storage import state_io
from xmonitor.runtime.runtime_state import build_runtime_state, set_runtime_attr
from xmonitor.storage.storage_sqlite import APP_STATE_KEY, PROCESSED_USERS_KEY, has_blob, has_processed_users_table, has_structured_state, load_blob, load_processed_users_set, load_structured_state


class FakeDeps(types.SimpleNamespace):
    pass


class StateIOTests(unittest.TestCase):
    def _make_deps(self, tmpdir):
        deps = FakeDeps()
        deps.DATA_DIR = tmpdir
        deps.STATE_FILE = os.path.join(tmpdir, 'spider_state.json')
        deps.PROCESSED_FILE = os.path.join(tmpdir, 'processed_users.json')
        deps.SQLITE_STATE_FILE = os.path.join(tmpdir, 'xmonitor_state.sqlite3')
        deps.STATE_JSON_FALLBACK = True
        deps.os = os
        deps.time = time
        deps.global_token = 'token-1'
        deps.monitor_tasks = [{'url': 'https://x.com/demo'}]
        deps.monitor_active = False
        deps.pending_results = [{'key': 'notif_1', 'handle': '@demo', 'content': 'hello', 'source': '通知页面'}]
        deps.notification_monitoring = True
        deps.delegated_account = '@boss'
        deps.delegated_enabled = True
        deps.headless_mode = True
        deps.history_ids = {'hist_1'}
        deps.content_dedupe = {'sig_1': 1.0}
        deps.DEFAULT_NOTIFY_REPLY_TEMPLATES = ['reply default']
        deps.DEFAULT_DM_TEMPLATES = ['dm default']
        deps.notify_reply_templates = ['reply a']
        deps.dm_message_templates = ['dm a']
        deps.LLM_FILTER_ENABLED = True
        deps.LLM_FILTER_BASE_URL = 'http://127.0.0.1:11434/v1'
        deps.LLM_FILTER_API_KEY = 'EMPTY'
        deps.LLM_FILTER_MODEL = 'qwen3.5:4b'
        deps.LLM_FILTER_TIMEOUT_SEC = 12.0
        deps.LLM_FILTER_PROMPT_TEMPLATE = 'prompt'
        deps.LLM_INTENT_PROMPT_TEMPLATE = 'intent prompt'
        deps.DM_LLM_REWRITE_ENABLED = True
        deps.DM_LLM_REWRITE_PROMPT_TEMPLATE = 'rewrite prompt'
        deps.DM_LLM_REWRITE_DEFAULT_PROMPT = 'rewrite default'
        deps.DM_LLM_REWRITE_MAX_CHARS = 200
        deps.DM_LLM_REWRITE_TEMPERATURE = 0.3
        deps.DM_LLM_REWRITE_MAX_REGEN = 1
        deps.DM_LLM_REWRITE_DEDUPE_SIZE = 50
        deps.dm_llm_rewrite_history = deque(['sig-a'], maxlen=50)
        deps.NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT = '关键词A\n关键词B'
        deps.NOTIFY_VOICE_BLOCK_KEYWORDS_BUILTIN = ('builtin',)
        deps.NOTIFY_VOICE_BLOCK_KEYWORDS = ('builtin', '关键词a', '关键词b')
        deps.NOTIFICATION_REPLY_ONLY_MODE = True
        deps.DOUBAO_TTS_ENABLED = False
        deps.DOUBAO_TTS_VOICE_TYPE = ''
        deps.processed_users = {'@old'}
        deps.monitor_started = False
        deps.runtime_state = build_runtime_state(deps)
        deps._set_runtime_attr = lambda name, value: set_runtime_attr(deps, name, value)
        deps.ensure_data_dir = lambda: os.makedirs(tmpdir, exist_ok=True)
        deps._sanitize_template_list = lambda raw, fallback: list(raw) if isinstance(raw, list) and raw else list(fallback)
        deps._normalize_keyword_lines = lambda text: [x.strip() for x in str(text or '').splitlines() if x.strip()]
        deps.clamp_llm_timeout = lambda x: float(x)
        deps._doubao_tts_is_ready = lambda: False
        deps.prune_content_dedupe = lambda: None
        deps.make_content_signature = lambda handle, content: f"{handle}|{content}" if (handle or content) else ''
        deps.start_monitor_thread = lambda: setattr(deps, 'monitor_started', True) or True
        deps.save_state = lambda: state_io.save_state(deps)
        deps.save_processed_users = lambda: state_io.save_processed_users(deps)
        return deps

    def test_save_state_writes_sqlite_and_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = self._make_deps(tmpdir)
            state_io.save_state(deps)
            self.assertTrue(os.path.exists(deps.STATE_FILE))
            self.assertTrue(os.path.exists(deps.SQLITE_STATE_FILE))
            self.assertTrue(has_blob(deps, APP_STATE_KEY))
            payload = load_blob(deps, APP_STATE_KEY)
            self.assertEqual(payload['token'], 'token-1')
            self.assertEqual(payload['tasks'][0]['url'], 'https://x.com/demo')
            self.assertTrue(has_structured_state(deps))
            structured = load_structured_state(deps)
            self.assertEqual(structured['pending_results'][0]['key'], 'notif_1')
            self.assertIn('hist_1', structured['history_ids'])
            self.assertEqual(structured['content_dedupe']['sig_1'], 1.0)

    def test_save_processed_users_writes_sqlite_and_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = self._make_deps(tmpdir)
            state_io.save_processed_users(deps)
            self.assertTrue(os.path.exists(deps.PROCESSED_FILE))
            self.assertTrue(has_blob(deps, PROCESSED_USERS_KEY))
            saved = load_blob(deps, PROCESSED_USERS_KEY)
            self.assertIn('@old', saved)
            self.assertTrue(has_processed_users_table(deps))
            self.assertEqual(load_processed_users_set(deps), ['@old'])

    def test_load_state_migrates_json_into_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = self._make_deps(tmpdir)
            legacy_state = {
                'token': 'legacy-token',
                'tasks': [{'url': 'https://x.com/legacy'}],
                'is_running': False,
                'pending': [{'key': 'legacy_1', 'handle': '@legacy', 'content': 'legacy content', 'source': '通知页面'}],
                'notification_monitoring': False,
                'delegated_account': '@legacyboss',
                'delegated_enabled': True,
                'headless_mode': False,
                'history_ids': ['legacy_hist'],
                'content_dedupe': {'legacy_sig': 2.0},
                'notify_reply_templates': ['r1'],
                'dm_message_templates': ['d1'],
                'llm_filter_enabled': False,
                'llm_filter_base_url': '',
                'llm_filter_api_key': '',
                'llm_filter_model': '',
                'llm_filter_timeout_sec': 10.0,
                'llm_filter_prompt_template': '',
                'llm_intent_prompt_template': '',
                'dm_llm_rewrite_enabled': False,
                'dm_llm_rewrite_prompt_template': '',
                'dm_llm_rewrite_max_chars': 180,
                'dm_llm_rewrite_temperature': 0.2,
                'dm_llm_rewrite_max_regen': 0,
                'dm_llm_rewrite_dedupe_size': 50,
                'dm_llm_rewrite_history': ['x'],
                'notify_voice_block_keywords_text': 'foo',
            }
            with open(deps.STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(legacy_state, f, ensure_ascii=False, indent=2)
            with open(deps.PROCESSED_FILE, 'w', encoding='utf-8') as f:
                json.dump(['@legacy_user'], f, ensure_ascii=False, indent=2)

            deps.global_token = ''
            deps.monitor_tasks = []
            deps.pending_results = []
            deps.history_ids = set()
            deps.content_dedupe = {}
            deps.processed_users = set()
            deps.runtime_state = build_runtime_state(deps)

            state_io.load_state(deps)

            self.assertEqual(deps.global_token, 'legacy-token')
            self.assertEqual(deps.monitor_tasks[0]['url'], 'https://x.com/legacy')
            self.assertIn('legacy_hist', deps.history_ids)
            self.assertIn('@legacy_user', deps.processed_users)
            self.assertTrue(has_blob(deps, APP_STATE_KEY))
            self.assertTrue(has_blob(deps, PROCESSED_USERS_KEY))
            sqlite_state = load_blob(deps, APP_STATE_KEY)
            self.assertEqual(sqlite_state['token'], 'legacy-token')
            self.assertTrue(has_structured_state(deps))
            structured = load_structured_state(deps)
            self.assertEqual(structured['pending_results'][0]['key'], 'legacy_1')
            self.assertIn('legacy_hist', structured['history_ids'])
            self.assertIn('legacy_sig', structured['content_dedupe'])


if __name__ == '__main__':
    unittest.main()
