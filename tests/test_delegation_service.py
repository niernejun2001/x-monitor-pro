import types
import unittest
from unittest import mock

from xmonitor.services.platform.delegation import (
    ensure_delegated_account_session,
    get_current_account_handle,
)
from xmonitor.services.platform.delegation_helpers import (
    click_visible_confirm_button,
    extract_handle_from_text,
    extract_profile_handle_from_href,
    find_matching_delegated_user_cell,
    safe_click_target,
)


class _VisibleState:
    def __init__(self, displayed=True):
        self.is_displayed = displayed


class _Cell:
    def __init__(self, text='', html='', displayed=True, click_error=None):
        self.text = text
        self.html = html
        self.states = _VisibleState(displayed)
        self._click_error = click_error
        self.clicked = 0

    def click(self):
        if self._click_error is not None:
            raise self._click_error
        self.clicked += 1


class _Page:
    def __init__(self, *, buttons=None, user_cells=None, account_btn=None, profile_href=''):
        self._buttons = buttons or []
        self._user_cells = user_cells or []
        self._account_btn = account_btn
        self._profile_href = profile_href
        self.clicks = []
        self.refreshed = 0

    def ele(self, selector, timeout=0):
        if selector.startswith('css:[data-testid="SideNav_AccountSwitcher_Button"]') or selector.startswith('css:button[data-testid="SideNav_AccountSwitcher_Button"]') or selector.startswith('css:div[data-testid="SideNav_AccountSwitcher_Button"]'):
            return self._account_btn
        if selector == 'css:a[data-testid="AppTabBar_Profile_Link"]' and self._profile_href:
            return types.SimpleNamespace(attr=lambda name: self._profile_href if name == 'href' else '')
        return None

    def eles(self, selector, timeout=0):
        if selector == 'css:[data-testid="UserCell"]':
            return self._user_cells
        if selector == 'tag:button':
            return self._buttons
        return []

    def run_js(self, script, arg=None):
        self.clicks.append((script, arg))

    def refresh(self):
        self.refreshed += 1


class DelegationServiceTests(unittest.TestCase):
    def test_extract_handle_helpers(self):
        self.assertEqual(extract_handle_from_text('foo @Demo_User bar'), 'demo_user')
        self.assertEqual(extract_profile_handle_from_href('/Demo_User'), 'demo_user')
        self.assertEqual(extract_profile_handle_from_href('/home'), '')

    def test_get_current_account_handle_prefers_switcher_text(self):
        page = _Page(account_btn=types.SimpleNamespace(text='Demo User\n@Demo_User'))
        self.assertEqual(get_current_account_handle(page), 'demo_user')

    def test_find_matching_delegated_user_cell_matches_html_or_text(self):
        logs = []
        user_cells = [
            _Cell(text='Foo\n@foo'),
            _Cell(text='Demo User', html='<span>@demo_user</span>'),
        ]
        page = _Page(user_cells=user_cells)
        found, cells = find_matching_delegated_user_cell(page, 'demo_user', log_to_ui=lambda level, msg: logs.append((level, msg)), sleep_fn=lambda _: None)
        self.assertIs(found, user_cells[1])
        self.assertEqual(cells, user_cells)

    def test_click_visible_confirm_button_clicks_first_matching_button(self):
        logs = []
        target = _Cell(text='切换', displayed=True)
        page = _Page(buttons=[_Cell(text='取消'), target])
        self.assertTrue(click_visible_confirm_button(page, log_to_ui=lambda level, msg: logs.append((level, msg)), sleep_fn=lambda _: None))
        self.assertEqual(target.clicked, 1)

    def test_safe_click_target_falls_back_to_js_when_element_click_fails(self):
        logs = []
        target = _Cell(text='切换', click_error=RuntimeError('cross world'))
        page = _Page()
        self.assertTrue(safe_click_target(page, target, log_to_ui=lambda level, msg: logs.append((level, msg)), label='测试点击'))
        self.assertTrue(any(arg is target for _, arg in page.clicks))

    def test_ensure_delegated_account_session_reuses_current_account(self):
        logs = []
        state = {}
        page = _Page(account_btn=types.SimpleNamespace(text='Demo User\n@demo_user'))
        deps = types.SimpleNamespace(
            normalize_handle=lambda text: str(text or '').strip().lstrip('@').lower(),
            log_to_ui=lambda level, msg: logs.append((level, msg)),
            _set_runtime_attr=lambda name, value: state.__setitem__(name, value),
            delegated_switch_ok=False,
            delegated_account_active='',
            switch_to_delegated_account=lambda page_obj, target: False,
        )
        with mock.patch('xmonitor.services.platform.delegation.time.sleep', lambda _: None):
            ok = ensure_delegated_account_session(page, '@Demo_User', deps)
        self.assertTrue(ok)
        self.assertEqual(state['delegated_account_active'], 'demo_user')
        self.assertTrue(state['delegated_switch_ok'])
        self.assertEqual(page.refreshed, 1)


if __name__ == '__main__':
    unittest.main()
