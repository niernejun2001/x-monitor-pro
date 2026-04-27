import types
import unittest

from xmonitor.services.notify.match import (
    extract_status_id_from_notification_item,
    extract_status_ids_from_article,
    match_notification_card_for_reply,
    match_reply_target_article,
)


class _Link:
    def __init__(self, href):
        self._href = href

    def attr(self, name):
        return self._href if name == 'href' else ''


class _TextEle:
    def __init__(self, text):
        self.text = text


class _ReplyBtn:
    def __init__(self, displayed=True):
        self.states = types.SimpleNamespace(is_displayed=displayed)


class _Article:
    def __init__(self, *, hrefs=None, user_text='', tweet_text='', text='', reply_visible=True):
        self._hrefs = list(hrefs or [])
        self._user_text = user_text
        self._tweet_text = tweet_text
        self.text = text
        self._reply_visible = reply_visible

    def eles(self, selector, timeout=0):
        if selector == 'tag:a':
            return [_Link(href) for href in self._hrefs]
        return []

    def ele(self, selector, timeout=0):
        if selector == 'css:[data-testid="User-Name"]':
            return _TextEle(self._user_text) if self._user_text else None
        if selector == 'css:[data-testid="tweetText"]':
            return _TextEle(self._tweet_text) if self._tweet_text else None
        if selector == 'css:[data-testid="reply"]':
            return _ReplyBtn(self._reply_visible)
        raise Exception('not found')


class _Page:
    def __init__(self, articles):
        self._articles = list(articles)

    def eles(self, selector, timeout=0):
        if selector == 'tag:article':
            return list(self._articles)
        return []


class NotificationMatchTests(unittest.TestCase):
    def test_extract_status_id_from_notification_item_falls_back_to_key(self):
        item = {'key': 'notif_status_1234567890123456789'}
        sid = extract_status_id_from_notification_item(item, pick_best_status_id_fn=lambda *parts: '')
        self.assertEqual(sid, '1234567890123456789')

    def test_extract_status_ids_from_article_collects_all_ids(self):
        article = _Article(hrefs=['/demo/status/1234567890123456789', '/demo/status/987654321012345678'])
        ids = extract_status_ids_from_article(article, pick_best_status_id_fn=lambda href: href.split('/')[-1])
        self.assertEqual(ids, {'1234567890123456789', '987654321012345678'})

    def test_match_reply_target_article_prefers_exact_status_and_handle(self):
        article_ok = _Article(
            hrefs=['/demo/status/1234567890123456789'],
            user_text='Demo\n@demo',
            tweet_text='hello world',
            reply_visible=True,
        )
        article_other = _Article(
            hrefs=['/other/status/555555555555555555'],
            user_text='Other\n@other',
            tweet_text='other content',
            reply_visible=True,
        )
        page = _Page([article_other, article_ok])
        article, score = match_reply_target_article(
            page,
            '1234567890123456789',
            '@demo',
            'hello world',
            extract_status_ids_from_article_fn=lambda art: extract_status_ids_from_article(art, pick_best_status_id_fn=lambda href: href.split('/')[-1]),
            normalize_handle_fn=lambda handle: str(handle or '').strip().lstrip('@').lower(),
            normalize_content_for_dedupe_fn=lambda text: str(text or '').strip().lower(),
        )
        self.assertIs(article, article_ok)
        self.assertGreaterEqual(score, 220)

    def test_match_notification_card_for_reply_prefers_best_score(self):
        article_ok = _Article(
            hrefs=['/demo/status/1234567890123456789'],
            user_text='Demo\n@demo',
            tweet_text='hello world',
            text='Demo @demo hello world',
            reply_visible=True,
        )
        article_low = _Article(
            hrefs=['/demo/status/1234567890123456789'],
            user_text='Demo\n@demo',
            tweet_text='different content',
            text='Demo @demo different content',
            reply_visible=True,
        )
        page = _Page([article_low, article_ok])
        article, reply_btn, score = match_notification_card_for_reply(
            page,
            '1234567890123456789',
            '@demo',
            'hello world',
            extract_notification_status_info_fn=lambda art: ('@demo', '1234567890123456789'),
            extract_notification_handle_fn=lambda art, article_text: '@demo',
            extract_notification_content_fn=lambda art, article_text, handle: art._tweet_text,
            normalize_handle_fn=lambda handle: str(handle or '').strip().lstrip('@').lower(),
            normalize_content_for_dedupe_fn=lambda text: str(text or '').strip().lower(),
        )
        self.assertIs(article, article_ok)
        self.assertIsNotNone(reply_btn)
        self.assertGreater(score, 260)


if __name__ == '__main__':
    unittest.main()
