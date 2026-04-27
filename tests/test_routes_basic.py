import queue
import threading
import types
import unittest
import tempfile
import os
from pathlib import Path

from flask import Flask

from xmonitor.web.basic_routes import register_basic_routes


class FakeMonitorTasksRepo:
    def __init__(self):
        self.tasks = []

    def snapshot(self):
        return list(self.tasks)

    def add(self, url):
        if any(task['url'] == url for task in self.tasks):
            return False
        self.tasks.append({'url': url, 'last_check': '等待'})
        return True

    def remove(self, url):
        before = len(self.tasks)
        self.tasks = [task for task in self.tasks if task['url'] != url]
        return before - len(self.tasks)


class FakePendingRepo:
    def __init__(self):
        self.rows = [
            {'key': 'n1', 'source': '通知页面', 'handle': '@a', 'content': 'one'},
            {'key': 't1', 'source': 'tweet', 'handle': '@b', 'content': 'two'},
        ]

    def snapshot(self):
        return list(self.rows)

    def remove_matching(self, key=None, handle=None):
        before = len(self.rows)
        if key:
            self.rows = [r for r in self.rows if r.get('key') != key]
        elif handle:
            self.rows = [r for r in self.rows if r.get('handle') != handle]
        return before - len(self.rows)

    def clear_results(self, result_type='all'):
        if result_type == 'notify':
            self.rows = [r for r in self.rows if r.get('source') != '通知页面']
        elif result_type == 'tweet':
            self.rows = [r for r in self.rows if r.get('source') == '通知页面']
        else:
            self.rows = []
        return True

    def list_reply_items(self, is_reply_fn, limit=200):
        items = [dict(item) for item in self.rows if is_reply_fn(item)]
        items.reverse()
        return items[:limit]


class FakeBrowserTab:
    def __init__(self):
        self.visited = []

    def get(self, url):
        self.visited.append(url)


class FakeBrowser:
    def __init__(self):
        self.tabs = []

    def new_tab(self):
        tab = FakeBrowserTab()
        self.tabs.append(tab)
        return tab


