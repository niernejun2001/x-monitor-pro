def _safe_runtime_payload(builder, default=None, **kwargs):
    fallback = {} if default is None else default
    if not callable(builder):
        return dict(fallback)
    try:
        return dict(builder(**kwargs) or {})
    except Exception:
        return dict(fallback)


def _copy_pending_rows_for_api(deps):
    pending_rows = []
    for row in deps.pending_results:
        if isinstance(row, dict) and row.get('source') == '通知页面':
            deps._ensure_notify_flow_fields(row)
        pending_rows.append(dict(row) if isinstance(row, dict) else row)
    return pending_rows


def build_template_payload(deps):
    return {
        'notify_reply_templates': list(deps.notify_reply_templates),
        'dm_message_templates': list(deps.dm_message_templates),
    }


def build_common_state_payload(deps, *, include_secrets):
    payload = {
        'llm_filter_enabled': bool(deps.LLM_FILTER_ENABLED),
        'llm_filter_base_url': str(deps.LLM_FILTER_BASE_URL or ''),
        'llm_filter_model': str(deps.LLM_FILTER_MODEL or ''),
        'llm_filter_timeout_sec': float(deps.LLM_FILTER_TIMEOUT_SEC),
        'llm_filter_prompt_template': str(deps.LLM_FILTER_PROMPT_TEMPLATE or ''),
        'llm_intent_prompt_template': str(deps.LLM_INTENT_PROMPT_TEMPLATE or ''),
        'dm_llm_rewrite_enabled': bool(deps.DM_LLM_REWRITE_ENABLED),
        'dm_llm_rewrite_prompt_template': str(deps.DM_LLM_REWRITE_PROMPT_TEMPLATE or ''),
        'dm_llm_rewrite_max_chars': int(deps.DM_LLM_REWRITE_MAX_CHARS),
        'dm_llm_rewrite_temperature': float(deps.DM_LLM_REWRITE_TEMPERATURE),
        'dm_llm_rewrite_max_regen': int(deps.DM_LLM_REWRITE_MAX_REGEN),
        'dm_llm_rewrite_dedupe_size': int(deps.DM_LLM_REWRITE_DEDUPE_SIZE),
        'notify_voice_block_keywords_text': str(deps.NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT or ''),
        **build_template_payload(deps),
    }
    if include_secrets:
        payload.update(
            {
                'token': deps.global_token,
                'llm_filter_api_key': str(deps.LLM_FILTER_API_KEY or ''),
            }
        )
    else:
        payload.update(
            {
                'token_configured': bool(str(deps.global_token or '').strip()),
                'llm_filter_api_key_configured': bool(str(deps.LLM_FILTER_API_KEY or '').strip()),
            }
        )
    return payload


def build_storage_state_payload(deps):
    payload = build_common_state_payload(deps, include_secrets=True)
    payload.update(
        {
            'tasks': deps.monitor_tasks,
            'is_running': deps.monitor_active,
            'pending': deps.pending_results,
            'notification_monitoring': deps.notification_monitoring,
            'delegated_account': deps.delegated_account,
            'delegated_enabled': deps.delegated_enabled,
            'headless_mode': deps.headless_mode,
            'history_ids': list(deps.history_ids),
            'content_dedupe': deps.content_dedupe,
            'dm_llm_rewrite_history': list(deps.dm_llm_rewrite_history),
        }
    )
    return payload


def build_api_state_payload(deps):
    with deps.data_lock:
        payload = build_common_state_payload(deps, include_secrets=False)
        payload.update(
            {
                'tasks': list(deps.monitor_tasks),
                'is_running': deps.monitor_active,
                'pending': _copy_pending_rows_for_api(deps),
                'updates_last_seq': int(deps.updates_event_seq),
                'updates_buffer_size': len(deps.updates_event_buffer),
                'notification_monitoring': deps.notification_monitoring,
                'delegated_account': deps.delegated_account,
                'delegated_enabled': deps.delegated_enabled,
                'headless_mode': deps.headless_mode,
                'llm_filter_timeout_max_sec': float(deps.LLM_FILTER_TIMEOUT_MAX_SEC),
                'notification_reply_only_mode': bool(deps.NOTIFICATION_REPLY_ONLY_MODE),
            }
        )
    payload.update(
        _safe_runtime_payload(deps._build_notify_tts_runtime_payload, include_secrets=False),
    )
    payload.update(
        _safe_runtime_payload(getattr(deps, '_build_notify_server_audio_runtime_payload', None)),
    )
    payload.update(
        _safe_runtime_payload(getattr(deps, '_build_twitter_cli_runtime_payload', None)),
    )
    payload.update(
        _safe_runtime_payload(getattr(deps, 'build_browser_proxy_runtime_payload', None)),
    )
    return payload
