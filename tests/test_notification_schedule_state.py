import types
import unittest

from xmonitor.services.notify.schedule_state import update_notification_refresh_schedule


class NotificationScheduleStateTests(unittest.TestCase):
    def test_update_notification_refresh_schedule_sets_next_refresh_at(self):
        deps = types.SimpleNamespace()
        deps._set_runtime_attr = lambda name, value: setattr(deps, name, value)

        next_at = update_notification_refresh_schedule(deps, last_refresh_at=100.0, interval=25.5)

        self.assertEqual(next_at, 125.5)
        self.assertEqual(deps.notification_last_refresh_at, 100.0)
        self.assertEqual(deps.notification_refresh_interval, 25.5)
        self.assertEqual(deps.notification_next_refresh_at, 125.5)

    def test_update_notification_refresh_schedule_clears_next_refresh_when_clock_is_reset(self):
        deps = types.SimpleNamespace(notification_refresh_interval=30.0)
        deps._set_runtime_attr = lambda name, value: setattr(deps, name, value)

        next_at = update_notification_refresh_schedule(deps, last_refresh_at=0.0)

        self.assertEqual(next_at, 0.0)
        self.assertEqual(deps.notification_last_refresh_at, 0.0)
        self.assertEqual(deps.notification_refresh_interval, 30.0)
        self.assertEqual(deps.notification_next_refresh_at, 0.0)


if __name__ == '__main__':
    unittest.main()
