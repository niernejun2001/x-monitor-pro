from xmonitor.services.analysis.llm_client import (
    call_ollama_native_json as _call_ollama_native_json_impl,
    call_openai_compatible_filter_api as _call_openai_compatible_filter_api_impl,
    call_openai_compatible_json as _call_openai_compatible_json_impl,
    guess_ollama_native_endpoint as _guess_ollama_native_endpoint_impl,
    parse_json_object_from_text as _parse_json_object_from_text_impl,
)


def build_analysis_llm_exports(deps):
    def _call_openai_compatible_json(system_prompt, user_prompt, *, base_url=None, api_key=None, model=None, timeout_sec=None, max_tokens=None, temperature=None):
        return _call_openai_compatible_json_impl(
            system_prompt,
            user_prompt,
            deps,
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_sec=timeout_sec,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def _guess_ollama_native_endpoint(base_url):
        return _guess_ollama_native_endpoint_impl(base_url, deps)

    def _call_ollama_native_json(system_prompt, user_prompt, *, base_url=None, model=None, timeout_sec=None):
        return _call_ollama_native_json_impl(
            system_prompt,
            user_prompt,
            deps,
            base_url=base_url,
            model=model,
            timeout_sec=timeout_sec,
        )

    def _call_openai_compatible_filter_api(content):
        return _call_openai_compatible_filter_api_impl(content, deps)

    def _parse_json_object_from_text(raw_text):
        return _parse_json_object_from_text_impl(raw_text)

    return {
        '_call_openai_compatible_json': _call_openai_compatible_json,
        '_guess_ollama_native_endpoint': _guess_ollama_native_endpoint,
        '_call_ollama_native_json': _call_ollama_native_json,
        '_call_openai_compatible_filter_api': _call_openai_compatible_filter_api,
        '_parse_json_object_from_text': _parse_json_object_from_text,
    }
