import types
import unittest

from xmonitor.services.dm.send_support import (
    attempt_send_via_button,
    confirm_send_result,
    ensure_editor_text_stable,
    finish_send_success,
)


class DMSendSupportTests(unittest.TestCase):
    def test_finish_send_success_returns_ok_when_composer_cleared(self):
        debug_logs = []
        deps = types.SimpleNamespace(
            log_headless_debug=lambda msg: debug_logs.append(msg),
            log_to_ui=lambda level, msg: None,
        )
        dom = types.SimpleNamespace(clear_composer_after_success=lambda editor: True)

        ok, err = finish_send_success(dom, deps, object(), success_text='sent')

        self.assertTrue(ok)
        self.assertEqual(err, '')
        self.assertEqual(debug_logs, ['sent'])

    def test_confirm_send_result_returns_uncleared_error_when_unconfirmed(self):
        deps = types.SimpleNamespace(
            DM_SEND_CONFIRM_WAIT_SEC=1.0,
            _confirm_dm_message_sent=lambda *args, **kwargs: False,
            log_headless_debug=lambda msg: None,
            log_to_ui=lambda level, msg: None,
        )
        dom = types.SimpleNamespace(
            composer_cleared=lambda editor: False,
            clear_composer_after_success=lambda editor: False,
        )

        ok, err = confirm_send_result(
            tab=types.SimpleNamespace(),
            dom=dom,
            deps=deps,
            editor_el=object(),
            before_counts={},
            probes=[],
            dm_text='hello',
            link_only_mode=False,
        )

        self.assertFalse(ok)
        self.assertEqual(err, '点击私信发送后输入框未清空')

    def test_ensure_editor_text_stable_link_only_uses_poke(self):
        poked = []
        idle_stages = []
        deps = types.SimpleNamespace(
            _poke_dm_editor_events=lambda tab, editor: poked.append((tab, editor)),
            _dm_humanized_idle=lambda tab, low, high, stage: idle_stages.append(stage),
            _humanized_type_dm_text=lambda tab, editor, text: False,
        )
        calls = {'count': 0}
        dom = types.SimpleNamespace(
            editor_has_text=lambda editor, text: (calls.__setitem__('count', calls['count'] + 1) or calls['count'] >= 2),
            force_fill_dm_editor_text=lambda editor, text: False,
        )

        ok, err = ensure_editor_text_stable(types.SimpleNamespace(), object(), 'https://x.com/demo/status/1', True, deps, dom)

        self.assertTrue(ok)
        self.assertEqual(err, '')
        self.assertEqual(len(poked), 1)

    def test_attempt_send_via_button_returns_click_error(self):
        deps = types.SimpleNamespace(
            _click_with_prompt_guard=lambda tab, btn, action: (False, 'click failed'),
            _dm_humanized_idle=lambda tab, low, high, stage: None,
            _confirm_dm_message_sent=lambda *args, **kwargs: False,
            DM_SEND_CONFIRM_WAIT_SEC=1.0,
            log_headless_debug=lambda msg: None,
            log_to_ui=lambda level, msg: None,
        )
        dom = types.SimpleNamespace(
            wait_send_button_after_input=lambda editor, text, link_mode=False: object(),
            composer_cleared=lambda editor: False,
            clear_composer_after_success=lambda editor: False,
        )

        ok, err = attempt_send_via_button(
            types.SimpleNamespace(),
            object(),
            'hello',
            False,
            deps,
            dom,
            before_counts={},
            probes=[],
        )

        self.assertFalse(ok)
        self.assertEqual(err, 'E_DM_SEND_BUTTON_CLICK: click failed')


if __name__ == '__main__':
    unittest.main()
