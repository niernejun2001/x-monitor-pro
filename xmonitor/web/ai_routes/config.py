from collections import deque

from flask import jsonify, request


def register_config_routes(app, deps):
    @app.route('/api/set_llm_filter_config', methods=['POST'])
    def set_llm_filter_config():
        payload = request.get_json(silent=True) or {}
        enabled = bool(payload.get('enabled', False))
        base_url = str(payload.get('base_url', '') or '').strip()
        api_key = str(payload.get('api_key', deps.LLM_FILTER_API_KEY) or '').strip() if ('api_key' in payload) else str(deps.LLM_FILTER_API_KEY or '').strip()
        model = str(payload.get('model', '') or '').strip()
        filter_prompt_template = str(payload.get('llm_filter_prompt_template', deps.LLM_FILTER_PROMPT_TEMPLATE) or '').strip()
        intent_prompt_template = str(payload.get('llm_intent_prompt_template', deps.LLM_INTENT_PROMPT_TEMPLATE) or '').strip()
        notify_voice_block_keywords_text = str(payload.get('notify_voice_block_keywords_text', deps.NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT) or '').strip()
        dm_llm_rewrite_enabled = bool(payload.get('dm_llm_rewrite_enabled', deps.DM_LLM_REWRITE_ENABLED))
        dm_llm_rewrite_prompt_template = str(payload.get('dm_llm_rewrite_prompt_template', deps.DM_LLM_REWRITE_PROMPT_TEMPLATE) or '').strip() or deps.DM_LLM_REWRITE_DEFAULT_PROMPT
        try:
            dm_llm_rewrite_max_chars = int(payload.get('dm_llm_rewrite_max_chars', deps.DM_LLM_REWRITE_MAX_CHARS))
        except Exception:
            dm_llm_rewrite_max_chars = deps.DM_LLM_REWRITE_MAX_CHARS
        dm_llm_rewrite_max_chars = max(80, min(1200, int(dm_llm_rewrite_max_chars)))
        try:
            dm_llm_rewrite_temperature = float(payload.get('dm_llm_rewrite_temperature', deps.DM_LLM_REWRITE_TEMPERATURE))
        except Exception:
            dm_llm_rewrite_temperature = deps.DM_LLM_REWRITE_TEMPERATURE
        dm_llm_rewrite_temperature = max(0.0, min(1.2, float(dm_llm_rewrite_temperature)))
        try:
            dm_llm_rewrite_max_regen = int(payload.get('dm_llm_rewrite_max_regen', deps.DM_LLM_REWRITE_MAX_REGEN))
        except Exception:
            dm_llm_rewrite_max_regen = deps.DM_LLM_REWRITE_MAX_REGEN
        dm_llm_rewrite_max_regen = max(0, min(5, int(dm_llm_rewrite_max_regen)))
        try:
            dm_llm_rewrite_dedupe_size = int(payload.get('dm_llm_rewrite_dedupe_size', deps.DM_LLM_REWRITE_DEDUPE_SIZE))
        except Exception:
            dm_llm_rewrite_dedupe_size = deps.DM_LLM_REWRITE_DEDUPE_SIZE
        dm_llm_rewrite_dedupe_size = max(50, min(1000, int(dm_llm_rewrite_dedupe_size)))
        try:
            timeout_sec = deps.clamp_llm_timeout(payload.get('timeout_sec', deps.LLM_FILTER_TIMEOUT_SEC))
        except Exception:
            timeout_sec = deps.LLM_FILTER_TIMEOUT_SEC
        if enabled and (not base_url or not model):
            return jsonify({'status': 'err', 'msg': '启用 LLM 过滤时，Base URL 和模型名不能为空'}), 400
        notify_voice_block_keywords = deps._normalize_keyword_lines(notify_voice_block_keywords_text)
        with deps.data_lock:
            deps.LLM_FILTER_ENABLED = enabled
            deps.LLM_FILTER_BASE_URL = base_url
            deps.LLM_FILTER_API_KEY = api_key
            deps.LLM_FILTER_MODEL = model
            deps.LLM_FILTER_TIMEOUT_SEC = timeout_sec
            deps.LLM_FILTER_PROMPT_TEMPLATE = filter_prompt_template
            deps.LLM_INTENT_PROMPT_TEMPLATE = intent_prompt_template
            deps.DM_LLM_REWRITE_ENABLED = dm_llm_rewrite_enabled
            deps.DM_LLM_REWRITE_PROMPT_TEMPLATE = dm_llm_rewrite_prompt_template
            deps.DM_LLM_REWRITE_MAX_CHARS = dm_llm_rewrite_max_chars
            deps.DM_LLM_REWRITE_TEMPERATURE = dm_llm_rewrite_temperature
            deps.DM_LLM_REWRITE_MAX_REGEN = dm_llm_rewrite_max_regen
            if deps.DM_LLM_REWRITE_DEDUPE_SIZE != dm_llm_rewrite_dedupe_size:
                deps.DM_LLM_REWRITE_DEDUPE_SIZE = dm_llm_rewrite_dedupe_size
                deps.dm_llm_rewrite_history = deque(list(deps.dm_llm_rewrite_history), maxlen=deps.DM_LLM_REWRITE_DEDUPE_SIZE)
            else:
                deps.DM_LLM_REWRITE_DEDUPE_SIZE = dm_llm_rewrite_dedupe_size
            deps.NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT = notify_voice_block_keywords_text
            deps.NOTIFY_VOICE_BLOCK_KEYWORDS = notify_voice_block_keywords
        with deps.llm_filter_cache_lock:
            deps.llm_filter_cache.clear()
        deps.save_state()
        if deps.LLM_FILTER_ENABLED and deps._llm_filter_is_ready():
            deps.log_to_ui('info', f'🤖 [LLMFilter] 配置已更新并启用: model={deps.LLM_FILTER_MODEL}')
        elif deps.LLM_FILTER_ENABLED:
            deps.log_to_ui('warn', '⚠️ [LLMFilter] 已启用但配置不完整')
        else:
            deps.log_to_ui('info', '🤖 [LLMFilter] 已禁用')
        deps.log_to_ui('info', f'🔇 [NotifyVoice] 不播报关键词已更新: {len(deps.NOTIFY_VOICE_BLOCK_KEYWORDS)} 条')
        return jsonify({
            'status': 'ok',
            'llm_filter_enabled': bool(deps.LLM_FILTER_ENABLED),
            'llm_filter_base_url': str(deps.LLM_FILTER_BASE_URL or ''),
            'llm_filter_api_key_configured': bool(str(deps.LLM_FILTER_API_KEY or '').strip()),
            'llm_filter_model': str(deps.LLM_FILTER_MODEL or ''),
            'llm_filter_timeout_sec': float(deps.LLM_FILTER_TIMEOUT_SEC),
            'llm_filter_timeout_max_sec': float(deps.LLM_FILTER_TIMEOUT_MAX_SEC),
            'llm_filter_prompt_template': str(deps.LLM_FILTER_PROMPT_TEMPLATE or ''),
            'llm_intent_prompt_template': str(deps.LLM_INTENT_PROMPT_TEMPLATE or ''),
            'dm_llm_rewrite_enabled': bool(deps.DM_LLM_REWRITE_ENABLED),
            'dm_llm_rewrite_prompt_template': str(deps.DM_LLM_REWRITE_PROMPT_TEMPLATE or ''),
            'dm_llm_rewrite_max_chars': int(deps.DM_LLM_REWRITE_MAX_CHARS),
            'dm_llm_rewrite_temperature': float(deps.DM_LLM_REWRITE_TEMPERATURE),
            'dm_llm_rewrite_max_regen': int(deps.DM_LLM_REWRITE_MAX_REGEN),
            'dm_llm_rewrite_dedupe_size': int(deps.DM_LLM_REWRITE_DEDUPE_SIZE),
            'notify_voice_block_keywords_text': str(deps.NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT or ''),
            'notify_voice_block_keywords': list(deps.NOTIFY_VOICE_BLOCK_KEYWORDS),
        })
