import re
import unicodedata


def is_negative_intent_reason(reason_text):
    """根据判定理由识别明显负向（非购买/噪声）语义。"""
    txt = str(reason_text or '').strip().lower()
    if not txt:
        return False
    negative_keywords = [
        'noise',
        'low',
        '噪声',
        '无意向',
        '无购买',
        '非购买',
        '无关',
        '不相关',
        '闲聊',
        '灌水',
        '段子',
        '调侃',
        '吐槽',
        '副厂配件',
        '极影相机',
        '手机壳',
        'fotorgear',
    ]
    return any(keyword in txt for keyword in negative_keywords)


def find_keyword_hits(text_lower, keywords):
    hits = []
    src = str(text_lower or '').lower()
    if not src:
        return hits
    for kw in keywords:
        kw_norm = str(kw or '').strip().lower()
        if kw_norm and kw_norm in src and kw_norm not in hits:
            hits.append(kw_norm)
    return hits


def is_short_reply_intent_signal(content):
    raw = str(content or '').strip()
    if not raw:
        return False
    norm = unicodedata.normalize('NFKC', raw).lower()
    compact = re.sub(r'\s+', '', norm)
    compact = compact.replace('＋', '+')
    if re.fullmatch(r'1{1,4}', compact):
        return True
    if re.fullmatch(r'\+1{1,4}', compact):
        return True
    if re.fullmatch(r'扣1{1,4}', compact) or compact == '扣一':
        return True
    return False


def is_performance_consult_signal(content):
    raw = str(content or '').strip()
    if not raw:
        return False
    norm = unicodedata.normalize('NFKC', raw).lower()
    compact = re.sub(r'\s+', '', norm)
    if not compact:
        return False
    intent_anchor = any(k in compact for k in ['算力舱', '算力仓', '算力', '配置', '规格', '机型', 'cpu', 'gpu'])
    perf_anchor = any(k in compact for k in ['速度', '性能', '跑', '并发', '吞吐', '延迟', '带宽'])
    ask_anchor = ('?' in norm) or ('？' in raw) or any(k in compact for k in ['多少', '几个', '能跑', '多快', '怎样', '怎么'])
    return bool((intent_anchor and perf_anchor) or (intent_anchor and ask_anchor))


def is_non_business_meme_signal(content):
    raw = str(content or '').strip()
    if not raw:
        return False
    norm = unicodedata.normalize('NFKC', raw).lower()
    compact = re.sub(r'\s+', '', norm)
    if not compact:
        return False
    business_anchors = ['懒猫', 'lazycat', '微服', '算力舱', '云电脑', '内网穿透', '沙箱', 'openclaw', '私有化', '部署']
    has_business_context = any(k in compact for k in business_anchors)
    has_business_question = any(
        k in compact for k in ['咨询', '了解', '购买', '报价', '价格', '多少钱', '试用', '部署', '合同', '发票', '联系', '怎么', '如何', '支持']
    )
    hard_meme_patterns = ['压力给到了义乌', '压力给到义乌', '压力给到了', '压力给到']
    if any(p in compact for p in hard_meme_patterns):
        return True
    consumer_patterns = ['副厂配件', '极影相机', 'vivo好', 'iphone', '安卓', '诺基亚', 'fotorgear', '手机壳', '镜头', '掌中宝', 'v998', '338c']
    if any(p in compact for p in consumer_patterns) and not (has_business_context and has_business_question):
        return True
    if 'token' in compact and any(k in compact for k in ['vivo', '发点', '计费', '烧完', '耗尽', '星期几', '问天气']):
        if has_business_context and has_business_question:
            return False
        return True
    return False


def is_business_consult_signal(content, deps):
    text = deps._normalize_content_for_filter(content)
    if not text:
        return False
    text_low = text.lower()
    consult_hits = find_keyword_hits(text_low, deps.INTENT_CONSULT_KEYWORDS)
    if not consult_hits:
        return False
    product_hits = find_keyword_hits(text_low, deps.INTENT_PRODUCT_KEYWORDS)
    contact_hits = find_keyword_hits(text_low, deps.INTENT_CONTACT_KEYWORDS)
    has_qmark = ('?' in text) or ('？' in text)
    if product_hits:
        return True
    if contact_hits and any(k in text_low for k in ['咨询', '了解', '报价', '价格', '购买', '试用', '部署', '开通', '合作']):
        return True
    if has_qmark and any(k in text_low for k in ['企业版', '私有化', '部署', '试用', '采购', '算力', '性能']):
        return True
    return False


