import threading
import types
import unittest

from xmonitor.services.filter_service import (
    is_emoji_only_content,
    make_content_signature,
    normalize_content_for_filter,
    should_skip_duplicate_content,
)


class FilterServiceTests(unittest.TestCase):
    def _make_deps(self):
        deps = types.SimpleNamespace()
        deps.EMOJI_UNICODE_RANGES = (
            (0x1F600, 0x1F64F),
            (0x2600, 0x26FF),
            (0x2700, 0x27BF),
        )
        deps.EMOJI_JOINER_CHARS = {'\u200d', '\ufe0f', '\u20e3'}
        deps.CONTENT_DEDUPE_MAX_ENTRIES = 100
        deps.CONTENT_DEDUPE_TTL_SEC = 3600
        deps.content_dedupe = {}
        deps.normalize_handle = lambda h: str(h or '').strip().lstrip('@').lower()
        return deps

    def test_normalize_content_for_filter(self):
        self.assertEqual(normalize_content_for_filter('  ＠User   hello\nworld  '), '@User hello world')

    def test_is_emoji_only_content(self):
        deps = self._make_deps()
        self.assertTrue(is_emoji_only_content('😀 😀', deps))
        self.assertFalse(is_emoji_only_content('😀 hello', deps))

    def test_make_content_signature_and_duplicate_check(self):
        deps = self._make_deps()
        sig = make_content_signature('@User', 'Hello  world', deps)
        self.assertTrue(sig)
        now_ts = 1000.0
        self.assertFalse(should_skip_duplicate_content('@User', 'Hello world', deps, now_ts=now_ts))
        self.assertTrue(should_skip_duplicate_content('@User', 'Hello world', deps, now_ts=now_ts + 10))
        self.assertFalse(should_skip_duplicate_content('@User', 'Hello world', deps, now_ts=now_ts + deps.CONTENT_DEDUPE_TTL_SEC + 1))


if __name__ == '__main__':
    unittest.main()
