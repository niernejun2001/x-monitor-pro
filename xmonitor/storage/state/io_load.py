import logging
from collections import deque

from xmonitor.services.support.error_format import format_runtime_error
from xmonitor.services.support.state_payload import build_storage_state_payload
from xmonitor.storage.state.io_common import load_json_snapshot, set_dep_attr
from xmonitor.storage.state.sqlite import (
    APP_STATE_KEY,
    PROCESSED_USERS_KEY,
    has_blob as _has_sqlite_blob,
    has_processed_users_table as _has_processed_users_table,
    has_structured_state as _has_structured_state,
    load_blob as _load_sqlite_blob,
    load_processed_users_set as _load_processed_users_set,
    load_structured_state as _load_structured_state,
    save_blob as _save_sqlite_blob,
    save_processed_users_set as _save_processed_users_set,
    save_structured_state as _save_structured_state,
    sqlite_state_file as _sqlite_state_file,
)


def _apply_state_payload(deps, data):
    deps.global_token = data.get('token', '')
    set_dep_attr(deps, 'monitor_tasks', data.get('tasks', []))
    set_dep_attr(deps, 'pending_results', data.get('pending', []))
    deps.notification_monitoring = data.get('notification_monitoring', False)
    deps.delegated_account = str(data.get('delegated_account', '') or '').strip()
    deps.delegated_enabled = bool(data.get('delegated_enabled', bool(deps.delegated_account)))
    deps.enterprise_wechat_webhook_url = str(data.get('enterprise_wechat_webhook_url', getattr(deps, 'enterprise_wechat_webhook_url', '')) or '').strip()
    deps.headless_mode = data.get('headless_mode', True)
    deps.notify_reply_templates = deps._sanitize_template_list(data.get('notify_reply_templates', []), deps.DEFAULT_NOTIFY_REPLY_TEMPLATES)
    deps.dm_message_templates = deps._sanitize_template_list(data.get('dm_message_templates', []), deps.DEFAULT_DM_TEMPLATES)
    deps.LLM_FILTER_ENABLED = bool(data.get('llm_filter_enabled', deps.LLM_FILTER_ENABLED))
    deps.LLM_FILTER_BASE_URL = str(data.get('llm_filter_base_url', deps.LLM_FILTER_BASE_URL) or '').strip()
    deps.LLM_FILTER_API_KEY = str(data.get('llm_filter_api_key', deps.LLM_FILTER_API_KEY) or '').strip()
    deps.LLM_FILTER_MODEL = str(data.get('llm_filter_model', deps.LLM_FILTER_MODEL) or '').strip()
    try:
        deps.LLM_FILTER_TIMEOUT_SEC = deps.clamp_llm_timeout(data.get('llm_filter_timeout_sec', deps.LLM_FILTER_TIMEOUT_SEC))
    except Exception:
        pass
    try:
        deps.LLM_FILTER_RETRY_COUNT = max(0, min(4, int(data.get('llm_filter_retry_count', deps.LLM_FILTER_RETRY_COUNT))))
    except Exception:
        pass
    try:
        deps.LLM_FILTER_RETRY_BACKOFF_SEC = max(0.05, min(5.0, float(data.get('llm_filter_retry_backoff_sec', deps.LLM_FILTER_RETRY_BACKOFF_SEC))))
    except Exception:
        pass
    deps.LLM_FILTER_PROMPT_TEMPLATE = str(data.get('llm_filter_prompt_template', deps.LLM_FILTER_PROMPT_TEMPLATE) or '').strip()
    deps.LLM_INTENT_PROMPT_TEMPLATE = str(data.get('llm_intent_prompt_template', deps.LLM_INTENT_PROMPT_TEMPLATE) or '').strip()
    deps.DM_LLM_REWRITE_ENABLED = bool(data.get('dm_llm_rewrite_enabled', deps.DM_LLM_REWRITE_ENABLED))
    saved_dm_prompt = str(data.get('dm_llm_rewrite_prompt_template', deps.DM_LLM_REWRITE_PROMPT_TEMPLATE) or '').strip()
    if (
        saved_dm_prompt
        and '必须明显重写句式' in saved_dm_prompt
        and '不要大幅重写' not in saved_dm_prompt
        and '保持主语、宾语、关注关系和动作方向不变' not in saved_dm_prompt
    ):
        saved_dm_prompt = deps.DM_LLM_REWRITE_DEFAULT_PROMPT
    deps.DM_LLM_REWRITE_PROMPT_TEMPLATE = saved_dm_prompt or deps.DM_LLM_REWRITE_DEFAULT_PROMPT
    try:
        deps.DM_LLM_REWRITE_MAX_CHARS = int(data.get('dm_llm_rewrite_max_chars', deps.DM_LLM_REWRITE_MAX_CHARS))
    except Exception:
        pass
    deps.DM_LLM_REWRITE_MAX_CHARS = max(80, min(1200, int(deps.DM_LLM_REWRITE_MAX_CHARS)))
    try:
        loaded_temp = float(data.get('dm_llm_rewrite_temperature', deps.DM_LLM_REWRITE_TEMPERATURE))
        if abs(loaded_temp - 0.7) < 1e-9:
            loaded_temp = deps.DM_LLM_REWRITE_TEMPERATURE
        deps.DM_LLM_REWRITE_TEMPERATURE = loaded_temp
    except Exception:
        pass
    deps.DM_LLM_REWRITE_TEMPERATURE = max(0.0, min(1.2, float(deps.DM_LLM_REWRITE_TEMPERATURE)))
    try:
        loaded_regen = int(data.get('dm_llm_rewrite_max_regen', deps.DM_LLM_REWRITE_MAX_REGEN))
        if loaded_regen == 2:
            loaded_regen = deps.DM_LLM_REWRITE_MAX_REGEN
        deps.DM_LLM_REWRITE_MAX_REGEN = loaded_regen
    except Exception:
        pass
    deps.DM_LLM_REWRITE_MAX_REGEN = max(0, min(5, int(deps.DM_LLM_REWRITE_MAX_REGEN)))
    try:
        loaded_dedupe_size = int(data.get('dm_llm_rewrite_dedupe_size', deps.DM_LLM_REWRITE_DEDUPE_SIZE))
    except Exception:
        loaded_dedupe_size = deps.DM_LLM_REWRITE_DEDUPE_SIZE
    deps.DM_LLM_REWRITE_DEDUPE_SIZE = max(50, min(1000, int(loaded_dedupe_size)))
    loaded_hist = data.get('dm_llm_rewrite_history', []) or []
    if not isinstance(loaded_hist, list):
        loaded_hist = []
    set_dep_attr(
        deps,
        'dm_llm_rewrite_history',
        deque([str(x or '').strip() for x in loaded_hist if str(x or '').strip()], maxlen=deps.DM_LLM_REWRITE_DEDUPE_SIZE),
    )
    deps.NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT = str(data.get('notify_voice_block_keywords_text', deps.NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT) or '').strip()
    deps.NOTIFY_VOICE_BLOCK_KEYWORDS = tuple(dict.fromkeys(list(deps.NOTIFY_VOICE_BLOCK_KEYWORDS_BUILTIN) + [kw.lower() for kw in deps._normalize_keyword_lines(deps.NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT)]))
    saved_dm_contacts = data.get('dm_recent_contacts', {})
    if isinstance(saved_dm_contacts, dict):
        setter = getattr(deps, 'set_recent_dm_contacts_result', None)
        if callable(setter):
            setter(saved_dm_contacts, save=False)
        else:
            set_dep_attr(deps, 'dm_recent_contacts_result', saved_dm_contacts)
    set_dep_attr(deps, 'history_ids', set(data.get('history_ids', [])))
    set_dep_attr(deps, 'content_dedupe', {})
    saved_content_dedupe = data.get('content_dedupe', {})
    if isinstance(saved_content_dedupe, dict) and saved_content_dedupe:
        for sig, ts in saved_content_dedupe.items():
            try:
                deps.content_dedupe[str(sig)] = float(ts)
            except Exception:
                continue
        deps.prune_content_dedupe()
        logging.info(f'✅ 已恢复 {len(deps.content_dedupe)} 条内容去重签名')

    pending_changed = False
    for item in deps.pending_results:
        if item.get('source') == '通知页面':
            deps._ensure_notify_flow_fields(item)
        if item.get('source') == '通知页面':
            migrated = False
            if 'reply_checked' in item and 'notify_replied' not in item:
                item['notify_replied'] = bool(item.get('reply_checked'))
                migrated = True
            if 'reply_text' in item and 'notify_reply_text' not in item:
                item['notify_reply_text'] = str(item.get('reply_text') or '')
                migrated = True
            if 'reply_time' in item and 'notify_reply_time' not in item:
                item['notify_reply_time'] = str(item.get('reply_time') or '')
                migrated = True
            if 'reply_checked' in item:
                item.pop('reply_checked', None)
                migrated = True
            if 'reply_text' in item:
                item.pop('reply_text', None)
                migrated = True
            if 'reply_time' in item:
                item.pop('reply_time', None)
                migrated = True
            if migrated:
                pending_changed = True
        if 'key' in item:
            deps.history_ids.add(item['key'])
        sig = deps.make_content_signature(item.get('handle', ''), item.get('content', ''))
        if sig:
            deps.content_dedupe[sig] = deps.time.time()
    deps.prune_content_dedupe()
    return pending_changed


