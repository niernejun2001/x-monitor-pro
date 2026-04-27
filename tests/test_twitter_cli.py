import types
import unittest
from unittest import mock

from xmonitor.services.platform.twitter_cli import (
    _IMPORT_STATE,
    _RUNTIME_META,
    _tweet_to_payload,
    enrich_notification_from_twitter_cli,
    fetch_twitter_cli_user,
    fetch_twitter_cli_tweet_detail,
    get_twitter_cli_status,
)


class TwitterCliTests(unittest.TestCase):
    def test_get_twitter_cli_status_formats_blank_error(self):
        class _BlankError(Exception):
            def __str__(self):
                return ''

        deps = types.SimpleNamespace(TWITTER_CLI_ENABLED=True)
        _IMPORT_STATE.update({'checked': True, 'ok': True, 'error': '', 'client_cls': object(), 'auth_mod': object()})
        with mock.patch('xmonitor.services.platform.twitter_cli._create_client_and_meta', side_effect=_BlankError()):
            result = get_twitter_cli_status(deps, verify=True)

        self.assertEqual(result['status'], 'err')
        self.assertEqual(result['msg'], '_BlankError')
        self.assertEqual(result['twitter_cli_last_error'], '_BlankError')

    def test_fetch_twitter_cli_tweet_detail_formats_blank_error(self):
        class _BlankError(Exception):
            def __str__(self):
                return ''

        deps = types.SimpleNamespace(TWITTER_CLI_ENABLED=True, TWITTER_CLI_TWEET_CACHE_TTL_SEC=300)
        _IMPORT_STATE.update({'checked': True, 'ok': True, 'error': '', 'client_cls': object(), 'auth_mod': object()})
        with mock.patch('xmonitor.services.platform.twitter_cli._create_client_and_meta', side_effect=_BlankError()):
            result = fetch_twitter_cli_tweet_detail(deps, '1234567890123456789')

        self.assertEqual(result['status'], 'err')
        self.assertEqual(result['msg'], '_BlankError')
        self.assertEqual(result['twitter_cli_last_error'], '_BlankError')

    def test_fetch_twitter_cli_user_formats_blank_error(self):
        class _BlankError(Exception):
            def __str__(self):
                return ''

        deps = types.SimpleNamespace(TWITTER_CLI_ENABLED=True, TWITTER_CLI_USER_CACHE_TTL_SEC=600)
        _IMPORT_STATE.update({'checked': True, 'ok': True, 'error': '', 'client_cls': object(), 'auth_mod': object()})
        with mock.patch('xmonitor.services.platform.twitter_cli._create_client_and_meta', side_effect=_BlankError()):
            result = fetch_twitter_cli_user(deps, '@demo')

        self.assertEqual(result['status'], 'err')
        self.assertEqual(result['msg'], '_BlankError')
        self.assertEqual(result['twitter_cli_last_error'], '_BlankError')

    def test_tweet_to_payload_canonicalizes_legacy_url(self):
        author = types.SimpleNamespace(screen_name='demo_user', id='1', name='Demo', verified=False)
        tweet = types.SimpleNamespace(
            id='1234567890123456789',
            text='hello',
            created_at='now',
            url='https://mobile.twitter.com/demo_user/statuses/1234567890123456789',
            author=author,
        )

        payload = _tweet_to_payload(tweet)

        self.assertEqual(payload['url'], 'https://x.com/demo_user/status/1234567890123456789')

    def test_enrich_notification_from_twitter_cli_canonicalizes_status_url(self):
        deps = types.SimpleNamespace()
        fake_detail = {
            'status': 'ok',
            'tweet': {
                'text': 'hello',
                'url': 'https://twitter.com/demo_user/statuses/1234567890123456789',
                'author': {'screen_name': 'demo_user'},
            },
        }

        with mock.patch('xmonitor.services.platform.twitter_cli.fetch_twitter_cli_tweet_detail', return_value=fake_detail):
            result = enrich_notification_from_twitter_cli(deps, '1234567890123456789')

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['status_url'], 'https://x.com/demo_user/status/1234567890123456789')


if __name__ == '__main__':
    unittest.main()
