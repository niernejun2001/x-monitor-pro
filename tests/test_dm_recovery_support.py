import types
import unittest

from xmonitor.services.dm.recovery_support import (
    execute_dm_recovery_strategies,
    prepare_second_dm_text,
    resolve_dm_send_failure,
    resolve_open_dm_failure,
)


class DMRecoverySupportTests(unittest.TestCase):
    def test_resolve_open_dm_failure_returns_closed_when_confirmed(self):
        logs = []
        deps = types.SimpleNamespace(
            _is_dm_closed_error_text=lambda msg: '不可私信' in str(msg or ''),
            _confirm_dm_closed_dual_stage=lambda tab, handle: (True, 'confirmed'),
            normalize_handle=lambda h: str(h or '').strip().lstrip('@').lower(),
            log_to_ui=lambda level, msg: logs.append((level, msg)),
        )

        err, closed = resolve_open_dm_failure(types.SimpleNamespace(), '@demo', '该用户当前不可私信', deps)

        self.assertTrue(closed)
        self.assertIn('不可私信', err)
        self.assertTrue(any('私信关闭已确认' in msg for _, msg in logs))

    def test_resolve_dm_send_failure_wraps_non_closed_error(self):
        deps = types.SimpleNamespace(
            _is_dm_closed_error_text=lambda msg: False,
            _confirm_dm_closed_dual_stage=lambda tab, handle: (False, ''),
            normalize_handle=lambda h: str(h or '').strip().lstrip('@').lower(),
            log_to_ui=lambda level, msg: None,
        )

        err, closed = resolve_dm_send_failure(types.SimpleNamespace(), '@demo', '发送按钮未出现', deps, prefix='发送私信文案失败')

        self.assertFalse(closed)
        self.assertEqual(err, '发送私信文案失败: 发送按钮未出现')

    def test_prepare_second_dm_text_returns_already_exists(self):
        deps = types.SimpleNamespace(
            _sanitize_dm_message_text=lambda text: str(text or '').strip(),
            _conversation_contains_dm_text=lambda tab, text: text == '模板文案',
            DM_LLM_DOWN_FALLBACK_TEMPLATE=True,
            _is_dm_llm_fallback_allowed=lambda code, detail: False,
            log_to_ui=lambda level, msg: None,
        )

        ok, text, fallback_used, state = prepare_second_dm_text(types.SimpleNamespace(), ' 模板文案 ', deps)

        self.assertTrue(ok)
        self.assertEqual(text, '模板文案')
        self.assertFalse(fallback_used)
        self.assertEqual(state, 'already_exists')

    def test_execute_recovery_strategies_continues_on_continuable_soft_error(self):
        logs = []
        tabs = [types.SimpleNamespace(name='tab1'), types.SimpleNamespace(name='tab2')]
        calls = []
        deps = types.SimpleNamespace(
            _classify_dm_error_text=lambda err: 'soft_send',
            _is_dm_soft_send_error_text=lambda err: True,
            _is_dm_send_fallback_continuable_error=lambda err: str(err).startswith('E_DM_SEND_BUTTON_CLICK:'),
            _capture_runtime_diagnostic=lambda *args, **kwargs: None,
            log_to_ui=lambda level, msg: logs.append((level, msg)),
        )

        def run_sequence_fn(tab, handle, share_link, dm_text, deps_obj, mark_func=None, progress=None, dm_text_supplier=None):
            calls.append(tab.name)
            if tab.name == 'tab1':
                return False, 'E_DM_SEND_BUTTON_CLICK: click failed', False
            return True, '', False

        status, work_tab, last_err, context_failure_count, dm_closed = execute_dm_recovery_strategies(
            strategies=[('当前标签页', lambda: tabs[0]), ('重建标签页', lambda: tabs[1])],
            work_tab=tabs[0],
            handle_norm='demo',
            share_link='https://x.com/demo/status/1',
            dm_text='hello',
            deps=deps,
            mark_func=None,
            progress={'link_sent': False, 'text_sent': False},
            dm_text_supplier=None,
            get_headless_mode_fn=lambda deps_obj: True,
            run_sequence_fn=run_sequence_fn,
        )

        self.assertEqual(status, 'ok')
        self.assertEqual(calls, ['tab1', 'tab2'])
        self.assertEqual(work_tab.name, 'tab2')
        self.assertEqual(last_err, '')
        self.assertFalse(dm_closed)
        self.assertTrue(any('允许进入下一恢复策略' in msg for _, msg in logs))


if __name__ == '__main__':
    unittest.main()