def _apply_structured_state_payload(deps, collections):
    if not isinstance(collections, dict):
        return False
    pending_results = collections.get('pending_results')
    history_ids = collections.get('history_ids')
    content_dedupe = collections.get('content_dedupe')
    if pending_results is None and history_ids is None and content_dedupe is None:
        return False
    if isinstance(pending_results, list):
        for item in pending_results:
            if isinstance(item, dict) and item.get('source') == '通知页面':
                deps._ensure_notify_flow_fields(item)
        set_dep_attr(deps, 'pending_results', pending_results)
    if isinstance(history_ids, list):
        set_dep_attr(deps, 'history_ids', set(str(x) for x in history_ids if str(x)))
    if isinstance(content_dedupe, dict):
        set_dep_attr(deps, 'content_dedupe', dict(content_dedupe))
        deps.prune_content_dedupe()
    return True


def _log_loaded_state_summary(deps):
    logging.info('✅ 状态加载成功:')
    logging.info(f"   - Token: {'已配置' if deps.global_token else '未配置'}")
    logging.info(f'   - 监控任务: {len(deps.monitor_tasks)} 个')
    logging.info(f'   - 待处理: {len(deps.pending_results)} 条')
    logging.info(f'   - 历史记录: {len(deps.history_ids)} 条')
    logging.info(f'   - 内容签名: {len(deps.content_dedupe)} 条')
    logging.info(f"   - 通知监控: {'启用' if deps.notification_monitoring else '禁用'}")
    delegated_label = f"{deps.delegated_account} (启用)" if (deps.delegated_enabled and deps.delegated_account) else '未启用'
    logging.info(f'   - 委派账户: {delegated_label}')
    logging.info(f"   - 浏览器模式: {'无头' if deps.headless_mode else '有头(调试)'}")
    logging.info(f'   - 回复模板: {len(deps.notify_reply_templates)} 条')
    logging.info(f'   - 私信模板: {len(deps.dm_message_templates)} 条')
    if deps.LLM_FILTER_ENABLED:
        logging.info(f"   - LLM过滤: 启用 ({deps.LLM_FILTER_MODEL or '未配置模型'})")
    else:
        logging.info('   - LLM过滤: 禁用')
    tts_status = '启用' if deps._doubao_tts_is_ready() else '禁用/未配置'
    logging.info(f"   - 豆包TTS: {tts_status} ({deps.DOUBAO_TTS_VOICE_TYPE or '未配置音色'})")
    logging.info(f'   - 语音不播报关键词: {len(deps.NOTIFY_VOICE_BLOCK_KEYWORDS)} 条')
    logging.info(f"   - 通知仅抓回复: {'启用' if deps.NOTIFICATION_REPLY_ONLY_MODE else '禁用'}")


