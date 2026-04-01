from xmonitor.services.analysis.filter import (
    contains_emoji_char as _contains_emoji_char_impl,
    is_emoji_only_content as _is_emoji_only_content_impl,
    llm_filter_endpoint as _llm_filter_endpoint_impl,
    llm_filter_is_ready as _llm_filter_is_ready_impl,
    llm_runtime_ready as _llm_runtime_ready_impl,
    make_content_signature as _make_content_signature_impl,
    normalize_content_for_filter as _normalize_content_for_filter_impl,
    normalize_content_for_dedupe as _normalize_content_for_dedupe_impl,
    prune_content_dedupe as _prune_content_dedupe_impl,
    prune_llm_filter_cache as _prune_llm_filter_cache_impl,
    should_skip_by_llm_filter as _should_skip_by_llm_filter_impl,
    should_skip_content_by_policy as _should_skip_content_by_policy_impl,
    should_skip_duplicate_content as _should_skip_duplicate_content_impl,
)
from xmonitor.services.audio.tts import (
    doubao_tts_is_ready as _doubao_tts_is_ready_impl,
    doubao_tts_mime_by_encoding as _doubao_tts_mime_by_encoding_impl,
    synthesize_doubao_tts_audio_base64 as _synthesize_doubao_tts_audio_base64_impl,
    truncate_text_for_tts as _truncate_text_for_tts_impl,
)


def build_analysis_filtering_exports(deps):
    def _normalize_content_for_filter(content):
        return _normalize_content_for_filter_impl(content)

    def _should_skip_by_llm_filter(content):
        return _should_skip_by_llm_filter_impl(content, deps)

    def normalize_content_for_dedupe(content):
        return _normalize_content_for_dedupe_impl(content)

    def make_content_signature(handle, content):
        return _make_content_signature_impl(handle, content, deps)

    def prune_content_dedupe(now_ts=None):
        return _prune_content_dedupe_impl(deps, now_ts=now_ts)

    def should_skip_duplicate_content(handle, content, now_ts=None):
        return _should_skip_duplicate_content_impl(handle, content, deps, now_ts=now_ts)

    def _contains_emoji_char(ch):
        return _contains_emoji_char_impl(ch, deps)

    def _is_emoji_only_content(content):
        return _is_emoji_only_content_impl(content, deps)

    def should_skip_content_by_policy(content, allow_llm_hard_filter=None):
        return _should_skip_content_by_policy_impl(content, deps, allow_llm_hard_filter=allow_llm_hard_filter)

    def _llm_filter_endpoint(base_url=None):
        return _llm_filter_endpoint_impl(deps, base_url=base_url)

    def _llm_runtime_ready(base_url=None, model=None):
        return _llm_runtime_ready_impl(deps, base_url=base_url, model=model)

    def _llm_filter_is_ready(base_url=None, model=None, enabled=None):
        return _llm_filter_is_ready_impl(deps, base_url=base_url, model=model, enabled=enabled)

    def _doubao_tts_is_ready():
        return _doubao_tts_is_ready_impl(deps)

    def _doubao_tts_mime_by_encoding(encoding):
        return _doubao_tts_mime_by_encoding_impl(encoding)

    def _truncate_text_for_tts(text):
        return _truncate_text_for_tts_impl(text, deps)

    def _synthesize_doubao_tts_audio_base64(text):
        return _synthesize_doubao_tts_audio_base64_impl(text, deps)

    def _prune_llm_filter_cache(now_ts=None):
        return _prune_llm_filter_cache_impl(deps, now_ts=now_ts)

    return {
        '_normalize_content_for_filter': _normalize_content_for_filter,
        '_should_skip_by_llm_filter': _should_skip_by_llm_filter,
        'normalize_content_for_dedupe': normalize_content_for_dedupe,
        'make_content_signature': make_content_signature,
        'prune_content_dedupe': prune_content_dedupe,
        'should_skip_duplicate_content': should_skip_duplicate_content,
        '_contains_emoji_char': _contains_emoji_char,
        '_is_emoji_only_content': _is_emoji_only_content,
        'should_skip_content_by_policy': should_skip_content_by_policy,
        '_llm_filter_endpoint': _llm_filter_endpoint,
        '_llm_runtime_ready': _llm_runtime_ready,
        '_llm_filter_is_ready': _llm_filter_is_ready,
        '_doubao_tts_is_ready': _doubao_tts_is_ready,
        '_doubao_tts_mime_by_encoding': _doubao_tts_mime_by_encoding,
        '_truncate_text_for_tts': _truncate_text_for_tts,
        '_synthesize_doubao_tts_audio_base64': _synthesize_doubao_tts_audio_base64,
        '_prune_llm_filter_cache': _prune_llm_filter_cache,
    }
