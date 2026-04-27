import threading
import types
import unittest

from xmonitor.services.dm.state_service import (
    clear_dm_unavailable_cache,
    get_status_link_from_item,
    is_dm_unavailable_cached,
    mark_dm_unavailable,
)


class DMStateServiceTests(unittest.TestCase):
    def _make_deps(self):
        return types.SimpleNamespace(
            normalize_handle=lambda handle: str(handle or '').strip().lstrip('@').lower(),
            _pick_best_status_id=lambda *parts: next((str(part) for part in parts if str(part or '').strip()), ''),
            _normalize_dm_share_link=lambda raw, status_id='', status_handle='', fallback_url='': (
                f'https://x.com/{str(status_handle or "").strip().lstrip("@").lower()}/status/{status_id}'
                if status_id and status_handle else
                str(raw or fallback_url or '')
            ),
            dm_unavailable_cache={},
            dm_unavailable_cache_lock=threading.Lock(),
            DM_UNAVAILABLE_CACHE_TTL_SEC=60.0,
        )

    def test_get_status_link_from_item_prefers_matched_status_fields(self):
        deps = self._make_deps()
        item = {
            'status_url': 'https://twitter.com/demo/statuses/111',
            'status_id': '111',
            'status_handle': '@demo',
            'handle': '@demo',
        }

        url = get_status_link_from_item(item, deps, matched_status_handle='@matched', matched_status_id='222')

        self.assertEqual(url, 'https://x.com/matched/status/222')

    def test_get_status_link_from_item_uses_item_fields_when_unmatched(self):
        deps = self._make_deps()
        item = {
            'status_url': '/demo/statuses/1234567890123456789',
            'status_id': '1234567890123456789',
            'status_handle': '@demo',
            'handle': '@demo',
        }

        url = get_status_link_from_item(item, deps)

        self.assertEqual(url, 'https://x.com/demo/status/1234567890123456789')

    def test_dm_unavailable_cache_roundtrip(self):
        deps = self._make_deps()

        self.assertFalse(is_dm_unavailable_cached('@demo', deps))
        mark_dm_unavailable('@demo', deps)
        self.assertTrue(is_dm_unavailable_cached('@demo', deps))
        clear_dm_unavailable_cache('@demo', deps)
        self.assertFalse(is_dm_unavailable_cached('@demo', deps))


if __name__ == '__main__':
    unittest.main()
