import queue
import threading
import types
import unittest

from flask import Flask

from xmonitor.web.routes_basic import register_basic_routes


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


class RoutesBasicTests(unittest.TestCase):
    def _make_deps(self):
        deps = types.SimpleNamespace()
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
        deps._build_notify_tts_runtime_payload = lambda include_secrets=True: {'notify_tts_enabled': False}
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
        deps.init_global_browser = lambda: None
        deps.start_monitor_thread = lambda: True
        deps.stop_monitor_thread = lambda wait_timeout=15: True
        deps.msg_queue = queue.Queue()
        deps.drain_msg_queue = lambda collect_new_data=False: [{'id': 1}] if collect_new_data else []
        deps.is_reply_to_me_notification_item = lambda item: item.get('source') == '通知页面'
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


if __name__ == '__main__':
    unittest.main()
