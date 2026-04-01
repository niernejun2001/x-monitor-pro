import unittest

from xmonitor.services.dm.runtime import is_dm_llm_fallback_allowed


class DMRuntimeTests(unittest.TestCase):
    def test_llm_copy_phrase_allows_template_fallback(self):
        self.assertTrue(
            is_dm_llm_fallback_allowed(
                'E_DM_LLM_COPY_PHRASE',
                '命中原句短语复用: 感谢您的关注与支持',
            )
        )

    def test_template_empty_does_not_allow_fallback(self):
        self.assertFalse(
            is_dm_llm_fallback_allowed(
                'E_DM_LLM_TEMPLATE_EMPTY',
                '私信模板为空，无法生成',
            )
        )


if __name__ == '__main__':
    unittest.main()
