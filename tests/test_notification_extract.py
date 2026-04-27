import unittest
import re

from xmonitor.services.notify.extract import (
    collect_notification_hrefs,
    collect_notification_tweet_texts,
    extract_notification_content,
    extract_notification_status_info,
    extract_status_from_href,
    strip_notification_meta_prefix,
    strip_notification_trailing_metrics,
)
from xmonitor.services.notify.text import (
    is_noise_notification_text,
    normalize_notification_text,
    score_notification_candidate,
)


class _FakeArticle:
    def __init__(self, text, tweet_texts=None, lang_texts=None, html=''):
        self.text = text
        self._tweet_texts = list(tweet_texts or [])
        self._lang_texts = list(lang_texts or [])
        self.html = html

    def ele(self, selector, timeout=0):
        raise Exception('not implemented')

    def eles(self, selector, timeout=0):
        if selector == 'css:[data-testid="tweetText"]':
            return [type('TweetTextEle', (), {'text': text})() for text in self._tweet_texts]
        if selector == 'css:div[lang]':
            return [type('LangTextEle', (), {'text': text})() for text in self._lang_texts]
        return []


class _HrefArticle:
    def __init__(self, hrefs=None, html=''):
        self._hrefs = list(hrefs or [])
        self.html = html

    def eles(self, selector, timeout=0):
        if selector != 'tag:a':
            return []
        return [type('LinkEle', (), {'attr': lambda self, name, _href=href: _href if name == 'href' else ''})() for href in self._hrefs]


