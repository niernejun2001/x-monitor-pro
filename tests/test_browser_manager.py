import unittest

from xmonitor.browser.browser_manager import _resolve_auth_bootstrap_strategy


class BrowserManagerTests(unittest.TestCase):
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
