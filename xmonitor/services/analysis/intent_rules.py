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