def build_intent_analysis_prompt(content, deps):
    default_prompt = (
        '你是销售线索意向识别器。请严格输出JSON对象，不要输出任何解释文本。\n'
        '字段:\n'
        '- intent_score: 0-100\n'
        '- intent_level: high|medium|low|noise\n'
        '- is_intent_user: true/false\n'
        '- force_notify: true/false\n'
        '- buying_signals: string[]\n'
        '- reason: string\n\n'
        '业务背景（来自 lazycat.cloud 官网）:\n'
        '懒猫微服（LazyCat）提供应用云电脑、内网穿透、沙箱隔离、一站式部署（含大模型部署）等能力，主打按需付费。\n'
        '常见购买场景包括：询价/报价、套餐选择、试用开通、企业或教育部署、售后与续费咨询。\n\n'
        '判定原则(销售线索优先):\n'
        '1) 明确购买/询价/报价/价格/下单/试用/部署/联系方式咨询（微信/vx/whatsapp）=> medium/high。\n'
        '2) 仅情绪表达、闲聊、纯表情、无意义灌水 => low/noise。\n'
        '2.1) 网络梗/段子（例如“压力给到了义乌”）按无业务相关处理，判定 noise。\n'
        '2.2) 对 token 计费的吐槽、手机品牌讨论（如 vivo）、副厂配件/极影相机等非购买讨论，判定 noise。\n'
        '2.3) 手机/数码消费品讨论（如 iPhone/安卓/诺基亚/Fotorgear/掌中宝/v998/338c/镜头/手机壳），即使出现价格词，也判定 noise。\n'
        '3) 出现“多少钱/什么价格/怎么买/购买方式/开票/合同/授权/代理/优惠”等词时，提高意向分。\n'
        '4) “1/11/111/+1/扣1”这类短回复在“回复你”通知中通常代表愿意沟通，至少判为 medium。\n'
        '5) force_notify 在强意向线索时设为 true（询价、采购、留联系方式、明确要买/试用/部署）。\n'
        '6) 若涉及本产品功能/性能/部署/试用等咨询但信息不完整，宁可判为 medium，也不要判 low/noise。\n'
        f'评论内容: {content}'
    )
    return deps._render_llm_prompt_template(deps.LLM_INTENT_PROMPT_TEMPLATE, content, default_prompt)


def should_notify_voice_by_intent(analysis):
    """语音播报门槛：低意向/噪声不播报，强意向或中高分才播报。"""
    if not isinstance(analysis, dict):
        return False
    score = 0
    try:
        score = int(float(analysis.get('intent_score', 0)))
    except Exception:
        score = 0
    score = max(0, min(100, score))
    level = str(analysis.get('intent_level', '') or '').strip().lower()
    is_intent_user = bool(analysis.get('is_intent_user', False))
    force_notify = bool(analysis.get('force_notify', False))
    block_intent = bool(analysis.get('block_intent', False))
    if block_intent:
        return False
    if force_notify:
        return True
    if level in {'low', 'noise'}:
        return False
    return bool(is_intent_user and score >= 55)


