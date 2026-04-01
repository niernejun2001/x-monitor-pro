import random
import re
import time


def _normalize_protected_literal(literal, kind, deps):
    text = str(literal or '').strip()
    if not text:
        return ''
    if kind == 'long_num':
        return re.sub(r'\D+', '', text)
    return deps._normalize_text_for_compare(text)


def extract_dm_rewrite_protected_literals(template_text, deps, max_items=16):
    text = deps._sanitize_dm_message_text(template_text)
    if not text:
        return []
    items = []
    seen = set()
    patterns = (
        ('url', r'https?://[^\s]+'),
        ('email', r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}'),
        ('long_num', r'(?<!\d)\d{6,}(?!\d)'),
    )
    for kind, pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            literal = str(match.group(0) or '').strip().strip('，。！？；;,')
            norm = _normalize_protected_literal(literal, kind, deps)
            key = (kind, norm)
            if not norm or key in seen:
                continue
            seen.add(key)
            items.append({'kind': kind, 'literal': literal, 'norm': norm})
            if len(items) >= max(1, int(max_items)):
                return items
    return items


def dm_rewrite_missing_protected_literal(generated_text, protected_literals, deps):
    if not protected_literals:
        return None
    generated = str(generated_text or '')
    for item in protected_literals:
        kind = str(item.get('kind', '') or '').strip()
        literal = str(item.get('literal', '') or '').strip()
        norm = str(item.get('norm', '') or '').strip()
        if not kind or not literal or not norm:
            continue
        generated_norm = _normalize_protected_literal(generated, kind, deps)
        if kind == 'long_num':
            if norm not in generated_norm:
                return item
            continue
        if norm not in generated_norm:
            return item
    return None


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
    generic_phrases = (
        '感谢您的关注',
        '感谢您的关注与支持',
        '感谢您关注我们',
        '感谢您对我们的关注',
        '欢迎添加',
        '欢迎联系',
        '一对一介绍',
        '购买方式',
        '备注推特id',
        '给您优惠',
        '可享优惠',
    )
    parts = re.split(r'[，。！？；;,\n]+', text)
    for part in parts:
        item = str(part or '').strip()
        if len(item) < 9 or len(item) > 28:
            continue
        if re.search(r'\d{4,}', item):
            continue
        item_low = item.lower()
        if any(phrase in item_low for phrase in generic_phrases):
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


def dm_rewrite_has_subject_inversion(source_text, generated_text, deps):
    src = deps._normalize_text_for_compare(source_text or '')
    dst = deps._normalize_text_for_compare(generated_text or '')
    if not src or not dst:
        return False, ''

    patterns = [
        (
            ['看您有在关注我们的产品', '您有在关注我们的产品', '您在关注我们的产品'],
            ['我在看你们的产品', '最近在看你们的产品', '我最近在看你们的产品'],
            'user_interest_inverted_to_self_interest',
        ),
        (
            ['咱们的产品', '我们的产品'],
            ['你们的产品'],
            'our_product_inverted_to_your_product',
        ),
    ]
    for src_tokens, dst_tokens, reason in patterns:
        if any(token in src for token in src_tokens) and any(token in dst for token in dst_tokens):
            return True, reason
    return False, ''


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
    protected_literals = extract_dm_rewrite_protected_literals(template_clean, deps)
    if forbidden_phrases:
        banned = '\n'.join(f'- {x}' for x in forbidden_phrases)
        prompt = f'{prompt}\n\n请避免原样复用下面这些模板短语（可同义改写）：\n{banned}'
    if protected_literals:
        protected_text = '\n'.join(f"- {item['literal']}" for item in protected_literals)
        prompt = (
            f'{prompt}\n\n'
            '下面这些联系方式/链接/邮箱/数字串必须逐字保持不变，不能改动任何一个字符，也不能替换、删减、补位：\n'
            f'{protected_text}'
        )
    attempts = max(1, int(deps.DM_LLM_REWRITE_MAX_REGEN) + 1)
    last_meta = {
        'error_code': 'E_DM_LLM_GENERATE_FAILED',
        'error_detail': '未知错误',
        'llm_used': True,
        'latency_ms': 0,
    }
    style_hints = [
        '优先保留原句结构，只做轻微顺句和润色',
        '保留原有主句和表达方向，只微调少数字词',
        '尽量不要整段重写，像人工顺一遍句子即可',
        '保持礼貌自然，但不要增加新的意思',
        '允许保留大部分原句，只修语气和流畅度',
        '避免夸张语气词，控制在轻度改写范围内',
        '在不改变联系方式和购买引导的前提下，可适度调整开场和结尾表达',
        '保持核心信息不变，但尽量换一种更自然的说法，避免每次都像同一段模板',
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
            missing_literal = dm_rewrite_missing_protected_literal(generated, protected_literals, deps)
            if missing_literal:
                last_meta = {
                    'error_code': 'E_DM_LLM_PROTECTED_LITERAL_CHANGED',
                    'error_detail': f"受保护字面量被改动: {missing_literal.get('literal', '')}",
                    'llm_used': True,
                    'latency_ms': latency_ms,
                }
                continue
            inverted, inversion_reason = dm_rewrite_has_subject_inversion(template_clean, generated, deps)
            if inverted:
                last_meta = {
                    'error_code': 'E_DM_LLM_SUBJECT_INVERTED',
                    'error_detail': f'改写出现主语/对象反转: {inversion_reason}',
                    'llm_used': True,
                    'latency_ms': latency_ms,
                }
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
