import types
import unittest
from unittest import mock

from xmonitor.services.dm.send_service import send_dm_message


class DMSendServiceTests(unittest.TestCase):
    def _make_deps(self):
        return types.SimpleNamespace(
            DM_EDITOR_SELECTORS=['editor'],
            DM_SEND_BUTTON_SELECTORS=['send'],
            DM_SEND_RETRY_HEADLESS=1,
            DM_SEND_RETRY_NORMAL=1,
            headless_mode=True,
            DM_FORCE_COMPOSER_BINDING=False,
            DM_ASSUME_SUCCESS_AFTER_CLICK=False,
            _sanitize_dm_message_text=lambda text: str(text or '').strip(),
            _is_link_only_message=lambda text: False,
            _build_dm_message_probes=lambda text: ['probe'],
            _read_dm_session_state=lambda tab, handle='': {'url_ok': True, 'conversation_ok': True, 'editor_ok': True, 'send_button_enabled': True},
            _throttle_dm_action_if_needed=lambda stage='': None,
            _prepare_reply_prompt_guard=lambda tab, stage='': None,
            _dm_humanized_idle=lambda tab, low=0.0, high=0.0, stage='': None,
            _handle_dm_passcode_prompt=lambda tab: False,
            _humanized_type_dm_text=lambda tab, editor, text: True,
            _paste_dm_text_exact=lambda tab, editor, text: True,
            _count_dm_probe_occurrence=lambda tab, probe: 0,
            _get_dm_conversation_text=lambda tab: '',
            _count_dm_sent_markers=lambda tab: 0,
            _capture_runtime_diagnostic=lambda *args, **kwargs: None,
            _classify_dm_error_text=lambda err: 'soft_send',
            _is_dm_send_fallback_continuable_error=lambda err: str(err).startswith('E_DM_SEND_BUTTON_CLICK:'),
            log_headless_debug=lambda msg: None,
            log_to_ui=lambda level, msg: None,
        )

    def test_send_dm_message_tries_enter_after_button_click_failure(self):
        deps = self._make_deps()
        tab = types.SimpleNamespace()
        editor = object()
        dom = types.SimpleNamespace(
            find_editor=lambda rounds=2, timeout_each=1.4: editor,
            editor_matches_bound_send=lambda editor_obj: True,
        )

        with mock.patch('xmonitor.services.dm.send_service.DMSendDomHelper', return_value=dom):
            with mock.patch('xmonitor.services.dm.send_service.ensure_editor_text_stable', return_value=(True, '')):
                with mock.patch('xmonitor.services.dm.send_service.attempt_send_via_button', return_value=(False, 'E_DM_SEND_BUTTON_CLICK: click failed')):
                    with mock.patch('xmonitor.services.dm.send_service.attempt_send_via_enter', return_value=(True, '')) as enter_mock:
                        with mock.patch('xmonitor.services.dm.send_service.attempt_send_via_dom', return_value=(False, 'should not run')) as dom_mock:
                            ok, err = send_dm_message(tab, 'hello', deps)

        self.assertTrue(ok)
        self.assertEqual(err, '')
        self.assertEqual(enter_mock.call_count, 1)
        self.assertEqual(dom_mock.call_count, 0)

    def test_send_dm_message_returns_button_error_when_no_fallback_succeeds(self):
        deps = self._make_deps()
        tab = types.SimpleNamespace()
        editor = object()
        dom = types.SimpleNamespace(
            find_editor=lambda rounds=2, timeout_each=1.4: editor,
            editor_matches_bound_send=lambda editor_obj: True,
        )

        with mock.patch('xmonitor.services.dm.send_service.DMSendDomHelper', return_value=dom):
            with mock.patch('xmonitor.services.dm.send_service.ensure_editor_text_stable', return_value=(True, '')):
                with mock.patch('xmonitor.services.dm.send_service.attempt_send_via_button', return_value=(False, 'E_DM_SEND_BUTTON_CLICK: click failed')):
                    with mock.patch('xmonitor.services.dm.send_service.attempt_send_via_enter', return_value=(None, '')):
                        with mock.patch('xmonitor.services.dm.send_service.attempt_send_via_dom', return_value=(None, '')):
                            ok, err = send_dm_message(tab, 'hello', deps)

        self.assertFalse(ok)
        self.assertEqual(err, 'E_DM_SEND_BUTTON_CLICK: click failed')


if __name__ == '__main__':
    unittest.main()