def rule_based_intent_analysis(content, deps):
    text = deps._normalize_content_for_filter(content)
    if not text:
        return {'intent_score': 0, 'intent_level': 'noise', 'signals': ['empty_content'], 'force_notify': False, 'block_intent': False, 'force_keywords': [], 'non_target_keywords': []}
    if deps._is_emoji_only_content(text):
        return {'intent_score': 5, 'intent_level': 'noise', 'signals': ['emoji_only'], 'force_notify': False, 'block_intent': False, 'force_keywords': [], 'non_target_keywords': []}
    if deps._is_short_reply_intent_signal(text):
        return {'intent_score': 62, 'intent_level': 'medium', 'signals': ['short_reply_intent_signal'], 'force_notify': True, 'block_intent': False, 'force_keywords': ['short_reply_signal'], 'non_target_keywords': []}
    if deps._is_performance_consult_signal(text):
        return {'intent_score': 72, 'intent_level': 'medium', 'signals': ['performance_consult_signal'], 'force_notify': True, 'block_intent': False, 'force_keywords': ['performance_consult'], 'non_target_keywords': []}
    if deps._is_business_consult_signal(text):
        return {'intent_score': 68, 'intent_level': 'medium', 'signals': ['business_consult_signal'], 'force_notify': True, 'block_intent': False, 'force_keywords': ['business_consult'], 'non_target_keywords': []}
    if deps._is_non_business_meme_signal(text):
        return {'intent_score': 8, 'intent_level': 'noise', 'signals': ['non_business_meme_signal'], 'force_notify': False, 'block_intent': True, 'force_keywords': [], 'non_target_keywords': ['meme']}

    text_low = text.lower()
    force_hits = deps._find_keyword_hits(text_low, deps.INTENT_FORCE_NOTIFY_KEYWORDS)
    product_hits = deps._find_keyword_hits(text_low, deps.INTENT_PRODUCT_KEYWORDS)
    contact_hits = deps._find_keyword_hits(text_low, deps.INTENT_CONTACT_KEYWORDS)
    consult_hits = deps._find_keyword_hits(text_low, deps.INTENT_CONSULT_KEYWORDS)
    non_target_hits = deps._find_keyword_hits(text_low, deps.INTENT_NON_TARGET_TOPIC_KEYWORDS)

    text_len = len(text)
    if text_len <= 2:
        score = 15
        signals = ['very_short_text']
    elif text_len <= 6:
        score = 25
        signals = ['short_text']
    elif text_len <= 20:
        score = 35
        signals = ['normal_text']
    else:
        score = 45
        signals = ['long_text']

    force_notify = False
    block_intent = False
    if force_hits:
        score = max(score, 74 if len(force_hits) == 1 else 82)
        force_notify = True
        signals.append('force_intent_keyword')
    if product_hits:
        score += min(15, 5 * len(product_hits))
        signals.append('product_keyword')
    if contact_hits:
        score += min(14, 7 * len(contact_hits))
        signals.append('contact_keyword')
    if consult_hits and product_hits:
        score = max(score, 58)
        force_notify = True
        signals.append('product_consult_signal')
    if product_hits and contact_hits:
        score = max(score, 68)
        force_notify = True
        signals.append('product_contact_combo')
    if non_target_hits and not force_hits and not (product_hits and contact_hits):
        score = min(score, 24)
        block_intent = True
        signals.append('non_target_topic')
    elif non_target_hits and not product_hits:
        score = min(score, 18)
        force_notify = False
        block_intent = True
        signals.append('non_target_consumer_topic')

    score = max(0, min(100, int(score)))
    level = deps._score_to_intent_level(score)
    return {
        'intent_score': score,
        'intent_level': level,
        'signals': list(dict.fromkeys(signals))[:10],
        'force_notify': bool(force_notify),
        'block_intent': bool(block_intent),
        'force_keywords': list(force_hits)[:8],
        'non_target_keywords': list(non_target_hits)[:8],
    }


def llm_intent_analysis(content, deps, *, base_url=None, api_key=None, model=None, timeout_sec=None):
    prompt = deps._build_intent_analysis_prompt(content)
    result_obj, _ = deps._call_openai_compatible_json(
        'You are a strict JSON intent classifier.',
        prompt,
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_sec=timeout_sec,
        max_tokens=180,
    )
    if not isinstance(result_obj, dict) or not result_obj:
        return None
    try:
        score = int(float(result_obj.get('intent_score', 0)))
    except Exception:
        score = 0
    score = max(0, min(100, score))
    level = str(result_obj.get('intent_level', '') or '').strip().lower()
    if level not in {'high', 'medium', 'low', 'noise'}:
        level = deps._score_to_intent_level(score)
    is_intent_user = result_obj.get('is_intent_user', None)
    if isinstance(is_intent_user, str):
        is_intent_user = is_intent_user.strip().lower() in {'1', 'true', 'yes', 'y'}
    elif is_intent_user is None:
        is_intent_user = score >= 50
    else:
        is_intent_user = bool(is_intent_user)
    raw_signals = result_obj.get('buying_signals', [])
    if not isinstance(raw_signals, list):
        raw_signals = [raw_signals] if raw_signals else []
    buying_signals = [str(x).strip() for x in raw_signals if str(x).strip()][:8]
    reason = str(result_obj.get('reason', '') or '').strip()
    force_notify_raw = result_obj.get('force_notify', False)
    if isinstance(force_notify_raw, str):
        force_notify = force_notify_raw.strip().lower() in {'1', 'true', 'yes', 'y'}
    else:
        force_notify = bool(force_notify_raw)
    if level in {'noise', 'low'}:
        score = min(score, 24 if level == 'noise' else 45)
        if score < 50:
            is_intent_user = False
        force_notify = False
    if deps._is_negative_intent_reason(reason):
        score = min(score, 30)
        level = 'noise' if level == 'noise' else 'low'
        is_intent_user = False
        force_notify = False
    return {
        'intent_score': score,
        'intent_level': level,
        'is_intent_user': bool(is_intent_user),
        'force_notify': bool(force_notify),
        'buying_signals': buying_signals,
        'reason': reason,
    }


