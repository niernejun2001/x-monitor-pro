def _bool_not_off(raw, default='0'):
    return str(raw if raw is not None else default).strip().lower() not in {'0', 'false', 'no', 'off'}


def _bool_on(raw, default='0'):
    return str(raw if raw is not None else default).strip().lower() in {'1', 'true', 'yes', 'on'}


def _safe_float(raw, default_val):
    try:
        return float(raw)
    except Exception:
        return float(default_val)


def _safe_int(raw, default_val):
    try:
        return int(raw)
    except Exception:
        return int(default_val)


def load_flow_runtime_settings(env, *, parse_backoff_seconds_fn):
    env = env or {}

    dm_followup_text = (
        '您好，我是懒猫微服的王勇，最近看您有在关注我们的产品，觉得挺有意思的。\n'
        '如果您想了解更多，欢迎添加我们工程师微信 17612774028，他会直接给您介绍购买方式。\n'
        '备注推特ID会有一些优惠。'
    )
    dm_llm_rewrite_default_prompt = (
        '你是私信文案改写助手。\n'
        '任务：将给定模板做轻度润色，生成自然、简洁、礼貌、口语化的中文私信。\n'
        '要求：\n'
        '1. 不要改变核心业务信息与联系方式。\n'
        '2. 不要输出解释，只输出最终私信正文。\n'
        '3. 语气真诚，不夸张，不添加模板中没有的承诺。\n'
        '4. 只做轻度润色和小幅度改写，优先保留原句主干、信息顺序和核心表达，不要大幅重写。\n'
        '5. 如果模板本身已经自然，可以只微调少数字词或语气词，不要求强行改写。\n'
        '6. 在不改变核心信息的前提下，可少量替换同义词、顺一下语序，但不要整段改写。\n'
        '7. 避免模板腔，但不要为了去模板腔而改变原句意思。\n'
        '8. 必须保持主语、宾语、关注关系和动作方向不变，不能把用户关注我们的产品改成我们关注用户的产品。\n'
        '9. 不能把“最近看您有在关注我们的产品”改写成“我在看你们的产品”或任何类似的角色反转表达。\n'
        '10. 如果模板里表达的是用户在关注我们的产品，改写后也必须保持这个含义。\n'
        '11. 模板中的手机号、微信号、QQ号、邮箱、链接、数字串（尤其是 6 位以上数字）必须逐字保持不变，不能改动任何一位。\n'
        '12. 可以适度变化开场、承接和结尾措辞，但不能改变联系方式、购买引导、优惠信息和核心业务含义。\n'
        '模板如下：\n'
        '{template}'
    )

    dm_entry_mode = str(env.get('XMONITOR_DM_ENTRY_MODE', 'profile_first') or '').strip().lower()
    if dm_entry_mode not in {'direct_compose_first', 'profile_first', 'dual_probe'}:
        dm_entry_mode = 'direct_compose_first'

    dm_closed_detect_mode = str(env.get('XMONITOR_DM_CLOSED_DETECT_MODE', 'dual_stage_confirm') or '').strip().lower()
    if dm_closed_detect_mode not in {'dual_stage_confirm', 'strict_hint_only'}:
        dm_closed_detect_mode = 'dual_stage_confirm'

    dm_unknown_failure_policy = str(env.get('XMONITOR_DM_UNKNOWN_FAILURE_POLICY', 'retry_queue') or '').strip().lower()
    if dm_unknown_failure_policy not in {'retry_queue', 'manual_only'}:
        dm_unknown_failure_policy = 'retry_queue'

    share_link_quick_path_mode = str(env.get('XMONITOR_SHARE_LINK_QUICK_MODE', 'always') or '').strip().lower()
    if share_link_quick_path_mode not in {'always', 'adaptive', 'off'}:
        share_link_quick_path_mode = 'always'

    reply_status_fallback_policy = str(env.get('XMONITOR_REPLY_STATUS_FALLBACK_POLICY', 'high_priority_only') or '').strip().lower()
    if reply_status_fallback_policy not in {'high_priority_only', 'always', 'off'}:
        reply_status_fallback_policy = 'high_priority_only'

    dm_text_verify_timeout_sec = max(0.5, min(4.0, _safe_float(env.get('XMONITOR_DM_TEXT_VERIFY_TIMEOUT_SEC', '1.2'), 1.2)))
    dm_soft_retry_min_sec = _safe_float(env.get('XMONITOR_DM_SOFT_RETRY_MIN_SEC', '0.08'), 0.08)
    dm_soft_retry_max_sec = _safe_float(env.get('XMONITOR_DM_SOFT_RETRY_MAX_SEC', '0.18'), 0.18)
    if dm_soft_retry_max_sec < dm_soft_retry_min_sec:
        dm_soft_retry_max_sec = dm_soft_retry_min_sec

    dm_context_restart_threshold = max(1, min(6, _safe_int(env.get('XMONITOR_DM_CONTEXT_RESTART_THRESHOLD', '2'), 2)))
    dm_task_max_retry = max(1, min(_safe_int(env.get('XMONITOR_DM_MAX_RETRY', '4'), 4), 8))
    dm_user_cooldown_sec = max(20, min(_safe_int(env.get('XMONITOR_DM_USER_COOLDOWN_SEC', '90'), 90), 900))
    reply_status_fallback_min_score = _safe_int(env.get('XMONITOR_REPLY_STATUS_FALLBACK_MIN_SCORE', '75'), 75)
    reply_failure_budget_max = _safe_int(env.get('XMONITOR_REPLY_FAILURE_BUDGET_MAX', '3'), 3)
    reply_failure_cooldown_sec = _safe_int(env.get('XMONITOR_REPLY_FAILURE_COOLDOWN_SEC', '900'), 900)
    reply_failure_window_sec = _safe_int(env.get('XMONITOR_REPLY_FAILURE_WINDOW_SEC', '1800'), 1800)
    headless_diag_max_html_chars = _safe_int(env.get('XMONITOR_HEADLESS_DIAG_MAX_HTML_CHARS', '12000'), 12000)

    dm_retry_backoff_sec = parse_backoff_seconds_fn(env.get('XMONITOR_DM_RETRY_BACKOFF_SEC', '2,5,9,15'))

    dm_llm_rewrite_max_chars = max(80, min(1200, _safe_int(env.get('XMONITOR_DM_LLM_REWRITE_MAX_CHARS', '260'), 260)))
    dm_llm_rewrite_temperature = max(0.0, min(1.2, _safe_float(env.get('XMONITOR_DM_LLM_REWRITE_TEMPERATURE', '0.35'), 0.35)))
    dm_llm_rewrite_max_regen = max(0, min(5, _safe_int(env.get('XMONITOR_DM_LLM_REWRITE_MAX_REGEN', '1'), 1)))
    dm_llm_rewrite_dedupe_size = max(50, min(1000, _safe_int(env.get('XMONITOR_DM_LLM_REWRITE_DEDUPE_SIZE', '200'), 200)))
    dm_llm_rewrite_similarity_max = max(0.60, min(0.98, _safe_float(env.get('XMONITOR_DM_LLM_REWRITE_SIMILARITY_MAX', '0.96'), 0.96)))
    dm_llm_rewrite_min_diff_chars = max(4, min(120, _safe_int(env.get('XMONITOR_DM_LLM_REWRITE_MIN_DIFF_CHARS', '6'), 6)))
    dm_llm_rewrite_max_shared_run = max(8, min(64, _safe_int(env.get('XMONITOR_DM_LLM_REWRITE_MAX_SHARED_RUN', '32'), 32)))
    dm_critical_max_hold_sec = max(30.0, min(900.0, _safe_float(env.get('XMONITOR_DM_CRITICAL_MAX_HOLD_SEC', '120'), 120.0)))
    dm_send_confirm_wait_sec = max(0.8, min(8.0, _safe_float(env.get('XMONITOR_DM_SEND_CONFIRM_WAIT_SEC', '3.0'), 3.0)))

    return {
        'ENGINE_VERSION': 'v11.3',
        'REPLY_ACTION_GAP_MIN_SEC': 1.0,
        'REPLY_ACTION_GAP_MAX_SEC': 2.0,
        'REPLY_PREPARE_REFRESH_MIN_GAP_SEC': 18.0,
        'REPLY_PROMPT_GUARD_MAX_RETRY': 2,
        'UNHANDLED_PROMPT_AUTO_RETRY': _safe_int(env.get('XMONITOR_UNHANDLED_PROMPT_AUTO_RETRY', '2'), 2),
        'DM_EDITOR_OPEN_RETRY_HEADLESS': 4,
        'DM_EDITOR_OPEN_RETRY_NORMAL': 3,
        'DM_SEND_RETRY_HEADLESS': 3,
        'DM_SEND_RETRY_NORMAL': 2,
        'DM_ACTION_GAP_MIN_SEC': 0.45,
        'DM_ACTION_GAP_MAX_SEC': 1.2,
        'DM_BETWEEN_MESSAGES_MIN_SEC': 0.2,
        'DM_BETWEEN_MESSAGES_MAX_SEC': 0.55,
        'DM_TEXT_VERIFY_TIMEOUT_SEC': dm_text_verify_timeout_sec,
        'DM_SOFT_RETRY_MIN_SEC': dm_soft_retry_min_sec,
        'DM_SOFT_RETRY_MAX_SEC': dm_soft_retry_max_sec,
        'DM_CONTEXT_RESTART_THRESHOLD': dm_context_restart_threshold,
        'DM_CRITICAL_LOCK_ENABLED': _bool_not_off(env.get('XMONITOR_DM_CRITICAL_LOCK_ENABLED', '1'), '1'),
        'DM_HUMAN_SCROLL_CHANCE': 0.18,
        'DM_SEND_FOLLOWUP_TEXT': _bool_not_off(env.get('XMONITOR_DM_SEND_FOLLOWUP_TEXT', '1'), '1'),
        'DM_ENTRY_MODE': dm_entry_mode,
        'DM_CLOSED_DETECT_MODE': dm_closed_detect_mode,
        'DM_UNKNOWN_FAILURE_POLICY': dm_unknown_failure_policy,
        'DM_TASK_MAX_RETRY': dm_task_max_retry,
        'DM_USER_COOLDOWN_SEC': dm_user_cooldown_sec,
        'DM_RETRY_BACKOFF_SEC': dm_retry_backoff_sec,
        'SHARE_LINK_QUICK_PATH': _bool_not_off(env.get('XMONITOR_SHARE_LINK_QUICK_PATH', '1'), '1'),
        'SHARE_LINK_QUICK_PATH_MODE': share_link_quick_path_mode,
        'REPLY_STATUS_FALLBACK_POLICY': reply_status_fallback_policy,
        'REPLY_STATUS_FALLBACK_MIN_SCORE': reply_status_fallback_min_score,
        'REPLY_ADAPTIVE_THROTTLE': _bool_not_off(env.get('XMONITOR_REPLY_ADAPTIVE_THROTTLE', '1'), '1'),
        'REPLY_ENABLE_ACCELERATION': _bool_not_off(env.get('XMONITOR_REPLY_ENABLE_ACCELERATION', '0'), '0'),
        'REPLY_FAILURE_STREAK_SLOWDOWN_FACTOR': _safe_float(env.get('XMONITOR_REPLY_FAILURE_SLOWDOWN_FACTOR', '1.35'), 1.35),
        'REPLY_QUEUE_ACCEL_FACTOR': _safe_float(env.get('XMONITOR_REPLY_QUEUE_ACCEL_FACTOR', '0.82'), 0.82),
        'REPLY_FAILURE_BUDGET_MAX': reply_failure_budget_max,
        'REPLY_FAILURE_COOLDOWN_SEC': reply_failure_cooldown_sec,
        'REPLY_FAILURE_WINDOW_SEC': reply_failure_window_sec,
        'HUMANIZE_BASE_MULTIPLIER': _safe_float(env.get('XMONITOR_HUMANIZE_BASE_MULTIPLIER', '1.28'), 1.28),
        'HUMANIZE_HEADLESS_EXTRA_MULTIPLIER': _safe_float(env.get('XMONITOR_HUMANIZE_HEADLESS_EXTRA_MULTIPLIER', '0.18'), 0.18),
        'DM_RECOVERY_ENABLE_RECREATE_TAB': _bool_not_off(env.get('XMONITOR_DM_RECOVERY_RECREATE_TAB', '1'), '1'),
        'DM_RECOVERY_ENABLE_RESTART_BROWSER': _bool_not_off(env.get('XMONITOR_DM_RECOVERY_RESTART_BROWSER', '1'), '1'),
        'DM_RECOVERY_ENABLE_HEADFUL_FALLBACK': _bool_not_off(env.get('XMONITOR_DM_RECOVERY_HEADFUL_FALLBACK', '1'), '1'),
        'DM_ASSUME_SUCCESS_AFTER_CLICK': _bool_not_off(env.get('XMONITOR_DM_ASSUME_SUCCESS_AFTER_CLICK', '0'), '0'),
        'DM_RECOVERY_HEADFUL_REQUIRE_DISPLAY': _bool_not_off(env.get('XMONITOR_DM_RECOVERY_HEADFUL_REQUIRE_DISPLAY', '1'), '1'),
        'HEADLESS_FORCE_TEMP_PROFILE': _bool_not_off(env.get('XMONITOR_HEADLESS_FORCE_TEMP_PROFILE', '1'), '1'),
        'HEADLESS_DIAG_MAX_HTML_CHARS': headless_diag_max_html_chars,
        'HEADLESS_VERBOSE_LOG': _bool_not_off(env.get('XMONITOR_HEADLESS_VERBOSE_LOG', '1'), '1'),
        'HEADFUL_MAINTENANCE_RESTART': _bool_on(env.get('XMONITOR_HEADFUL_MAINTENANCE_RESTART', '0'), '0'),
        'HEADFUL_NOTIFY_DISCONNECT_RESTART': _bool_on(env.get('XMONITOR_HEADFUL_NOTIFY_DISCONNECT_RESTART', '0'), '0'),
        'DM_UNAVAILABLE_CACHE_TTL_SEC': 12 * 3600,
        'CONTENT_DEDUPE_TTL_SEC': 72 * 3600,
        'CONTENT_DEDUPE_MAX_ENTRIES': 40000,
        'MAINTENANCE_INTERVAL_MIN_SEC': 40 * 60,
        'MAINTENANCE_INTERVAL_MAX_SEC': 70 * 60,
        'TASK_PARALLEL_MIN': 2,
        'TASK_PARALLEL_MAX': 5,
        'TASK_SUBMIT_JITTER_MIN_SEC': 0.18,
        'TASK_SUBMIT_JITTER_MAX_SEC': 0.95,
        'TASK_BATCH_GAP_MIN_SEC': 1.0,
        'TASK_BATCH_GAP_MAX_SEC': 3.2,
        'TAB_OPEN_JITTER_MIN_SEC': 0.2,
        'TAB_OPEN_JITTER_MAX_SEC': 1.2,
        'ARTICLE_REORDER_CHUNK_MIN': 3,
        'ARTICLE_REORDER_CHUNK_MAX': 7,
        'DM_FOLLOWUP_TEXT': dm_followup_text,
        'DEFAULT_NOTIFY_REPLY_TEMPLATES': [
            '老板我给您私信了',
            '老板 我私信您了',
            '大佬我私信您了',
            '大佬 我给您私信了',
            '大佬 我给您私信介绍了',
        ],
        'DEFAULT_DM_TEMPLATES': [dm_followup_text],
        'DM_LLM_REWRITE_DEFAULT_PROMPT': dm_llm_rewrite_default_prompt,
        'DM_LLM_REWRITE_ENABLED': _bool_not_off(env.get('XMONITOR_DM_LLM_REWRITE_ENABLED', '1'), '1'),
        'DM_LLM_REWRITE_PROMPT_TEMPLATE': str(env.get('XMONITOR_DM_LLM_REWRITE_PROMPT_TEMPLATE', dm_llm_rewrite_default_prompt) or dm_llm_rewrite_default_prompt).strip(),
        'DM_LLM_REWRITE_MAX_CHARS': dm_llm_rewrite_max_chars,
        'DM_LLM_REWRITE_TEMPERATURE': dm_llm_rewrite_temperature,
        'DM_LLM_REWRITE_MAX_REGEN': dm_llm_rewrite_max_regen,
        'DM_LLM_REWRITE_DEDUPE_SIZE': dm_llm_rewrite_dedupe_size,
        'DM_LLM_REWRITE_SIMILARITY_MAX': dm_llm_rewrite_similarity_max,
        'DM_LLM_REWRITE_MIN_DIFF_CHARS': dm_llm_rewrite_min_diff_chars,
        'DM_LLM_REWRITE_MAX_SHARED_RUN': dm_llm_rewrite_max_shared_run,
        'DM_CLOSED_FALLBACK_REPLY_TEXT': '大佬 您没有开私信 有需要可以给我私信呀',
        'DM_REJECT_NEW_MESSAGE_OVERLAY': _bool_on(env.get('XMONITOR_DM_REJECT_NEW_MESSAGE_OVERLAY', '1'), '1'),
        'DM_FORCE_COMPOSER_BINDING': _bool_on(env.get('XMONITOR_DM_FORCE_COMPOSER_BINDING', '1'), '1'),
        'DM_LLM_DOWN_FALLBACK_TEMPLATE': _bool_on(env.get('XMONITOR_DM_LLM_DOWN_FALLBACK_TEMPLATE', '1'), '1'),
        'DM_PROFILE_NO_BUTTON_AS_CLOSED': _bool_on(env.get('XMONITOR_DM_PROFILE_NO_BUTTON_AS_CLOSED', '1'), '1'),
        'DM_CRITICAL_MAX_HOLD_SEC': dm_critical_max_hold_sec,
        'DM_SEND_CONFIRM_WAIT_SEC': dm_send_confirm_wait_sec,
        'DM_PASSCODE': str(env.get('XMONITOR_DM_PASSCODE', '1234') or '').strip(),
        'PROXY_ENV_KEYS': (
            'XMONITOR_PROXY',
            'ALL_PROXY',
            'all_proxy',
            'HTTPS_PROXY',
            'https_proxy',
            'HTTP_PROXY',
            'http_proxy',
        ),
    }
