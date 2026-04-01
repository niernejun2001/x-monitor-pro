import types
import unittest
from unittest import mock

from xmonitor.services.dm.open_support import (
    DM_PLATFORM_CLOSED_MSG,
    capture_dm_open_failure,
    mark_dm_unavailable_and_return,
    try_open_dm_via_profile_click,
)


class DMOpenSupportTests(unittest.TestCase):
    def test_mark_dm_unavailable_and_return_marks_cache(self):
        marked = []
        deps = types.SimpleNamespace(_mark_dm_unavailable=lambda handle: marked.append(handle))

        editor, err = mark_dm_unavailable_and_return(deps, 'demo', 'closed')

        self.assertIsNone(editor)
        self.assertEqual(err, 'closed')
        self.assertEqual(marked, ['demo'])

    def test_capture_dm_open_failure_returns_standard_error(self):
        captured = []
        deps = types.SimpleNamespace(_capture_runtime_diagnostic=lambda *args, **kwargs: captured.append((args, kwargs)))

        editor, err = capture_dm_open_failure(
            types.SimpleNamespace(),
            'demo',
            ['btn'],
            ['editor'],
            open_attempts=3,
            headless_mode=True,
            dm_entry_mode='direct_compose_first',
            entry_path='profile_click',
            entry_stage='open',
            deps=deps,
        )

        self.assertIsNone(editor)
        self.assertIn('未打开私信输入框', err)
        self.assertEqual(len(captured), 1)

    def test_try_open_dm_via_profile_click_returns_closed_after_failed_rescue(self):
        tab = types.SimpleNamespace(get=lambda url: None)

        with mock.patch('xmonitor.services.dm.open_support.time.sleep', lambda *_: None):
            editor, err, opened_rounds, dm_btn_seen = try_open_dm_via_profile_click(
                tab,
                'demo',
                open_attempts=1,
                has_cannot_dm_hint=lambda: False,
                find_dm_btn=lambda: object(),
                click_with_prompt_guard=lambda tab, btn, action: (True, ''),
                wait_editor_or_closed=lambda timeout_sec=0: (None, 'closed'),
                page_mentions_handle=lambda: False,
                try_rescue_dm_popup_func=lambda *args, **kwargs: False,
                log_headless_debug=lambda msg: None,
                log_to_ui=lambda level, msg: None,
                handle_dm_passcode_prompt=lambda tab: False,
                wait_document_ready=lambda tab, timeout=0: None,
                load_profile_page=lambda tab, handle_norm, attempt: None,
            )

        self.assertIsNone(editor)
        self.assertEqual(err, DM_PLATFORM_CLOSED_MSG)
        self.assertEqual(opened_rounds, 1)
        self.assertTrue(dm_btn_seen)


if __name__ == '__main__':
    unittest.main()
