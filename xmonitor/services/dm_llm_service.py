import random
import re
import time


def normalize_dm_rewrite_signature(text, deps):
    raw = deps.normalize_content_for_dedupe(deps._normalize_text_for_compare(text or ''))
    if not raw:
        return ''
    raw = re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', raw.lower())
    if not raw:
        return ''
    return deps.hashlib.md5(raw.encode('utf-8')).hexdigest()


def build_dm_llm_rewrite_prompt(template_text, deps):
    tpl = str(deps.DM_LLM_REWRITE_PROMPT_TEMPLATE or '').strip() or deps.DM_LLM_REWRITE_DEFAULT_PROMPT
    template_clean = deps._sanitize_dm_message_text(template_text)
    if '{template}' in tpl or '{{template}}' in tpl:
        return tpl.replace('{{template}}', template_clean).replace('{template}', template_clean)
    return f'{tpl}\n模板如下：\n{template_clean}'


def dm_rewrite_longest_common_substring_len(source_text, generated_text, deps):
    src = deps._normalize_text_for_compare(source_text or '')
    dst = deps._normalize_text_for_compare(generated_text or '')
    if not src or not dst:
        return 0
    src = re.sub(r'(工程师)?微信\s*[:：]?\s*[0-9a-zA-Z_-]{4,}', '<contact>', src, flags=re.IGNORECASE)
    dst = re.sub(r'(工程师)?微信\s*[:：]?\s*[0-9a-zA-Z_-]{4,}', '<contact>', dst, flags=re.IGNORECASE)
    src = re.sub(r'\d{6,}', '<num>', src)
    dst = re.sub(r'\d{6,}', '<num>', dst)
    rows = len(src) + 1
    cols = len(dst) + 1
    dp = [0] * cols
    max_len = 0
    for i in range(1, rows):
        prev = 0
        for j in range(1, cols):
            cur = dp[j]
            if src[i - 1] == dst[j - 1]:
                dp[j] = prev + 1
                if dp[j] > max_len:
                    max_len = dp[j]
            else:
                dp[j] = 0
            prev = cur
    return max_len


def extract_dm_rewrite_forbidden_phrases(template_text, deps, max_items=5):
    text = deps._sanitize_dm_message_text(template_text)
    if not text:
        return []
    items = []
    seen = set()
    parts = re.split(r'[，。！？；;,\n]+', text)
    for part in parts:
        item = str(part or '').strip()
        if len(item) < 9 or len(item) > 28:
            continue
        if re.search(r'\d{4,}', item):
            continue
        sig = deps.normalize_content_for_dedupe(item.lower())
        if not sig or sig in seen:
            continue
        seen.add(sig)
        items.append(item)
        if len(items) >= max(1, int(max_items)):
            break
    return items


def dm_rewrite_contains_forbidden_phrase(generated_text, forbidden_phrases, deps):
    if not forbidden_phrases:
        return ''
    dst = deps.normalize_content_for_dedupe(deps._normalize_text_for_compare(generated_text or ''))
    if not dst:
        return ''
    for phrase in forbidden_phrases:
        p = deps.normalize_content_for_dedupe(deps._normalize_text_for_compare(phrase or ''))
        if p and p in dst:
            return phrase
    return ''


def dm_rewrite_similarity_score(source_text, generated_text, deps):
    src = deps._normalize_text_for_compare(source_text or '')
    dst = deps._normalize_text_for_compare(generated_text or '')
    if not src or not dst:
        return 0.0
    try:
        return float(deps.difflib.SequenceMatcher(None, src, dst).ratio())
    except Exception:
        return 0.0


def dm_rewrite_is_too_similar(source_text, generated_text, deps):
    src = deps._normalize_text_for_compare(source_text or '')
    dst = deps._normalize_text_for_compare(generated_text or '')
    if not src or not dst:
        return False, 0.0, 0, 0
    score = dm_rewrite_similarity_score(src, dst, deps)
    diff_chars = abs(len(src) - len(dst))
    shared_run = dm_rewrite_longest_common_substring_len(src, dst, deps)
    if src == dst:
        return True, score, diff_chars, shared_run
    too_similar = (score >= float(deps.DM_LLM_REWRITE_SIMILARITY_MAX)) and (diff_chars < int(deps.DM_LLM_REWRITE_MIN_DIFF_CHARS))
    if shared_run >= int(deps.DM_LLM_REWRITE_MAX_SHARED_RUN) and score >= 0.45:
        too_similar = True
    return bool(too_similar), score, diff_chars, shared_run


def record_dm_llm_rewrite_signature(sig, deps):
    if not sig:
        return
    with deps.dm_llm_rewrite_lock:
        deps.dm_llm_rewrite_history.append(sig)


def is_dm_llm_rewrite_duplicate(sig, deps):
    if not sig:
        return False
    with deps.dm_llm_rewrite_lock:
        return sig in deps.dm_llm_rewrite_history


