import types
import unittest

from xmonitor.services.reply.ops import _build_status_fallback_urls


class ReplyOpsTests(unittest.TestCase):
    def test_build_status_fallback_urls_canonicalizes_and_dedupes(self):
        deps = types.SimpleNamespace(
            normalize_handle=lambda handle: str(handle or '').strip().lstrip('@').lower(),
            _get_status_link_from_item=lambda item: 'https://mobile.twitter.com/demo/statuses/1234567890123456789',
            _normalize_dm_share_link=lambda raw, status_id='', status_handle='', fallback_url='': (
                f'https://x.com/{str(status_handle or "").strip().lstrip("@").lower() or "demo"}/status/{status_id}'
                if status_id else str(raw or fallback_url or '')
            ),
        )
        item = {
            'status_url': '/demo/statuses/1234567890123456789',
            'status_handle': '@demo',
            'handle': '@demo',
        }

        urls = _build_status_fallback_urls(item, '1234567890123456789', deps)

        self.assertEqual(urls, ['https://x.com/demo/status/1234567890123456789'])

    def test_build_status_fallback_urls_supports_handle_only_fallback(self):
        deps = types.SimpleNamespace(
            normalize_handle=lambda handle: str(handle or '').strip().lstrip('@').lower(),
            _get_status_link_from_item=lambda item: '',
            _normalize_dm_share_link=lambda raw, status_id='', status_handle='', fallback_url='': (
                f'https://x.com/{str(status_handle or "").strip().lstrip("@").lower()}/status/{status_id}'
                if status_id and status_handle else ''
            ),
        )
        item = {
            'status_url': '',
            'status_handle': '',
            'handle': '@demo',
        }

        urls = _build_status_fallback_urls(item, '1234567890123456789', deps)

        self.assertEqual(urls, ['https://x.com/demo/status/1234567890123456789'])


if __name__ == '__main__':
    unittest.main()
