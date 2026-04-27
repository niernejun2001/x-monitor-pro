import unittest

from xmonitor.services.notify.text import (
    classify_notification_type,
    is_noise_notification_text,
    normalize_notification_text,
    normalize_one_line,
    score_notification_candidate,
)


class NotificationTextTests(unittest.TestCase):
    def test_classify_notification_type_for_reply_variants(self):
        result = classify_notification_type('lawrence · 1小时 回复了你的帖子 以前，用的时候，它叫轨迹球。')
        self.assertEqual(result['notification_type'], 'reply_to_you')
        self.assertTrue(result['is_reply_like'])
        self.assertTrue(result['is_reply_to_me'])

    def test_classify_notification_type_for_mention_variant(self):
        result = classify_notification_type('demo_user · 2分钟 在帖子中提到了你 方便留个联系方式吗')
        self.assertEqual(result['notification_type'], 'mention_you')
        self.assertTrue(result['is_mention_to_me'])

    def test_is_noise_notification_text_filters_action_only_text(self):
        self.assertTrue(is_noise_notification_text('回复了你的帖子', '@demo', set()))
        self.assertTrue(is_noise_notification_text('@demo', '@demo', set()))
        self.assertFalse(is_noise_notification_text('方便留个联系方式吗', '@demo', set()))

    def test_score_notification_candidate_prefers_stripped_and_trimmed_variants(self):
        base = score_notification_candidate('以前，用的时候，它叫轨迹球。 10', 'tweetText', set())
        stripped = score_notification_candidate('以前，用的时候，它叫轨迹球。', 'tweetText_trimmed', set())
        self.assertGreater(stripped, base)

    def test_normalizers_compact_whitespace(self):
        self.assertEqual(normalize_notification_text(' a \n b '), 'a b')
        self.assertEqual(normalize_one_line(' a \n b ', limit=10), 'a b')


if __name__ == '__main__':
    unittest.main()
