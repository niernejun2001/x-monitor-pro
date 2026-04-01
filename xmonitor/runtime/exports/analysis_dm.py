from xmonitor.services.dm.llm_service import (
    build_dm_llm_rewrite_prompt as _build_dm_llm_rewrite_prompt_impl,
    dm_rewrite_contains_forbidden_phrase as _dm_rewrite_contains_forbidden_phrase_impl,
    dm_rewrite_is_too_similar as _dm_rewrite_is_too_similar_impl,
    dm_rewrite_longest_common_substring_len as _dm_rewrite_longest_common_substring_len_impl,
    dm_rewrite_similarity_score as _dm_rewrite_similarity_score_impl,
    extract_dm_rewrite_forbidden_phrases as _extract_dm_rewrite_forbidden_phrases_impl,
    generate_dm_text_with_llm as _generate_dm_text_with_llm_impl,
    is_dm_llm_rewrite_duplicate as _is_dm_llm_rewrite_duplicate_impl,
    normalize_dm_rewrite_signature as _normalize_dm_rewrite_signature_impl,
    record_dm_llm_rewrite_signature as _record_dm_llm_rewrite_signature_impl,
)


def build_analysis_dm_exports(deps):
    def _normalize_dm_rewrite_signature(text):
        return _normalize_dm_rewrite_signature_impl(text, deps)

    def _build_dm_llm_rewrite_prompt(template_text):
        return _build_dm_llm_rewrite_prompt_impl(template_text, deps)

    def _dm_rewrite_longest_common_substring_len(source_text, generated_text):
        return _dm_rewrite_longest_common_substring_len_impl(source_text, generated_text, deps)

    def _extract_dm_rewrite_forbidden_phrases(template_text, max_items=5):
        return _extract_dm_rewrite_forbidden_phrases_impl(template_text, deps, max_items=max_items)

    def _dm_rewrite_contains_forbidden_phrase(generated_text, forbidden_phrases):
        return _dm_rewrite_contains_forbidden_phrase_impl(generated_text, forbidden_phrases, deps)

    def _dm_rewrite_similarity_score(source_text, generated_text):
        return _dm_rewrite_similarity_score_impl(source_text, generated_text, deps)

    def _dm_rewrite_is_too_similar(source_text, generated_text):
        return _dm_rewrite_is_too_similar_impl(source_text, generated_text, deps)

    def _record_dm_llm_rewrite_signature(sig):
        return _record_dm_llm_rewrite_signature_impl(sig, deps)

    def _is_dm_llm_rewrite_duplicate(sig):
        return _is_dm_llm_rewrite_duplicate_impl(sig, deps)

    def _generate_dm_text_with_llm(template_text):
        return _generate_dm_text_with_llm_impl(template_text, deps)

    return {
        '_normalize_dm_rewrite_signature': _normalize_dm_rewrite_signature,
        '_build_dm_llm_rewrite_prompt': _build_dm_llm_rewrite_prompt,
        '_dm_rewrite_longest_common_substring_len': _dm_rewrite_longest_common_substring_len,
        '_extract_dm_rewrite_forbidden_phrases': _extract_dm_rewrite_forbidden_phrases,
        '_dm_rewrite_contains_forbidden_phrase': _dm_rewrite_contains_forbidden_phrase,
        '_dm_rewrite_similarity_score': _dm_rewrite_similarity_score,
        '_dm_rewrite_is_too_similar': _dm_rewrite_is_too_similar,
        '_record_dm_llm_rewrite_signature': _record_dm_llm_rewrite_signature,
        '_is_dm_llm_rewrite_duplicate': _is_dm_llm_rewrite_duplicate,
        '_generate_dm_text_with_llm': _generate_dm_text_with_llm,
    }
