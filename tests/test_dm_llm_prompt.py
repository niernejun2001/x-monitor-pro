import unittest

import app
from xmonitor.services.dm_llm_service import dm_rewrite_has_subject_inversion


class DMLLMPromptTests(unittest.TestCase):
    def test_default_followup_text_uses_correct_subject_direction(self):
        self.assertIn('最近看您有在关注我们的产品', app.DM_FOLLOWUP_TEXT)
        self.assertNotIn('最近在看你们的产品', app.DM_FOLLOWUP_TEXT)

    def test_default_rewrite_prompt_blocks_subject_inversion(self):
        prompt = app.DM_LLM_REWRITE_DEFAULT_PROMPT
        self.assertIn('保持主语、宾语、关注关系和动作方向不变', prompt)
        self.assertIn('不能把“最近看您有在关注我们的产品”改写成“我在看你们的产品”', prompt)

    def test_subject_inversion_detector_hits_wrong_direction(self):
        inverted, reason = dm_rewrite_has_subject_inversion(
            '您好，我是懒猫微服的王勇，最近看您有在关注我们的产品，觉得挺有意思的。',
            '嗨，我是懒猫微服的王勇，最近在看你们的产品，挺有意思的。',
            app,
        )
        self.assertTrue(inverted)
        self.assertEqual(reason, 'user_interest_inverted_to_self_interest')


if __name__ == '__main__':
    unittest.main()
