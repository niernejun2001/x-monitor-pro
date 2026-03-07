import threading
import types
import unittest
from unittest import mock

from xmonitor.runtime.action_throttle import throttle_dm_action_if_needed, throttle_reply_action_if_needed
from xmonitor.runtime.timing_helpers import (
    get_random_maintenance_interval,
    get_random_notification_interval,
    get_random_task_parallel,
    schedule_next_notification_refresh_interval,
)


class TimingHelpersTests(unittest.TestCase):
    def _make_deps(self):
        deps = types.SimpleNamespace()
        deps.NOTIFICATION_SCAN_INTERVAL_MIN_SEC = 3.0
        deps.NOTIFICATION_SCAN_INTERVAL_MAX_SEC = 6.0
        deps.NOTIFICATION_REFRESH_INTERVAL_MIN_SEC = 20.0
        deps.NOTIFICATION_REFRESH_INTERVAL_MAX_SEC = 40.0
        deps.NOTIFICATION_REFRESH_COOLDOWN_PROB = 0.0
        deps.NOTIFICATION_REFRESH_COOLDOWN_MIN_SEC = 8.0
        deps.NOTIFICATION_REFRESH_COOLDOWN_MAX_SEC = 22.0
        deps.MAINTENANCE_INTERVAL_MIN_SEC = 60.0
        deps.MAINTENANCE_INTERVAL_MAX_SEC = 120.0
        deps.TASK_PARALLEL_MIN = 2
        deps.TASK_PARALLEL_MAX = 5
        deps.REPLY_ACTION_GAP_MIN_SEC = 1.0
        deps.REPLY_ACTION_GAP_MAX_SEC = 1.2
        deps.DM_ACTION_GAP_MIN_SEC = 0.4
        deps.DM_ACTION_GAP_MAX_SEC = 0.5
        deps.reply_rate_limit_lock = threading.Lock()
        deps.dm_rate_limit_lock = threading.Lock()
        deps.last_reply_action_ts = 0.0
        deps.last_dm_action_ts = 0.0
        deps._get_adaptive_reply_gap_factor = lambda: 1.0
        deps._get_humanize_multiplier = lambda: 1.0
        deps.log_to_ui = lambda level, msg: None
        deps.log_headless_debug = lambda msg: None
        return deps

    def test_notification_and_maintenance_intervals(self):
        deps = self._make_deps()
        self.assertGreaterEqual(get_random_notification_interval(deps), 2.5)
        self.assertGreaterEqual(schedule_next_notification_refresh_interval(25.0, deps), 5.0)
        self.assertGreaterEqual(get_random_maintenance_interval(deps), 60.0)
        parallel = get_random_task_parallel(10, deps)
        self.assertGreaterEqual(parallel, 2)
        self.assertLessEqual(parallel, 5)

    def test_throttle_helpers_update_timestamps(self):
        deps = self._make_deps()
        with mock.patch('time.sleep'):
            throttle_reply_action_if_needed(deps)
            throttle_dm_action_if_needed(deps, stage_text='dm')
        self.assertGreater(deps.last_reply_action_ts, 0.0)
        self.assertGreater(deps.last_dm_action_ts, 0.0)


if __name__ == '__main__':
    unittest.main()
