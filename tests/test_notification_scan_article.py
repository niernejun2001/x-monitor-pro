import types
import unittest

from xmonitor.services.notify.scan_article import (
    _normalize_share_status_url_from_raw,
    process_notification_article,
)


class _Article:
    def __init__(self, text='demo text', html=''):
        self.text = text
        self.html = html

    def ele(self, selector, timeout=0):
        raise Exception('no time element')


class NotificationScanArticleTests(unittest.TestCase):
    def _make_deps(self):
        return types.SimpleNamespace(
            NOTIFICATION_REPLY_ONLY_MODE=True,
            TWITTER_CLI_ENABLED=False,
            TWITTER_CLI_NOTIFY_ENRICH=False,
            _normalize_one_line=lambda text, limit=120: str(text or '')[:limit],
            _extract_status_id_candidates_from_text=lambda html: [],
            _collect_notification_hrefs=lambda article: [],
            _collect_notification_tweet_texts=lambda article: [],
            _extract_notification_status_info=lambda article: ('@demo', '123'),
            _parse_notification_age_minutes=lambda article: 1.0,
            _extract_notification_handle=lambda article, article_text: '@demo',
            _extract_notification_content=lambda article, article_text, handle: 'hello',
            should_skip_content_by_policy=lambda content: (False, ''),
            _pick_best_status_id=lambda status_id: str(status_id),
            normalize_handle=lambda handle: str(handle or '').strip().lstrip('@').lower(),
            history_ids=set(),
        )

    def test_reply_only_skip_non_reply_notification(self):
        deps = self._make_deps()
        deps._classify_notification_type = lambda text: {
            'notification_type': 'mention',
            'is_reply_like': False,
            'is_reply_to_me': False,
            'is_mention_to_me': True,
            'is_interaction_only': False,
            'normalized_text': str(text or ''),
        }

        outcome = process_notification_article(
            _Article(text='@demo 提到了你'),
            1,
            max_recent_minutes=45,
            trace_limit=5,
            blocked_norm_set=set(),
            delegated_norm='',
            seen_in_page=set(),
            deps=deps,
        )

        self.assertIsNone(outcome['result'])
        self.assertEqual(outcome['stats']['skipped_non_reply'], 1)
        self.assertIn('reply_only_filter', outcome['traces'][0])

    def test_duplicate_status_id_is_skipped(self):
        deps = self._make_deps()
        deps.history_ids = {'notif_status_123'}
        deps._classify_notification_type = lambda text: {
            'notification_type': 'reply_to_you',
            'is_reply_like': True,
            'is_reply_to_me': True,
            'is_mention_to_me': False,
            'is_interaction_only': False,
            'normalized_text': str(text or ''),
        }

        outcome = process_notification_article(
            _Article(text='@demo 回复了你'),
            1,
            max_recent_minutes=45,
            trace_limit=5,
            blocked_norm_set=set(),
            delegated_norm='',
            seen_in_page=set(),
            deps=deps,
        )

        self.assertIsNone(outcome['result'])
        self.assertEqual(outcome['stats']['skipped_duplicate'], 1)
        self.assertIn('skip=duplicate', outcome['traces'][0])

    def test_recovers_status_id_from_html_hints_before_fallback_no_status(self):
        deps = self._make_deps()
        deps._extract_notification_status_info = lambda article: ('', '')
        deps._extract_status_id_candidates_from_text = lambda html: ['1234567890123456789']
        deps._classify_notification_type = lambda text: {
            'notification_type': 'reply_to_you',
            'is_reply_like': True,
            'is_reply_to_me': True,
            'is_mention_to_me': False,
            'is_interaction_only': False,
            'normalized_text': str(text or ''),
        }

        outcome = process_notification_article(
            _Article(text='@demo 回复了你', html='<div data-id="1234567890123456789"></div>'),
            1,
            max_recent_minutes=45,
            trace_limit=5,
            blocked_norm_set=set(),
            delegated_norm='',
            seen_in_page=set(),
            deps=deps,
        )

        self.assertIsNotNone(outcome['result'])
        self.assertEqual(outcome['result']['status_id'], '1234567890123456789')
        self.assertIn('recover=status_hint', ' '.join(outcome['traces']))

    def test_result_falls_back_status_handle_to_comment_handle(self):
        deps = self._make_deps()
        deps._extract_notification_status_info = lambda article: ('', '123')
        deps._classify_notification_type = lambda text: {
            'notification_type': 'reply_to_you',
            'is_reply_like': True,
            'is_reply_to_me': True,
            'is_mention_to_me': False,
            'is_interaction_only': False,
            'normalized_text': str(text or ''),
        }

        outcome = process_notification_article(
            _Article(text='@demo 回复了你'),
            1,
            max_recent_minutes=45,
            trace_limit=5,
            blocked_norm_set=set(),
            delegated_norm='',
            seen_in_page=set(),
            deps=deps,
        )

        self.assertEqual(outcome['result']['status_handle'], '@demo')
        self.assertEqual(outcome['result']['status_url'], 'https://x.com/demo/status/123')

    def test_normalize_share_status_url_from_raw_canonicalizes_legacy_absolute_url(self):
        deps = self._make_deps()
        normalized = _normalize_share_status_url_from_raw(
            'https://mobile.twitter.com/demo_plain/statuses/1234567890123456789',
            '1234567890123456789',
            '@demo_plain',
            deps,
        )
        self.assertEqual(normalized, 'https://x.com/demo_plain/status/1234567890123456789')

    def test_normalize_share_status_url_from_raw_canonicalizes_relative_legacy_url(self):
        deps = self._make_deps()
        normalized = _normalize_share_status_url_from_raw(
            '/demo_plain/statuses/1234567890123456789',
            '1234567890123456789',
            '@demo_plain',
            deps,
        )
        self.assertEqual(normalized, 'https://x.com/demo_plain/status/1234567890123456789')

    def test_enrich_failure_message_is_formatted(self):
        class _BlankError(Exception):
            def __str__(self):
                return ''

        deps = self._make_deps()
        deps.TWITTER_CLI_ENABLED = True
        deps.TWITTER_CLI_NOTIFY_ENRICH = True
        deps._extract_notification_status_info = lambda article: ('', '123')
        deps._extract_notification_content = lambda article, article_text, handle: 'hello'
        deps._enrich_notification_from_twitter_cli = lambda *args, **kwargs: (_ for _ in ()).throw(_BlankError())
        deps._classify_notification_type = lambda text: {
            'notification_type': 'reply_to_you',
            'is_reply_like': True,
            'is_reply_to_me': True,
            'is_mention_to_me': False,
            'is_interaction_only': False,
            'normalized_text': str(text or ''),
        }

        outcome = process_notification_article(
            _Article(text='@demo 回复了你'),
            1,
            max_recent_minutes=45,
            trace_limit=5,
            blocked_norm_set=set(),
            delegated_norm='',
            seen_in_page=set(),
            deps=deps,
        )

        self.assertEqual(outcome['result']['twitter_cli_enrich_error'], '_BlankError')

    def test_enrich_failure_trace_contains_error(self):
        class _BlankError(Exception):
            def __str__(self):
                return ''

        deps = self._make_deps()
        deps.TWITTER_CLI_ENABLED = True
        deps.TWITTER_CLI_NOTIFY_ENRICH = True
        deps._extract_notification_status_info = lambda article: ('', '123')
        deps._extract_notification_content = lambda article, article_text, handle: ''
        deps._enrich_notification_from_twitter_cli = lambda *args, **kwargs: (_ for _ in ()).throw(_BlankError())
        deps._classify_notification_type = lambda text: {
            'notification_type': 'reply_to_you',
            'is_reply_like': True,
            'is_reply_to_me': True,
            'is_mention_to_me': False,
            'is_interaction_only': False,
            'normalized_text': str(text or ''),
        }

        outcome = process_notification_article(
            _Article(text='@demo 回复了你'),
            1,
            max_recent_minutes=45,
            trace_limit=5,
            blocked_norm_set=set(),
            delegated_norm='',
            seen_in_page=set(),
            deps=deps,
        )

        self.assertIsNone(outcome['result'])
        joined = ' '.join(outcome['traces'])
        self.assertIn('enrich=twitter_cli_err', joined)
        self.assertIn('_BlankError', joined)

    def test_result_normalizes_status_handle_from_enrich_without_at(self):
        deps = self._make_deps()
        deps.TWITTER_CLI_ENABLED = True
        deps.TWITTER_CLI_NOTIFY_ENRICH = True
        deps._extract_notification_status_info = lambda article: ('', '123')
        deps._extract_notification_content = lambda article, article_text, handle: ''
        deps._enrich_notification_from_twitter_cli = lambda *args, **kwargs: {
            'status': 'ok',
            'status_handle': 'demo_plain',
            'content': 'hello',
            'status_url': '',
            'source': 'twitter_cli',
        }
        deps._classify_notification_type = lambda text: {
            'notification_type': 'reply_to_you',
            'is_reply_like': True,
            'is_reply_to_me': True,
            'is_mention_to_me': False,
            'is_interaction_only': False,
            'normalized_text': str(text or ''),
        }

        outcome = process_notification_article(
            _Article(text='@demo 回复了你'),
            1,
            max_recent_minutes=45,
            trace_limit=5,
            blocked_norm_set=set(),
            delegated_norm='',
            seen_in_page=set(),
            deps=deps,
        )

        self.assertEqual(outcome['result']['status_handle'], '@demo_plain')

    def test_result_canonicalizes_enriched_legacy_status_url(self):
        deps = self._make_deps()
        deps.TWITTER_CLI_ENABLED = True
        deps.TWITTER_CLI_NOTIFY_ENRICH = True
        deps._extract_notification_status_info = lambda article: ('', '1234567890123456789')
        deps._extract_notification_content = lambda article, article_text, handle: ''
        deps._enrich_notification_from_twitter_cli = lambda *args, **kwargs: {
            'status': 'ok',
            'status_handle': '@demo_plain',
            'content': 'hello',
            'status_url': 'https://mobile.twitter.com/demo_plain/statuses/1234567890123456789',
            'source': 'twitter_cli',
        }
        deps._classify_notification_type = lambda text: {
            'notification_type': 'reply_to_you',
            'is_reply_like': True,
            'is_reply_to_me': True,
            'is_mention_to_me': False,
            'is_interaction_only': False,
            'normalized_text': str(text or ''),
        }

        outcome = process_notification_article(
            _Article(text='@demo 回复了你'),
            1,
            max_recent_minutes=45,
            trace_limit=5,
            blocked_norm_set=set(),
            delegated_norm='',
            seen_in_page=set(),
            deps=deps,
        )

        self.assertEqual(
            outcome['result']['status_url'],
            'https://x.com/demo_plain/status/1234567890123456789',
        )

    def test_result_uses_normalize_dm_share_link_when_available(self):
        deps = self._make_deps()
        deps._normalize_dm_share_link = lambda raw, status_id='', status_handle='', fallback_url='': f'https://x.com/custom/status/{status_id}'
        deps.TWITTER_CLI_ENABLED = True
        deps.TWITTER_CLI_NOTIFY_ENRICH = True
        deps._extract_notification_status_info = lambda article: ('', '1234567890123456789')
        deps._extract_notification_content = lambda article, article_text, handle: ''
        deps._enrich_notification_from_twitter_cli = lambda *args, **kwargs: {
            'status': 'ok',
            'status_handle': '@demo_plain',
            'content': 'hello',
            'status_url': 'https://twitter.com/demo_plain/statuses/1234567890123456789',
            'source': 'twitter_cli',
        }
        deps._classify_notification_type = lambda text: {
            'notification_type': 'reply_to_you',
            'is_reply_like': True,
            'is_reply_to_me': True,
            'is_mention_to_me': False,
            'is_interaction_only': False,
            'normalized_text': str(text or ''),
        }

        outcome = process_notification_article(
            _Article(text='@demo 回复了你'),
            1,
            max_recent_minutes=45,
            trace_limit=5,
            blocked_norm_set=set(),
            delegated_norm='',
            seen_in_page=set(),
            deps=deps,
        )

        self.assertEqual(outcome['result']['status_url'], 'https://x.com/custom/status/1234567890123456789')

    def test_result_canonicalizes_relative_legacy_status_url(self):
        deps = self._make_deps()
        deps.TWITTER_CLI_ENABLED = True
        deps.TWITTER_CLI_NOTIFY_ENRICH = True
        deps._extract_notification_status_info = lambda article: ('', '1234567890123456789')
        deps._extract_notification_content = lambda article, article_text, handle: ''
        deps._enrich_notification_from_twitter_cli = lambda *args, **kwargs: {
            'status': 'ok',
            'status_handle': '@demo_plain',
            'content': 'hello',
            'status_url': '/demo_plain/statuses/1234567890123456789',
            'source': 'twitter_cli',
        }
        deps._classify_notification_type = lambda text: {
            'notification_type': 'reply_to_you',
            'is_reply_like': True,
            'is_reply_to_me': True,
            'is_mention_to_me': False,
            'is_interaction_only': False,
            'normalized_text': str(text or ''),
        }

        outcome = process_notification_article(
            _Article(text='@demo 回复了你'),
            1,
            max_recent_minutes=45,
            trace_limit=5,
            blocked_norm_set=set(),
            delegated_norm='',
            seen_in_page=set(),
            deps=deps,
        )

        self.assertEqual(
            outcome['result']['status_url'],
            'https://x.com/demo_plain/status/1234567890123456789',
        )

    def test_enrich_recovers_missing_handle_before_skip(self):
        deps = self._make_deps()
        deps.TWITTER_CLI_ENABLED = True
        deps.TWITTER_CLI_NOTIFY_ENRICH = True
        deps._extract_notification_status_info = lambda article: ('', '123')
        deps._extract_notification_handle = lambda article, article_text: ''
        deps._extract_notification_content = lambda article, article_text, handle: 'hello'
        deps._enrich_notification_from_twitter_cli = lambda *args, **kwargs: {
            'status': 'ok',
            'status_handle': '@recovered_user',
            'content': '',
            'status_url': '',
            'source': 'twitter_cli',
        }
        deps._classify_notification_type = lambda text: {
            'notification_type': 'reply_to_you',
            'is_reply_like': True,
            'is_reply_to_me': True,
            'is_mention_to_me': False,
            'is_interaction_only': False,
            'normalized_text': str(text or ''),
        }

        outcome = process_notification_article(
            _Article(text='有人回复了你'),
            1,
            max_recent_minutes=45,
            trace_limit=5,
            blocked_norm_set=set(),
            delegated_norm='',
            seen_in_page=set(),
            deps=deps,
        )

        self.assertIsNotNone(outcome['result'])
        self.assertEqual(outcome['result']['handle'], '@recovered_user')
        self.assertEqual(outcome['stats']['recovered_handle'], 1)
        self.assertEqual(outcome['stats']['twitter_cli_enrich_ok'], 1)
        self.assertEqual(outcome['stats']['twitter_cli_enrich_handle_filled'], 1)

    def test_no_handle_trace_includes_hrefs_and_tweet_texts(self):
        deps = self._make_deps()
        deps._extract_notification_status_info = lambda article: ('', '123')
        deps._extract_notification_handle = lambda article, article_text: ''
        deps._collect_notification_hrefs = lambda article: ['/demo_user/status/123']
        deps._collect_notification_tweet_texts = lambda article: ['正文线索']
        deps._classify_notification_type = lambda text: {
            'notification_type': 'reply_to_you',
            'is_reply_like': True,
            'is_reply_to_me': True,
            'is_mention_to_me': False,
            'is_interaction_only': False,
            'normalized_text': str(text or ''),
        }

        outcome = process_notification_article(
            _Article(text='有人回复了你'),
            1,
            max_recent_minutes=45,
            trace_limit=5,
            blocked_norm_set=set(),
            delegated_norm='',
            seen_in_page=set(),
            deps=deps,
        )

        self.assertIsNone(outcome['result'])
        joined = ' '.join(outcome['traces'])
        self.assertIn("tweetText=['正文线索']", joined)
        self.assertIn("hrefs=['/demo_user/status/123']", joined)

    def test_no_content_trace_includes_hrefs_and_tweet_texts(self):
        deps = self._make_deps()
        deps._extract_notification_status_info = lambda article: ('@demo', '123')
        deps._extract_notification_content = lambda article, article_text, handle: ''
        deps._collect_notification_hrefs = lambda article: ['/demo_user/status/123']
        deps._collect_notification_tweet_texts = lambda article: ['正文线索']
        deps._classify_notification_type = lambda text: {
            'notification_type': 'reply_to_you',
            'is_reply_like': True,
            'is_reply_to_me': True,
            'is_mention_to_me': False,
            'is_interaction_only': False,
            'normalized_text': str(text or ''),
        }

        outcome = process_notification_article(
            _Article(text='@demo 回复了你'),
            1,
            max_recent_minutes=45,
            trace_limit=5,
            blocked_norm_set=set(),
            delegated_norm='',
            seen_in_page=set(),
            deps=deps,
        )

        self.assertIsNone(outcome['result'])
        joined = ' '.join(outcome['traces'])
        self.assertIn("tweetText=['正文线索']", joined)
        self.assertIn("hrefs=['/demo_user/status/123']", joined)


if __name__ == '__main__':
    unittest.main()