def analyze_comment_intent(content, deps, *, base_url=None, api_key=None, model=None, timeout_sec=None):
    _normalize_content_for_filter = deps._normalize_content_for_filter
    _normalize_one_line = deps._normalize_one_line
    log_to_ui = deps.log_to_ui
    _llm_runtime_ready = deps._llm_runtime_ready
    _is_negative_intent_reason = deps._is_negative_intent_reason
    INTENT_LLM_PRIMARY_MODE = deps.INTENT_LLM_PRIMARY_MODE
    _score_to_intent_level = deps._score_to_intent_level
    _intent_level_rank = deps._intent_level_rank
    _max_intent_level = deps._max_intent_level
    text = _normalize_content_for_filter(content)
    rule_result = rule_based_intent_analysis(text, deps)
    rule_score = int(rule_result.get('intent_score', 0))
    rule_level = str(rule_result.get('intent_level', 'noise'))
    rule_signals = list(rule_result.get('signals', []))
    rule_force_notify = bool(rule_result.get('force_notify', False))
    rule_block_intent = bool(rule_result.get('block_intent', False))

    result = {
        'content': text,
        'intent_score': rule_score,
        'intent_level': rule_level,
        'is_intent_user': bool(rule_force_notify or rule_score >= 55),
        'force_notify': bool(rule_force_notify),
        'block_intent': bool(rule_block_intent),
        'signals': list(rule_signals),
        'reason': 'rule_only',
        'rule_score': rule_score,
        'rule_level': rule_level,
        'rule_force_notify': bool(rule_force_notify),
        'rule_force_keywords': list(rule_result.get('force_keywords', [])),
        'rule_non_target_keywords': list(rule_result.get('non_target_keywords', [])),
        'llm_used': False,
        'llm_score': None,
        'llm_level': '',
        'llm_reason': '',
        'llm_error': '',
    }
    preview = _normalize_one_line(text, 120) if text else ''
    log_to_ui('debug', f'🤖 [Intent] analyze_start len={len(text)} rule_score={rule_score} text={preview}')
    if not _llm_runtime_ready(base_url=base_url, model=model):
        log_to_ui('debug', '🤖 [Intent] llm_skip runtime_not_ready -> rule_only')
        return result
    try:
        llm_result = llm_intent_analysis(text, deps, base_url=base_url, api_key=api_key, model=model, timeout_sec=timeout_sec)
        if not llm_result:
            log_to_ui('debug', '🤖 [Intent] llm_empty_result -> rule_only')
            return result
    except Exception as e:
        result['llm_error'] = str(e)
        log_to_ui('warn', f'🤖 [Intent] llm_error: {e}')
        return result

    llm_score = int(llm_result.get('intent_score', 0))
    llm_level = str(llm_result.get('intent_level', 'noise'))
    llm_reason = str(llm_result.get('reason', '') or '').strip()
    llm_signals = list(llm_result.get('buying_signals', []))
    llm_force_notify = bool(llm_result.get('force_notify', False))
    llm_is_intent_user = bool(llm_result.get('is_intent_user', False))
    llm_reason_negative = _is_negative_intent_reason(llm_reason)

    if INTENT_LLM_PRIMARY_MODE:
        hard_rule_force = 'short_reply_intent_signal' in set(rule_signals)
        hard_rule_block = 'non_business_meme_signal' in set(rule_signals)
        final_score = max(0, min(100, int(llm_score)))
        final_level = str(llm_level or '').strip().lower()
        if final_level not in {'high', 'medium', 'low', 'noise'}:
            final_level = _score_to_intent_level(final_score)
        final_force_notify = bool(llm_force_notify)
        final_is_intent = bool(llm_is_intent_user or final_force_notify or (final_score >= 60 and _intent_level_rank(final_level) >= _intent_level_rank('medium')))
        final_block = bool(hard_rule_block)
        if llm_reason_negative or final_level in {'low', 'noise'}:
            cap = 30 if final_level == 'noise' else 45
            final_score = min(final_score, cap)
            final_level = _score_to_intent_level(final_score)
            final_is_intent = False
            final_force_notify = False
            if _intent_level_rank(final_level) <= _intent_level_rank('low'):
                final_block = True
        if hard_rule_force:
            final_score = max(final_score, 62)
            final_level = _max_intent_level(final_level, 'medium')
            final_is_intent = True
            final_force_notify = True
            final_block = False
        merged_signals = []
        for sig in (rule_signals + llm_signals):
            sig_text = str(sig).strip()
            if sig_text and sig_text not in merged_signals:
                merged_signals.append(sig_text)
        if llm_reason_negative and 'llm_negative_reason' not in merged_signals:
            merged_signals.append('llm_negative_reason')
        result.update({
            'intent_score': int(final_score),
            'intent_level': str(final_level),
            'is_intent_user': bool(final_is_intent),
            'force_notify': bool(final_force_notify),
            'block_intent': bool(final_block),
            'signals': merged_signals[:12],
            'reason': llm_reason or 'llm_primary',
            'llm_used': True,
            'llm_score': llm_score,
            'llm_level': llm_level,
            'llm_reason': llm_reason,
        })
        log_to_ui('debug', f"🤖 [Intent] llm_primary score={result['intent_score']} level={result['intent_level']} intent={result['is_intent_user']} force={result['force_notify']} block={result.get('block_intent', False)} rule={rule_score} llm={llm_score}/{llm_level} reason={result['reason'] or '-'}")
        return result

    llm_positive = bool((not llm_reason_negative) and (llm_force_notify or (llm_is_intent_user and llm_score >= 55) or _intent_level_rank(llm_level) >= _intent_level_rank('medium') or bool(llm_signals)))
    llm_weight = 0.65 if llm_positive else 0.20
    llm_score_for_blend = llm_score if llm_positive else min(llm_score, 45)
    blended_score = int(round(max(rule_score, (rule_score * (1.0 - llm_weight) + llm_score_for_blend * llm_weight))))
    if (not llm_positive) and _intent_level_rank(llm_level) <= _intent_level_rank('low') and rule_score < 55:
        blended_score = min(blended_score, 49)
    blended_score = max(0, min(100, blended_score))
    score_level = _score_to_intent_level(blended_score)
    llm_intent_hint = bool((not llm_reason_negative) and llm_is_intent_user and llm_score >= 55 and (_intent_level_rank(llm_level) >= _intent_level_rank('medium') or llm_force_notify or bool(llm_signals)))
    blended_force_notify = bool(rule_force_notify or llm_force_notify or llm_intent_hint)
    if blended_force_notify:
        blended_score = max(blended_score, 55)
        score_level = _score_to_intent_level(blended_score)
    blended_level = _max_intent_level(score_level, rule_level, llm_level)
    merged_signals = []
    for sig in (rule_signals + llm_signals):
        sig_text = str(sig).strip()
        if sig_text and sig_text not in merged_signals:
            merged_signals.append(sig_text)
    result.update({
        'intent_score': blended_score,
        'intent_level': blended_level,
        'is_intent_user': bool(blended_score >= 55 or llm_intent_hint or blended_force_notify),
        'force_notify': bool(blended_force_notify),
        'signals': merged_signals[:12],
        'reason': llm_reason or 'rule_llm_blended',
        'llm_used': True,
        'llm_score': llm_score,
        'llm_level': llm_level,
        'llm_reason': llm_reason,
    })
    if rule_block_intent:
        blocked_score = min(int(result.get('intent_score', 0) or 0), 18)
        blocked_level = _score_to_intent_level(blocked_score)
        blocked_signals = list(result.get('signals', []))
        if 'rule_block_intent' not in blocked_signals:
            blocked_signals.append('rule_block_intent')
        result.update({'intent_score': blocked_score, 'intent_level': blocked_level, 'is_intent_user': False, 'force_notify': False, 'block_intent': True, 'signals': blocked_signals[:12]})
    if (not rule_force_notify) and llm_reason_negative and _intent_level_rank(llm_level) <= _intent_level_rank('low'):
        blocked_score = min(int(result.get('intent_score', 0) or 0), 30)
        blocked_signals = list(result.get('signals', []))
        if 'llm_negative_reason' not in blocked_signals:
            blocked_signals.append('llm_negative_reason')
        result.update({'intent_score': blocked_score, 'intent_level': _score_to_intent_level(blocked_score), 'is_intent_user': False, 'force_notify': False, 'block_intent': True, 'signals': blocked_signals[:12]})
    log_to_ui('debug', f"🤖 [Intent] llm_done score={result['intent_score']} level={result['intent_level']} intent={result['is_intent_user']} force={result['force_notify']} block={result.get('block_intent', False)} rule={rule_score} llm={llm_score}/{llm_level} llm_intent={llm_is_intent_user} hint={llm_intent_hint} reason={result['reason'] or '-'}")
    return result
