import unittest

from xmonitor.browser.core.manager import _format_browser_error, _resolve_auth_bootstrap_strategy


class BrowserManagerTests(unittest.TestCase):
    def test_format_browser_error_falls_back_to_exception_type(self):
        class _BlankError(Exception):
            def __str__(self):
                return ''

        self.assertEqual(_format_browser_error(_BlankError()), '_BlankError')

    def test_prefers_profile_token_over_saved_token(self):
        result = _resolve_auth_bootstrap_strategy('saved-old-token', 'profile-fresh-token')
        self.assertEqual(result['mode'], 'reuse_profile')
        self.assertEqual(result['token'], 'profile-fresh-token')
        self.assertTrue(result['saved_token_present'])
        self.assertFalse(result['tokens_match'])

    def test_injects_saved_token_when_profile_missing(self):
        result = _resolve_auth_bootstrap_strategy('saved-old-token', '')
        self.assertEqual(result['mode'], 'inject_saved')
        self.assertEqual(result['token'], 'saved-old-token')

    def test_no_token_when_both_missing(self):
        result = _resolve_auth_bootstrap_strategy('', '')
        self.assertEqual(result['mode'], 'no_token')
        self.assertEqual(result['token'], '')


if __name__ == '__main__':
    unittest.main()
