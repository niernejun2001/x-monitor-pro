import unittest

import app


class AppNotifyHelpersTests(unittest.TestCase):
    def test_is_reply_to_me_notification_item_uses_keywords(self):
        item = {
            'source': '通知页面',
            'notification_text': '某某 回复了你 你好',
            'content': '你好',
        }
        self.assertTrue(app.is_reply_to_me_notification_item(item))

    def test_is_reply_to_me_notification_item_rejects_non_notify_source(self):
        item = {
            'source': 'tweet',
            'notification_text': '回复了你',
            'content': '你好',
        }
        self.assertFalse(app.is_reply_to_me_notification_item(item))


if __name__ == '__main__':
    unittest.main()
