def extract_llm_runtime_from_payload(payload, deps):
    payload = payload or {}
    base_url = str(payload.get('base_url', deps.LLM_FILTER_BASE_URL) or '').strip()
    api_key = str(payload.get('api_key', deps.LLM_FILTER_API_KEY) or '').strip() or 'EMPTY'
    model = str(payload.get('model', deps.LLM_FILTER_MODEL) or '').strip()
    timeout_sec = deps.clamp_llm_timeout(payload.get('timeout_sec', deps.LLM_FILTER_TIMEOUT_SEC))
    return {
        'base_url': base_url,
        'api_key': api_key,
        'model': model,
        'timeout_sec': timeout_sec,
    }
