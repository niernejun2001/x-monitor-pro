import threading
import types
import unittest
from unittest import mock

from xmonitor.services.dm_flow_service import (
    dm_humanized_idle,
    ensure_dm_context_for_handle,
    should_use_share_link_quick_path,
)


class DMFlowServiceTests(unittest.TestCase):
    def _make_deps(self):
        deps = types.SimpleNamespace()
        deps.SHARE_LINK_QUICK_PATH_MODE = 'adaptive'
        deps.SHARE_LINK_QUICK_PATH = True
        deps.notify_state_facade = types.SimpleNamespace(get_pending_notify_count=lambda: 20)
        deps.reply_metrics_lock = threading.Lock()
        deps.reply_outcome_recent = [1] * 8
        deps.reply_failure_streak = 0
        deps.DM_HUMAN_SCROLL_CHANCE = 0.0
        deps._get_humanize_multiplier = lambda: 1.0
        deps.log_headless_debug = lambda msg: None
        deps.normalize_handle = lambda h: str(h or '').strip().lstrip('@').lower()
        deps._is_dm_context_url = lambda url: 'messages' in str(url)
        deps._open_dm_editor_for_handle = lambda tab, handle: (object(), '') if handle == 'demo' else (None, 'not found')
        deps.log_to_ui = lambda level, msg: None
        return deps

    def test_should_use_share_link_quick_path(self):
        deps = self._make_deps()
        self.assertTrue(should_use_share_link_quick_path(deps))
        deps.reply_failure_streak = 1
        self.assertFalse(should_use_share_link_quick_path(deps))

    def test_ensure_dm_context_for_handle(self):
        deps = self._make_deps()
        tab = types.SimpleNamespace(url='https://x.com/home')
        self.assertTrue(ensure_dm_context_for_handle(tab, '@demo', deps))
        self.assertFalse(ensure_dm_context_for_handle(tab, '@missing', deps))

    def test_dm_humanized_idle(self):
        deps = self._make_deps()
        tab = types.SimpleNamespace(run_js=lambda *args, **kwargs: None)
        with mock.patch('time.sleep') as sleep_mock:
            dm_humanized_idle(tab, deps, low=0.01, high=0.02, stage_text='test')
            self.assertTrue(sleep_mock.called)


if __name__ == '__main__':
    unittest.main()
