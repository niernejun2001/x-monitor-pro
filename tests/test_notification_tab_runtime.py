import threading
import types
import unittest

from xmonitor.services.notify.tab_runtime import scan_persistent_notification_tab


class NotificationTabRuntimeTests(unittest.TestCase):
    def test_returns_zero_without_notification_tab(self):
        deps = types.SimpleNamespace(notification_tab=None)
        self.assertEqual(scan_persistent_notification_tab([], deps), 0)

    def test_scans_and_appends_items_after_refresh(self):
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
        deps.scan_notifications_page = lambda tab_obj, blocked, minutes, allow_navigation=True: (
            [{'key': 'k1', 'handle': '@a', 'content': 'hello'}],
            None,
        )
        deps.notification_disconnect_streak = 0
        deps.LLM_FILTER_ENABLED = False
        deps.LLM_FILTER_BASE_URL = ''
        deps.LLM_FILTER_MODEL = ''
        deps.LLM_FILTER_API_KEY = ''
        deps.LLM_FILTER_TIMEOUT_SEC = 12.0
        audio_items = []
        deps.analyze_comment_intent = lambda *args, **kwargs: {'intent_score': 62, 'intent_level': 'medium', 'is_intent_user': True, 'force_notify': True, 'llm_used': False, 'reason': '', 'signals': ['short_reply_intent_signal']}
        deps._should_notify_voice_by_intent = lambda analysis: True
        deps.data_lock = threading.Lock()
        deps.history_ids = set()
        deps.should_skip_duplicate_content = lambda handle, content: False
        deps.pending_results = []
        deps._ensure_notify_flow_fields = lambda row: row
        deps.enqueue_new_data = lambda item: None
        deps._enqueue_notify_server_audio = lambda item: audio_items.append(dict(item))
        deps.save_state = lambda: None
        deps.log_to_ui = lambda level, msg: None
        self.assertEqual(scan_persistent_notification_tab([], deps), 1)
        self.assertEqual(len(deps.pending_results), 1)
        self.assertIn('k1', deps.history_ids)
        self.assertGreater(deps.notification_last_refresh_at, 0.0)
        self.assertEqual(deps.notification_refresh_interval, 10.0)
        self.assertEqual(len(audio_items), 1)
        self.assertTrue(audio_items[0]['voice_should_notify'])

    def test_scan_only_does_not_advance_refresh_clock(self):
        tab = types.SimpleNamespace(
            url='https://x.com/notifications',
            eles=lambda selector, timeout=0.8: [],
            run_js=lambda script: None,
            refresh=lambda: (_ for _ in ()).throw(AssertionError('refresh should not be called')),
        )
        deps = types.SimpleNamespace()
        deps.notification_tab = tab
        deps.notification_tab_lock = threading.Lock()
        deps.notification_last_refresh_at = 123.0
        deps.notification_refresh_interval = 999.0
        deps.NOTIFICATION_RECENT_WINDOW_MINUTES = 45
        deps._wait_document_ready = lambda tab_obj, timeout=5.0: None
        deps._set_runtime_attr = lambda name, value: setattr(deps, name, value)
        deps._schedule_next_notification_refresh_interval = lambda prev=None: (_ for _ in ()).throw(
            AssertionError('refresh interval should not be rescheduled')
        )
        deps.scan_notifications_page = lambda tab_obj, blocked, minutes, allow_navigation=True: ([], None)
        deps.notification_disconnect_streak = 0
        deps.LLM_FILTER_ENABLED = False
        deps.LLM_FILTER_BASE_URL = ''
        deps.LLM_FILTER_MODEL = ''
        deps.LLM_FILTER_API_KEY = ''
        deps.LLM_FILTER_TIMEOUT_SEC = 12.0
        deps.analyze_comment_intent = lambda *args, **kwargs: {}
        deps._should_notify_voice_by_intent = lambda analysis: False
        deps.data_lock = threading.Lock()
        deps.history_ids = set()
        deps.should_skip_duplicate_content = lambda handle, content: False
        deps.pending_results = []
        deps._ensure_notify_flow_fields = lambda row: row
        deps.enqueue_new_data = lambda item: None
        deps._enqueue_notify_server_audio = lambda item: None
        deps.save_state = lambda: None
        logs = []
        deps.log_to_ui = lambda level, msg: logs.append((level, msg))

        self.assertEqual(scan_persistent_notification_tab([], deps), 0)
        self.assertEqual(deps.notification_last_refresh_at, 123.0)
        self.assertEqual(deps.notification_refresh_interval, 999.0)
        self.assertEqual(logs, [])

    def test_allow_refresh_false_keeps_background_scan_without_refresh(self):
        tab = types.SimpleNamespace(
            url='https://x.com/notifications',
            eles=lambda selector, timeout=0.8: [],
            run_js=lambda script: None,
            refresh=lambda: (_ for _ in ()).throw(AssertionError('refresh should not be called')),
        )
        deps = types.SimpleNamespace()
        deps.notification_tab = tab
        deps.notification_tab_lock = threading.Lock()
        deps.notification_last_refresh_at = 0.0
        deps.notification_refresh_interval = 1.0
        deps.NOTIFICATION_RECENT_WINDOW_MINUTES = 45
        deps._wait_document_ready = lambda tab_obj, timeout=5.0: None
        deps._set_runtime_attr = lambda name, value: setattr(deps, name, value)
        deps._schedule_next_notification_refresh_interval = lambda prev=None: (_ for _ in ()).throw(
            AssertionError('refresh interval should not be rescheduled')
        )
        scan_args = []
        deps.scan_notifications_page = lambda tab_obj, blocked, minutes, allow_navigation=True: (
            scan_args.append(allow_navigation) or [{'key': 'k2', 'handle': '@b', 'content': 'world'}],
            None,
        )
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
        deps._ensure_notify_flow_fields = lambda row: row
        deps.enqueue_new_data = lambda item: None
        deps._enqueue_notify_server_audio = lambda item: None
        deps.save_state = lambda: None
        logs = []
        deps.log_to_ui = lambda level, msg: logs.append((level, msg))

        self.assertEqual(scan_persistent_notification_tab([], deps, allow_refresh=False), 1)
        self.assertEqual(scan_args, [False])
        self.assertEqual(len(deps.pending_results), 1)
        self.assertEqual(deps.notification_last_refresh_at, 0.0)
        self.assertEqual(deps.notification_refresh_interval, 1.0)
        self.assertFalse(any('通知刷新策略=' in msg for _, msg in logs))

    def test_empty_article_streak_triggers_soft_recover(self):
        visited = []
        tab = types.SimpleNamespace(
            url='https://x.com/notifications',
            eles=lambda selector, timeout=0.8: [],
            run_js=lambda script: None,
            refresh=lambda: None,
            get=lambda url: visited.append(url),
        )
        deps = types.SimpleNamespace()
        deps.notification_tab = tab
        deps.notification_tab_lock = threading.Lock()
        deps.notification_last_refresh_at = 123.0
        deps.notification_refresh_interval = 999.0
        deps.notification_empty_article_streak = 2
        deps.NOTIFICATION_EMPTY_RECOVER_SOFT_THRESHOLD = 3
        deps.NOTIFICATION_EMPTY_RECOVER_HARD_THRESHOLD = 6
        deps.NOTIFICATION_RECENT_WINDOW_MINUTES = 45
        deps._wait_document_ready = lambda tab_obj, timeout=5.0: None
        deps._set_runtime_attr = lambda name, value: setattr(deps, name, value)
        deps._schedule_next_notification_refresh_interval = lambda prev=None: 17.0
        deps.scan_notifications_page = lambda tab_obj, blocked, minutes, allow_navigation=True: ([], None)
        deps.notification_disconnect_streak = 0
        deps.LLM_FILTER_ENABLED = False
        deps.LLM_FILTER_BASE_URL = ''
        deps.LLM_FILTER_MODEL = ''
        deps.LLM_FILTER_API_KEY = ''
        deps.LLM_FILTER_TIMEOUT_SEC = 12.0
        deps.analyze_comment_intent = lambda *args, **kwargs: {}
        deps._should_notify_voice_by_intent = lambda analysis: False
        deps.data_lock = threading.Lock()
        deps.history_ids = set()
        deps.should_skip_duplicate_content = lambda handle, content: False
        deps.pending_results = []
        deps._ensure_notify_flow_fields = lambda row: row
        deps.enqueue_new_data = lambda item: None
        deps._enqueue_notify_server_audio = lambda item: None
        deps.save_state = lambda: None
        logs = []
        deps.log_to_ui = lambda level, msg: logs.append((level, msg))
        deps.close_notification_tab = lambda: (_ for _ in ()).throw(AssertionError('hard recover should not run'))
        deps.ensure_notification_tab = lambda blocked: None

        self.assertEqual(scan_persistent_notification_tab([], deps), 0)
        self.assertEqual(deps.notification_empty_article_streak, 3)
        self.assertEqual(visited, ['https://x.com/notifications'])
        self.assertEqual(deps.notification_refresh_interval, 17.0)
        self.assertTrue(any('执行软恢复刷新' in msg for _, msg in logs))

    def test_empty_article_streak_triggers_hard_recover(self):
        tab = types.SimpleNamespace(
            url='https://x.com/notifications',
            eles=lambda selector, timeout=0.8: [],
            run_js=lambda script: None,
            refresh=lambda: None,
        )
        events = []
        deps = types.SimpleNamespace()
        deps.notification_tab = tab
        deps.notification_tab_lock = threading.Lock()
        deps.notification_last_refresh_at = 123.0
        deps.notification_refresh_interval = 999.0
        deps.notification_empty_article_streak = 5
        deps.NOTIFICATION_EMPTY_RECOVER_SOFT_THRESHOLD = 3
        deps.NOTIFICATION_EMPTY_RECOVER_HARD_THRESHOLD = 6
        deps.NOTIFICATION_RECENT_WINDOW_MINUTES = 45
        deps._wait_document_ready = lambda tab_obj, timeout=5.0: None
        deps._set_runtime_attr = lambda name, value: setattr(deps, name, value)
        deps._schedule_next_notification_refresh_interval = lambda prev=None: 17.0
        deps.scan_notifications_page = lambda tab_obj, blocked, minutes, allow_navigation=True: ([], None)
        deps.notification_disconnect_streak = 0
        deps.LLM_FILTER_ENABLED = False
        deps.LLM_FILTER_BASE_URL = ''
        deps.LLM_FILTER_MODEL = ''
        deps.LLM_FILTER_API_KEY = ''
        deps.LLM_FILTER_TIMEOUT_SEC = 12.0
        deps.analyze_comment_intent = lambda *args, **kwargs: {}
        deps._should_notify_voice_by_intent = lambda analysis: False
        deps.data_lock = threading.Lock()
        deps.history_ids = set()
        deps.should_skip_duplicate_content = lambda handle, content: False
        deps.pending_results = []
        deps._ensure_notify_flow_fields = lambda row: row
        deps.enqueue_new_data = lambda item: None
        deps._enqueue_notify_server_audio = lambda item: None
        deps.save_state = lambda: None
        logs = []
        deps.log_to_ui = lambda level, msg: logs.append((level, msg))
        deps.close_notification_tab = lambda: events.append('close')
        deps.ensure_notification_tab = lambda blocked: events.append('init')

        self.assertEqual(scan_persistent_notification_tab([], deps), 0)
        self.assertEqual(events, ['close', 'init'])
        self.assertEqual(deps.notification_last_refresh_at, 0.0)
        self.assertTrue(any('重建通知标签页恢复' in msg for _, msg in logs))


if __name__ == '__main__':
    unittest.main()
