from xmonitor.services.analysis.filter import (
    contains_emoji_char as _contains_emoji_char_impl,
    is_emoji_only_content as _is_emoji_only_content_impl,
    llm_filter_endpoint as _llm_filter_endpoint_impl,
    llm_filter_is_ready as _llm_filter_is_ready_impl,
    llm_runtime_ready as _llm_runtime_ready_impl,
    prune_llm_filter_cache as _prune_llm_filter_cache_impl,
    should_skip_content_by_policy as _should_skip_content_by_policy_impl,
)
from xmonitor.services.analysis.llm_client import parse_json_object_from_text as _parse_json_object_from_text_impl


def build_support_analysis_exports(deps, *, clamp_llm_timeout_fn):
    def clamp_llm_timeout(raw_timeout):
        return clamp_llm_timeout_fn(raw_timeout)

    def _contains_emoji_char(ch):
        return _contains_emoji_char_impl(ch, deps)

    def _is_emoji_only_content(content):
        return _is_emoji_only_content_impl(content, deps)

    def should_skip_content_by_policy(content, allow_llm_hard_filter=None):
        return _should_skip_content_by_policy_impl(
            content,
            deps,
            allow_llm_hard_filter=allow_llm_hard_filter,
        )

    def _llm_filter_endpoint(base_url=None):
        return _llm_filter_endpoint_impl(deps, base_url=base_url)

    def _llm_runtime_ready(base_url=None, model=None):
        return _llm_runtime_ready_impl(deps, base_url=base_url, model=model)

    def _llm_filter_is_ready(base_url=None, model=None, enabled=None):
        return _llm_filter_is_ready_impl(
            deps,
            base_url=base_url,
            model=model,
            enabled=enabled,
        )

    def _prune_llm_filter_cache(now_ts=None):
        return _prune_llm_filter_cache_impl(deps, now_ts=now_ts)

    def _parse_json_object_from_text(raw_text):
        return _parse_json_object_from_text_impl(raw_text)

    return {
        'clamp_llm_timeout': clamp_llm_timeout,
        '_contains_emoji_char': _contains_emoji_char,
        '_is_emoji_only_content': _is_emoji_only_content,
        'should_skip_content_by_policy': should_skip_content_by_policy,
        '_llm_filter_endpoint': _llm_filter_endpoint,
        '_llm_runtime_ready': _llm_runtime_ready,
        '_llm_filter_is_ready': _llm_filter_is_ready,
        '_prune_llm_filter_cache': _prune_llm_filter_cache,
        '_parse_json_object_from_text': _parse_json_object_from_text,
    }
