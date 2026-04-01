from xmonitor.services.analysis.intent import (
    analyze_comment_intent as _analyze_comment_intent_impl,
    build_intent_analysis_prompt as _build_intent_analysis_prompt_impl,
    find_keyword_hits as _find_keyword_hits_impl,
    is_business_consult_signal as _is_business_consult_signal_impl,
    is_negative_intent_reason as _is_negative_intent_reason_impl,
    is_non_business_meme_signal as _is_non_business_meme_signal_impl,
    is_performance_consult_signal as _is_performance_consult_signal_impl,
    is_short_reply_intent_signal as _is_short_reply_intent_signal_impl,
    llm_intent_analysis as _llm_intent_analysis_impl,
    rule_based_intent_analysis as _rule_based_intent_analysis_impl,
    should_notify_voice_by_intent as _should_notify_voice_by_intent_impl,
)


def build_analysis_intent_exports(deps):
    def _score_to_intent_level(score):
        val = int(max(0, min(100, int(score))))
        if val >= 75:
            return 'high'
        if val >= 50:
            return 'medium'
        if val >= 25:
            return 'low'
        return 'noise'

    def _intent_level_rank(level):
        lv = str(level or '').strip().lower()
        if lv == 'high':
            return 4
        if lv == 'medium':
            return 3
        if lv == 'low':
            return 2
        return 1

    def _max_intent_level(*levels):
        best = 'noise'
        best_rank = 0
        for lv in levels:
            rank = _intent_level_rank(lv)
            if rank > best_rank:
                best_rank = rank
                best = str(lv or '').strip().lower() or 'noise'
        return best

    def _is_negative_intent_reason(reason_text):
        return _is_negative_intent_reason_impl(reason_text)

    def _find_keyword_hits(text_lower, keywords):
        return _find_keyword_hits_impl(text_lower, keywords)

    def _is_short_reply_intent_signal(content):
        return _is_short_reply_intent_signal_impl(content)

    def _is_performance_consult_signal(content):
        return _is_performance_consult_signal_impl(content)

    def _is_non_business_meme_signal(content):
        return _is_non_business_meme_signal_impl(content)

    def _is_business_consult_signal(content):
        return _is_business_consult_signal_impl(content, deps)

    def _rule_based_intent_analysis(content):
        return _rule_based_intent_analysis_impl(content, deps)

    def _build_intent_analysis_prompt(content):
        return _build_intent_analysis_prompt_impl(content, deps)

    def _llm_intent_analysis(content, *, base_url=None, api_key=None, model=None, timeout_sec=None):
        return _llm_intent_analysis_impl(
            content,
            deps,
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_sec=timeout_sec,
        )

    def analyze_comment_intent(content, *, base_url=None, api_key=None, model=None, timeout_sec=None):
        return _analyze_comment_intent_impl(content, deps, base_url=base_url, api_key=api_key, model=model, timeout_sec=timeout_sec)

    def _should_notify_voice_by_intent(analysis):
        return _should_notify_voice_by_intent_impl(analysis)

    return {
        '_score_to_intent_level': _score_to_intent_level,
        '_intent_level_rank': _intent_level_rank,
        '_max_intent_level': _max_intent_level,
        '_is_negative_intent_reason': _is_negative_intent_reason,
        '_find_keyword_hits': _find_keyword_hits,
        '_is_short_reply_intent_signal': _is_short_reply_intent_signal,
        '_is_performance_consult_signal': _is_performance_consult_signal,
        '_is_non_business_meme_signal': _is_non_business_meme_signal,
        '_is_business_consult_signal': _is_business_consult_signal,
        '_rule_based_intent_analysis': _rule_based_intent_analysis,
        '_build_intent_analysis_prompt': _build_intent_analysis_prompt,
        '_llm_intent_analysis': _llm_intent_analysis,
        'analyze_comment_intent': analyze_comment_intent,
        '_should_notify_voice_by_intent': _should_notify_voice_by_intent,
    }
