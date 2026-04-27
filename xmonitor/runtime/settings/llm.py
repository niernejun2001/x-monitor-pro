import re

INTENT_FORCE_NOTIFY_DEFAULT = (
    '询价,报价,多少价格,什么价格,多少钱,怎么卖,怎么买,购买方式,购买,下单,开通,试用,demo,演示,企业版,私有化,部署,合同,发票,开票,授权,代理,经销,渠道,优惠,折扣,售后,客服,联系方式,微信,vx,v我,whatsapp,telegram,算力舱,算力配置,性能,并发,吞吐,能跑多快,能跑多少'
)
INTENT_PRODUCT_DEFAULT = (
    '懒猫微服,lazycat,lazycat.cloud,应用云电脑,云电脑,内网穿透,沙箱隔离,一站式部署,大模型,deepseek,远程桌面,异地组网,家庭服务器,nas,openclaw,算力舱,算力,算力规格,cpu,gpu'
)
INTENT_CONTACT_DEFAULT = '微信,vx,v我,加我,联系我,联系方式,私信,电话,whatsapp,telegram,email,邮箱'
INTENT_CONSULT_DEFAULT = (
    '咨询,了解,介绍,是否支持,支持吗,能否,可以,怎么,如何,多少钱,什么价格,报价,预算,方案,套餐,配置,规格,速度,性能,并发,吞吐,试用,部署,开通,企业版,私有化,交付,售后,发票,合同,采购'
)
INTENT_NON_TARGET_DEFAULT = (
    '互赞,互粉,互关,抽奖,返现,领券,薅羊毛,义乌,压力给到了,压力给到,副厂配件,极影相机,vivo好,发点token,token计费,token耗尽,token烧完,iphone,安卓,诺基亚,fotorgear,手机壳,镜头,掌中宝,v998,338c'
)
NOTIFY_VOICE_BLOCK_KEYWORDS_BUILTIN = (
    '副厂配件',
    '极影相机',
    'vivo好',
    '发点token',
    'token计费',
    'token耗尽',
    'token烧完',
)


def parse_keywords_env(env, env_key, default_text=''):
    raw = str((env or {}).get(env_key, default_text) or default_text or '').strip()
    items = []
    seen = set()
    for part in re.split(r'[\n,，;；]+', raw):
        kw = str(part or '').strip().lower()
        if not kw or kw in seen:
            continue
        seen.add(kw)
        items.append(kw)
    return tuple(items)


def normalize_notify_voice_block_keywords(raw_text, builtin_keywords=NOTIFY_VOICE_BLOCK_KEYWORDS_BUILTIN):
    return tuple(
        dict.fromkeys(
            list(builtin_keywords)
            + [
                kw.strip().lower()
                for kw in re.split(r'[\n,，;；]+', str(raw_text or ''))
                if kw.strip()
            ]
        )
    )


def clamp_llm_timeout(raw_timeout, *, default_timeout, timeout_max):
    try:
        timeout_val = float(raw_timeout)
    except Exception:
        timeout_val = float(default_timeout)
    return max(2.0, min(float(timeout_max), timeout_val))


