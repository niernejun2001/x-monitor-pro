import types
import unittest
from tempfile import TemporaryDirectory
from unittest import mock

from xmonitor.services.scan.tweet_scan import scan_page_content


class _FakeElement:
    def __init__(self, text='', html='', attrs=None):
        self.text = text
        self.html = html
        self._attrs = attrs or {}

    def ele(self, selector, timeout=0):
        if selector == 'css:[data-testid="User-Name"]':
            return _FakeElement(self._attrs.get('user_text', ''))
        if selector == 'css:[data-testid="tweetText"]':
            return _FakeElement(self._attrs.get('tweet_text', ''))
        if selector == 'css:[data-testid="reply"]':
            return None
        return None

    def eles(self, selector, timeout=0):
        return []


class _FakeWait:
    def ele_displayed(self, selector, timeout=0):
        return True


class _FakePage:
    def __init__(self, articles):
        self._articles = articles
        self.url = 'https://x.com/demo/status/123'
        self.html = '<html></html>'
        self._scroll_y = 0

    def get(self, url):
        self.url = url

    @property
    def wait(self):
        return _FakeWait()

    def eles(self, selector, timeout=0):
        if selector == 'tag:article':
            return self._articles
        return []

    def run_js(self, script, *args):
        if 'scrollBy' in script:
            return None
        if 'scrollY' in script:
            return self._scroll_y
        return 0


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

    def test_scan_page_content_writes_copyable_ids_with_one(self):
        articles = [
            _FakeElement(
                text='Alice @alice · 1分钟 1',
                html='article-a',
                attrs={'user_text': 'Alice\n@alice', 'tweet_text': '1'},
            ),
            _FakeElement(
                text='Bob @bob · 1分钟 1 求软件',
                html='article-b',
                attrs={'user_text': 'Bob\n@bob', 'tweet_text': '1 求软件'},
            ),
            _FakeElement(
                text='Carl @carl · 1分钟 @grok 这是什么软件',
                html='article-c',
                attrs={'user_text': 'Carl\n@carl', 'tweet_text': '@grok 这是什么软件'},
            ),
        ]

        with TemporaryDirectory() as tmpdir, mock.patch('xmonitor.services.scan.tweet_scan.time.sleep'):
            with open(f'{tmpdir}/comment_ids_with_1.txt', 'w', encoding='utf-8') as f:
                f.write('@old\n@alice\n')
            logs = []
            deps = types.SimpleNamespace(
                DATA_DIR=tmpdir,
                history_ids=set(),
                log_to_ui=lambda level, msg: logs.append((level, msg)),
                reorder_articles_for_scan=lambda rows: rows,
                should_skip_content_by_policy=lambda content: (False, ''),
                get_effective_delegated_account=lambda: '',
            )

            results, err = scan_page_content(_FakePage(articles), 'https://x.com/demo/status/123', [], deps)

            self.assertIsNone(err)
            self.assertEqual([item['handle'] for item in results], ['@alice', '@bob', '@carl'])
            with open(f'{tmpdir}/comment_ids_with_1.txt', encoding='utf-8') as f:
                saved = f.read().splitlines()
            self.assertEqual(saved, ['@old', '@alice', '@bob'])
            joined_logs = '\n'.join(msg for _, msg in logs)
            self.assertIn('本轮新增ID:\n@bob', joined_logs)
            self.assertNotIn('本轮新增ID:\n@alice', joined_logs)
            self.assertNotIn('@carl\n', joined_logs)
            self.assertIn('本轮新增 1 个，累计 3 个', joined_logs)


if __name__ == '__main__':
    unittest.main()
