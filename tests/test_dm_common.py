import types
import unittest

from xmonitor.services.dm.common import confirm_dm_message_sent, conversation_contains_dm_text


class DMCommonTests(unittest.TestCase):
    def test_conversation_contains_dm_text_accepts_long_message_by_probes(self):
        tab = types.SimpleNamespace(
            run_js=lambda script: '前文 您好呀，这里是懒猫微服，给您补充一下详细信息，工程师微信17612774028，备注推特ID可享优惠 后文'
        )
        self.assertTrue(
            conversation_contains_dm_text(
                tab,
                '您好呀，这里是懒猫微服，给您补充一下详细信息，工程师微信17612774028，备注推特ID可享优惠',
            )
        )

    def test_confirm_dm_message_sent_accepts_message_presence_when_snapshot_changed(self):
        tab = types.SimpleNamespace(
            run_js=lambda script: '会话更新 您好呀，这里是懒猫微服，给您补充一下详细信息，工程师微信17612774028，备注推特ID可享优惠'
        )
        probes = ['您好呀，这里是懒猫微服', '备注推特id可享优惠']
        before_counts = {
            probes[0]: 99,
            probes[1]: 99,
            '__snapshot': '',
            '__sent_markers': 0,
        }
        self.assertTrue(
            confirm_dm_message_sent(
                tab,
                before_counts,
                probes,
                wait_sec=0.2,
                message_text='您好呀，这里是懒猫微服，给您补充一下详细信息，工程师微信17612774028，备注推特ID可享优惠',
            )
        )


if __name__ == '__main__':
    unittest.main()
