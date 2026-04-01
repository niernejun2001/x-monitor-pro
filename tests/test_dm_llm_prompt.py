import unittest
from types import SimpleNamespace

import app
from xmonitor.services.dm.llm_service import (
    dm_rewrite_has_subject_inversion,
    extract_dm_rewrite_protected_literals,
    extract_dm_rewrite_forbidden_phrases,
    generate_dm_text_with_llm,
)


class DMLLMPromptTests(unittest.TestCase):
    def test_default_followup_text_uses_correct_subject_direction(self):
        self.assertIn('最近看您有在关注我们的产品', app.DM_FOLLOWUP_TEXT)
        self.assertNotIn('最近在看你们的产品', app.DM_FOLLOWUP_TEXT)

    def test_default_rewrite_prompt_blocks_subject_inversion(self):
        prompt = app.DM_LLM_REWRITE_DEFAULT_PROMPT
        self.assertIn('保持主语、宾语、关注关系和动作方向不变', prompt)
        self.assertIn('不能把“最近看您有在关注我们的产品”改写成“我在看你们的产品”', prompt)
        self.assertIn('手机号、微信号、QQ号、邮箱、链接、数字串', prompt)

    def test_subject_inversion_detector_hits_wrong_direction(self):
        inverted, reason = dm_rewrite_has_subject_inversion(
            '您好，我是懒猫微服的王勇，最近看您有在关注我们的产品，觉得挺有意思的。',
            '嗨，我是懒猫微服的王勇，最近在看你们的产品，挺有意思的。',
            app,
        )
        self.assertTrue(inverted)
        self.assertEqual(reason, 'user_interest_inverted_to_self_interest')

    def test_extract_protected_literals_captures_phone(self):
        literals = extract_dm_rewrite_protected_literals(
            '欢迎添加工程师微信 17612774028，我们给您一对一介绍。',
            app,
        )
        values = [item['literal'] for item in literals]
        self.assertIn('17612774028', values)

    def test_generic_polite_phrase_not_treated_as_forbidden_copy(self):
        phrases = extract_dm_rewrite_forbidden_phrases(
            '老板您好，我是 懒猫微服 CEO 王勇，感谢您的关注与支持。\n如需了解更详细的产品资料，欢迎添加我们的工程师微信 17612774028，我们将为您提供一对一的专业介绍与支持，工程师告诉您购买方式~\n备注推特ID给您优惠。',
            app,
            max_items=10,
        )
        self.assertFalse(any('感谢您的关注与支持' in x for x in phrases))

    def test_generate_dm_text_with_llm_retries_when_phone_changes(self):
        calls = {'count': 0}

        def fake_call(*args, **kwargs):
            calls['count'] += 1
            if calls['count'] == 1:
                return {'text': '欢迎添加工程师微信 17612074028，我们给您一对一介绍。'}, ''
            return {'text': '欢迎添加工程师微信 17612774028，我们给您一对一介绍。'}, ''

        deps = SimpleNamespace(
            DM_LLM_REWRITE_PROMPT_TEMPLATE='模板如下：\n{template}',
            DM_LLM_REWRITE_DEFAULT_PROMPT='模板如下：\n{template}',
            DM_LLM_REWRITE_MAX_REGEN=1,
            DM_LLM_REWRITE_MAX_CHARS=260,
            DM_LLM_REWRITE_TEMPERATURE=0.35,
            LLM_FILTER_TIMEOUT_SEC=8.0,
            DM_LLM_REWRITE_DEDUPE_SIZE=200,
            DM_LLM_REWRITE_SIMILARITY_MAX=0.99,
            DM_LLM_REWRITE_MIN_DIFF_CHARS=1,
            DM_LLM_REWRITE_MAX_SHARED_RUN=999,
            dm_llm_rewrite_history=[],
            dm_llm_rewrite_lock=app.threading.Lock(),
            _sanitize_dm_message_text=lambda text: str(text or '').strip(),
            _llm_runtime_ready=lambda: True,
            _build_dm_llm_rewrite_prompt=lambda template: f'模板如下：\n{template}',
            _extract_dm_rewrite_forbidden_phrases=lambda template: [],
            _call_openai_compatible_json=fake_call,
            _dm_rewrite_contains_forbidden_phrase=lambda generated, forbidden: '',
            _dm_rewrite_is_too_similar=lambda source, generated: (False, 0.0, 12, 0),
            _normalize_dm_rewrite_signature=lambda text: text,
            _is_dm_llm_rewrite_duplicate=lambda sig: False,
            _record_dm_llm_rewrite_signature=lambda sig: None,
            _normalize_text_for_compare=lambda text: str(text or ''),
            normalize_content_for_dedupe=lambda text: str(text or '').lower(),
            difflib=app.difflib,
            hashlib=app.hashlib,
        )
        ok, text, meta = generate_dm_text_with_llm(
            '欢迎添加工程师微信 17612774028，我们给您一对一介绍。',
            deps,
        )
        self.assertTrue(ok)
        self.assertIn('17612774028', text)
        self.assertEqual(meta.get('regen_attempt'), 2)


if __name__ == '__main__':
    unittest.main()
