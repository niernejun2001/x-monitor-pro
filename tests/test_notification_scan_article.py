import types
import unittest

from xmonitor.services.notify.scan_article import process_notification_article


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


if __name__ == '__main__':
    unittest.main()