def _load_state_payload(deps):
    data = None
    source = ''
    try:
        if _has_sqlite_blob(deps, APP_STATE_KEY):
            data = _load_sqlite_blob(deps, APP_STATE_KEY, default=None)
            if isinstance(data, dict):
                source = 'sqlite'
    except Exception as e:
        logging.error(f'读取SQLite状态失败: {format_runtime_error(e)}')

    if not isinstance(data, dict):
        if deps.os.path.exists(deps.STATE_FILE):
            try:
                data = load_json_snapshot(deps.STATE_FILE)
                if isinstance(data, dict):
                    source = 'json'
            except Exception as e:
                logging.error(f'加载JSON状态失败: {format_runtime_error(e)}')
        else:
            logging.warning(f'⚠️ 状态文件不存在: {deps.STATE_FILE}')
    return data if isinstance(data, dict) else None, source


def _load_processed_users_payload(deps):
    users = None
    source = ''
    try:
        if _has_processed_users_table(deps):
            users = _load_processed_users_set(deps)
            if isinstance(users, list):
                source = 'sqlite_table'
        elif _has_sqlite_blob(deps, PROCESSED_USERS_KEY):
            users = _load_sqlite_blob(deps, PROCESSED_USERS_KEY, default=None)
            if isinstance(users, list):
                source = 'sqlite_blob'
    except Exception as e:
        logging.error(f'读取SQLite黑名单失败: {format_runtime_error(e)}')

    if not isinstance(users, list):
        if deps.os.path.exists(deps.PROCESSED_FILE):
            try:
                users = load_json_snapshot(deps.PROCESSED_FILE)
                if isinstance(users, list):
                    source = 'json'
            except Exception as e:
                logging.error(f'加载黑名单失败: {format_runtime_error(e)}')
        else:
            logging.warning(f'⚠️ 黑名单文件不存在: {deps.PROCESSED_FILE}')
    return users if isinstance(users, list) else [], source


