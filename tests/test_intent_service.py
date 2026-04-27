import types
import unittest

from xmonitor.services.analysis.intent import (
    analyze_comment_intent,
    is_business_consult_signal,
    llm_intent_analysis,
    rule_based_intent_analysis,
    should_notify_voice_by_intent,
)


class IntentServiceTests(unittest.TestCase):
    def _make_deps(self):
        deps = types.SimpleNamespace()
        deps._normalize_content_for_filter = lambda text: str(text or '').strip()
        deps.INTENT_CONSULT_KEYWORDS = (
            '咨询', '了解', '介绍', '怎么', '如何', '多少钱', '什么价格', '报价',
            '预算', '方案', '套餐', '配置', '规格', '速度', '性能', '并发', '吞吐',
            '试用', '部署', '开通', '企业版', '私有化', '交付', '售后', '发票', '合同', '采购',
        )
        deps.INTENT_PRODUCT_KEYWORDS = (
            '懒猫微服', 'lazycat', 'lazycat.cloud', '应用云电脑', '云电脑', '内网穿透', '沙箱隔离',
            '一站式部署', '大模型', 'deepseek', '远程桌面', '异地组网', '家庭服务器', 'nas',
            'openclaw', '算力舱', '算力', '算力规格', 'cpu', 'gpu',
        )
        deps.INTENT_CONTACT_KEYWORDS = ('微信', 'vx', 'v我', '加我', '联系我', '联系方式', '私信')
        deps.INTENT_FORCE_NOTIFY_KEYWORDS = ()
        deps.INTENT_NON_TARGET_TOPIC_KEYWORDS = ()
        deps._find_keyword_hits = lambda text, keywords: [kw for kw in keywords if kw in str(text or '').lower()]
        deps._is_emoji_only_content = lambda text: False
        deps._is_short_reply_intent_signal = lambda text: False
        deps._is_performance_consult_signal = lambda text: False
        deps._is_business_consult_signal = lambda text: is_business_consult_signal(text, deps)
        deps._is_non_business_meme_signal = lambda text: False
        deps._score_to_intent_level = lambda score: 'high' if score >= 85 else ('medium' if score >= 55 else ('low' if score >= 25 else 'noise'))
        return deps

    def test_short_polite_consult_is_business_signal(self):
        deps = self._make_deps()
        self.assertTrue(is_business_consult_signal('老板 想了解下', deps))

    def test_short_polite_consult_becomes_medium_and_voice(self):
        deps = self._make_deps()
        result = rule_based_intent_analysis('老板 想了解下', deps)
        self.assertEqual(result['intent_level'], 'medium')
        self.assertTrue(result['force_notify'])
        self.assertIn('business_consult_signal', result['signals'])
        analysis = {
            'intent_score': result['intent_score'],
            'intent_level': result['intent_level'],
            'is_intent_user': True,
            'force_notify': result['force_notify'],
            'block_intent': result['block_intent'],
        }
        self.assertTrue(should_notify_voice_by_intent(analysis))

    def test_llm_intent_analysis_tolerates_none_score(self):
        deps = self._make_deps()
        deps._build_intent_analysis_prompt = lambda content: f'prompt:{content}'
        deps._call_openai_compatible_json = lambda *args, **kwargs: ({
            'intent_score': None,
            'intent_level': 'medium',
            'is_intent_user': True,
            'force_notify': False,
            'buying_signals': ['咨询'],
            'reason': '正常咨询',
        }, '{}')
        deps._is_negative_intent_reason = lambda reason: False
        deps._score_to_intent_level = lambda score: 'high' if score >= 85 else ('medium' if score >= 55 else ('low' if score >= 25 else 'noise'))

        result = llm_intent_analysis('老板 想了解下', deps)

        self.assertIsInstance(result, dict)
        self.assertEqual(result['intent_score'], 0)
        self.assertEqual(result['intent_level'], 'medium')

    def test_analyze_comment_intent_formats_blank_llm_error(self):
        class _BlankError(Exception):
            def __str__(self):
                return ''

        deps = self._make_deps()
        deps._normalize_one_line = lambda text, limit=120: str(text or '')[:limit]
        logs = []
        deps.log_to_ui = lambda level, msg: logs.append((level, msg))
        deps._llm_runtime_ready = lambda **kwargs: True
        deps.INTENT_LLM_PRIMARY_MODE = False
        deps._intent_level_rank = lambda level: {'noise': 0, 'low': 1, 'medium': 2, 'high': 3}.get(level, 0)
        deps._max_intent_level = lambda *levels: max(levels, key=lambda level: deps._intent_level_rank(level))
        deps._is_negative_intent_reason = lambda reason: False
        deps._call_openai_compatible_json = lambda *args, **kwargs: (_ for _ in ()).throw(_BlankError())
        deps._build_intent_analysis_prompt = lambda content: f'prompt:{content}'

        result = analyze_comment_intent('老板 想了解下', deps)

        self.assertEqual(result['llm_error'], '_BlankError')
        self.assertTrue(any('_BlankError' in msg for _, msg in logs))


if __name__ == '__main__':
    unittest.main()
