import threading
import types
import unittest

from xmonitor.browser.work_tab_service import ensure_reply_work_tab
from xmonitor.runtime.runtime_state import build_runtime_state, set_runtime_attr


class WorkTabServiceTests(unittest.TestCase):
    def test_ensure_reply_work_tab_sets_runtime_attr(self):
        created = []
        class FakeBrowser:
            def new_tab(self):
                tab = types.SimpleNamespace(url='https://x.com/home', close=lambda: None)
                created.append(tab)
                return tab
        deps = types.SimpleNamespace()
        deps.reply_work_tab = None
        deps.reply_work_tab_lock = threading.Lock()
        deps.init_global_browser = lambda: FakeBrowser()
        deps._warmup_dm_passcode_if_needed = lambda tab: None
        deps.log_to_ui = lambda level, msg: None
        deps.runtime_state = build_runtime_state(deps)
        deps._set_runtime_attr = lambda name, value: set_runtime_attr(deps, name, value)
        tab = ensure_reply_work_tab(deps)
        self.assertIs(tab, created[0])
        self.assertIs(deps.runtime_state.reply_work_tab, tab)


if __name__ == '__main__':
    unittest.main()
