import types
import unittest

from xmonitor.services.notify.reply_finalize import finalize_notify_dm_followup, log_notify_reply_timing


class NotifyReplyFinalizeTests(unittest.TestCase):
    def test_log_notify_reply_timing_emits_dm_closed_variant(self):
        logs = []
        log_notify_reply_timing(
            lambda level, msg: logs.append((level, msg)),
            {'match_card': 1.0, 'prepare_share_link': 2.0, 'send_reply': 3.0, 'fallback_reply': 4.0},
            flow_started_at=0.0,
            dm_closed=True,
        )
        self.assertTrue(any('私信关闭' in msg for _, msg in logs))

    def test_log_notify_reply_timing_emits_normal_variant(self):
        logs = []
        log_notify_reply_timing(
            lambda level, msg: logs.append((level, msg)),
            {'match_card': 1.0, 'prepare_share_link': 2.0, 'send_reply': 3.0, 'open_dm': 4.0, 'send_dm_link': 5.0, 'send_dm_text': 6.0},
            flow_started_at=0.0,
            dm_closed=False,
        )
        self.assertTrue(any('发文案' in msg for _, msg in logs))

    def test_finalize_notify_dm_followup_returns_error_when_dm_failed_without_closed(self):
        deps = types.SimpleNamespace(log_to_ui=lambda level, msg: None, DM_CLOSED_FALLBACK_REPLY_TEXT='fallback')

        ok, err = finalize_notify_dm_followup(
            tab=types.SimpleNamespace(),
            ok_dm=False,
            dm_err='boom',
            dm_closed=False,
            share_link='https://x.com/demo/status/1',
            status_id='123',
            handle_hint='@demo',
            flow_started_at=0.0,
            stage_marks={},
            deps=deps,
            mark_func=lambda stage: None,
            mark_stage_func=lambda stage, **kwargs: None,
            prepare_notifications_view=lambda force_refresh=False: None,
            match_target_card=lambda: (None, None, 0, '', '', ''),
            send_reply_from_button=lambda btn, score, text: (True, ''),
        )

        self.assertFalse(ok)
        self.assertEqual(err, 'boom')

    def test_finalize_notify_dm_followup_sends_closed_fallback_reply(self):
        marks = []
        logs = []
        deps = types.SimpleNamespace(
            log_to_ui=lambda level, msg: logs.append((level, msg)),
            DM_CLOSED_FALLBACK_REPLY_TEXT='fallback',
            _wait_document_ready=lambda tab, timeout=5.5: None,
        )
        tab = types.SimpleNamespace(url='https://x.com/messages/1', get=lambda url: logs.append(('get', url)))

        ok, err = finalize_notify_dm_followup(
            tab=tab,
            ok_dm=False,
            dm_err='closed',
            dm_closed=True,
            share_link='https://x.com/demo/status/1',
            status_id='123',
            handle_hint='@demo',
            flow_started_at=0.0,
            stage_marks={},
            deps=deps,
            mark_func=lambda stage: marks.append(stage),
            mark_stage_func=lambda stage, **kwargs: marks.append((stage, kwargs)),
            prepare_notifications_view=lambda force_refresh=False: logs.append(('prepare', force_refresh)),
            match_target_card=lambda: ('article', 'reply_btn', 320, '@demo', '123', ''),
            send_reply_from_button=lambda btn, score, text: (True, ''),
        )

        self.assertTrue(ok)
        self.assertEqual(err, '')
        self.assertTrue(any(stage == 'fallback_reply' for stage in marks if isinstance(stage, str)))
        self.assertTrue(any('私信关闭' in msg for _, msg in logs if isinstance(msg, str)))

    def test_finalize_notify_dm_followup_returns_error_when_closed_fallback_reply_fails(self):
        deps = types.SimpleNamespace(
            log_to_ui=lambda level, msg: None,
            DM_CLOSED_FALLBACK_REPLY_TEXT='fallback',
            _wait_document_ready=lambda tab, timeout=5.5: None,
        )
        tab = types.SimpleNamespace(url='https://x.com/messages/1', get=lambda url: None)

        ok, err = finalize_notify_dm_followup(
            tab=tab,
            ok_dm=False,
            dm_err='closed',
            dm_closed=True,
            share_link='https://x.com/demo/status/1',
            status_id='123',
            handle_hint='@demo',
            flow_started_at=0.0,
            stage_marks={},
            deps=deps,
            mark_func=lambda stage: None,
            mark_stage_func=lambda stage, **kwargs: None,
            prepare_notifications_view=lambda force_refresh=False: None,
            match_target_card=lambda: (None, None, 0, '', '', 'match failed'),
            send_reply_from_button=lambda btn, score, text: (True, ''),
        )

        self.assertFalse(ok)
        self.assertIn('补充评论失败', err)


if __name__ == '__main__':
    unittest.main()
