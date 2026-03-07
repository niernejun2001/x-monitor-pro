import threading
import types
import unittest

from flask import Flask

from xmonitor.web.routes_notify import register_notify_routes


class FakePendingRepo:
    def __init__(self):
        self.rows = [{'key': 'n1', 'source': '通知页面', 'handle': '@a', 'content': 'hello', 'notify_flow_attempt': 0}]

    def find_notify_by_key(self, key, copy_row=False):
        for idx, row in enumerate(self.rows):
            if row.get('key') == key and row.get('source') == '通知页面':
                return idx, (dict(row) if copy_row else row)
        return -1, None

    def update_notify_manual_reply(self, key, message, dm_message, dm_llm_enabled=False):
        for row in self.rows:
            if row.get('key') == key:
                row['notify_reply_text'] = message
                row['notify_dm_text'] = dm_message
                row['notify_dm_llm_used'] = bool(dm_llm_enabled)
                if not str(row.get('notify_flow_stage', '')).strip():
                    row['notify_flow_stage'] = 'reply_pending'
                return True
        return False


class FakeNotifyFacade:
    def __init__(self):
        self.rows = {'n1': {'key': 'n1', 'source': '通知页面', 'handle': '@a', 'notify_reply_text': 'r', 'notify_dm_text': 'd', 'notify_flow_attempt': 0}}
        self.updated = []
        self.marked = []

    def update_flow_state(self, *args, **kwargs):
        self.updated.append((args, kwargs))
        return True

    def schedule_retry(self, key, err, attempt, reason='retry_queue', save=True):
        return True, 1234567890.0, '已加入重试队列，2s 后重试'

    def mark_reply_success(self, key, message, dm_message, reply_time_text=None, save=True):
        self.marked.append((key, message, dm_message))
        return True

    def find_pending_item_by_key(self, key):
        row = self.rows.get(key)
        return (0, dict(row)) if row else (-1, None)


class RoutesNotifyTests(unittest.TestCase):
    def _client(self, send_ok=True):
        deps = types.SimpleNamespace()
        deps.pending_results_repo = FakePendingRepo()
        deps.notify_state_facade = FakeNotifyFacade()
        deps.DM_LLM_REWRITE_ENABLED = False
        deps.UNHANDLED_PROMPT_AUTO_RETRY = 0
        deps.headless_mode = True
        deps._check_reply_failure_budget = lambda handle: (True, '')
        deps.save_state = lambda: None
        deps.log_to_ui = lambda level, msg: None
        deps._prepare_reply_prompt_guard = lambda tab, stage: None
        deps.ensure_reply_work_tab = lambda force_recreate=False: types.SimpleNamespace(url='https://x.com/notifications', get=lambda url: None)
        deps._wait_document_ready = lambda tab, timeout=5.0: None
        deps._is_unhandled_prompt_error = lambda err: False
        deps._record_reply_outcome = lambda handle, ok, err='': None
        deps._split_flow_error = lambda err: ('E_ERR', str(err))
        deps._resolve_notify_resume_stage = lambda item: 'reply_pending'
        deps.send_notification_reply = (lambda item, message, dm_message='': (True, '')) if send_ok else (lambda item, message, dm_message='': (False, 'fail'))
        app = Flask(__name__)
        register_notify_routes(app, deps)
        return app.test_client(), deps

    def test_notify_reply_missing_key(self):
        client, _ = self._client()
        resp = client.post('/api/notify_reply', json={'message': 'hi'})
        self.assertEqual(resp.status_code, 400)

    def test_notify_reply_success(self):
        client, deps = self._client(send_ok=True)
        resp = client.post('/api/notify_reply', json={'key': 'n1', 'message': 'hi', 'dm_message': 'dm'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['status'], 'ok')
        self.assertTrue(deps.notify_state_facade.marked)

    def test_notify_retry_failure_schedules_retry(self):
        client, _ = self._client(send_ok=False)
        resp = client.post('/api/notify_retry', json={'key': 'n1'})
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.get_json()['status'], 'retry_waiting')


if __name__ == '__main__':
    unittest.main()
