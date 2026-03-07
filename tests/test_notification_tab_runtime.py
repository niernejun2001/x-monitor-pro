import threading
import types
import unittest

from xmonitor.services.notification_tab_runtime import scan_persistent_notification_tab


class NotificationTabRuntimeTests(unittest.TestCase):
    def test_returns_zero_without_notification_tab(self):
        deps = types.SimpleNamespace(notification_tab=None)
        self.assertEqual(scan_persistent_notification_tab([], deps), 0)

    def test_scans_and_appends_items(self):
        tab = types.SimpleNamespace(
            url='https://x.com/notifications',
            eles=lambda selector, timeout=0.8: [],
            run_js=lambda script: None,
            refresh=lambda: None,
        )
        deps = types.SimpleNamespace()
        deps.notification_tab = tab
        deps.notification_tab_lock = threading.Lock()
        deps.notification_last_refresh_at = 0.0
        deps.notification_refresh_interval = 1.0
        deps.NOTIFICATION_RECENT_WINDOW_MINUTES = 45
        deps._wait_document_ready = lambda tab_obj, timeout=5.0: None
        deps._set_runtime_attr = lambda name, value: setattr(deps, name, value)
        deps._schedule_next_notification_refresh_interval = lambda prev=None: 10.0
        deps.scan_notifications_page = lambda tab_obj, blocked, minutes: ([{'key': 'k1', 'handle': '@a', 'content': 'hello'}], None)
        deps.notification_disconnect_streak = 0
        deps.LLM_FILTER_ENABLED = False
        deps.LLM_FILTER_BASE_URL = ''
        deps.LLM_FILTER_MODEL = ''
        deps.LLM_FILTER_API_KEY = ''
        deps.LLM_FILTER_TIMEOUT_SEC = 12.0
        deps.analyze_comment_intent = lambda *args, **kwargs: {'intent_score': 0, 'intent_level': 'noise', 'is_intent_user': False, 'force_notify': False, 'llm_used': False, 'reason': '', 'signals': []}
        deps._should_notify_voice_by_intent = lambda analysis: False
        deps.data_lock = threading.Lock()
        deps.history_ids = set()
        deps.should_skip_duplicate_content = lambda handle, content: False
        deps.pending_results = []
        deps.enqueue_new_data = lambda item: None
        deps.save_state = lambda: None
        deps.log_to_ui = lambda level, msg: None
        self.assertEqual(scan_persistent_notification_tab([], deps), 1)
        self.assertEqual(len(deps.pending_results), 1)
        self.assertIn('k1', deps.history_ids)


if __name__ == '__main__':
    unittest.main()
