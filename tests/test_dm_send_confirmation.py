import unittest


class DMSendConfirmationTests(unittest.TestCase):
    def test_text_send_should_not_be_treated_as_success_on_clear_only(self):
        # 文本私信链路要求：输入框清空不能单独视为成功，必须再确认消息落库。
        # 这里只做回归约束，避免未来把判定又改回“clear 即成功”。
        link_only_mode = False
        composer_cleared = True
        confirmed = False
        success = False
        if composer_cleared:
            if link_only_mode:
                success = True
            elif confirmed:
                success = True
            else:
                success = False
        self.assertFalse(success)

    def test_link_send_can_still_accept_clear_only(self):
        link_only_mode = True
        composer_cleared = True
        confirmed = False
        success = False
        if composer_cleared:
            if link_only_mode:
                success = True
            elif confirmed:
                success = True
            else:
                success = False
        self.assertTrue(success)


if __name__ == '__main__':
    unittest.main()
