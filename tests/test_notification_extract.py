import unittest

from xmonitor.services.notify.extract import (
    extract_notification_content,
    strip_notification_meta_prefix,
)
from xmonitor.services.notify.text import (
    is_noise_notification_text,
    normalize_notification_text,
    score_notification_candidate,
)


class _FakeArticle:
    def __init__(self, text):
        self.text = text

    def ele(self, selector, timeout=0):
        raise Exception('not implemented')

    def eles(self, selector, timeout=0):
        return []


class NotificationExtractTests(unittest.TestCase):
    def test_strip_notification_meta_prefix(self):
        text = '18295025596mike · 27秒 回复 @manateelazycat 1'
        self.assertEqual(strip_notification_meta_prefix(text), '1')

    def test_extract_notification_content_prefers_stripped_reply_body(self):
        article_text = '18295025596mike@gmai @18295025596mike · 27秒 回复 @manateelazycat 1'
        article = _FakeArticle(article_text)
        content = extract_notification_content(
            article,
            article_text,
            '@18295025596mike',
            normalize_notification_text_fn=normalize_notification_text,
            is_noise_notification_text_fn=is_noise_notification_text,
            score_notification_candidate_fn=score_notification_candidate,
        )
        self.assertEqual(content, '1')


if __name__ == '__main__':
    unittest.main()
