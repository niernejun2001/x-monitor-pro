import types
import unittest

from xmonitor.services.notify.reply_context import NotifyReplyProgressTracker, build_notify_dm_text_supplier


class NotifyReplyContextTests(unittest.TestCase):
    def test_progress_tracker_mark_updates_stage_and_timing(self):
        updates = []
        tracker = NotifyReplyProgressTracker(
            task_key='task-1',
            flow_started_at=0.0,
            notify_state_facade=types.SimpleNamespace(
                update_flow_state=lambda key, **kwargs: updates.append((key, kwargs)) or True
            ),
        )

        tracker.mark('prepare_share_link')

        self.assertIn('prepare_share_link', tracker.stage_marks)
        self.assertEqual(updates[0][0], 'task-1')
        self.assertEqual(updates[0][1]['stage'], 'share_link_ready')

    def test_progress_tracker_mark_stage_ignores_empty_task_key(self):
        updates = []
        tracker = NotifyReplyProgressTracker(
            task_key='',
            flow_started_at=0.0,
            notify_state_facade=types.SimpleNamespace(
                update_flow_state=lambda key, **kwargs: updates.append((key, kwargs)) or True
            ),
        )

        tracker.mark_stage('reply_sent')

        self.assertEqual(updates, [])

    def test_supplier_uses_cached_generated_text(self):
        updates = []
        supplier = build_notify_dm_text_supplier(
            task_key='task-1',
            share_link='https://x.com/demo/status/1',
            dm_template_text='模板文案',
            deps=types.SimpleNamespace(
                DM_LLM_REWRITE_ENABLED=True,
                _sanitize_dm_message_text=lambda text: str(text or '').strip(),
                _generate_dm_text_with_llm=lambda template: (_ for _ in ()).throw(AssertionError('should not call llm')),
            ),
            notify_state_facade=types.SimpleNamespace(update_flow_state=lambda *args, **kwargs: updates.append((args, kwargs)) or True),
            mark_stage=lambda *args, **kwargs: updates.append(('mark', args, kwargs)),
            generated_dm_text_cache='缓存文案',
            generated_dm_meta_cache={'llm_used': True, 'latency_ms': 12, 'regen_attempt': 1},
        )

        ok, text, meta = supplier()

        self.assertTrue(ok)
        self.assertEqual(text, '缓存文案')
        self.assertTrue(meta['cached'])
        self.assertEqual(updates, [])

    def test_supplier_records_failure_meta_when_llm_generation_fails(self):
        updates = []
        supplier = build_notify_dm_text_supplier(
            task_key='task-1',
            share_link='https://x.com/demo/status/1',
            dm_template_text='模板文案',
            deps=types.SimpleNamespace(
                DM_LLM_REWRITE_ENABLED=True,
                _sanitize_dm_message_text=lambda text: str(text or '').strip(),
                _generate_dm_text_with_llm=lambda template: (
                    False,
                    '模板文案',
                    {'error_code': 'E_DM_LLM_GENERATE_FAILED', 'error_detail': 'timeout', 'llm_used': True, 'latency_ms': 321},
                ),
            ),
            notify_state_facade=types.SimpleNamespace(
                update_flow_state=lambda key, **kwargs: updates.append((key, kwargs)) or True
            ),
            mark_stage=lambda *args, **kwargs: updates.append(('mark', args, kwargs)),
            generated_dm_text_cache='',
            generated_dm_meta_cache={},
        )

        ok, text, meta = supplier()

        self.assertFalse(ok)
        self.assertEqual(text, '模板文案')
        self.assertEqual(meta['error_code'], 'E_DM_LLM_GENERATE_FAILED')
        extras = []
        for record in updates:
            if len(record) == 2:
                _, kwargs = record
                extras.append(kwargs.get('extra', {}))
            elif len(record) == 3:
                _, _, kwargs = record
                extras.append(kwargs.get('extra', {}))
        self.assertTrue(any('notify_dm_llm_error_code' in extra for extra in extras))


if __name__ == '__main__':
    unittest.main()