def generate_dm_text_with_llm(template_text, deps):
    """根据模板生成第二条私信文案（总是生成，失败即返回错误）。"""
    template_clean = deps._sanitize_dm_message_text(template_text)
    if not template_clean:
        return False, '', {
            'error_code': 'E_DM_LLM_TEMPLATE_EMPTY',
            'error_detail': '私信模板为空，无法生成',
            'llm_used': False,
            'latency_ms': 0,
        }
    if not deps._llm_runtime_ready():
        return False, '', {
            'error_code': 'E_DM_LLM_NOT_READY',
            'error_detail': 'LLM模型未就绪，请检查 Base URL 和模型名',
            'llm_used': False,
            'latency_ms': 0,
        }

    prompt = deps._build_dm_llm_rewrite_prompt(template_clean)
    forbidden_phrases = deps._extract_dm_rewrite_forbidden_phrases(template_clean)
    if forbidden_phrases:
        banned = '\n'.join(f'- {x}' for x in forbidden_phrases)
        prompt = f'{prompt}\n\n请避免原样复用下面这些模板短语（可同义改写）：\n{banned}'
    attempts = max(1, int(deps.DM_LLM_REWRITE_MAX_REGEN) + 1)
    last_meta = {
        'error_code': 'E_DM_LLM_GENERATE_FAILED',
        'error_detail': '未知错误',
        'llm_used': True,
        'latency_ms': 0,
    }
    style_hints = [
        '开头不要使用“您好，我是…”，换成自然一点的开场',
        '减少“感谢您的关注和支持”这种固定套话，改成同义表达',
        '一句一意，优先短句，读起来像真人即兴输入',
        '先给价值点，再给联系方式，结尾一句行动建议',
        '语气礼貌但干练，不要出现公文感',
        '保持销售目标明确，但像聊天而不是公告',
    ]

    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            style_hint = random.choice(style_hints)
            result_obj, raw_text = deps._call_openai_compatible_json(
                '你是私信改写助手。只输出JSON，不要输出模板原句。',
                prompt + f'\n\n补充风格要求：{style_hint}。' + '\n请输出JSON：{"text":"改写后的私信正文"}',
                max_tokens=min(512, max(96, int(deps.DM_LLM_REWRITE_MAX_CHARS * 2))),
                timeout_sec=deps.LLM_FILTER_TIMEOUT_SEC,
                temperature=deps.DM_LLM_REWRITE_TEMPERATURE,
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            generated = ''
            if isinstance(result_obj, dict):
                generated = str(result_obj.get('text') or result_obj.get('message') or result_obj.get('content') or '')
            if not generated:
                generated = str(raw_text or '')
            generated = deps._sanitize_dm_message_text(generated)
            if len(generated) > int(deps.DM_LLM_REWRITE_MAX_CHARS):
                generated = generated[: int(deps.DM_LLM_REWRITE_MAX_CHARS)].rstrip()
            if not generated:
                last_meta = {'error_code': 'E_DM_LLM_EMPTY_OUTPUT', 'error_detail': 'LLM返回为空', 'llm_used': True, 'latency_ms': latency_ms}
                continue
            copied_phrase = deps._dm_rewrite_contains_forbidden_phrase(generated, forbidden_phrases)
            if copied_phrase:
                last_meta = {'error_code': 'E_DM_LLM_COPY_PHRASE', 'error_detail': f'命中原句短语复用: {copied_phrase}', 'llm_used': True, 'latency_ms': latency_ms}
                continue
            too_similar, sim_score, diff_chars, shared_run = deps._dm_rewrite_is_too_similar(template_clean, generated)
            if too_similar:
                last_meta = {'error_code': 'E_DM_LLM_TOO_SIMILAR', 'error_detail': f'改写与模板过于相似(sim={sim_score:.3f}, diff={diff_chars}, shared={shared_run})', 'llm_used': True, 'latency_ms': latency_ms}
                continue
            sig = deps._normalize_dm_rewrite_signature(generated)
            if deps._is_dm_llm_rewrite_duplicate(sig):
                last_meta = {'error_code': 'E_DM_LLM_DUPLICATE_TEXT', 'error_detail': f'生成文案命中最近{deps.DM_LLM_REWRITE_DEDUPE_SIZE}条去重窗口', 'llm_used': True, 'latency_ms': latency_ms}
                continue
            deps._record_dm_llm_rewrite_signature(sig)
            return True, generated, {'error_code': '', 'error_detail': '', 'llm_used': True, 'latency_ms': latency_ms, 'regen_attempt': attempt}
        except Exception as e:
            latency_ms = int((time.perf_counter() - started) * 1000)
            err_text = str(e or '').strip()
            err_code = 'E_DM_LLM_GENERATE_FAILED'
            if 'timed out' in err_text.lower():
                err_code = 'E_DM_LLM_TIMEOUT'
            last_meta = {'error_code': err_code, 'error_detail': err_text or 'LLM改写失败', 'llm_used': True, 'latency_ms': latency_ms}

    return False, '', last_meta
