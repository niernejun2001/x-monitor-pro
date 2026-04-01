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
    compact = re.sub(r'\s+', '', unicodedata.normalize('NFKC', text_low))
    consult_hits = find_keyword_hits(text_low, deps.INTENT_CONSULT_KEYWORDS)
    if not consult_hits:
        return False
    product_hits = find_keyword_hits(text_low, deps.INTENT_PRODUCT_KEYWORDS)
    contact_hits = find_keyword_hits(text_low, deps.INTENT_CONTACT_KEYWORDS)
    has_qmark = ('?' in text) or ('？' in text)
    short_consult_phrases = (
        '想了解',
        '了解下',
        '了解一下',
        '咨询下',
        '咨询一下',
        '请教下',
        '请教一下',
        '问下',
        '问一下',
    )
    polite_titles = ('老板', '老闆', '大佬', '佬', '哥', '姐')
    if product_hits:
        return True
    if contact_hits and any(k in text_low for k in ['咨询', '了解', '报价', '价格', '购买', '试用', '部署', '开通', '合作']):
        return True
    if has_qmark and any(k in text_low for k in ['企业版', '私有化', '部署', '试用', '采购', '算力', '性能']):
        return True
    if any(title in compact for title in polite_titles) and any(phrase in compact for phrase in short_consult_phrases):
        return True
    return False
