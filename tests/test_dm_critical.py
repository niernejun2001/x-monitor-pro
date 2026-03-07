import threading
import types
import unittest
from unittest import mock

from xmonitor.runtime.dm_critical import (
    enter_dm_critical,
    is_dm_critical_active,
    leave_dm_critical,
    maybe_log_dm_critical_skip,
)


class DMCriticalTests(unittest.TestCase):
    def _make_deps(self):
        deps = types.SimpleNamespace()
        deps.DM_CRITICAL_LOCK_ENABLED = True
        deps.DM_CRITICAL_MAX_HOLD_SEC = 10
        deps.dm_critical_lock = threading.RLock()
        deps.dm_critical_state_lock = threading.Lock()
        deps.dm_critical_depth = 0
        deps.dm_critical_started_at = 0.0
        deps.dm_critical_last_skip_log_ts = 0.0
        deps.dm_critical_last_timeout_warn_ts = 0.0
        deps.logs = []
        deps.log_to_ui = lambda level, msg: deps.logs.append((level, msg))
        return deps

    def test_enter_leave_and_active(self):
        deps = self._make_deps()
        self.assertTrue(enter_dm_critical(deps))
        self.assertTrue(is_dm_critical_active(deps))
        leave_dm_critical(deps)
        self.assertFalse(is_dm_critical_active(deps))

    def test_timeout_and_skip_log(self):
        deps = self._make_deps()
        enter_dm_critical(deps)
        deps.dm_critical_started_at = 1.0
        with mock.patch('time.time', return_value=20.0):
            self.assertFalse(is_dm_critical_active(deps))
            maybe_log_dm_critical_skip(deps)
        self.assertTrue(any('私信关键区占用超过' in msg for _, msg in deps.logs))
        self.assertTrue(any('已延后通知扫描' in msg for _, msg in deps.logs))


if __name__ == '__main__':
    unittest.main()
