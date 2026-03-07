import threading
import types
import unittest

from xmonitor.storage.notify_state_facade import NotifyStateFacade


class NotifyStateFacadeTests(unittest.TestCase):
    def _make_deps(self):
        deps = types.SimpleNamespace()
        deps.pending_results = [
            {'key': 'k1', 'source': '通知页面', 'notify_flow_stage': 'retry_waiting', 'notify_retry_at': 0, 'handle': '@a'},
            {'key': 'k2', 'source': 'tweet', 'handle': '@b'},
        ]
        deps.data_lock = threading.Lock()
        deps.DM_RETRY_BACKOFF_SEC = [2, 5, 9]
        deps.DM_TASK_MAX_RETRY = 4
        deps.DM_UNKNOWN_FAILURE_POLICY = 'retry_queue'
        deps.pending_results_repo = types.SimpleNamespace(count_by_source=lambda source: 1 if source == '通知页面' else 0)
        deps._normalize_notify_flow_stage = lambda x: str(x or '').strip().lower()
        deps._split_flow_error = lambda err: ('E_ERR', str(err or ''))
        deps._resolve_notify_resume_stage = lambda row: 'reply_pending'
        deps._is_dm_closed_error_text = lambda msg: 'closed' in str(msg or '').lower()
        deps.save_state = lambda: None
        deps.send_notification_reply = lambda item, reply_text, dm_message='': (True, '')
        deps._record_reply_outcome = lambda handle, ok, err='': None
        deps.log_to_ui = lambda level, message: None
        return deps

    def test_find_update_and_count(self):
        deps = self._make_deps()
        facade = NotifyStateFacade(deps)
        idx, row = facade.find_pending_item_by_key('k1')
        self.assertEqual(idx, 0)
        self.assertEqual(row['handle'], '@a')
        self.assertEqual(facade.get_pending_notify_count(), 1)
        updated = facade.update_flow_state('k1', stage='done', error='', save=False)
        self.assertTrue(updated)
        self.assertEqual(deps.pending_results[0]['notify_flow_stage'], 'done')

    def test_schedule_retry_and_mark_success(self):
        deps = self._make_deps()
        facade = NotifyStateFacade(deps)
        scheduled, retry_at, msg = facade.schedule_retry('k1', 'temporary error', 1, save=False)
        self.assertTrue(scheduled)
        self.assertGreater(retry_at, 0)
        self.assertIn('后重试', msg)
        marked = facade.mark_reply_success('k1', 'reply', 'dm', save=False)
        self.assertTrue(marked)
        self.assertTrue(deps.pending_results[0]['notify_replied'])


if __name__ == '__main__':
    unittest.main()