def load_llm_runtime_settings(env):
    env = env or {}
    timeout_max_raw = env.get('XMONITOR_LLM_TIMEOUT_MAX_SEC', '120')
    try:
        timeout_max = float(timeout_max_raw)
    except Exception:
        timeout_max = 120.0
    timeout_max = max(10.0, min(300.0, float(timeout_max)))

    timeout_raw = env.get('XMONITOR_LLM_TIMEOUT_SEC', '8')
    try:
        timeout_val = float(timeout_raw)
    except Exception:
        timeout_val = 8.0
    timeout_val = clamp_llm_timeout(timeout_val, default_timeout=8.0, timeout_max=timeout_max)

    try:
        cache_ttl_sec = int(env.get('XMONITOR_LLM_CACHE_TTL_SEC', str(6 * 3600)))
    except Exception:
        cache_ttl_sec = 6 * 3600
    try:
        cache_max_entries = int(env.get('XMONITOR_LLM_CACHE_MAX', '5000'))
    except Exception:
        cache_max_entries = 5000
    try:
        retry_count = int(env.get('XMONITOR_LLM_RETRY_COUNT', '2'))
    except Exception:
        retry_count = 2
    retry_count = max(0, min(4, retry_count))
    try:
        retry_backoff_sec = float(env.get('XMONITOR_LLM_RETRY_BACKOFF_SEC', '0.35'))
    except Exception:
        retry_backoff_sec = 0.35
    retry_backoff_sec = max(0.05, min(5.0, retry_backoff_sec))

    notify_voice_block_keywords_text = str(env.get('XMONITOR_NOTIFY_VOICE_BLOCK_KEYWORDS', '') or '').strip()

    return {
        'INTENT_FORCE_NOTIFY_KEYWORDS': parse_keywords_env(env, 'XMONITOR_INTENT_FORCE_NOTIFY_KEYWORDS', INTENT_FORCE_NOTIFY_DEFAULT),
        'INTENT_PRODUCT_KEYWORDS': parse_keywords_env(env, 'XMONITOR_INTENT_PRODUCT_KEYWORDS', INTENT_PRODUCT_DEFAULT),
        'INTENT_CONTACT_KEYWORDS': parse_keywords_env(env, 'XMONITOR_INTENT_CONTACT_KEYWORDS', INTENT_CONTACT_DEFAULT),
        'INTENT_CONSULT_KEYWORDS': parse_keywords_env(env, 'XMONITOR_INTENT_CONSULT_KEYWORDS', INTENT_CONSULT_DEFAULT),
        'INTENT_NON_TARGET_TOPIC_KEYWORDS': parse_keywords_env(env, 'XMONITOR_INTENT_NON_TARGET_TOPIC_KEYWORDS', INTENT_NON_TARGET_DEFAULT),
        'INTENT_LLM_PRIMARY_MODE': str(env.get('XMONITOR_INTENT_LLM_PRIMARY_MODE', '1') or '').strip().lower() in {'1', 'true', 'yes', 'on'},
        'LLM_FILTER_ENABLED': str(env.get('XMONITOR_LLM_FILTER_ENABLED', '0') or '').strip().lower() in {'1', 'true', 'yes', 'on'},
        'LLM_FILTER_BASE_URL': str(env.get('XMONITOR_LLM_BASE_URL', '') or '').strip(),
        'LLM_FILTER_API_KEY': str(env.get('XMONITOR_LLM_API_KEY', 'EMPTY') or '').strip(),
        'LLM_FILTER_MODEL': str(env.get('XMONITOR_LLM_MODEL', '') or '').strip(),
        'LLM_FILTER_PROMPT_TEMPLATE': str(env.get('XMONITOR_LLM_FILTER_PROMPT_TEMPLATE', '') or '').strip(),
        'LLM_INTENT_PROMPT_TEMPLATE': str(env.get('XMONITOR_LLM_INTENT_PROMPT_TEMPLATE', '') or '').strip(),
        'NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT': notify_voice_block_keywords_text,
        'NOTIFY_VOICE_BLOCK_KEYWORDS_BUILTIN': NOTIFY_VOICE_BLOCK_KEYWORDS_BUILTIN,
        'NOTIFY_VOICE_BLOCK_KEYWORDS': normalize_notify_voice_block_keywords(notify_voice_block_keywords_text),
        'LLM_FILTER_TIMEOUT_SEC': timeout_val,
        'LLM_FILTER_TIMEOUT_MAX_SEC': timeout_max,
        'LLM_FILTER_RETRY_COUNT': retry_count,
        'LLM_FILTER_RETRY_BACKOFF_SEC': retry_backoff_sec,
        'LLM_FILTER_CACHE_TTL_SEC': cache_ttl_sec,
        'LLM_FILTER_CACHE_MAX_ENTRIES': cache_max_entries,
        'LLM_HARD_FILTER_ENABLED': str(env.get('XMONITOR_LLM_HARD_FILTER_ENABLED', '0') or '').strip().lower() in {'1', 'true', 'yes', 'on'},
    }