class RoutesBasicTests(unittest.TestCase):
    def _make_deps(self):
        deps = types.SimpleNamespace()
        deps.BASE_DIR = '/tmp/xmonitor-test'
        deps.data_lock = threading.Lock()
        deps.global_token = 'token'
        deps.monitor_active = False
        deps.pending_results = []
        deps.monitor_tasks = []
        deps.updates_event_seq = 3
        deps.updates_event_buffer = []
        deps.notification_monitoring = True
        deps.delegated_account = ''
        deps.delegated_enabled = False
        deps.headless_mode = True
        deps.notify_reply_templates = ['r1']
        deps.dm_message_templates = ['d1']
        deps.LLM_FILTER_ENABLED = False
        deps.LLM_FILTER_BASE_URL = ''
        deps.LLM_FILTER_API_KEY = ''
        deps.LLM_FILTER_MODEL = ''
        deps.LLM_FILTER_TIMEOUT_SEC = 12.0
        deps.LLM_FILTER_TIMEOUT_MAX_SEC = 30.0
        deps.LLM_FILTER_PROMPT_TEMPLATE = ''
        deps.LLM_INTENT_PROMPT_TEMPLATE = ''
        deps.DM_LLM_REWRITE_ENABLED = False
        deps.DM_LLM_REWRITE_PROMPT_TEMPLATE = ''
        deps.DM_LLM_REWRITE_MAX_CHARS = 200
        deps.DM_LLM_REWRITE_TEMPERATURE = 0.2
        deps.DM_LLM_REWRITE_MAX_REGEN = 1
        deps.DM_LLM_REWRITE_DEDUPE_SIZE = 50
        deps.NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT = ''
        deps.NOTIFICATION_REPLY_ONLY_MODE = True
        deps.notification_refresh_interval = 88.0
        deps.notification_last_refresh_at = 123.0
        deps.notification_next_refresh_at = 211.0
        deps.notification_scan_interval = 9.5
        deps.notification_last_scan_at = 456.0
        deps.notification_next_scan_at = 465.5
        deps.notification_last_new_item_at = 100.0
        deps.notification_idle_scan_streak = 2
        deps.notification_full_refresh_pending = False
        deps.notification_full_refresh_reason = ''
        deps.notification_dm_light_scan_count = 0
        deps.get_notification_schedule_snapshot = lambda: {
            'period_label': 'active',
            'boost_active': True,
            'idle_active': False,
            'scan_multiplier': 0.72,
            'refresh_multiplier': 0.79,
            'idle_scan_streak': deps.notification_idle_scan_streak,
            'boost_age_sec': 23.0,
        }
        deps.format_notification_schedule_snapshot = lambda snapshot: 'period=active mode=boost scanX=0.72 refreshX=0.79 idleStreak=2 boostAge=23s'
        deps._build_notify_tts_runtime_payload = lambda include_secrets=True: {
            'notify_tts_enabled': False,
            'notify_tts_access_token_configured': False,
            'notify_tts_secret_key_configured': False,
        }
        deps._build_notify_server_audio_runtime_payload = lambda: {'notify_server_audio_enabled': False, 'notify_server_audio_ready': False}
        deps._build_twitter_cli_runtime_payload = lambda: {'twitter_cli_enabled': True, 'twitter_cli_available': True}
        deps.build_browser_proxy_runtime_payload = lambda: {
            'browser_proxy_configured': True,
            'browser_proxy_source': 'XMONITOR_PROXY',
            'browser_proxy_display': 'socks5://127.0.0.1:1080',
        }
        deps._get_twitter_cli_status = lambda verify=False: {'status': 'ok', 'verify': bool(verify), 'authenticated': bool(verify)}
        deps._fetch_twitter_cli_tweet_detail = lambda tweet_id, max_count=8, force_refresh=False: {
            'status': 'ok',
            'tweet_id': str(tweet_id),
            'tweet': {'id': str(tweet_id), 'text': 'detail'},
            'reply_count': 0,
        }
        deps._fetch_twitter_cli_user = lambda handle, force_refresh=False: {
            'status': 'ok',
            'handle': str(handle),
            'user': {'screen_name': str(handle).lstrip('@')},
        }
        deps.monitor_tasks_repo = FakeMonitorTasksRepo()
        deps.pending_results_repo = FakePendingRepo()
        deps.processed_users_repo = types.SimpleNamespace(clear=lambda: None)
        deps.processed_users = set()
        deps.save_processed_users = lambda: None
        deps.save_state = lambda: None
        deps.log_to_ui = lambda level, msg: None
        deps.normalize_handle = lambda h: str(h or '').strip().lstrip('@').lower()
        deps.re = __import__('re')
        deps.browser_lock = threading.Lock()
        deps.browser_initialized = False
        deps.global_browser = None
        deps._set_runtime_attr = lambda name, value: setattr(deps, name, value)
        deps.init_global_browser = lambda: FakeBrowser()
        deps.start_monitor_thread = lambda: True
        deps.stop_monitor_thread = lambda wait_timeout=15: True
        deps.msg_queue = queue.Queue()
        deps.drain_msg_queue = lambda collect_new_data=False: [{'id': 1}] if collect_new_data else []
        deps.is_reply_to_me_notification_item = lambda item: item.get('source') == '通知页面'
        deps._ensure_notify_flow_fields = lambda row: row.update({
            'notify_flow_stage': row.get('notify_flow_stage', ''),
            'notify_retry_at': row.get('notify_retry_at', 0.0),
            'notify_dm_text_generated': row.get('notify_dm_text_generated', ''),
        }) or row
        return deps

    def _client(self):
        deps = self._make_deps()
        app = Flask(__name__)
        register_basic_routes(app, deps)
        return app.test_client(), deps

    def test_task_add_and_remove(self):
        client, deps = self._client()
        resp = client.post('/api/task/add', json={'url': 'https://x.com/a'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(deps.monitor_tasks_repo.snapshot()), 1)
        resp2 = client.post('/api/task/remove', json={'url': 'https://x.com/a'})
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(deps.monitor_tasks_repo.snapshot(), [])

    def test_mark_done_and_notify_replies(self):
        client, deps = self._client()
        resp = client.get('/api/notify_replies?limit=10')
        data = resp.get_json()
        self.assertEqual(data['count'], 1)
        resp2 = client.post('/api/mark_done', json={'key': 'n1'})
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(len(deps.pending_results_repo.snapshot()), 1)

    def test_updates_endpoint(self):
        client, _ = self._client()
        resp = client.get('/api/updates')
        data = resp.get_json()
        self.assertEqual(data['last_seq'], 3)
        self.assertEqual(data['new_items'], [{'id': 1}])

    def test_index_includes_asset_version_query(self):
        deps = self._make_deps()
        templates_dir = str((Path(__file__).resolve().parents[1] / 'templates'))
        app = Flask(__name__, template_folder=templates_dir)
        register_basic_routes(app, deps)
        client = app.test_client()
        with tempfile.TemporaryDirectory() as tmpdir:
            deps.BASE_DIR = tmpdir
            os.makedirs(os.path.join(tmpdir, 'static', 'app'), exist_ok=True)
            js_path = os.path.join(tmpdir, 'static', 'app', 'app.js')
            css_path = os.path.join(tmpdir, 'static', 'app', 'app.css')
            with open(js_path, 'w', encoding='utf-8') as f:
                f.write('console.log(1)')
            with open(css_path, 'w', encoding='utf-8') as f:
                f.write('body{}')
            resp = client.get('/')
            html = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('/static/app/app.js?v=', html)
        self.assertIn('/static/app/app.css?v=', html)

    def test_state_endpoint_masks_secret_fields(self):
        client, deps = self._client()
        deps.LLM_FILTER_API_KEY = 'secret-key'
        resp = client.get('/api/state')
        data = resp.get_json()
        self.assertTrue(data['token_configured'])
        self.assertTrue(data['llm_filter_api_key_configured'])
        self.assertNotIn('llm_filter_api_key', data)
        self.assertFalse(data['notify_tts_access_token_configured'])
        self.assertTrue(data['browser_proxy_configured'])
        self.assertEqual(data['browser_proxy_source'], 'XMONITOR_PROXY')
        self.assertEqual(data['browser_proxy_display'], 'socks5://127.0.0.1:1080')
        self.assertTrue(data['twitter_cli_enabled'])
        self.assertTrue(data['twitter_cli_available'])
        self.assertEqual(data['llm_filter_retry_count'], 2)
        self.assertEqual(data['llm_filter_retry_backoff_sec'], 0.35)
        self.assertEqual(data['notification_schedule_snapshot']['period_label'], 'active')
        self.assertEqual(data['notification_schedule_text'], 'period=active mode=boost scanX=0.72 refreshX=0.79 idleStreak=2 boostAge=23s')
        self.assertEqual(data['notification_refresh_interval'], 88.0)
        self.assertEqual(data['notification_next_refresh_at'], 211.0)
        self.assertEqual(data['notification_scan_interval'], 9.5)
        self.assertEqual(data['notification_last_scan_at'], 456.0)
        self.assertEqual(data['notification_next_scan_at'], 465.5)
        self.assertFalse(data['notification_full_refresh_pending'])

    def test_start_route_reuses_saved_token_when_payload_missing(self):
        client, deps = self._client()
        deps.global_token = 'saved-token'
        resp = client.post('/api/start', json={})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(deps.global_token, 'saved-token')

    def test_start_route_requires_token_when_missing_everywhere(self):
        client, deps = self._client()
        deps.global_token = ''
        resp = client.post('/api/start', json={})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('请先配置 Token', resp.get_json()['msg'])

    def test_template_routes(self):
        client, deps = self._client()

        resp_add = client.post('/api/template/add', json={'type': 'reply', 'content': '新回复模板'})
        self.assertEqual(resp_add.status_code, 200)
        self.assertIn('新回复模板', deps.notify_reply_templates)

        idx = deps.notify_reply_templates.index('新回复模板')
        resp_update = client.post('/api/template/update', json={'type': 'reply', 'index': idx, 'content': '改后的回复模板'})
        self.assertEqual(resp_update.status_code, 200)
        self.assertIn('改后的回复模板', deps.notify_reply_templates)
        self.assertNotIn('新回复模板', deps.notify_reply_templates)

        idx2 = deps.notify_reply_templates.index('改后的回复模板')
        resp_delete = client.post('/api/template/delete', json={'type': 'reply', 'index': idx2})
        self.assertEqual(resp_delete.status_code, 200)
        self.assertNotIn('改后的回复模板', deps.notify_reply_templates)

    def test_twitter_cli_routes(self):
        client, _ = self._client()
        resp = client.get('/api/twitter_cli/status?verify=1')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['authenticated'])

        resp2 = client.post('/api/twitter_cli/tweet_detail', json={'tweet_id': '123'})
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.get_json()['tweet_id'], '123')

        resp3 = client.get('/api/twitter_cli/user?handle=@demo')
        self.assertEqual(resp3.status_code, 200)
        self.assertEqual(resp3.get_json()['user']['screen_name'], 'demo')

    def test_clear_results_routes(self):
        client, deps = self._client()

        resp = client.post('/api/clear_results', json={'type': 'notify'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([row['source'] for row in deps.pending_results_repo.snapshot()], ['tweet'])

        resp2 = client.post('/api/clear_results', json={'type': 'all'})
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(deps.pending_results_repo.snapshot(), [])

    def test_clear_blocklist_route(self):
        cleared = {'called': False}
        saved = {'called': False}
        client, deps = self._client()
        deps.processed_users_repo = types.SimpleNamespace(clear=lambda: cleared.__setitem__('called', True))
        deps.save_processed_users = lambda: saved.__setitem__('called', True)

        resp = client.post('/api/clear_blocklist', json={})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(cleared['called'])
        self.assertTrue(saved['called'])

    def test_set_delegated_account_resets_runtime_switch_state(self):
        client, deps = self._client()
        deps.delegated_account = '@oldboss'
        deps.delegated_enabled = True
        deps.delegated_account_active = '@oldboss'
        deps.delegated_switch_ok = True

        resp = client.post('/api/set_delegated_account', json={'account': '@newboss'})
        data = resp.get_json()

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data['delegated_account'], '@newboss')
        self.assertTrue(data['delegated_enabled'])
        self.assertEqual(deps.delegated_account_active, '')
        self.assertFalse(deps.delegated_switch_ok)

    def test_open_user_replies_page_opens_new_tab(self):
        client, deps = self._client()
        resp = client.post('/api/open_user_replies_page', json={'handle': '@Demo_User'})
        data = resp.get_json()

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data['handle'], '@demo_user')
        self.assertEqual(data['url'], 'https://x.com/demo_user/with_replies')

    def test_open_user_replies_page_rejects_invalid_handle(self):
        client, _ = self._client()
        resp = client.post('/api/open_user_replies_page', json={'handle': '@bad-handle'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('推特ID格式不合法', resp.get_json()['msg'])


if __name__ == '__main__':
    unittest.main()
