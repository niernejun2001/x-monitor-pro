import types
import unittest

from xmonitor.services.notify.reply_support import (
    build_notify_tab_ops,
    ensure_notifications_page,
    handle_notify_unhandled_prompt,
    load_notify_resume_state,
    match_notify_target_card,
    restore_notifications_tab,
)


class NotifyReplySupportTests(unittest.TestCase):
    def test_load_notify_resume_state_restores_flags_and_share_link(self):
        updates = []

        class Facade:
            def find_pending_item_by_key(self, key):
                return 0, {
                    'key': key,
                    'notify_flow_stage': 'dm_link_sent',
                    'notify_share_link': 'https://x.com/demo/status/123',
                }

            def update_flow_state(self, key, stage='', error='', retry_at=0.0, extra=None, save=False):
                updates.append((key, stage, extra or {}))
                return True

        deps = types.SimpleNamespace(
            notify_state_facade=Facade(),
            _resolve_notify_resume_stage=lambda row: str(row.get('notify_flow_stage') or 'reply_pending'),
            _normalize_dm_share_link=lambda raw, status_id='', status_handle='', fallback_url='': str(raw or fallback_url or ''),
            _get_status_link_from_item=lambda item: 'https://x.com/demo/status/123',
            _notify_stage_at_least=lambda current, target: {
                ('dm_link_sent', 'reply_sent'): True,
                ('dm_link_sent', 'share_link_ready'): True,
                ('dm_link_sent', 'dm_link_sent'): True,
                ('dm_link_sent', 'dm_text_sent'): False,
            }.get((current, target), False),
        )
        item = {'handle': '@demo', 'status_handle': '@demo'}

        row, stage, share_link, need_reply, need_share, dm_progress = load_notify_resume_state(
            'task-1', item, '123', deps, lambda stage, **kwargs: updates.append(('mark', stage, kwargs))
        )

        self.assertEqual(stage, 'dm_link_sent')
        self.assertEqual(share_link, 'https://x.com/demo/status/123')
        self.assertFalse(need_reply)
        self.assertFalse(need_share)
        self.assertTrue(dm_progress['link_sent'])
        self.assertFalse(dm_progress['text_sent'])

    def test_match_notify_target_card_skips_when_no_work_needed(self):
        logs = []
        deps = types.SimpleNamespace(
            normalize_handle=lambda handle: str(handle or '').strip().lstrip('@').lower(),
            _reply_humanized_idle=lambda *args, **kwargs: None,
            _capture_runtime_diagnostic=lambda *args, **kwargs: '',
        )
        article, btn, score, handle, status_id, err = match_notify_target_card(
            tab=types.SimpleNamespace(),
            item={'handle': '@demo', 'status_handle': '@demo'},
            need_reply=False,
            need_share=False,
            resume_stage='dm_text_sent',
            status_id='123',
            handle_hint='@demo',
            deps=deps,
            mark_func=lambda stage: None,
            mark_stage_func=lambda stage, **kwargs: None,
            log_to_ui=lambda level, msg: logs.append((level, msg)),
            prepare_notifications_view=lambda force_refresh=False: (_ for _ in ()).throw(AssertionError('should not prepare view')),
            match_target_card=lambda: (_ for _ in ()).throw(AssertionError('should not match card')),
        )

        self.assertIsNone(article)
        self.assertIsNone(btn)
        self.assertEqual(score, 0)
        self.assertEqual(handle, 'demo')
        self.assertEqual(status_id, '123')
        self.assertEqual(err, '')
        self.assertTrue(any('跳过通知卡片匹配' in msg for _, msg in logs))

    def test_ensure_notifications_page_navigates_when_off_page(self):
        logs = []
        waits = []
        tab = types.SimpleNamespace(
            url='https://x.com/home',
            get=lambda url: logs.append(('get', url)),
            wait=types.SimpleNamespace(ele_displayed=lambda selector, timeout=5: logs.append(('wait', selector, timeout))),
        )
        deps = types.SimpleNamespace(
            _wait_document_ready=lambda tab_obj, timeout=5.0: waits.append(timeout),
            _reply_humanized_idle=lambda tab_obj, low=0.0, high=0.0, stage='': logs.append(('idle', stage)),
        )

        ensure_notifications_page(tab, deps, lambda level, msg: logs.append((level, msg)))

        self.assertIn(('get', 'https://x.com/notifications'), logs)
        self.assertTrue(waits)
        self.assertTrue(any('已进入通知页' in msg for _, msg in logs if isinstance(msg, str)))

    def test_build_notify_tab_ops_delegates_to_deps_impls(self):
        calls = []
        tab = types.SimpleNamespace()
        item = {'key': 'n1'}
        deps = types.SimpleNamespace(
            _prepare_notifications_view_impl=lambda tab_obj, deps_obj, force_refresh=False: calls.append(('prepare', tab_obj, force_refresh)) or 'p',
            _match_target_card_impl=lambda tab_obj, item_obj, status_id, deps_obj: calls.append(('match', tab_obj, item_obj, status_id)) or 'm',
            _send_reply_from_button_impl=lambda tab_obj, btn, score, reply_text, status_id, handle_hint, deps_obj: calls.append(('send', btn, score, reply_text, status_id, handle_hint)) or 's',
        )

        prepare, match, send = build_notify_tab_ops(tab, item, '123', '@demo', deps)

        self.assertEqual(prepare(force_refresh=True), 'p')
        self.assertEqual(match(), 'm')
        self.assertEqual(send('btn', 320, 'hello'), 's')
        self.assertEqual(calls[0][0], 'prepare')
        self.assertEqual(calls[1][0], 'match')
        self.assertEqual(calls[2][0], 'send')

    def test_handle_notify_unhandled_prompt_prefers_diag_reference(self):
        calls = []
        deps = types.SimpleNamespace(
            _capture_runtime_diagnostic=lambda *args, **kwargs: (calls.append((args, kwargs)) or ('/tmp/diag.json' if kwargs.get('extra', {}).get('phase') == 'before_clear' else '')),
            _prepare_reply_prompt_guard=lambda tab, stage='': calls.append(('guard', stage)),
        )

        ok, err = handle_notify_unhandled_prompt(types.SimpleNamespace(), '123', '@demo', deps, 'prompt')

        self.assertFalse(ok)
        self.assertIn('/tmp/diag.json', err)
        self.assertEqual(len(calls), 3)

    def test_handle_notify_unhandled_prompt_without_diag_reference(self):
        calls = []
        deps = types.SimpleNamespace(
            _capture_runtime_diagnostic=lambda *args, **kwargs: (calls.append((args, kwargs)) or ''),
            _prepare_reply_prompt_guard=lambda tab, stage='': calls.append(('guard', stage)),
        )

        ok, err = handle_notify_unhandled_prompt(types.SimpleNamespace(), '123', '@demo', deps, 'prompt')

        self.assertFalse(ok)
        self.assertNotIn('/tmp/', err)
        self.assertIn('请重试一次', err)

    def test_restore_notifications_tab_returns_to_notifications(self):
        gets = []
        tab = types.SimpleNamespace(url='https://x.com/messages/1', get=lambda url: gets.append(url))

        restore_notifications_tab(tab)

        self.assertEqual(gets, ['https://x.com/notifications'])


if __name__ == '__main__':
    unittest.main()
