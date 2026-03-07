import threading
import types
import unittest

from xmonitor.runtime.reply_metrics import (
    is_reply_flow_active_deps,
    record_reply_outcome_deps,
    set_reply_flow_active_deps,
)
from xmonitor.runtime.runtime_state import build_runtime_state, set_runtime_attr


class ReplyMetricsTests(unittest.TestCase):
    def _make_deps(self):
        deps = types.SimpleNamespace()
        deps.reply_flow_state_lock = threading.Lock()
        deps.reply_metrics_lock = threading.Lock()
        deps.reply_outcome_recent = []
        deps.reply_handle_failures = {}
        deps.REPLY_FAILURE_WINDOW_SEC = 60
        deps.REPLY_FAILURE_BUDGET_MAX = 3
        deps.REPLY_FAILURE_COOLDOWN_SEC = 120
        deps.normalize_handle = lambda h: str(h or '').strip().lstrip('@').lower()
        deps.reply_flow_active = False
        deps.reply_failure_streak = 0
        deps.runtime_state = build_runtime_state(deps)
        deps._set_runtime_attr = lambda name, value: set_runtime_attr(deps, name, value)
        deps._get_runtime_attr = lambda name, default=None: getattr(deps.runtime_state, name, default)
        return deps

    def test_reply_flow_active(self):
        deps = self._make_deps()
        set_reply_flow_active_deps(True, deps)
        self.assertTrue(is_reply_flow_active_deps(deps))
        self.assertTrue(deps.runtime_state.reply_flow_active)

    def test_record_reply_outcome(self):
        deps = self._make_deps()
        record_reply_outcome_deps('@demo', False, 'err', deps)
        self.assertEqual(deps.runtime_state.reply_failure_streak, 1)
        self.assertIn('demo', deps.reply_handle_failures)
        record_reply_outcome_deps('@demo', True, '', deps)
        self.assertEqual(deps.runtime_state.reply_failure_streak, 0)


if __name__ == '__main__':
    unittest.main()
