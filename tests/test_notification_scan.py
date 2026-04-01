import types
import unittest

from xmonitor.services.notify.scan import scan_notifications_page


class _FakeLink:
    def __init__(self, href):
        self._href = href

    def attr(self, name):
        if name == 'href':
            return self._href
        return ''


class _FakeArticle:
    def __init__(self):
        self.text = 'demo notification text'
        self.html = '<a href="/demo/status/1234567890123456789">tweet</a>'

    def eles(self, selector, timeout=0):
        if selector == 'tag:a':
            return [_FakeLink('/demo/status/1234567890123456789')]
        return []

    def ele(self, selector, timeout=0):
        raise Exception('not implemented')


class NotificationScanTests(unittest.TestCase):
    def test_uses_twitter_cli_enrichment_when_content_missing(self):
        article = _FakeArticle()
        page = types.SimpleNamespace(
            url='https://x.com/notifications',
            eles=lambda selector, timeout=0.8: [article] if selector == 'tag:article' else [],
        )
        logs = []
        deps = types.SimpleNamespace(
            NOTIFICATION_RECENT_WINDOW_MINUTES=45,
            NOTIFICATION_MAX_SCAN_ARTICLES=180,
            NOTIFICATION_VERBOSE_TRACE=False,
            NOTIFICATION_TRACE_MAX_ARTICLES=0,
            NOTIFICATION_REPLY_ONLY_MODE=True,
            TWITTER_CLI_ENABLED=True,
            TWITTER_CLI_NOTIFY_ENRICH=True,
            reorder_articles_for_scan=lambda articles: articles,
            log_to_ui=lambda level, msg: logs.append((level, msg)),
            normalize_handle=lambda h: str(h or '').strip().lstrip('@').lower(),
            get_effective_delegated_account=lambda: '',
            _normalize_one_line=lambda text, limit=120: str(text or '')[:limit],
            _classify_notification_type=lambda text: {
                'notification_type': 'reply_to_you',
                'is_reply_like': True,
                'is_reply_to_me': True,
                'is_mention_to_me': False,
                'is_interaction_only': False,
                'normalized_text': str(text or ''),
            },
            _extract_notification_status_info=lambda article_obj: ('@demo', '1234567890123456789'),
            _parse_notification_age_minutes=lambda article_obj: 1.0,
            _extract_notification_handle=lambda article_obj, article_text: '@demo',
            _extract_notification_content=lambda article_obj, article_text, handle: '',
            _enrich_notification_from_twitter_cli=lambda status_id, handle_hint='', content_hint='': {
                'status': 'ok',
                'content': 'api enriched content',
                'status_handle': '@demo',
                'status_url': 'https://x.com/demo/status/1234567890123456789',
                'source': 'twitter_cli_tweet_detail',
            },
            should_skip_content_by_policy=lambda content: (False, ''),
            _pick_best_status_id=lambda *parts: '1234567890123456789',
            history_ids=set(),
        )

        results, err = scan_notifications_page(page, [], 45, deps, allow_navigation=True)

        self.assertIsNone(err)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['content'], 'api enriched content')
        self.assertEqual(results[0]['status_handle'], '@demo')
        self.assertEqual(results[0]['status_url'], 'https://x.com/demo/status/1234567890123456789')
        self.assertTrue(results[0]['twitter_cli_enriched'])
        self.assertEqual(results[0]['twitter_cli_enrich_source'], 'twitter_cli_tweet_detail')


if __name__ == '__main__':
    unittest.main()
