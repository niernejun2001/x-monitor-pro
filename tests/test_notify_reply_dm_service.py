import types
import unittest

from xmonitor.services.notify.reply_dm_service import (
    prepare_notify_share_link,
    run_notify_dm_followup,
)


class NotifyReplyDmServiceTests(unittest.TestCase):
    def _make_deps(self):
        return types.SimpleNamespace(
            _normalize_dm_share_link=lambda raw, status_id='', status_handle='', fallback_url='': str(raw or fallback_url or ''),
            _get_status_link_from_item=lambda item, matched_handle='', matched_status_id='': str(item.get('status_url', '') or ''),
            _should_use_share_link_quick_path=lambda: False,
            _prepare_reply_prompt_guard=lambda tab, stage='': None,
            _reply_humanized_idle=lambda tab, low=0.0, high=0.0, stage='': None,
            _click_share_copy_link=lambda tab, article, fallback: ('', ''),
            _capture_runtime_diagnostic=lambda *args, **kwargs: '',
            log_to_ui=lambda level, msg: None,
        )

    def test_prepare_notify_share_link_uses_quick_path_when_enabled(self):
        deps = self._make_deps()
        deps._should_use_share_link_quick_path = lambda: True
        item = {'status_url': 'https://x.com/demo/status/123'}

        ok, share_link, err = prepare_notify_share_link(
            tab=types.SimpleNamespace(),
            item=item,
            share_link='',
            need_share=True,
            matched_handle='@demo',
            matched_status_id='123',
            status_id='123',
            deps=deps,
        )

        self.assertTrue(ok)
        self.assertEqual(share_link, 'https://x.com/demo/status/123')
        self.assertEqual(err, '')

    def test_prepare_notify_share_link_normalizes_xdotcom_without_scheme(self):
        deps = self._make_deps()
        deps._click_share_copy_link = lambda tab, article, fallback: ('x.com/demo/status/123', '')
        item = {'status_url': 'https://x.com/demo/status/123', '_target_article': object()}

        ok, share_link, err = prepare_notify_share_link(
            tab=types.SimpleNamespace(),
            item=item,
            share_link='',
            need_share=True,
            matched_handle='@demo',
            matched_status_id='123',
            status_id='123',
            deps=deps,
        )

        self.assertTrue(ok)
        self.assertEqual(share_link, 'https://x.com/demo/status/123')
        self.assertEqual(err, '')

    def test_prepare_notify_share_link_reuses_saved_link_on_resume(self):
        deps = self._make_deps()
        item = {'status_url': 'https://x.com/demo/status/123', 'notify_flow_stage': 'share_link_ready'}

        ok, share_link, err = prepare_notify_share_link(
            tab=types.SimpleNamespace(),
            item=item,
            share_link='https://x.com/demo/status/123',
            need_share=False,
            matched_handle='@demo',
            matched_status_id='123',
            status_id='123',
            deps=deps,
        )

        self.assertTrue(ok)
        self.assertEqual(share_link, 'https://x.com/demo/status/123')
        self.assertEqual(err, '')

    def test_prepare_notify_share_link_returns_error_when_missing(self):
        calls = []
        deps = self._make_deps()
        deps._capture_runtime_diagnostic = lambda *args, **kwargs: calls.append((args, kwargs)) or '/tmp/share-missing.json'
        item = {'status_url': '', '_target_article': object()}

        ok, share_link, err = prepare_notify_share_link(
            tab=types.SimpleNamespace(),
            item=item,
            share_link='',
            need_share=True,
            matched_handle='@demo',
            matched_status_id='123',
            status_id='123',
            deps=deps,
        )

        self.assertFalse(ok)
        self.assertEqual(share_link, '')
        self.assertIn('无法确定要发送的链接', err)
        self.assertEqual(len(calls), 1)

    def test_prepare_notify_share_link_rejects_invalid_url_shape(self):
        deps = self._make_deps()
        deps._click_share_copy_link = lambda tab, article, fallback: ('not-a-url', '')
        item = {'status_url': 'https://x.com/demo/status/123', '_target_article': object()}

        ok, share_link, err = prepare_notify_share_link(
            tab=types.SimpleNamespace(),
            item=item,
            share_link='',
            need_share=True,
            matched_handle='@demo',
            matched_status_id='123',
            status_id='123',
            deps=deps,
        )

        self.assertFalse(ok)
        self.assertEqual(share_link, '')
        self.assertIn('复制链接格式异常', err)

    def test_run_notify_dm_followup_returns_cooldown_error(self):
        deps = self._make_deps()
        deps.notify_state_facade = types.SimpleNamespace(update_flow_state=lambda *args, **kwargs: True)
        deps._sanitize_dm_message_text = lambda text: str(text or '').strip()
        deps.dm_message_templates = []
        deps.DM_FOLLOWUP_TEXT = '默认模板'
        deps.DM_LLM_REWRITE_ENABLED = False
        deps._reserve_notify_dm_user_slot = lambda handle, task_key='': (False, 12.3)
        deps.normalize_handle = lambda h: str(h or '').strip().lstrip('@').lower()

        ok, err, dm_closed = run_notify_dm_followup(
            tab=types.SimpleNamespace(),
            item={'handle': '@Demo'},
            share_link='https://x.com/demo/status/123',
            dm_message='模板',
            dm_progress={'link_sent': False, 'text_sent': False},
            task_key='task-1',
            row_snapshot={},
            deps=deps,
        )

        self.assertFalse(ok)
        self.assertFalse(dm_closed)
        self.assertIn('E_DM_USER_COOLDOWN', err)
        self.assertIn('@demo', err)

    def test_run_notify_dm_followup_uses_default_template_and_marks_opening(self):
        calls = []
        deps = self._make_deps()
        deps.notify_state_facade = types.SimpleNamespace(update_flow_state=lambda *args, **kwargs: True)
        deps._sanitize_dm_message_text = lambda text: str(text or '').strip()
        deps.dm_message_templates = []
        deps.DM_FOLLOWUP_TEXT = '默认模板'
        deps.DM_LLM_REWRITE_ENABLED = False
        deps._reserve_notify_dm_user_slot = lambda handle, task_key='': (True, 0.0)
        deps.normalize_handle = lambda h: str(h or '').strip().lstrip('@').lower()
        deps._run_dm_send_with_recovery = lambda tab, dm_handle, share_link, dm_text, mark_func=None, progress=None, dm_text_supplier=None: (
            calls.append((dm_handle, share_link, dm_text, dm_text_supplier())),
            (True, '', False, tab),
        )[1]

        ok, err, dm_closed, dm_tab = run_notify_dm_followup(
            tab=types.SimpleNamespace(),
            item={'handle': '@Demo'},
            share_link='https://x.com/demo/status/123',
            dm_message='',
            dm_progress={'link_sent': False, 'text_sent': False},
            task_key='task-1',
            row_snapshot={},
            deps=deps,
            mark_stage_func=lambda stage, **kwargs: calls.append(('stage', stage, kwargs)),
        )

        self.assertTrue(ok)
        self.assertEqual(err, '')
        self.assertFalse(dm_closed)
        self.assertIsNotNone(dm_tab)
        self.assertTrue(any(call[0] == 'stage' and call[1] == 'dm_opening' for call in calls))
        dm_call = next(call for call in calls if call[0] == '@Demo')
        self.assertEqual(dm_call[2], '默认模板')
        self.assertTrue(dm_call[3][0])


if __name__ == '__main__':
    unittest.main()
