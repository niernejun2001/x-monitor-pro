import unittest

from xmonitor.services.dm.open_service import direct_compose_state_indicates_closed


class DMOpenServiceTests(unittest.TestCase):
    def test_no_results_for_typed_handle_is_closed(self):
        state = {
            'search_scene': True,
            'no_results': True,
            'candidate_count': 0,
            'exact_match': False,
            'next_visible': False,
            'next_disabled': False,
            'typed_value': '@designbyjl',
        }
        self.assertTrue(direct_compose_state_indicates_closed(state, 'DesignbyJL'))

    def test_disabled_next_with_no_candidates_is_closed(self):
        state = {
            'search_scene': True,
            'no_results': False,
            'candidate_count': 0,
            'exact_match': False,
            'next_visible': True,
            'next_disabled': True,
            'typed_value': 'designbyjl',
        }
        self.assertTrue(direct_compose_state_indicates_closed(state, '@DesignbyJL'))

    def test_exact_match_candidate_is_not_closed(self):
        state = {
            'search_scene': True,
            'no_results': False,
            'candidate_count': 3,
            'exact_match': True,
            'next_visible': True,
            'next_disabled': False,
            'typed_value': '@designbyjl',
        }
        self.assertFalse(direct_compose_state_indicates_closed(state, 'designbyjl'))

    def test_blocked_match_candidate_is_closed(self):
        state = {
            'search_scene': True,
            'no_results': False,
            'candidate_count': 1,
            'exact_match': True,
            'next_visible': True,
            'next_disabled': True,
            'blocked_match': True,
            'typed_value': '@xufei2022',
        }
        self.assertTrue(direct_compose_state_indicates_closed(state, 'Xufei2022'))

    def test_blocked_root_text_match_is_closed(self):
        state = {
            'search_scene': True,
            'no_results': False,
            'candidate_count': 0,
            'exact_match': False,
            'next_visible': False,
            'next_disabled': False,
            'blocked_match': True,
            'typed_value': 'sgxiang8',
        }
        self.assertTrue(direct_compose_state_indicates_closed(state, '@sgxiang8'))


if __name__ == '__main__':
    unittest.main()
