import threading
import types
import unittest
from unittest import mock

from xmonitor.services.scan.page_scan import scan_task_with_tab, scan_task_worker


class _FakeTab:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakeBrowser:
    def __init__(self):
        self.tab = _FakeTab()

    def new_tab(self):
        return self.tab


class PageScanTests(unittest.TestCase):
    def _make_deps(self):
        deps = types.SimpleNamespace()
        deps.data_lock = threading.Lock()
        deps.tab_lock = threading.Lock()
        deps.monitor_tasks = [{'url': 'https://x.com/demo/status/123', 'last_check': '等待'}]
        deps.pending_results = []
        deps.history_ids = set()
        deps.browser_initialized = True
        deps.global_browser = _FakeBrowser()
        deps.TAB_OPEN_JITTER_MIN_SEC = 0.0
        deps.TAB_OPEN_JITTER_MAX_SEC = 0.0
        deps._set_runtime_attr = lambda name, value: setattr(deps, name, value)
        deps.should_skip_duplicate_content = lambda handle, content: False
        deps.enqueue_new_data_calls = []
        deps.enqueue_new_data = lambda item: deps.enqueue_new_data_calls.append(item)
        deps.save_state_calls = 0
        deps.save_state = lambda: setattr(deps, 'save_state_calls', deps.save_state_calls + 1)
        deps.logs = []
        deps.log_to_ui = lambda level, msg: deps.logs.append((level, msg))
        return deps

    def test_scan_task_worker_stores_results_and_updates_last_check(self):
        deps = self._make_deps()
        deps.scan_page_content = lambda page, url, blocked: (
            [{'key': 'k1', 'handle': '@a', 'content': 'hello', 'source': url}],
            None,
        )

        added = scan_task_worker(deps.monitor_tasks[0], object(), [], deps)

        self.assertEqual(added, 1)
        self.assertEqual(len(deps.pending_results), 1)
        self.assertIn('k1', deps.history_ids)
        self.assertEqual(len(deps.enqueue_new_data_calls), 1)
        self.assertEqual(deps.save_state_calls, 1)
        self.assertIn('新增 1', deps.monitor_tasks[0]['last_check'])

    def test_scan_task_with_tab_closes_tab(self):
        deps = self._make_deps()
        deps.scan_page_content_with_tab = lambda tab, url, blocked: (
            [{'key': 'k2', 'handle': '@b', 'content': 'world', 'source': url}],
            None,
        )

        with mock.patch('xmonitor.services.scan.page_scan.time.sleep'):
            added = scan_task_with_tab(deps.monitor_tasks[0], [], deps)

        self.assertEqual(added, 1)
        self.assertTrue(deps.global_browser.tab.closed)
        self.assertEqual(deps.pending_results[0]['key'], 'k2')

    def test_scan_task_with_tab_reports_scan_error(self):
        deps = self._make_deps()
        deps.scan_page_content_with_tab = lambda tab, url, blocked: ([], 'boom')

        with mock.patch('xmonitor.services.scan.page_scan.time.sleep'):
            added = scan_task_with_tab(deps.monitor_tasks[0], [], deps)

        self.assertEqual(added, 0)
        self.assertTrue(deps.global_browser.tab.closed)
        self.assertIn('失败: boom', deps.monitor_tasks[0]['last_check'])
        self.assertEqual(deps.pending_results, [])


if __name__ == '__main__':
    unittest.main()
