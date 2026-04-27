import types
import unittest

from xmonitor.services.notify.reply_bootstrap import prepare_notify_reply_context


class NotifyReplyBootstrapTests(unittest.TestCase):
    def test_prepare_notify_reply_context_requires_token(self):
        deps = types.SimpleNamespace(
            global_token='   ',
            extract_status_id_from_notification_item=lambda item: '123',
            _throttle_reply_action_if_needed=lambda: None,
            _set_reply_flow_active=lambda active: None,
            notify_state_facade=types.SimpleNamespace(update_flow_state=lambda *args, **kwargs: True),
            ensure_reply_work_tab=lambda: None,
        )

        ctx, err = prepare_notify_reply_context({'key': 'n1'}, deps)

        self.assertIsNone(ctx)
        self.assertIn('auth_token', err)

    def test_prepare_notify_reply_context_requires_status_id(self):
        deps = types.SimpleNamespace(
            global_token='token',
            extract_status_id_from_notification_item=lambda item: '',
            _throttle_reply_action_if_needed=lambda: None,
            _set_reply_flow_active=lambda active: None,
            notify_state_facade=types.SimpleNamespace(update_flow_state=lambda *args, **kwargs: True),
            ensure_reply_work_tab=lambda: None,
        )

        ctx, err = prepare_notify_reply_context({'key': 'n1'}, deps)

        self.assertIsNone(ctx)
        self.assertIn('状态ID', err)

    def test_prepare_notify_reply_context_builds_progress_context(self):
        flags = []
        deps = types.SimpleNamespace(
            global_token='token',
            extract_status_id_from_notification_item=lambda item: '123',
            _throttle_reply_action_if_needed=lambda: flags.append('throttle'),
            _set_reply_flow_active=lambda active: flags.append(('active', active)),
            notify_state_facade=types.SimpleNamespace(update_flow_state=lambda *args, **kwargs: True),
            ensure_reply_work_tab=lambda: types.SimpleNamespace(url='https://x.com/notifications'),
        )

        ctx, err = prepare_notify_reply_context({'key': 'n1', 'handle': '@demo'}, deps)

        self.assertEqual(err, '')
        self.assertEqual(ctx['status_id'], '123')
        self.assertEqual(ctx['handle_hint'], '@demo')
        self.assertEqual(ctx['task_key'], 'n1')
        self.assertIn('throttle', flags)
        self.assertIn(('active', True), flags)

    def test_prepare_notify_reply_context_resets_flow_active_when_tab_init_fails(self):
        flags = []
        deps = types.SimpleNamespace(
            global_token='token',
            extract_status_id_from_notification_item=lambda item: '123',
            _throttle_reply_action_if_needed=lambda: flags.append('throttle'),
            _set_reply_flow_active=lambda active: flags.append(('active', active)),
            notify_state_facade=types.SimpleNamespace(update_flow_state=lambda *args, **kwargs: True),
            ensure_reply_work_tab=lambda: (_ for _ in ()).throw(RuntimeError('tab failed')),
        )

        ctx, err = prepare_notify_reply_context({'key': 'n1', 'handle': '@demo'}, deps)

        self.assertIsNone(ctx)
        self.assertIn('工作标签页', err)
        self.assertIn(('active', False), flags)


if __name__ == '__main__':
    unittest.main()
