import types
import unittest

from xmonitor.runtime.runtime_state import build_runtime_state, get_runtime_attr, set_runtime_attr


class RuntimeStateTests(unittest.TestCase):
    def test_build_runtime_state_copies_module_fields(self):
        module = types.SimpleNamespace(
            monitor_active=True,
            monitor_thread='thread-1',
            global_browser='browser',
            global_browser_dir='/tmp/browser',
            browser_initialized=True,
            browser_force_temp_profile=True,
            reply_work_tab='reply-tab',
            notification_tab='notify-tab',
            delegated_account_active='demo',
            delegated_switch_ok=True,
            notification_refresh_interval=12.5,
            notification_last_refresh_at=34.5,
            notification_empty_article_streak=2,
            llm_filter_cache={'a': 1},
            dm_llm_rewrite_history=['x'],
            content_dedupe={'sig': 1.0},
            pending_results=[{'k': 1}],
            history_ids={'1'},
            monitor_tasks=['task'],
        )
        state = build_runtime_state(module)
        self.assertTrue(state.monitor_active)
        self.assertEqual(state.global_browser, 'browser')
        self.assertEqual(state.delegated_account_active, 'demo')
        self.assertEqual(state.notification_refresh_interval, 12.5)
        self.assertEqual(state.pending_results, [{'k': 1}])

    def test_set_runtime_attr_updates_module_and_state(self):
        module = types.SimpleNamespace(monitor_active=False)
        module.runtime_state = build_runtime_state(module)
        set_runtime_attr(module, 'monitor_active', True)
        self.assertTrue(module.monitor_active)
        self.assertTrue(module.runtime_state.monitor_active)
        self.assertTrue(get_runtime_attr(module, 'monitor_active'))

    def test_get_runtime_attr_falls_back_to_module_value(self):
        module = types.SimpleNamespace(custom_value=42)
        self.assertEqual(get_runtime_attr(module, 'custom_value'), 42)
        self.assertEqual(get_runtime_attr(module, 'missing', default='x'), 'x')


if __name__ == '__main__':
    unittest.main()