class NotificationExtractTests(unittest.TestCase):
    def test_strip_notification_meta_prefix(self):
        text = '18295025596mike · 27秒 回复 @manateelazycat 1'
        self.assertEqual(strip_notification_meta_prefix(text), '1')

    def test_strip_notification_meta_prefix_for_reply_to_your_post(self):
        text = 'lawrence @twiterLawrence · 1小时 回复了你的帖子 以前，用的时候，它叫轨迹球。'
        self.assertEqual(strip_notification_meta_prefix(text), '以前，用的时候，它叫轨迹球。')

    def test_strip_notification_meta_prefix_for_mentioned_you_in_post(self):
        text = 'demo_user · 2分钟 在帖子中提到了你 方便留个联系方式吗'
        self.assertEqual(strip_notification_meta_prefix(text), '方便留个联系方式吗')

    def test_extract_notification_content_from_reply_to_your_post_tail_pattern(self):
        article_text = 'lawrence @twiterLawrence · 1小时 replied to your post: how much is it'
        article = _FakeArticle(article_text)
        content = extract_notification_content(
            article,
            article_text,
            '@twiterLawrence',
            normalize_notification_text_fn=normalize_notification_text,
            is_noise_notification_text_fn=is_noise_notification_text,
            score_notification_candidate_fn=score_notification_candidate,
        )
        self.assertEqual(content, 'how much is it')

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

    def test_strip_notification_trailing_metrics_removes_engagement_counts(self):
        text = '以前，用的时候，它叫轨迹球。 10'
        self.assertEqual(strip_notification_trailing_metrics(text), '以前，用的时候，它叫轨迹球。')

    def test_extract_notification_content_removes_trailing_metrics_but_keeps_single_digit_reply(self):
        article_text = 'lawrence @twiterLawrence · 1小时 回复 @manateelazycat 以前，用的时候，它叫轨迹球。 10'
        article = _FakeArticle(article_text)
        content = extract_notification_content(
            article,
            article_text,
            '@twiterLawrence',
            normalize_notification_text_fn=normalize_notification_text,
            is_noise_notification_text_fn=is_noise_notification_text,
            score_notification_candidate_fn=score_notification_candidate,
        )
        self.assertEqual(content, '以前，用的时候，它叫轨迹球。')

    def test_extract_notification_content_prefers_trimmed_tweet_text_variant(self):
        article = _FakeArticle(
            'lawrence @twiterLawrence · 1小时 回复 @manateelazycat 以前，用的时候，它叫轨迹球。 10',
            tweet_texts=['以前，用的时候，它叫轨迹球。 10'],
        )
        content = extract_notification_content(
            article,
            article.text,
            '@twiterLawrence',
            normalize_notification_text_fn=normalize_notification_text,
            is_noise_notification_text_fn=is_noise_notification_text,
            score_notification_candidate_fn=score_notification_candidate,
        )
        self.assertEqual(content, '以前，用的时候，它叫轨迹球。')

    def test_extract_notification_content_cleans_reply_to_your_post_fallback_text(self):
        article_text = 'lawrence @twiterLawrence · 1小时 回复了你的帖子 以前，用的时候，它叫轨迹球。'
        article = _FakeArticle(article_text)
        content = extract_notification_content(
            article,
            article_text,
            '@twiterLawrence',
            normalize_notification_text_fn=normalize_notification_text,
            is_noise_notification_text_fn=is_noise_notification_text,
            score_notification_candidate_fn=score_notification_candidate,
        )
        self.assertEqual(content, '以前，用的时候，它叫轨迹球。')

    def test_extract_notification_status_info_prefers_time_href_over_other_status_links(self):
        article = _HrefArticle(
            hrefs=['/quoted_user/status/111111', '/demo_user/status/222222'],
            html='<a href="/demo_user/status/222222"><time datetime="2026-04-07T01:00:00.000Z"></time></a>',
        )

        def pick_best_status_id(*parts):
            for part in parts:
                match = re.search(r'(\d{3,})', str(part or ''))
                if match:
                    return match.group(1)
            return ''

        handle, status_id = extract_notification_status_info(
            article,
            extract_status_from_href_fn=lambda href: extract_status_from_href(href, pick_best_status_id_fn=pick_best_status_id),
            pick_best_status_id_fn=pick_best_status_id,
        )

        self.assertEqual(handle, '@demo_user')
        self.assertEqual(status_id, '222222')

    def test_extract_notification_status_info_fills_handle_from_other_href_when_time_href_is_i_status(self):
        article = _HrefArticle(
            hrefs=['/demo_user/status/222222', 'https://x.com/i/web/status/222222?s=20'],
            html='<a href="https://x.com/i/web/status/222222?s=20"><time datetime="2026-04-07T01:00:00.000Z"></time></a>',
        )

        def pick_best_status_id(*parts):
            for part in parts:
                match = re.search(r'(\d{3,})', str(part or ''))
                if match:
                    return match.group(1)
            return ''

        handle, status_id = extract_notification_status_info(
            article,
            extract_status_from_href_fn=lambda href: extract_status_from_href(href, pick_best_status_id_fn=pick_best_status_id),
            pick_best_status_id_fn=pick_best_status_id,
        )

        self.assertEqual(handle, '@demo_user')
        self.assertEqual(status_id, '222222')

    def test_extract_status_from_href_supports_statuses_and_status_id_query(self):
        def pick_best_status_id(*parts):
            for part in parts:
                match = re.search(r'(\d{3,})', str(part or ''))
                if match:
                    return match.group(1)
            return ''

        handle1, status_id1 = extract_status_from_href(
            'https://twitter.com/demo_user/statuses/333333',
            pick_best_status_id_fn=pick_best_status_id,
        )
        handle2, status_id2 = extract_status_from_href(
            'https://x.com/i/web/status/1?status_id=444444',
            pick_best_status_id_fn=pick_best_status_id,
        )

        self.assertEqual(handle1, '@demo_user')
        self.assertEqual(status_id1, '333333')
        self.assertIsNone(handle2)
        self.assertEqual(status_id2, '444444')

    def test_collect_notification_hrefs_prioritizes_status_links(self):
        article = _HrefArticle(
            hrefs=[
                '/compose/post',
                '/demo_user/status/222222',
                '/search',
                'https://x.com/i/web/status/333333?s=20',
                '/demo_user/status/222222',
            ],
        )

        hrefs = collect_notification_hrefs(article, max_links=3)

        self.assertEqual(
            hrefs,
            [
                'https://x.com/i/status/333333',
                'https://x.com/demo_user/status/222222',
                '/compose/post',
            ],
        )

    def test_collect_notification_hrefs_falls_back_to_html(self):
        article = _FakeArticle(
            '',
            html='<div><a href="/compose/post"></a><a href="https://twitter.com/demo_user/statuses/222222?s=20"></a></div>',
        )

        hrefs = collect_notification_hrefs(article, max_links=3)

        self.assertEqual(
            hrefs,
            [
                'https://x.com/demo_user/status/222222',
                '/compose/post',
            ],
        )

    def test_collect_notification_hrefs_dedupes_equivalent_status_urls(self):
        article = _HrefArticle(
            hrefs=[
                '/demo_user/status/222222',
                'https://twitter.com/demo_user/statuses/222222?s=20',
                'https://mobile.twitter.com/demo_user/status/222222',
            ],
        )

        hrefs = collect_notification_hrefs(article, max_links=4)

        self.assertEqual(hrefs, ['https://x.com/demo_user/status/222222'])

    def test_collect_notification_hrefs_normalizes_status_id_query(self):
        article = _HrefArticle(
            hrefs=[
                'https://x.com/i/web/status/1?status_id=444444',
                'https://x.com/i/status/444444',
            ],
        )

        hrefs = collect_notification_hrefs(article, max_links=4)

        self.assertEqual(hrefs, ['https://x.com/i/status/444444'])

    def test_collect_notification_tweet_texts_falls_back_to_lang_nodes(self):
        article = _FakeArticle('', tweet_texts=[], lang_texts=['第一条正文', '第二条正文'])

        samples = collect_notification_tweet_texts(
            article,
            max_items=2,
            normalize_one_line_fn=lambda text, limit=80: str(text or '')[:limit],
        )

        self.assertEqual(samples, ['第一条正文', '第二条正文'])

    def test_collect_notification_tweet_texts_falls_back_to_article_text_lines(self):
        article = _FakeArticle('lawrence @twiterLawrence · 1小时 回复了你的帖子 以前，用的时候，它叫轨迹球。')

        samples = collect_notification_tweet_texts(
            article,
            max_items=2,
            normalize_one_line_fn=lambda text, limit=80: str(text or '')[:limit],
        )

        self.assertIn('以前，用的时候，它叫轨迹球。', samples)


if __name__ == '__main__':
    unittest.main()
