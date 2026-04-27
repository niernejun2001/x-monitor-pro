import unittest

from xmonitor.services.support.status_links import (
    canonical_status_url,
    extract_status_id_candidates,
    extract_status_link_parts,
    status_identity,
    status_url_priority,
    status_url_quality,
)


def _normalize_status_id_digits(value):
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return digits if len(digits) >= 6 else ''


def _pick_best_status_id(*parts):
    candidates = []
    for part in parts:
        candidates.extend(extract_status_id_candidates(part, normalize_status_id_digits_fn=_normalize_status_id_digits))
    return candidates[-1] if candidates else ''


class StatusLinksTests(unittest.TestCase):
    def test_extract_status_link_parts_supports_user_and_query_forms(self):
        self.assertEqual(
            extract_status_link_parts('https://twitter.com/demo_user/statuses/123456', pick_best_status_id_fn=_pick_best_status_id),
            ('@demo_user', '123456'),
        )
        self.assertEqual(
            extract_status_link_parts('https://x.com/i/web/status/1?status_id=654321', pick_best_status_id_fn=_pick_best_status_id),
            (None, '654321'),
        )

    def test_canonical_status_url_prefers_user_link_when_present(self):
        self.assertEqual(
            canonical_status_url(
                'https://mobile.twitter.com/demo_user/statuses/123456',
                normalize_handle_fn=lambda handle: str(handle or '').strip().lstrip('@').lower(),
                pick_best_status_id_fn=_pick_best_status_id,
            ),
            'https://x.com/demo_user/status/123456',
        )

    def test_canonical_status_url_uses_fallback_handle(self):
        self.assertEqual(
            canonical_status_url(
                '',
                status_id='123456',
                status_handle='@fallback_user',
                normalize_handle_fn=lambda handle: str(handle or '').strip().lstrip('@').lower(),
                pick_best_status_id_fn=_pick_best_status_id,
            ),
            'https://x.com/fallback_user/status/123456',
        )

    def test_status_identity_uses_status_id_when_present(self):
        self.assertEqual(
            status_identity('https://mobile.twitter.com/demo_user/statuses/123456', pick_best_status_id_fn=_pick_best_status_id),
            'status:123456',
        )

    def test_status_url_quality_prefers_user_link_over_i_status(self):
        self.assertGreater(
            status_url_quality('https://x.com/demo_user/status/123456'),
            status_url_quality('https://x.com/i/status/123456'),
        )

    def test_status_url_priority_prefers_status_links_and_queries(self):
        self.assertGreater(
            status_url_priority('https://x.com/demo_user/status/123456'),
            status_url_priority('/compose/post'),
        )
        self.assertGreater(
            status_url_priority('https://x.com/i/web/status/1?status_id=654321'),
            status_url_priority('/search'),
        )


if __name__ == '__main__':
    unittest.main()