def load_state(deps):
    deps.ensure_data_dir()
    state_data, state_source = _load_state_payload(deps)
    if state_data is not None:
        pending_changed = _apply_state_payload(deps, state_data)

        structured_loaded = False
        try:
            if _has_structured_state(deps):
                structured_state = _load_structured_state(deps)
                structured_loaded = _apply_structured_state_payload(deps, structured_state)
                if structured_loaded:
                    logging.info('🗄️ 已从SQLite结构化表恢复 pending/history/content_dedupe')
        except Exception as e:
            logging.error(f'读取SQLite结构化状态失败: {format_runtime_error(e)}')

        if state_source == 'json':
            try:
                _save_sqlite_blob(deps, APP_STATE_KEY, build_storage_state_payload(deps))
                _save_structured_state(deps, deps.pending_results, deps.history_ids, deps.content_dedupe)
                logging.info(f'🗄️ 已将JSON状态迁移到SQLite: {_sqlite_state_file(deps)}')
            except Exception as e:
                logging.error(f'迁移状态到SQLite失败: {format_runtime_error(e)}')
        elif (state_source == 'sqlite') and (not structured_loaded):
            try:
                _save_structured_state(deps, deps.pending_results, deps.history_ids, deps.content_dedupe)
                logging.info('🗄️ 已补写SQLite结构化状态表')
            except Exception as e:
                logging.error(f'补写结构化状态表失败: {format_runtime_error(e)}')

        if pending_changed:
            deps.save_state()
        _log_loaded_state_summary(deps)
        if state_data.get('is_running', False):
            deps.start_monitor_thread()

    saved_users, users_source = _load_processed_users_payload(deps)
    if saved_users:
        deps.processed_users.update(saved_users)
        logging.info(f'✅ 已恢复 {len(deps.processed_users)} 个已处理用户')
        if users_source in {'json', 'sqlite_blob'}:
            try:
                _save_sqlite_blob(deps, PROCESSED_USERS_KEY, sorted(str(x) for x in deps.processed_users))
                _save_processed_users_set(deps, deps.processed_users)
                logging.info(f'🗄️ 已将黑名单迁移到SQLite实表: {_sqlite_state_file(deps)}')
            except Exception as e:
                logging.error(f'迁移黑名单到SQLite失败: {format_runtime_error(e)}')
