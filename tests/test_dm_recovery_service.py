import types
import unittest

from xmonitor.services.dm_recovery_service import read_dm_session_state, run_dm_send_sequence_once


class DMRecoveryServiceTests(unittest.TestCase):
    def test_read_dm_session_state_requires_target_match(self):
        tab = types.SimpleNamespace(
            url='https://x.com/messages/compose',
            run_js=lambda script, handle: {
                'conversationOk': False,
                'editorOk': True,
                'sendPresent': True,
                'sendEnabled': True,
            },
        )
        deps = types.SimpleNamespace(
            normalize_handle=lambda h: str(h or '').strip().lstrip('@').lower(),
            _is_dm_context_url=lambda url: '/messages' in str(url),
        )
        state = read_dm_session_state(tab, '@demo', deps)
        self.assertTrue(state['url_ok'])
        self.assertTrue(state['editor_ok'])
        self.assertFalse(state['conversation_ok'])
        self.assertFalse(state['ready'])

    def test_run_dm_send_sequence_once_returns_dm_closed_on_link_send(self):
        logs = []
        deps = types.SimpleNamespace(
            _open_dm_editor_for_handle=lambda tab, handle: (object(), ''),
            _send_dm_message_with_retry=lambda tab, text, handle='': (False, '该用户当前不可私信（资料页无私信入口）'),
            _is_dm_closed_error_text=lambda msg: '不可私信' in str(msg or ''),
            _confirm_dm_closed_dual_stage=lambda tab, handle: (True, 'closed_hint_confirmed_twice'),
            normalize_handle=lambda h: str(h or '').strip().lstrip('@').lower(),
            log_to_ui=lambda level, msg: logs.append((level, msg)),
            _sanitize_dm_message_text=lambda text: str(text or '').strip(),
            _prepare_reply_prompt_guard=lambda tab, stage: None,
            _humanized_gap_between_dm_messages=lambda tab: None,
            DM_LLM_DOWN_FALLBACK_TEMPLATE=True,
            _is_dm_llm_fallback_allowed=lambda code, detail: False,
        )
        ok, err, dm_closed = run_dm_send_sequence_once(
            tab=types.SimpleNamespace(),
            dm_handle='@demo',
            share_link='https://x.com/demo/status/1',
            dm_text='hello',
            deps=deps,
        )
        self.assertFalse(ok)
        self.assertTrue(dm_closed)
        self.assertIn('不可私信', err)
        self.assertTrue(any('私信关闭已确认' in msg for _, msg in logs))


if __name__ == '__main__':
    unittest.main()
