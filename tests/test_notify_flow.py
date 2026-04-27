import unittest

from xmonitor.services.notify.flow import (
    ensure_notify_flow_fields,
    normalize_notify_flow_stage,
    notify_stage_at_least,
    notify_stage_rank,
    resolve_notify_resume_stage,
    split_flow_error,
)


class NotifyFlowTests(unittest.TestCase):
    def test_normalize_and_rank_notify_stage(self):
        self.assertEqual(normalize_notify_flow_stage('DM_LINK_SENT'), 'dm_link_sent')
        self.assertEqual(notify_stage_rank('dm_link_sent'), 60)
        self.assertEqual(notify_stage_rank('unknown'), 0)

    def test_notify_stage_at_least(self):
        self.assertTrue(notify_stage_at_least('dm_text_sent', 'dm_link_sent'))
        self.assertFalse(notify_stage_at_least('reply_sent', 'dm_opening'))

    def test_resolve_notify_resume_stage_prefers_resume_hint_for_retry_waiting(self):
        row = {'notify_flow_stage': 'retry_waiting', 'notify_resume_stage': 'dm_opening'}
        self.assertEqual(resolve_notify_resume_stage(row), 'dm_opening')
        self.assertEqual(resolve_notify_resume_stage({'notify_flow_stage': 'retry_waiting'}), 'reply_pending')

    def test_split_flow_error_extracts_code_and_detail(self):
        code, detail = split_flow_error('E_DM_SEND_FAILED: timeout')
        self.assertEqual(code, 'E_DM_SEND_FAILED')
        self.assertEqual(detail, 'timeout')
        code2, detail2 = split_flow_error('plain error')
        self.assertEqual(code2, 'E_REPLY_FAILED')
        self.assertEqual(detail2, 'plain error')

    def test_ensure_notify_flow_fields_sets_defaults(self):
        row = ensure_notify_flow_fields({'key': 'n1'})
        self.assertIn('notify_flow_stage', row)
        self.assertIn('notify_dm_text_generated', row)
        self.assertEqual(row['key'], 'n1')


if __name__ == '__main__':
    unittest.main()
