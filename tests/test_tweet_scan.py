import types
import unittest

from xmonitor.services.scan.tweet_scan import scan_page_content


class TweetScanTests(unittest.TestCase):
    def test_scan_page_content_formats_blank_error(self):
        class _BlankError(Exception):
            def __str__(self):
                return ''

        page = types.SimpleNamespace(
            get=lambda url: (_ for _ in ()).throw(_BlankError()),
        )
        logs = []
        deps = types.SimpleNamespace(
            history_ids=set(),
            log_to_ui=lambda level, msg: logs.append((level, msg)),
            reorder_articles_for_scan=lambda articles: articles,
            should_skip_content_by_policy=lambda content: (False, ''),
            get_effective_delegated_account=lambda: '',
        )

        results, err = scan_page_content(page, 'https://x.com/demo/status/123', [], deps)

        self.assertEqual(results, [])
        self.assertEqual(err, '_BlankError')
        self.assertTrue(any('_BlankError' in msg for _, msg in logs))


if __name__ == '__main__':
    unittest.main()
