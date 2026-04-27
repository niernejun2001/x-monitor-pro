import types
import unittest

from xmonitor.runtime.monitor_runtime import (
    _consume_notification_full_refresh_pending,
    _mark_notification_full_refresh_pending,
)


class MonitorRuntimeTests(unittest.TestCase):
    def test_mark_notification_full_refresh_pending_counts_light_scans(self):
        deps = types.SimpleNamespace()
        deps.notification_dm_light_scan_count = 1
        deps._set_runtime_attr = lambda name, value: setattr(deps, name, value)

        count = _mark_notification_full_refresh_pending(deps, reason='dm_critical_scan')

        self.assertEqual(count, 2)
        self.assertTrue(deps.notification_full_refresh_pending)
        self.assertEqual(deps.notification_full_refresh_reason, 'dm_critical_scan')
        self.assertEqual(deps.notification_dm_light_scan_count, 2)

    def test_consume_notification_full_refresh_pending_resets_state(self):
        deps = types.SimpleNamespace(
            notification_full_refresh_pending=True,
            notification_full_refresh_reason='dm_critical_scan',
            notification_dm_light_scan_count=3,
        )
        deps._set_runtime_attr = lambda name, value: setattr(deps, name, value)

        pending, reason, count = _consume_notification_full_refresh_pending(deps)

        self.assertTrue(pending)
        self.assertEqual(reason, 'dm_critical_scan')
        self.assertEqual(count, 3)
        self.assertFalse(deps.notification_full_refresh_pending)
        self.assertEqual(deps.notification_full_refresh_reason, '')
        self.assertEqual(deps.notification_dm_light_scan_count, 0)


if __name__ == '__main__':
    unittest.main()
