import json
import re
import urllib.error
import urllib.request


def parse_json_object_from_text(raw_text):
    text = str(raw_text or '').strip()
    if not text:
        return {}
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict):
                return obj
        except Exception:
            return {}
    return {}


def guess_ollama_native_endpoint(base_url, deps):
    base = str(base_url or deps.LLM_FILTER_BASE_URL or '').strip().rstrip('/')
    if not base:
        return ''
    if base.endswith('/v1/chat/completions'):
        base = base[:-len('/v1/chat/completions')]
    elif base.endswith('/chat/completions'):
        base = base[:-len('/chat/completions')]
    elif base.endswith('/v1'):
        base = base[:-len('/v1')]
    return f'{base}/api/chat'


def call_ollama_native_json(system_prompt, user_prompt, deps, *, base_url=None, model=None, timeout_sec=None):
    endpoint = guess_ollama_native_endpoint(base_url, deps)
    model_name = str(model if model is not None else deps.LLM_FILTER_MODEL or '').strip()
    if not endpoint:
        raise ValueError('Ollama endpoint 未配置')
    if not model_name:
        raise ValueError('LLM 模型名未配置')

    timeout_val = deps.clamp_llm_timeout(timeout_sec if timeout_sec is not None else deps.LLM_FILTER_TIMEOUT_SEC)
    payload = {
        'model': model_name,
        'stream': False,
        'format': 'json',
        'messages': [
            {'role': 'system', 'content': str(system_prompt or '').strip()},
            {'role': 'user', 'content': str(user_prompt or '').strip()},
        ],
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout_val) as resp:
        raw_resp = resp.read().decode('utf-8', errors='ignore')

    data = json.loads(raw_resp or '{}')
    msg = data.get('message') or {}
    content_text = str(msg.get('content') or '')
    return parse_json_object_from_text(content_text), content_text


def call_openai_compatible_json(
    system_prompt,
    user_prompt,
    deps,
    *,
    base_url=None,
    api_key=None,
    model=None,
    timeout_sec=None,
    max_tokens=120,
    temperature=0.0,
):
    endpoint = deps._llm_filter_endpoint(base_url=base_url)
    model_name = str(model if model is not None else deps.LLM_FILTER_MODEL or '').strip()
    if not endpoint:
        raise ValueError('LLM Base URL 未配置')
    if not model_name:
        raise ValueError('LLM 模型名未配置')

    api_key_val = str(api_key if api_key is not None else deps.LLM_FILTER_API_KEY or 'EMPTY').strip() or 'EMPTY'
    timeout_val = deps.clamp_llm_timeout(timeout_sec if timeout_sec is not None else deps.LLM_FILTER_TIMEOUT_SEC)

    base_payload = {
        'model': model_name,
        'temperature': max(0.0, min(1.2, float(temperature))),
        'max_tokens': int(max(32, min(512, int(max_tokens)))),
        'messages': [
            {'role': 'system', 'content': str(system_prompt or '').strip()},
            {'role': 'user', 'content': str(user_prompt or '').strip()},
        ],
    }
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key_val}',
    }

    data = {}
    last_err = None
    last_err_body = ''
    payload_variants = [
        {**base_payload, 'response_format': {'type': 'json_object'}},
        dict(base_payload),
    ]
    for payload in payload_variants:
        try:
            body = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(endpoint, data=body, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=timeout_val) as resp:
                raw_resp = resp.read().decode('utf-8', errors='ignore')
            data = json.loads(raw_resp or '{}')
            last_err = None
            break
        except urllib.error.HTTPError as e:
            last_err = e
            try:
                last_err_body = e.read().decode('utf-8', errors='ignore')
            except Exception:
                last_err_body = ''
            continue

    if last_err is not None and not data:
        fallback_allowed = (
            int(getattr(last_err, 'code', 0) or 0) == 404
            or ('404 page not found' in str(last_err_body or '').lower())
        )
        if fallback_allowed:
            native_obj, native_raw = call_ollama_native_json(
                system_prompt,
                user_prompt,
                deps,
                base_url=base_url,
                model=model_name,
                timeout_sec=timeout_val,
            )
            return native_obj, native_raw

        err_text = f"HTTP {getattr(last_err, 'code', 'error')}"
        if last_err_body:
            err_text = f'{err_text}: {last_err_body[:220]}'
        raise RuntimeError(err_text)

    content_text = ''
    try:
        choices = data.get('choices') or []
        if choices:
            message = choices[0].get('message') or {}
            content_text = str(message.get('content') or '')
    except Exception:
        content_text = ''

    return parse_json_object_from_text(content_text), content_text


def call_openai_compatible_filter_api(content, deps):
    default_prompt = (
        '你是评论过滤器。只输出JSON对象，不要输出其他文本。\n'
        '返回字段: skip(boolean), reason(string), intent_score(number 0-100)。\n'
        '规则:\n'
        '1) 只有在明显垃圾内容、纯表情或完全无意义字符时，才返回 skip=true。\n'
        '2) 其他情况统一返回 skip=false。\n'
        '3) reason 使用简短英文下划线词，例如 normal/spam/emoji_or_noise。\n'
        f'评论内容: {content}'
    )
    prompt = deps._render_llm_prompt_template(
        deps.LLM_FILTER_PROMPT_TEMPLATE,
        content,
        default_prompt,
    )
    result_obj, _ = call_openai_compatible_json(
        'You are a strict JSON classifier.',
        prompt,
        deps,
        max_tokens=80,
    )
    if not isinstance(result_obj, dict) or not result_obj:
        return False, ''

    skip_raw = result_obj.get('skip', False)
    if isinstance(skip_raw, str):
        skip = skip_raw.strip().lower() in {'1', 'true', 'yes', 'y'}
    else:
        skip = bool(skip_raw)
    reason = str(result_obj.get('reason', '') or '').strip().lower()
    if skip and not reason:
        reason = 'llm_filter'
    return skip, reason
