import threading
import types
import unittest
from unittest import mock

from xmonitor.runtime.action_throttle import throttle_dm_action_if_needed, throttle_reply_action_if_needed
from xmonitor.runtime.timing_helpers import (
    format_notification_schedule_snapshot,
    get_random_maintenance_interval,
    get_random_notification_interval,
    get_random_task_parallel,
    get_random_notification_refresh_interval,
    get_notification_schedule_snapshot,
    schedule_next_notification_refresh_interval,
)


class TimingHelpersTests(unittest.TestCase):
    def _make_deps(self):
        deps = types.SimpleNamespace()
        deps.NOTIFICATION_SCAN_INTERVAL_MIN_SEC = 6.0
        deps.NOTIFICATION_SCAN_INTERVAL_MAX_SEC = 14.0
        deps.NOTIFICATION_REFRESH_INTERVAL_MIN_SEC = 55.0
        deps.NOTIFICATION_REFRESH_INTERVAL_MAX_SEC = 135.0
        deps.NOTIFICATION_REFRESH_COOLDOWN_PROB = 0.0
        deps.NOTIFICATION_REFRESH_COOLDOWN_MIN_SEC = 16.0
        deps.NOTIFICATION_REFRESH_COOLDOWN_MAX_SEC = 48.0
        deps.NOTIFICATION_ACTIVE_HOURS_START = 8
        deps.NOTIFICATION_ACTIVE_HOURS_END = 23
        deps.NOTIFICATION_ACTIVE_SCAN_MULTIPLIER = 0.92
        deps.NOTIFICATION_ACTIVE_REFRESH_MULTIPLIER = 0.94
        deps.NOTIFICATION_ACTIVE_COOLDOWN_MULTIPLIER = 0.90
        deps.NOTIFICATION_QUIET_SCAN_MULTIPLIER = 1.28
        deps.NOTIFICATION_QUIET_REFRESH_MULTIPLIER = 1.36
        deps.NOTIFICATION_QUIET_COOLDOWN_MULTIPLIER = 1.22
        deps.NOTIFICATION_ADAPTIVE_BOOST_WINDOW_SEC = 210.0
        deps.NOTIFICATION_ADAPTIVE_SCAN_BOOST_MULTIPLIER = 0.78
        deps.NOTIFICATION_ADAPTIVE_REFRESH_BOOST_MULTIPLIER = 0.84
        deps.NOTIFICATION_ADAPTIVE_IDLE_THRESHOLD = 4
        deps.NOTIFICATION_ADAPTIVE_IDLE_SCAN_MULTIPLIER = 1.18
        deps.NOTIFICATION_ADAPTIVE_IDLE_REFRESH_MULTIPLIER = 1.24
        deps.notification_last_new_item_at = 0.0
        deps.notification_idle_scan_streak = 0
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
        notification_interval = get_random_notification_interval(deps)
        refresh_interval = schedule_next_notification_refresh_interval(90.0, deps)
        self.assertGreaterEqual(notification_interval, 5.5)
        self.assertLessEqual(notification_interval, 30.0)
        self.assertGreaterEqual(refresh_interval, 50.0)
        self.assertLessEqual(refresh_interval, 310.0)
        self.assertGreaterEqual(get_random_maintenance_interval(deps), 60.0)
        parallel = get_random_task_parallel(10, deps)
        self.assertGreaterEqual(parallel, 2)
        self.assertLessEqual(parallel, 5)

    def test_quiet_hours_slow_down_notification_scan(self):
        deps = self._make_deps()
        with mock.patch('xmonitor.runtime.timing_helpers.time.localtime', return_value=types.SimpleNamespace(tm_hour=10)):
            with mock.patch('xmonitor.runtime.timing_helpers.random.betavariate', return_value=0.5):
                with mock.patch('xmonitor.runtime.timing_helpers.random.random', return_value=1.0):
                    active_interval = get_random_notification_interval(deps)

        with mock.patch('xmonitor.runtime.timing_helpers.time.localtime', return_value=types.SimpleNamespace(tm_hour=2)):
            with mock.patch('xmonitor.runtime.timing_helpers.random.betavariate', return_value=0.5):
                with mock.patch('xmonitor.runtime.timing_helpers.random.random', return_value=1.0):
                    quiet_interval = get_random_notification_interval(deps)

        self.assertGreater(quiet_interval, active_interval)

    def test_quiet_hours_slow_down_notification_refresh(self):
        deps = self._make_deps()
        with mock.patch('xmonitor.runtime.timing_helpers.time.localtime', return_value=types.SimpleNamespace(tm_hour=14)):
            with mock.patch('xmonitor.runtime.timing_helpers.random.betavariate', return_value=0.5):
                with mock.patch('xmonitor.runtime.timing_helpers.random.random', return_value=1.0):
                    active_refresh = get_random_notification_refresh_interval(deps)

        with mock.patch('xmonitor.runtime.timing_helpers.time.localtime', return_value=types.SimpleNamespace(tm_hour=3)):
            with mock.patch('xmonitor.runtime.timing_helpers.random.betavariate', return_value=0.5):
                with mock.patch('xmonitor.runtime.timing_helpers.random.random', return_value=1.0):
                    quiet_refresh = get_random_notification_refresh_interval(deps)

        self.assertGreater(quiet_refresh, active_refresh)

    def test_recent_hit_boost_speeds_up_notification_scan(self):
        deps = self._make_deps()
        with mock.patch('xmonitor.runtime.timing_helpers.time.localtime', return_value=types.SimpleNamespace(tm_hour=11)):
            with mock.patch('xmonitor.runtime.timing_helpers.time.time', return_value=1000.0):
                with mock.patch('xmonitor.runtime.timing_helpers.random.betavariate', return_value=0.5):
                    with mock.patch('xmonitor.runtime.timing_helpers.random.random', return_value=1.0):
                        normal_interval = get_random_notification_interval(deps)
                        deps.notification_last_new_item_at = 940.0
                        boosted_interval = get_random_notification_interval(deps)

        self.assertLess(boosted_interval, normal_interval)

    def test_idle_streak_slows_down_refresh_interval(self):
        deps = self._make_deps()
        with mock.patch('xmonitor.runtime.timing_helpers.time.localtime', return_value=types.SimpleNamespace(tm_hour=11)):
            with mock.patch('xmonitor.runtime.timing_helpers.time.time', return_value=1000.0):
                with mock.patch('xmonitor.runtime.timing_helpers.random.betavariate', return_value=0.5):
                    with mock.patch('xmonitor.runtime.timing_helpers.random.random', return_value=1.0):
                        normal_refresh = get_random_notification_refresh_interval(deps)
                        deps.notification_idle_scan_streak = 6
                        idle_refresh = get_random_notification_refresh_interval(deps)

        self.assertGreater(idle_refresh, normal_refresh)

    def test_schedule_snapshot_formats_state_summary(self):
        deps = self._make_deps()
        deps.notification_last_new_item_at = 970.0
        with mock.patch('xmonitor.runtime.timing_helpers.time.localtime', return_value=types.SimpleNamespace(tm_hour=11)):
            snapshot = get_notification_schedule_snapshot(deps, now_ts=1000.0)

        self.assertEqual(snapshot['period_label'], 'active')
        self.assertTrue(snapshot['boost_active'])
        text = format_notification_schedule_snapshot(snapshot)
        self.assertIn('period=active', text)
        self.assertIn('mode=boost', text)

    def test_schedule_snapshot_marks_idle_mode(self):
        deps = self._make_deps()
        deps.notification_idle_scan_streak = 6
        with mock.patch('xmonitor.runtime.timing_helpers.time.localtime', return_value=types.SimpleNamespace(tm_hour=2)):
            snapshot = get_notification_schedule_snapshot(deps, now_ts=1000.0)

        self.assertEqual(snapshot['period_label'], 'quiet')
        self.assertTrue(snapshot['idle_active'])
        text = format_notification_schedule_snapshot(snapshot)
        self.assertIn('mode=idle', text)
        self.assertIn('idleStreak=6', text)

    def test_throttle_helpers_update_timestamps(self):
        deps = self._make_deps()
        with mock.patch('time.sleep'):
            throttle_reply_action_if_needed(deps)
            throttle_dm_action_if_needed(deps, stage_text='dm')
        self.assertGreater(deps.last_reply_action_ts, 0.0)
        self.assertGreater(deps.last_dm_action_ts, 0.0)


if __name__ == '__main__':
    unittest.main()
