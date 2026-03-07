import time
import re
import traceback
import tempfile
import shutil
import os
import socket
import datetime
import threading
import queue
import random
import json
import logging
import hashlib
import unicodedata
import difflib
import base64
import uuid
import concurrent.futures
import subprocess
import urllib.request
import urllib.error
import sys
from collections import deque
from DrissionPage import ChromiumPage, ChromiumOptions
from xmonitor.services.dm_open_service import open_dm_editor_for_handle as _open_dm_editor_for_handle_impl
from xmonitor.services.intent_service import (
    analyze_comment_intent as _analyze_comment_intent_impl,
    build_intent_analysis_prompt as _build_intent_analysis_prompt_impl,
    find_keyword_hits as _find_keyword_hits_impl,
    is_business_consult_signal as _is_business_consult_signal_impl,
    is_negative_intent_reason as _is_negative_intent_reason_impl,
    is_non_business_meme_signal as _is_non_business_meme_signal_impl,
    is_performance_consult_signal as _is_performance_consult_signal_impl,
    is_short_reply_intent_signal as _is_short_reply_intent_signal_impl,
    llm_intent_analysis as _llm_intent_analysis_impl,
    rule_based_intent_analysis as _rule_based_intent_analysis_impl,
    should_notify_voice_by_intent as _should_notify_voice_by_intent_impl,
)
from xmonitor.services.dm_llm_service import (
    build_dm_llm_rewrite_prompt as _build_dm_llm_rewrite_prompt_impl,
    dm_rewrite_contains_forbidden_phrase as _dm_rewrite_contains_forbidden_phrase_impl,
    dm_rewrite_is_too_similar as _dm_rewrite_is_too_similar_impl,
    dm_rewrite_longest_common_substring_len as _dm_rewrite_longest_common_substring_len_impl,
    dm_rewrite_similarity_score as _dm_rewrite_similarity_score_impl,
    extract_dm_rewrite_forbidden_phrases as _extract_dm_rewrite_forbidden_phrases_impl,
    generate_dm_text_with_llm as _generate_dm_text_with_llm_impl,
    is_dm_llm_rewrite_duplicate as _is_dm_llm_rewrite_duplicate_impl,
    normalize_dm_rewrite_signature as _normalize_dm_rewrite_signature_impl,
    record_dm_llm_rewrite_signature as _record_dm_llm_rewrite_signature_impl,
)
from xmonitor.services.diagnostics_service import (
    as_json_safe as _as_json_safe_impl,
    capture_runtime_diagnostic as _capture_runtime_diagnostic_impl,
    probe_selectors_snapshot as _probe_selectors_snapshot_impl,
)
from xmonitor.services.llm_client import (
    call_ollama_native_json as _call_ollama_native_json_impl,
    call_openai_compatible_filter_api as _call_openai_compatible_filter_api_impl,
    call_openai_compatible_json as _call_openai_compatible_json_impl,
    guess_ollama_native_endpoint as _guess_ollama_native_endpoint_impl,
    parse_json_object_from_text as _parse_json_object_from_text_impl,
)
from xmonitor.browser.browser_options import init_browser_options as _init_browser_options_impl
from xmonitor.services.tts_service import (
    doubao_tts_is_ready as _doubao_tts_is_ready_impl,
    doubao_tts_mime_by_encoding as _doubao_tts_mime_by_encoding_impl,
    synthesize_doubao_tts_audio_base64 as _synthesize_doubao_tts_audio_base64_impl,
    truncate_text_for_tts as _truncate_text_for_tts_impl,
)
from xmonitor.browser.browser_interaction import (
    click_first_actionable_by_selectors as _click_first_actionable_by_selectors_impl,
    click_share_copy_link as _click_share_copy_link_impl,
    click_with_prompt_guard as _click_with_prompt_guard_impl,
    confirm_dm_closed_dual_stage as _confirm_dm_closed_dual_stage_impl,
    dismiss_pending_browser_prompt as _dismiss_pending_browser_prompt_impl,
    install_headless_dialog_guard as _install_headless_dialog_guard_impl,
)
from xmonitor.services.filter_service import (
    contains_emoji_char as _contains_emoji_char_impl,
    is_emoji_only_content as _is_emoji_only_content_impl,
    llm_filter_endpoint as _llm_filter_endpoint_impl,
    llm_filter_is_ready as _llm_filter_is_ready_impl,
    llm_runtime_ready as _llm_runtime_ready_impl,
    make_content_signature as _make_content_signature_impl,
    normalize_content_for_dedupe as _normalize_content_for_dedupe_impl,
    normalize_content_for_filter as _normalize_content_for_filter_impl,
    prune_content_dedupe as _prune_content_dedupe_impl,
    prune_llm_filter_cache as _prune_llm_filter_cache_impl,
    reorder_articles_for_scan as _reorder_articles_for_scan_impl,
    should_skip_by_llm_filter as _should_skip_by_llm_filter_impl,
    should_skip_content_by_policy as _should_skip_content_by_policy_impl,
    should_skip_duplicate_content as _should_skip_duplicate_content_impl,
)
from xmonitor.browser.browser_maintenance import run_headful_soft_maintenance as _run_headful_soft_maintenance_impl
from xmonitor.runtime.runtime_control import (
    start_monitor_thread as _start_monitor_thread_impl,
    stop_monitor_thread as _stop_monitor_thread_impl,
)
from xmonitor.browser.browser_profile_service import (
    auto_cleanup_profile_runtime as _auto_cleanup_profile_runtime_impl,
    cleanup_stale_profile_singletons as _cleanup_stale_profile_singletons_impl,
    extract_singleton_lock_pid as _extract_singleton_lock_pid_impl,
    is_profile_locked_by_alive_process as _is_profile_locked_by_alive_process_impl,
    list_profile_bound_browser_pids as _list_profile_bound_browser_pids_impl,
    pid_exists as _pid_exists_impl,
    terminate_pids as _terminate_pids_impl,
)
from xmonitor.runtime.runtime_state import build_runtime_state as _build_runtime_state_impl, get_runtime_attr as _get_runtime_attr_impl, set_runtime_attr as _set_runtime_attr_impl
from xmonitor.services.dm_send_service import (
    send_dm_message as _send_dm_message_impl,
    send_dm_message_with_retry as _send_dm_message_with_retry_impl,
)
from xmonitor.services.dm_passcode_service import (
    handle_dm_passcode_prompt as _handle_dm_passcode_prompt_impl,
    warmup_dm_passcode_if_needed as _warmup_dm_passcode_if_needed_impl,
)
from xmonitor.services.dm_recovery_service import (
    read_dm_session_state as _read_dm_session_state_impl,
    run_dm_send_sequence_once as _run_dm_send_sequence_once_impl,
    run_dm_send_with_recovery as _run_dm_send_with_recovery_impl,
)
from xmonitor.services.dm_runtime import (
    classify_dm_error_text as _classify_dm_error_text,
    humanized_gap_between_dm_messages as _humanized_gap_between_dm_messages_impl,
    humanized_type_dm_text as _humanized_type_dm_text_impl,
    is_dm_closed_error_text as _is_dm_closed_error_text,
    is_dm_context_or_editor_error_text as _is_dm_context_or_editor_error_text,
    is_dm_context_url as _is_dm_context_url,
    is_dm_llm_fallback_allowed as _is_dm_llm_fallback_allowed,
    is_dm_soft_send_error_text as _is_dm_soft_send_error_text,
    paste_dm_text_exact as _paste_dm_text_exact_impl,
    poke_dm_editor_events as _poke_dm_editor_events_impl,
    refresh_dm_editor_state as _refresh_dm_editor_state_impl,
)
from xmonitor.services.dm_common import (
    build_dm_message_probes as _build_dm_message_probes,
    confirm_dm_message_sent as _confirm_dm_message_sent,
    count_dm_probe_occurrence as _count_dm_probe_occurrence,
    count_dm_sent_markers as _count_dm_sent_markers,
    extract_status_id_candidates_from_text as _extract_status_id_candidates_from_text,
    get_dm_conversation_text as _get_dm_conversation_text,
    is_link_only_message as _is_link_only_message,
    normalize_dm_share_link as _normalize_dm_share_link,
    normalize_handle,
    normalize_status_id_digits as _normalize_status_id_digits,
    normalize_text_for_compare as _normalize_text_for_compare,
    pick_best_status_id as _pick_best_status_id,
    sanitize_dm_message_text as _sanitize_dm_message_text,
)
from xmonitor.services.notification_extract import (
    collect_notification_hrefs as _collect_notification_hrefs_impl,
    collect_notification_tweet_texts as _collect_notification_tweet_texts_impl,
    extract_notification_content as _extract_notification_content_impl,
    extract_notification_status_info as _extract_notification_status_info_impl,
    extract_status_from_href as _extract_status_from_href_impl,
)
from xmonitor.services.notification_scan import scan_notifications_page as _scan_notifications_page_impl
from xmonitor.browser.notification_tab_service import (
    close_notification_tab as _close_notification_tab_impl,
    ensure_notification_tab as _ensure_notification_tab_impl,
    init_notification_tab as _init_notification_tab_impl,
)
from xmonitor.services.notification_match import (
    extract_status_id_from_notification_item as _extract_status_id_from_notification_item_impl,
    extract_status_ids_from_article as _extract_status_ids_from_article_impl,
    is_reply_to_me_notification_item as _is_reply_to_me_notification_item_impl,
    match_notification_card_for_reply as _match_notification_card_for_reply_impl,
    match_reply_target_article as _match_reply_target_article_impl,
)
from xmonitor.services.notify_reply_service import send_notification_reply as _send_notification_reply_impl
from xmonitor.services.tweet_scan import scan_page_content as _scan_page_content_impl
from xmonitor.services.notification_tab_runtime import scan_persistent_notification_tab as _scan_persistent_notification_tab_impl
from xmonitor.services.page_scan import (
    scan_page_content_with_tab as _scan_page_content_with_tab_impl,
    scan_task_with_tab as _scan_task_with_tab_impl,
    scan_task_worker as _scan_task_worker_impl,
)
from xmonitor.services.notification_scan_helpers import (
    extract_notification_handle as _extract_notification_handle_impl,
    parse_notification_age_minutes as _parse_notification_age_minutes_impl,
)
from xmonitor.services.notification_text import (
    NOTIFICATION_REPLY_TO_YOU_KEYWORDS,
    classify_notification_type as _classify_notification_type,
    is_display_name_like as _is_display_name_like,
    is_noise_notification_text as _is_noise_notification_text,
    normalize_notification_text as _normalize_notification_text,
    normalize_one_line as _normalize_one_line,
    score_notification_candidate as _score_notification_candidate,
)
from xmonitor.services.notify_flow import (
    NOTIFY_FLOW_STAGE_ORDER,
    notify_stage_at_least as _notify_stage_at_least,
    notify_stage_rank as _notify_stage_rank,
    normalize_notify_flow_stage as _normalize_notify_flow_stage,
    resolve_notify_resume_stage as _resolve_notify_resume_stage,
    split_flow_error as _split_flow_error,
)
from xmonitor.browser.selectors import DM_EDITOR_SELECTORS, DM_PROFILE_BUTTON_SELECTORS, DM_SEND_BUTTON_SELECTORS
from xmonitor.web.app_factory import create_flask_app
from xmonitor.services.delegation_service import (
    ensure_delegated_account_session as _ensure_delegated_account_session_impl,
    get_current_account_handle as _get_current_account_handle_impl,
    switch_to_delegated_account as _switch_to_delegated_account_impl,
)
from xmonitor.services.tts_config_service import (
    apply_notify_tts_config as _apply_notify_tts_config_impl,
    build_notify_tts_runtime_payload as _build_notify_tts_runtime_payload_impl,
    normalize_notify_tts_config_from_payload as _normalize_notify_tts_config_from_payload_impl,
)
from xmonitor.runtime.monitor_runtime import monitoring_loop as _monitoring_loop_impl
from xmonitor.storage.state_io import (
    load_state as _load_state_impl,
    save_processed_users as _save_processed_users_impl,
    save_state as _save_state_impl,
)
from xmonitor.storage.repositories import MonitorTasksRepository, PendingResultsRepository, ProcessedUsersRepository
from xmonitor.storage.notify_state_facade import NotifyStateFacade
from xmonitor.browser.browser_manager import (
    cleanup_global_browser as _cleanup_global_browser_impl,
    init_global_browser as _init_global_browser_impl,
    restart_global_browser as _restart_global_browser_impl,
)
from xmonitor.browser.web_helpers import (
    is_element_actionable as _is_element_actionable,
    wait_document_ready as _wait_document_ready,
    wait_first_actionable as _wait_first_actionable,
    wait_first_visible as _wait_first_visible,
)
from xmonitor.runtime.runtime_flow import (
    clamp as _clamp,
    get_adaptive_reply_gap_factor as _get_adaptive_reply_gap_factor_impl,
    get_humanize_multiplier as _get_humanize_multiplier_impl,
    reserve_notify_dm_user_slot as _reserve_notify_dm_user_slot_impl,
)
from xmonitor.runtime.timing_helpers import (
    get_random_maintenance_interval as _get_random_maintenance_interval_impl,
    get_random_notification_interval as _get_random_notification_interval_impl,
    get_random_notification_refresh_interval as _get_random_notification_refresh_interval_impl,
    get_random_task_parallel as _get_random_task_parallel_impl,
    schedule_next_notification_refresh_interval as _schedule_next_notification_refresh_interval_impl,
)
from xmonitor.runtime.action_throttle import (
    throttle_dm_action_if_needed as _throttle_dm_action_if_needed_impl,
    throttle_reply_action_if_needed as _throttle_reply_action_if_needed_impl,
)
from xmonitor.runtime.reply_metrics import (
    is_reply_flow_active_deps as _is_reply_flow_active_deps_impl,
    record_reply_outcome_deps as _record_reply_outcome_deps_impl,
    set_reply_flow_active_deps as _set_reply_flow_active_deps_impl,
)
from xmonitor.runtime.dm_critical import (
    enter_dm_critical as _enter_dm_critical_impl,
    is_dm_critical_active as _is_dm_critical_active_impl,
    leave_dm_critical as _leave_dm_critical_impl,
    maybe_log_dm_critical_skip as _maybe_log_dm_critical_skip_impl,
)
from xmonitor.services.dm_state_service import (
    clear_dm_unavailable_cache as _clear_dm_unavailable_cache_impl,
    get_status_link_from_item as _get_status_link_from_item_impl,
    is_dm_unavailable_cached as _is_dm_unavailable_cached_impl,
    mark_dm_unavailable as _mark_dm_unavailable_impl,
    reply_humanized_idle as _reply_humanized_idle_impl,
)
from xmonitor.browser.work_tab_service import ensure_reply_work_tab as _ensure_reply_work_tab_impl
from xmonitor.services.dm_context_service import ensure_dm_session_ready_for_handle as _ensure_dm_session_ready_for_handle_impl
from xmonitor.services.template_utils import (
    normalize_keyword_lines as _normalize_keyword_lines_impl,
    render_llm_prompt_template as _render_llm_prompt_template_impl,
    sanitize_template_list as _sanitize_template_list_impl,
)
from xmonitor.runtime.event_bus import (
    drain_msg_queue as _drain_msg_queue_impl,
    publish_new_data_event as _publish_new_data_event_impl,
)
from xmonitor.runtime.config_helpers import (
    get_data_dir as _get_data_dir_impl,
    get_default_user_data_dir as _get_default_user_data_dir_impl,
    parse_backoff_seconds as _parse_backoff_seconds_impl,
    resolve_server_port as _resolve_server_port_impl,
)
from xmonitor.services.dm_flow_service import (
    dm_humanized_idle as _dm_humanized_idle_impl,
    ensure_dm_context_for_handle as _ensure_dm_context_for_handle_impl,
    should_use_share_link_quick_path as _should_use_share_link_quick_path_impl,
)
from xmonitor.services.reply_ops import (
    match_target_card as _match_target_card_impl,
    prepare_notifications_view as _prepare_notifications_view_impl,
    send_reply_from_button as _send_reply_from_button_impl,
)
from xmonitor.services.reply_runtime import (
    is_reply_flow_active as _is_reply_flow_active_impl,
    record_reply_outcome as _record_reply_outcome_impl,
    set_reply_flow_active as _set_reply_flow_active_impl,
)
from xmonitor.browser.tab_manager import ensure_worker_tab

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_TTS_CONFIG_FILE = os.path.join(BASE_DIR, "data", "local_tts_config.json")


def _load_local_tts_config():
    """读取本地私有TTS配置（git忽略），用于保存密钥。"""
    try:
        if not os.path.exists(LOCAL_TTS_CONFIG_FILE):
            return {}
        with open(LOCAL_TTS_CONFIG_FILE, "r", encoding="utf-8") as f:
            obj = json.load(f)
            if isinstance(obj, dict):
                return obj
    except Exception as e:
        logging.warning(f"读取本地TTS配置失败: {e}")
    return {}


LOCAL_TTS_CONFIG = _load_local_tts_config()


def _save_local_tts_config(cfg):
    """保存本地私有TTS配置（不进入git）。"""
    try:
        target = os.path.abspath(os.path.expanduser(LOCAL_TTS_CONFIG_FILE))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True, ""
    except Exception as e:
        return False, str(e)

# --- 配置文件路径（自动检测环境）---
def get_default_user_data_dir():
    """返回当前用户默认数据目录。"""
    return _get_default_user_data_dir_impl()


def get_data_dir():
    """根据运行环境自动选择数据目录"""
    return _get_data_dir_impl(BASE_DIR)

DATA_DIR = get_data_dir()
STATE_FILE = os.path.join(DATA_DIR, "spider_state.json")
PROCESSED_FILE = os.path.join(DATA_DIR, "processed_users.json")
SQLITE_STATE_FILE = os.path.join(DATA_DIR, "xmonitor_state.sqlite3")
STATE_JSON_FALLBACK = str(os.environ.get("XMONITOR_STATE_JSON_FALLBACK", "1")).strip().lower() not in {"0", "false", "no", "off"}
RUNTIME_LOG_FILE = os.path.join(DATA_DIR, "runtime.log")
DIAG_DIR = os.path.join(DATA_DIR, "diagnostics")
BROWSER_PROFILE_DIR = os.environ.get(
    "XMONITOR_BROWSER_PROFILE_DIR",
    os.path.join(DATA_DIR, "chromium-profile")
)
BROWSER_PROFILE_DIR = os.path.abspath(os.path.expanduser(BROWSER_PROFILE_DIR))
BROWSER_PROFILE_PERSIST = str(
    os.environ.get("XMONITOR_PERSIST_BROWSER_PROFILE", "1")
).strip().lower() not in {"0", "false", "no", "off"}


def ensure_data_dir():
    """确保数据目录存在。"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception as e:
        logging.error(f"创建数据目录失败: {e}")


def migrate_legacy_state_files():
    """迁移历史版本写在项目根目录的数据文件到 data/ 目录。"""
    try:
        def sync_if_newer(legacy_file, target_file, label):
            if legacy_file == target_file or not os.path.exists(legacy_file):
                return
            if (not os.path.exists(target_file)) or (os.path.getmtime(legacy_file) > os.path.getmtime(target_file)):
                shutil.copy2(legacy_file, target_file)
                logging.info(f"📦 已同步{label}: {legacy_file} -> {target_file}")

        legacy_state_candidates = [
            os.path.join(BASE_DIR, "spider_state.json"),
            os.path.join(BASE_DIR, "data", "spider_state.json"),
        ]
        legacy_processed_candidates = [
            os.path.join(BASE_DIR, "processed_users.json"),
            os.path.join(BASE_DIR, "data", "processed_users.json"),
        ]

        for legacy_state in legacy_state_candidates:
            sync_if_newer(legacy_state, STATE_FILE, "状态文件")
        for legacy_processed in legacy_processed_candidates:
            sync_if_newer(legacy_processed, PROCESSED_FILE, "黑名单文件")
    except Exception as e:
        logging.warning(f"迁移历史数据文件失败: {e}")


# 模块加载即确保目录存在并迁移旧数据（Qt 导入 app.py 时也生效）
ensure_data_dir()
migrate_legacy_state_files()

# --- 全局变量 ---
monitor_active = False
monitor_tasks = []
processed_users = set() # 已屏蔽/已私信的用户集合
pending_results = []    # 关键修复：待处理的结果列表（持久化）
history_ids = set()     # 本次运行的抓取去重
msg_queue = queue.Queue()
try:
    UPDATES_EVENT_BUFFER_MAX = int(os.environ.get("XMONITOR_UPDATES_EVENT_BUFFER_MAX", "5000"))
except Exception:
    UPDATES_EVENT_BUFFER_MAX = 5000
UPDATES_EVENT_BUFFER_MAX = max(200, min(50000, int(UPDATES_EVENT_BUFFER_MAX)))
updates_event_seq = 0
updates_event_buffer = deque(maxlen=UPDATES_EVENT_BUFFER_MAX)
global_token = ""
delegated_account = ""  # 新增：委派账户用户名（格式：@username 或 username）
delegated_enabled = False  # 委派账户功能开关（仅当为 True 时才会执行委派切换）
delegated_account_active = ""  # 当前浏览器会话已切换到的委派账户（标准化handle）
delegated_switch_ok = False
headless_mode = True    # 无头模式开关：True=无头，False=有头（调试用）
data_lock = threading.Lock()
browser_lock = threading.Lock() # 浏览器操作锁（用于多标签页同步）
browser_init_lock = threading.Lock() # 浏览器初始化串行锁，避免并发重入互相干扰
tab_lock = threading.Lock()     # 标签页创建/销毁锁
notification_monitoring = False  # 新增：通知监控开关
try:
    NOTIFICATION_SCAN_INTERVAL_MIN_SEC = float(os.environ.get("XMONITOR_NOTIFY_SCAN_MIN_SEC", "3"))
except Exception:
    NOTIFICATION_SCAN_INTERVAL_MIN_SEC = 3.0
try:
    NOTIFICATION_SCAN_INTERVAL_MAX_SEC = float(os.environ.get("XMONITOR_NOTIFY_SCAN_MAX_SEC", "6"))
except Exception:
    NOTIFICATION_SCAN_INTERVAL_MAX_SEC = 6.0
try:
    NOTIFICATION_RECENT_WINDOW_MINUTES = int(os.environ.get("XMONITOR_NOTIFY_RECENT_WINDOW_MIN", "45"))
except Exception:
    NOTIFICATION_RECENT_WINDOW_MINUTES = 45
try:
    NOTIFICATION_MAX_SCAN_ARTICLES = int(os.environ.get("XMONITOR_NOTIFY_MAX_ARTICLES", "180"))
except Exception:
    NOTIFICATION_MAX_SCAN_ARTICLES = 180
NOTIFICATION_VERBOSE_TRACE = str(
    os.environ.get("XMONITOR_NOTIFY_VERBOSE_TRACE", "1")
).strip().lower() not in {"0", "false", "no", "off"}
try:
    NOTIFICATION_TRACE_MAX_ARTICLES = int(os.environ.get("XMONITOR_NOTIFY_TRACE_MAX_ARTICLES", "12"))
except Exception:
    NOTIFICATION_TRACE_MAX_ARTICLES = 12
try:
    NOTIFICATION_TRACE_TEXT_LEN = int(os.environ.get("XMONITOR_NOTIFY_TRACE_TEXT_LEN", "120"))
except Exception:
    NOTIFICATION_TRACE_TEXT_LEN = 120
try:
    NOTIFICATION_REFRESH_INTERVAL_MIN_SEC = float(os.environ.get("XMONITOR_NOTIFY_REFRESH_MIN_SEC", "20"))
except Exception:
    NOTIFICATION_REFRESH_INTERVAL_MIN_SEC = 20.0
try:
    NOTIFICATION_REFRESH_INTERVAL_MAX_SEC = float(os.environ.get("XMONITOR_NOTIFY_REFRESH_MAX_SEC", "40"))
except Exception:
    NOTIFICATION_REFRESH_INTERVAL_MAX_SEC = 40.0
try:
    NOTIFICATION_REFRESH_SKIP_PROB = float(os.environ.get("XMONITOR_NOTIFY_REFRESH_SKIP_PROB", "0.22"))
except Exception:
    NOTIFICATION_REFRESH_SKIP_PROB = 0.22
try:
    NOTIFICATION_REFRESH_SOFT_NAV_PROB = float(os.environ.get("XMONITOR_NOTIFY_REFRESH_SOFT_NAV_PROB", "0.24"))
except Exception:
    NOTIFICATION_REFRESH_SOFT_NAV_PROB = 0.24
try:
    NOTIFICATION_REFRESH_COOLDOWN_PROB = float(os.environ.get("XMONITOR_NOTIFY_REFRESH_COOLDOWN_PROB", "0.16"))
except Exception:
    NOTIFICATION_REFRESH_COOLDOWN_PROB = 0.16
try:
    NOTIFICATION_REFRESH_COOLDOWN_MIN_SEC = float(
        os.environ.get("XMONITOR_NOTIFY_REFRESH_COOLDOWN_MIN_SEC", "8")
    )
except Exception:
    NOTIFICATION_REFRESH_COOLDOWN_MIN_SEC = 8.0
try:
    NOTIFICATION_REFRESH_COOLDOWN_MAX_SEC = float(
        os.environ.get("XMONITOR_NOTIFY_REFRESH_COOLDOWN_MAX_SEC", "22")
    )
except Exception:
    NOTIFICATION_REFRESH_COOLDOWN_MAX_SEC = 22.0
try:
    NOTIFICATION_EMPTY_RECOVER_SOFT_THRESHOLD = int(
        os.environ.get("XMONITOR_NOTIFY_EMPTY_RECOVER_SOFT_THRESHOLD", "3")
    )
except Exception:
    NOTIFICATION_EMPTY_RECOVER_SOFT_THRESHOLD = 3
try:
    NOTIFICATION_EMPTY_RECOVER_HARD_THRESHOLD = int(
        os.environ.get("XMONITOR_NOTIFY_EMPTY_RECOVER_HARD_THRESHOLD", "6")
    )
except Exception:
    NOTIFICATION_EMPTY_RECOVER_HARD_THRESHOLD = 6
NOTIFICATION_REPLY_ONLY_MODE = str(
    os.environ.get("XMONITOR_NOTIFY_REPLY_ONLY", "1")
).strip().lower() not in {"0", "false", "no", "off"}
ENGINE_VERSION = "v11.3"
REPLY_ACTION_GAP_MIN_SEC = 1.0
REPLY_ACTION_GAP_MAX_SEC = 2.0
REPLY_PREPARE_REFRESH_MIN_GAP_SEC = 18.0
REPLY_PROMPT_GUARD_MAX_RETRY = 2
try:
    UNHANDLED_PROMPT_AUTO_RETRY = int(os.environ.get("XMONITOR_UNHANDLED_PROMPT_AUTO_RETRY", "2"))
except Exception:
    UNHANDLED_PROMPT_AUTO_RETRY = 2
DM_EDITOR_OPEN_RETRY_HEADLESS = 4
DM_EDITOR_OPEN_RETRY_NORMAL = 3
DM_SEND_RETRY_HEADLESS = 3
DM_SEND_RETRY_NORMAL = 2
DM_ACTION_GAP_MIN_SEC = 0.45
DM_ACTION_GAP_MAX_SEC = 1.2
DM_BETWEEN_MESSAGES_MIN_SEC = 0.2
DM_BETWEEN_MESSAGES_MAX_SEC = 0.55
try:
    DM_TEXT_VERIFY_TIMEOUT_SEC = float(os.environ.get("XMONITOR_DM_TEXT_VERIFY_TIMEOUT_SEC", "1.2"))
except Exception:
    DM_TEXT_VERIFY_TIMEOUT_SEC = 1.2
DM_TEXT_VERIFY_TIMEOUT_SEC = max(0.5, min(4.0, DM_TEXT_VERIFY_TIMEOUT_SEC))
try:
    DM_SOFT_RETRY_MIN_SEC = float(os.environ.get("XMONITOR_DM_SOFT_RETRY_MIN_SEC", "0.08"))
except Exception:
    DM_SOFT_RETRY_MIN_SEC = 0.08
try:
    DM_SOFT_RETRY_MAX_SEC = float(os.environ.get("XMONITOR_DM_SOFT_RETRY_MAX_SEC", "0.18"))
except Exception:
    DM_SOFT_RETRY_MAX_SEC = 0.18
if DM_SOFT_RETRY_MAX_SEC < DM_SOFT_RETRY_MIN_SEC:
    DM_SOFT_RETRY_MAX_SEC = DM_SOFT_RETRY_MIN_SEC
try:
    DM_CONTEXT_RESTART_THRESHOLD = int(os.environ.get("XMONITOR_DM_CONTEXT_RESTART_THRESHOLD", "2"))
except Exception:
    DM_CONTEXT_RESTART_THRESHOLD = 2
DM_CONTEXT_RESTART_THRESHOLD = max(1, min(6, DM_CONTEXT_RESTART_THRESHOLD))
DM_CRITICAL_LOCK_ENABLED = str(
    os.environ.get("XMONITOR_DM_CRITICAL_LOCK_ENABLED", "1")
).strip().lower() not in {"0", "false", "no", "off"}
DM_HUMAN_SCROLL_CHANCE = 0.18
DM_SEND_FOLLOWUP_TEXT = str(
    os.environ.get("XMONITOR_DM_SEND_FOLLOWUP_TEXT", "1")
).strip().lower() not in {"0", "false", "no", "off"}
DM_ENTRY_MODE = str(
    os.environ.get("XMONITOR_DM_ENTRY_MODE", "profile_first")
).strip().lower()
if DM_ENTRY_MODE not in {"direct_compose_first", "profile_first", "dual_probe"}:
    DM_ENTRY_MODE = "direct_compose_first"
DM_CLOSED_DETECT_MODE = str(
    os.environ.get("XMONITOR_DM_CLOSED_DETECT_MODE", "dual_stage_confirm")
).strip().lower()
if DM_CLOSED_DETECT_MODE not in {"dual_stage_confirm", "strict_hint_only"}:
    DM_CLOSED_DETECT_MODE = "dual_stage_confirm"
DM_UNKNOWN_FAILURE_POLICY = str(
    os.environ.get("XMONITOR_DM_UNKNOWN_FAILURE_POLICY", "retry_queue")
).strip().lower()
if DM_UNKNOWN_FAILURE_POLICY not in {"retry_queue", "manual_only"}:
    DM_UNKNOWN_FAILURE_POLICY = "retry_queue"
try:
    DM_TASK_MAX_RETRY = int(os.environ.get("XMONITOR_DM_MAX_RETRY", "4"))
except Exception:
    DM_TASK_MAX_RETRY = 4
DM_TASK_MAX_RETRY = max(1, min(DM_TASK_MAX_RETRY, 8))
try:
    DM_USER_COOLDOWN_SEC = int(os.environ.get("XMONITOR_DM_USER_COOLDOWN_SEC", "90"))
except Exception:
    DM_USER_COOLDOWN_SEC = 90
DM_USER_COOLDOWN_SEC = max(20, min(DM_USER_COOLDOWN_SEC, 900))


def _parse_backoff_seconds(raw, default_values=(2, 5, 9, 15)):
    return _parse_backoff_seconds_impl(raw, default_values=default_values)


DM_RETRY_BACKOFF_SEC = _parse_backoff_seconds(
    os.environ.get("XMONITOR_DM_RETRY_BACKOFF_SEC", "2,5,9,15")
)
SHARE_LINK_QUICK_PATH = str(
    os.environ.get("XMONITOR_SHARE_LINK_QUICK_PATH", "1")
).strip().lower() not in {"0", "false", "no", "off"}
SHARE_LINK_QUICK_PATH_MODE = str(
    os.environ.get("XMONITOR_SHARE_LINK_QUICK_MODE", "always")
).strip().lower()
if SHARE_LINK_QUICK_PATH_MODE not in {"always", "adaptive", "off"}:
    SHARE_LINK_QUICK_PATH_MODE = "always"
REPLY_STATUS_FALLBACK_POLICY = str(
    os.environ.get("XMONITOR_REPLY_STATUS_FALLBACK_POLICY", "high_priority_only")
).strip().lower()
if REPLY_STATUS_FALLBACK_POLICY not in {"high_priority_only", "always", "off"}:
    REPLY_STATUS_FALLBACK_POLICY = "high_priority_only"
try:
    REPLY_STATUS_FALLBACK_MIN_SCORE = int(
        os.environ.get("XMONITOR_REPLY_STATUS_FALLBACK_MIN_SCORE", "75")
    )
except Exception:
    REPLY_STATUS_FALLBACK_MIN_SCORE = 75
REPLY_ADAPTIVE_THROTTLE = str(
    os.environ.get("XMONITOR_REPLY_ADAPTIVE_THROTTLE", "1")
).strip().lower() not in {"0", "false", "no", "off"}
REPLY_ENABLE_ACCELERATION = str(
    os.environ.get("XMONITOR_REPLY_ENABLE_ACCELERATION", "0")
).strip().lower() not in {"0", "false", "no", "off"}
try:
    REPLY_FAILURE_STREAK_SLOWDOWN_FACTOR = float(
        os.environ.get("XMONITOR_REPLY_FAILURE_SLOWDOWN_FACTOR", "1.35")
    )
except Exception:
    REPLY_FAILURE_STREAK_SLOWDOWN_FACTOR = 1.35
try:
    REPLY_QUEUE_ACCEL_FACTOR = float(
        os.environ.get("XMONITOR_REPLY_QUEUE_ACCEL_FACTOR", "0.82")
    )
except Exception:
    REPLY_QUEUE_ACCEL_FACTOR = 0.82
try:
    REPLY_FAILURE_BUDGET_MAX = int(os.environ.get("XMONITOR_REPLY_FAILURE_BUDGET_MAX", "3"))
except Exception:
    REPLY_FAILURE_BUDGET_MAX = 3
try:
    REPLY_FAILURE_COOLDOWN_SEC = int(os.environ.get("XMONITOR_REPLY_FAILURE_COOLDOWN_SEC", "900"))
except Exception:
    REPLY_FAILURE_COOLDOWN_SEC = 900
try:
    REPLY_FAILURE_WINDOW_SEC = int(os.environ.get("XMONITOR_REPLY_FAILURE_WINDOW_SEC", "1800"))
except Exception:
    REPLY_FAILURE_WINDOW_SEC = 1800
try:
    HUMANIZE_BASE_MULTIPLIER = float(os.environ.get("XMONITOR_HUMANIZE_BASE_MULTIPLIER", "1.28"))
except Exception:
    HUMANIZE_BASE_MULTIPLIER = 1.28
try:
    HUMANIZE_HEADLESS_EXTRA_MULTIPLIER = float(os.environ.get("XMONITOR_HUMANIZE_HEADLESS_EXTRA_MULTIPLIER", "0.18"))
except Exception:
    HUMANIZE_HEADLESS_EXTRA_MULTIPLIER = 0.18
DM_RECOVERY_ENABLE_RECREATE_TAB = str(
    os.environ.get("XMONITOR_DM_RECOVERY_RECREATE_TAB", "1")
).strip().lower() not in {"0", "false", "no", "off"}
DM_RECOVERY_ENABLE_RESTART_BROWSER = str(
    os.environ.get("XMONITOR_DM_RECOVERY_RESTART_BROWSER", "1")
).strip().lower() not in {"0", "false", "no", "off"}
DM_RECOVERY_ENABLE_HEADFUL_FALLBACK = str(
    os.environ.get("XMONITOR_DM_RECOVERY_HEADFUL_FALLBACK", "1")
).strip().lower() not in {"0", "false", "no", "off"}
DM_ASSUME_SUCCESS_AFTER_CLICK = str(
    os.environ.get("XMONITOR_DM_ASSUME_SUCCESS_AFTER_CLICK", "0")
).strip().lower() not in {"0", "false", "no", "off"}
DM_RECOVERY_HEADFUL_REQUIRE_DISPLAY = str(
    os.environ.get("XMONITOR_DM_RECOVERY_HEADFUL_REQUIRE_DISPLAY", "1")
).strip().lower() not in {"0", "false", "no", "off"}
HEADLESS_FORCE_TEMP_PROFILE = str(
    os.environ.get("XMONITOR_HEADLESS_FORCE_TEMP_PROFILE", "1")
).strip().lower() not in {"0", "false", "no", "off"}
try:
    HEADLESS_DIAG_MAX_HTML_CHARS = int(os.environ.get("XMONITOR_HEADLESS_DIAG_MAX_HTML_CHARS", "12000"))
except Exception:
    HEADLESS_DIAG_MAX_HTML_CHARS = 12000
HEADLESS_VERBOSE_LOG = str(
    os.environ.get("XMONITOR_HEADLESS_VERBOSE_LOG", "1")
).strip().lower() not in {"0", "false", "no", "off"}
HEADFUL_MAINTENANCE_RESTART = str(
    os.environ.get("XMONITOR_HEADFUL_MAINTENANCE_RESTART", "0")
).strip().lower() in {"1", "true", "yes", "on"}
HEADFUL_NOTIFY_DISCONNECT_RESTART = str(
    os.environ.get("XMONITOR_HEADFUL_NOTIFY_DISCONNECT_RESTART", "0")
).strip().lower() in {"1", "true", "yes", "on"}
DM_UNAVAILABLE_CACHE_TTL_SEC = 12 * 3600
CONTENT_DEDUPE_TTL_SEC = 72 * 3600
CONTENT_DEDUPE_MAX_ENTRIES = 40000
MAINTENANCE_INTERVAL_MIN_SEC = 40 * 60
MAINTENANCE_INTERVAL_MAX_SEC = 70 * 60
TASK_PARALLEL_MIN = 2
TASK_PARALLEL_MAX = 5
TASK_SUBMIT_JITTER_MIN_SEC = 0.18
TASK_SUBMIT_JITTER_MAX_SEC = 0.95
TASK_BATCH_GAP_MIN_SEC = 1.0
TASK_BATCH_GAP_MAX_SEC = 3.2
TAB_OPEN_JITTER_MIN_SEC = 0.2
TAB_OPEN_JITTER_MAX_SEC = 1.2
ARTICLE_REORDER_CHUNK_MIN = 3
ARTICLE_REORDER_CHUNK_MAX = 7
DM_FOLLOWUP_TEXT = (
    "老板您好，我是 懒猫微服 CEO 王勇，感谢您的关注与支持。\n"
    "如需了解更详细的产品资料，欢迎添加我们的工程师微信 17612774028，"
    "我们将为您提供一对一的专业介绍与支持，工程师告诉您购买方式~\n"
    "备注推特ID给您优惠。"
)
DEFAULT_NOTIFY_REPLY_TEMPLATES = [
    '老板我给您私信了',
    '老板 我私信您了',
    '大佬我私信您了',
    '大佬 我给您私信了',
    '大佬 我给您私信介绍了',
]
DEFAULT_DM_TEMPLATES = [DM_FOLLOWUP_TEXT]
DM_LLM_REWRITE_DEFAULT_PROMPT = (
    "你是私信文案改写助手。\n"
    "任务：将给定模板改写成自然、简洁、礼貌、口语化的中文私信。\n"
    "要求：\n"
    "1. 不要改变核心业务信息与联系方式。\n"
    "2. 不要输出解释，只输出最终私信正文。\n"
    "3. 语气真诚，不夸张，不添加模板中没有的承诺。\n"
    "4. 必须明显重写句式，不得大段复用原句；连续复用原文不得超过8个字。\n"
    "5. 在不改变核心信息的前提下，可替换同义表达并重排语序。\n"
    "6. 避免模板腔，不要总用“您好，我是……感谢关注”这类固定开头。\n"
    "模板如下：\n"
    "{template}"
)
DM_LLM_REWRITE_ENABLED = str(
    os.environ.get("XMONITOR_DM_LLM_REWRITE_ENABLED", "1")
).strip().lower() not in {"0", "false", "no", "off"}
DM_LLM_REWRITE_PROMPT_TEMPLATE = str(
    os.environ.get("XMONITOR_DM_LLM_REWRITE_PROMPT_TEMPLATE", DM_LLM_REWRITE_DEFAULT_PROMPT) or DM_LLM_REWRITE_DEFAULT_PROMPT
).strip()
try:
    DM_LLM_REWRITE_MAX_CHARS = int(os.environ.get("XMONITOR_DM_LLM_REWRITE_MAX_CHARS", "260"))
except Exception:
    DM_LLM_REWRITE_MAX_CHARS = 260
DM_LLM_REWRITE_MAX_CHARS = max(80, min(1200, DM_LLM_REWRITE_MAX_CHARS))
try:
    DM_LLM_REWRITE_TEMPERATURE = float(os.environ.get("XMONITOR_DM_LLM_REWRITE_TEMPERATURE", "0.7"))
except Exception:
    DM_LLM_REWRITE_TEMPERATURE = 0.7
DM_LLM_REWRITE_TEMPERATURE = max(0.0, min(1.2, DM_LLM_REWRITE_TEMPERATURE))
try:
    DM_LLM_REWRITE_MAX_REGEN = int(os.environ.get("XMONITOR_DM_LLM_REWRITE_MAX_REGEN", "2"))
except Exception:
    DM_LLM_REWRITE_MAX_REGEN = 2
DM_LLM_REWRITE_MAX_REGEN = max(0, min(5, DM_LLM_REWRITE_MAX_REGEN))
try:
    DM_LLM_REWRITE_DEDUPE_SIZE = int(os.environ.get("XMONITOR_DM_LLM_REWRITE_DEDUPE_SIZE", "200"))
except Exception:
    DM_LLM_REWRITE_DEDUPE_SIZE = 200
DM_LLM_REWRITE_DEDUPE_SIZE = max(50, min(1000, DM_LLM_REWRITE_DEDUPE_SIZE))
try:
    DM_LLM_REWRITE_SIMILARITY_MAX = float(os.environ.get("XMONITOR_DM_LLM_REWRITE_SIMILARITY_MAX", "0.86"))
except Exception:
    DM_LLM_REWRITE_SIMILARITY_MAX = 0.86
DM_LLM_REWRITE_SIMILARITY_MAX = max(0.60, min(0.98, DM_LLM_REWRITE_SIMILARITY_MAX))
try:
    DM_LLM_REWRITE_MIN_DIFF_CHARS = int(os.environ.get("XMONITOR_DM_LLM_REWRITE_MIN_DIFF_CHARS", "18"))
except Exception:
    DM_LLM_REWRITE_MIN_DIFF_CHARS = 18
DM_LLM_REWRITE_MIN_DIFF_CHARS = max(8, min(120, DM_LLM_REWRITE_MIN_DIFF_CHARS))
try:
    DM_LLM_REWRITE_MAX_SHARED_RUN = int(os.environ.get("XMONITOR_DM_LLM_REWRITE_MAX_SHARED_RUN", "14"))
except Exception:
    DM_LLM_REWRITE_MAX_SHARED_RUN = 14
DM_LLM_REWRITE_MAX_SHARED_RUN = max(6, min(28, DM_LLM_REWRITE_MAX_SHARED_RUN))
DM_CLOSED_FALLBACK_REPLY_TEXT = "大佬 您的私信是关闭的，如果有需要可以给我私信呀"
DM_REJECT_NEW_MESSAGE_OVERLAY = str(
    os.environ.get("XMONITOR_DM_REJECT_NEW_MESSAGE_OVERLAY", "1")
).strip().lower() in {"1", "true", "yes", "on"}
DM_FORCE_COMPOSER_BINDING = str(
    os.environ.get("XMONITOR_DM_FORCE_COMPOSER_BINDING", "1")
).strip().lower() in {"1", "true", "yes", "on"}
DM_LLM_DOWN_FALLBACK_TEMPLATE = str(
    os.environ.get("XMONITOR_DM_LLM_DOWN_FALLBACK_TEMPLATE", "1")
).strip().lower() in {"1", "true", "yes", "on"}
try:
    DM_PROFILE_NO_BUTTON_AS_CLOSED = str(
        os.environ.get("XMONITOR_DM_PROFILE_NO_BUTTON_AS_CLOSED", "1")
    ).strip().lower() in {"1", "true", "yes", "on"}
except Exception:
    DM_PROFILE_NO_BUTTON_AS_CLOSED = True
try:
    DM_CRITICAL_MAX_HOLD_SEC = float(os.environ.get("XMONITOR_DM_CRITICAL_MAX_HOLD_SEC", "120"))
except Exception:
    DM_CRITICAL_MAX_HOLD_SEC = 120.0
DM_CRITICAL_MAX_HOLD_SEC = max(30.0, min(900.0, float(DM_CRITICAL_MAX_HOLD_SEC)))
try:
    DM_SEND_CONFIRM_WAIT_SEC = float(os.environ.get("XMONITOR_DM_SEND_CONFIRM_WAIT_SEC", "3.0"))
except Exception:
    DM_SEND_CONFIRM_WAIT_SEC = 3.0
DM_SEND_CONFIRM_WAIT_SEC = max(0.8, min(8.0, float(DM_SEND_CONFIRM_WAIT_SEC)))
# 私信口令（Enter Passcode）自动处理默认启用，可用环境变量覆盖
DM_PASSCODE = str(os.environ.get("XMONITOR_DM_PASSCODE", "1234") or "").strip()
PROXY_ENV_KEYS = (
    "XMONITOR_PROXY",
    "ALL_PROXY",
    "all_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
)


def _parse_keywords_env(env_key, default_text=""):
    raw = str(os.environ.get(env_key, default_text) or default_text or "").strip()
    items = []
    seen = set()
    for part in re.split(r"[\n,，;；]+", raw):
        kw = str(part or "").strip().lower()
        if not kw or kw in seen:
            continue
        seen.add(kw)
        items.append(kw)
    return tuple(items)


# 为空表示不按“正文包含@xxx”做内容拦截，避免误杀通知正文
CONTENT_FILTER_BLOCKED_MENTIONS = ()
INTENT_FORCE_NOTIFY_KEYWORDS = _parse_keywords_env(
    "XMONITOR_INTENT_FORCE_NOTIFY_KEYWORDS",
    "询价,报价,多少价格,什么价格,多少钱,怎么卖,怎么买,购买方式,购买,下单,开通,试用,demo,演示,企业版,私有化,部署,合同,发票,开票,授权,代理,经销,渠道,优惠,折扣,售后,客服,联系方式,微信,vx,v我,whatsapp,telegram,算力舱,算力配置,性能,并发,吞吐,能跑多快,能跑多少"
)
INTENT_PRODUCT_KEYWORDS = _parse_keywords_env(
    "XMONITOR_INTENT_PRODUCT_KEYWORDS",
    "懒猫微服,lazycat,lazycat.cloud,应用云电脑,云电脑,内网穿透,沙箱隔离,一站式部署,大模型,deepseek,远程桌面,异地组网,家庭服务器,nas,openclaw,算力舱,算力,算力规格,cpu,gpu"
)
INTENT_CONTACT_KEYWORDS = _parse_keywords_env(
    "XMONITOR_INTENT_CONTACT_KEYWORDS",
    "微信,vx,v我,加我,联系我,联系方式,私信,电话,whatsapp,telegram,email,邮箱"
)
INTENT_CONSULT_KEYWORDS = _parse_keywords_env(
    "XMONITOR_INTENT_CONSULT_KEYWORDS",
    "咨询,了解,介绍,是否支持,支持吗,能否,可以,怎么,如何,多少钱,什么价格,报价,预算,方案,套餐,配置,规格,速度,性能,并发,吞吐,试用,部署,开通,企业版,私有化,交付,售后,发票,合同,采购"
)
INTENT_NON_TARGET_TOPIC_KEYWORDS = _parse_keywords_env(
    "XMONITOR_INTENT_NON_TARGET_TOPIC_KEYWORDS",
    "互赞,互粉,互关,抽奖,返现,领券,薅羊毛,义乌,压力给到了,压力给到,副厂配件,极影相机,vivo好,发点token,token计费,token耗尽,token烧完,iphone,安卓,诺基亚,fotorgear,手机壳,镜头,掌中宝,v998,338c"
)
INTENT_LLM_PRIMARY_MODE = str(
    os.environ.get("XMONITOR_INTENT_LLM_PRIMARY_MODE", "1")
).strip().lower() in {"1", "true", "yes", "on"}
LLM_FILTER_ENABLED = str(
    os.environ.get("XMONITOR_LLM_FILTER_ENABLED", "0")
).strip().lower() in {"1", "true", "yes", "on"}
LLM_FILTER_BASE_URL = str(os.environ.get("XMONITOR_LLM_BASE_URL", "") or "").strip()
LLM_FILTER_API_KEY = str(os.environ.get("XMONITOR_LLM_API_KEY", "EMPTY") or "").strip()
LLM_FILTER_MODEL = str(os.environ.get("XMONITOR_LLM_MODEL", "") or "").strip()
LLM_FILTER_PROMPT_TEMPLATE = str(
    os.environ.get("XMONITOR_LLM_FILTER_PROMPT_TEMPLATE", "") or ""
).strip()
LLM_INTENT_PROMPT_TEMPLATE = str(
    os.environ.get("XMONITOR_LLM_INTENT_PROMPT_TEMPLATE", "") or ""
).strip()
NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT = str(
    os.environ.get("XMONITOR_NOTIFY_VOICE_BLOCK_KEYWORDS", "") or ""
).strip()
NOTIFY_VOICE_BLOCK_KEYWORDS_BUILTIN = (
    "副厂配件",
    "极影相机",
    "vivo好",
    "发点token",
    "token计费",
    "token耗尽",
    "token烧完",
)
NOTIFY_VOICE_BLOCK_KEYWORDS = tuple(
    dict.fromkeys(
        list(NOTIFY_VOICE_BLOCK_KEYWORDS_BUILTIN)
        + [
            kw.strip().lower()
            for kw in re.split(r"[\n,，;；]+", NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT)
            if kw.strip()
        ]
    )
)
DOUBAO_TTS_APP_ID = str(
    os.environ.get("XMONITOR_DOUBAO_TTS_APP_ID", LOCAL_TTS_CONFIG.get("app_id", "")) or ""
).strip()
DOUBAO_TTS_ACCESS_TOKEN = str(
    os.environ.get("XMONITOR_DOUBAO_TTS_ACCESS_TOKEN", LOCAL_TTS_CONFIG.get("access_token", "")) or ""
).strip()
DOUBAO_TTS_SECRET_KEY = str(
    os.environ.get("XMONITOR_DOUBAO_TTS_SECRET_KEY", LOCAL_TTS_CONFIG.get("secret_key", "")) or ""
).strip()
DOUBAO_TTS_VOICE_TYPE = str(
    os.environ.get("XMONITOR_DOUBAO_TTS_VOICE_TYPE", LOCAL_TTS_CONFIG.get("voice_type", "zh_female_vv_uranus_bigtts")) or "zh_female_vv_uranus_bigtts"
).strip()
DOUBAO_TTS_CLUSTER = str(
    os.environ.get("XMONITOR_DOUBAO_TTS_CLUSTER", LOCAL_TTS_CONFIG.get("cluster", "volcano_tts")) or "volcano_tts"
).strip()
DOUBAO_TTS_ENDPOINT = str(
    os.environ.get("XMONITOR_DOUBAO_TTS_ENDPOINT", LOCAL_TTS_CONFIG.get("endpoint", "https://openspeech.bytedance.com/api/v1/tts")) or "https://openspeech.bytedance.com/api/v1/tts"
).strip()
DOUBAO_TTS_UID = str(
    os.environ.get("XMONITOR_DOUBAO_TTS_UID", LOCAL_TTS_CONFIG.get("uid", "xmonitor-notify")) or "xmonitor-notify"
).strip()
DOUBAO_TTS_ENCODING = str(
    os.environ.get("XMONITOR_DOUBAO_TTS_ENCODING", LOCAL_TTS_CONFIG.get("encoding", "mp3")) or "mp3"
).strip().lower()
try:
    DOUBAO_TTS_SPEED_RATIO = float(
        os.environ.get("XMONITOR_DOUBAO_TTS_SPEED_RATIO", LOCAL_TTS_CONFIG.get("speed_ratio", 1.0))
    )
except Exception:
    DOUBAO_TTS_SPEED_RATIO = 1.0
try:
    DOUBAO_TTS_VOLUME_RATIO = float(
        os.environ.get("XMONITOR_DOUBAO_TTS_VOLUME_RATIO", LOCAL_TTS_CONFIG.get("volume_ratio", 1.35))
    )
except Exception:
    DOUBAO_TTS_VOLUME_RATIO = 1.35
DOUBAO_TTS_VOLUME_RATIO = max(0.2, min(3.0, float(DOUBAO_TTS_VOLUME_RATIO)))
try:
    DOUBAO_TTS_PITCH_RATIO = float(
        os.environ.get("XMONITOR_DOUBAO_TTS_PITCH_RATIO", LOCAL_TTS_CONFIG.get("pitch_ratio", 1.0))
    )
except Exception:
    DOUBAO_TTS_PITCH_RATIO = 1.0
try:
    DOUBAO_TTS_TIMEOUT_SEC = float(
        os.environ.get("XMONITOR_DOUBAO_TTS_TIMEOUT_SEC", LOCAL_TTS_CONFIG.get("timeout_sec", 12.0))
    )
except Exception:
    DOUBAO_TTS_TIMEOUT_SEC = 12.0
try:
    DOUBAO_TTS_TEXT_MAX_CHARS = int(
        os.environ.get("XMONITOR_DOUBAO_TTS_TEXT_MAX_CHARS", LOCAL_TTS_CONFIG.get("text_max_chars", 160))
    )
except Exception:
    DOUBAO_TTS_TEXT_MAX_CHARS = 160
DOUBAO_TTS_ENABLED = str(
    os.environ.get(
        "XMONITOR_DOUBAO_TTS_ENABLED",
        LOCAL_TTS_CONFIG.get("enabled", "1" if (DOUBAO_TTS_APP_ID and DOUBAO_TTS_ACCESS_TOKEN) else "0"),
    )
).strip().lower() in {"1", "true", "yes", "on"}


def _safe_float(val, default_val):
    try:
        return float(val)
    except Exception:
        return float(default_val)


def _safe_int(val, default_val):
    try:
        return int(val)
    except Exception:
        return int(default_val)


def _build_notify_tts_runtime_payload(include_secrets=True):
    return _build_notify_tts_runtime_payload_impl(sys.modules[__name__], include_secrets=include_secrets)


def _normalize_notify_tts_config_from_payload(payload):
    return _normalize_notify_tts_config_from_payload_impl(payload, sys.modules[__name__])


def _apply_notify_tts_config(cfg):
    return _apply_notify_tts_config_impl(cfg, sys.modules[__name__])
try:
    LLM_FILTER_TIMEOUT_SEC = float(os.environ.get("XMONITOR_LLM_TIMEOUT_SEC", "8"))
except Exception:
    LLM_FILTER_TIMEOUT_SEC = 8.0
try:
    LLM_FILTER_TIMEOUT_MAX_SEC = float(os.environ.get("XMONITOR_LLM_TIMEOUT_MAX_SEC", "120"))
except Exception:
    LLM_FILTER_TIMEOUT_MAX_SEC = 120.0
LLM_FILTER_TIMEOUT_MAX_SEC = max(10.0, min(300.0, float(LLM_FILTER_TIMEOUT_MAX_SEC)))


def clamp_llm_timeout(raw_timeout):
    try:
        timeout_val = float(raw_timeout)
    except Exception:
        timeout_val = float(LLM_FILTER_TIMEOUT_SEC)
    return max(2.0, min(float(LLM_FILTER_TIMEOUT_MAX_SEC), timeout_val))


LLM_FILTER_TIMEOUT_SEC = clamp_llm_timeout(LLM_FILTER_TIMEOUT_SEC)
try:
    LLM_FILTER_CACHE_TTL_SEC = int(os.environ.get("XMONITOR_LLM_CACHE_TTL_SEC", str(6 * 3600)))
except Exception:
    LLM_FILTER_CACHE_TTL_SEC = 6 * 3600
try:
    LLM_FILTER_CACHE_MAX_ENTRIES = int(os.environ.get("XMONITOR_LLM_CACHE_MAX", "5000"))
except Exception:
    LLM_FILTER_CACHE_MAX_ENTRIES = 5000
LLM_HARD_FILTER_ENABLED = str(
    os.environ.get("XMONITOR_LLM_HARD_FILTER_ENABLED", "0")
).strip().lower() in {"1", "true", "yes", "on"}

# --- 全局浏览器实例 (单浏览器多标签页模式) ---
global_browser = None
global_browser_dir = None
browser_initialized = False
browser_force_temp_profile = False  # 检测到固定 profile 冲突后，后续初始化优先使用临时目录

reply_action_lock = threading.Lock()
reply_rate_limit_lock = threading.Lock()
reply_work_tab = None
reply_work_tab_lock = threading.Lock()
reply_flow_state_lock = threading.Lock()
reply_flow_active = False
dm_passcode_warmed = False
dm_passcode_lock = threading.Lock()
dm_rate_limit_lock = threading.Lock()
dm_critical_lock = threading.RLock()
dm_critical_state_lock = threading.Lock()
dm_critical_depth = 0
dm_critical_started_at = 0.0
dm_critical_last_skip_log_ts = 0.0
dm_critical_last_timeout_warn_ts = 0.0
reply_metrics_lock = threading.Lock()
notify_reply_templates = list(DEFAULT_NOTIFY_REPLY_TEMPLATES)
dm_message_templates = list(DEFAULT_DM_TEMPLATES)
last_reply_action_ts = 0.0
last_dm_action_ts = 0.0
last_reply_prepare_refresh_ts = 0.0
reply_outcome_recent = deque(maxlen=50)  # 最近回复成功/失败，用于自适应节流
reply_failure_streak = 0
reply_handle_failures = {}  # {handle: {"count": int, "first_ts": float, "cooldown_until": float, "last_err": str}}
notify_dm_user_cooldown = {}  # {handle: {"until": float, "task_key": str}}
notify_dm_user_cooldown_lock = threading.Lock()
dm_unavailable_cache = {}  # {handle: expire_ts}
dm_unavailable_cache_lock = threading.Lock()
llm_filter_cache = {}  # {signature: {"ts": float, "skip": bool, "reason": str}}
llm_filter_cache_lock = threading.Lock()
dm_llm_rewrite_history = deque(maxlen=DM_LLM_REWRITE_DEDUPE_SIZE)  # 最近改写签名
dm_llm_rewrite_lock = threading.Lock()

# --- 线程池 (根据任务数动态调整) ---
task_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

# --- 持久通知标签页 ---
notification_tab = None
notification_tab_lock = threading.Lock()
monitor_thread = None
monitor_thread_lock = threading.Lock()
content_dedupe = {}  # {signature: last_seen_ts}
notification_refresh_interval = random.uniform(NOTIFICATION_REFRESH_INTERVAL_MIN_SEC, NOTIFICATION_REFRESH_INTERVAL_MAX_SEC)
notification_last_refresh_at = 0.0
notification_disconnect_streak = 0
notification_empty_article_streak = 0

runtime_state = _build_runtime_state_impl(sys.modules[__name__])
monitor_tasks_repo = MonitorTasksRepository(sys.modules[__name__])
pending_results_repo = PendingResultsRepository(sys.modules[__name__])
processed_users_repo = ProcessedUsersRepository(sys.modules[__name__])
notify_state_facade = NotifyStateFacade(sys.modules[__name__])

def _set_runtime_attr(name, value):
    return _set_runtime_attr_impl(sys.modules[__name__], name, value)

def _get_runtime_attr(name, default=None):
    return _get_runtime_attr_impl(sys.modules[__name__], name, default=default)


def _enter_dm_critical(section='dm_send'):
    return _enter_dm_critical_impl(sys.modules[__name__], section=section)


def _leave_dm_critical():
    return _leave_dm_critical_impl(sys.modules[__name__])


def _is_dm_critical_active():
    return _is_dm_critical_active_impl(sys.modules[__name__])


def _maybe_log_dm_critical_skip():
    return _maybe_log_dm_critical_skip_impl(sys.modules[__name__])


def is_persistent_browser_profile_dir(path):
    if not path or not BROWSER_PROFILE_PERSIST:
        return False
    try:
        return os.path.abspath(path) == os.path.abspath(BROWSER_PROFILE_DIR)
    except Exception:
        return False


def create_browser_user_data_dir(prefer_persistent=True):
    """创建浏览器用户目录：默认固定持久目录，可在运行时回退到临时目录。"""
    if BROWSER_PROFILE_PERSIST and prefer_persistent:
        os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)
        return BROWSER_PROFILE_DIR
    return tempfile.mkdtemp()


def cleanup_browser_user_data_dir(path):
    """清理浏览器用户目录：固定持久目录不删除。"""
    if not path or is_persistent_browser_profile_dir(path):
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def _pid_exists(pid):
    return _pid_exists_impl(pid)


def _extract_singleton_lock_pid(profile_dir):
    return _extract_singleton_lock_pid_impl(profile_dir)


def _cleanup_stale_profile_singletons(profile_dir):
    return _cleanup_stale_profile_singletons_impl(profile_dir)


def _list_profile_bound_browser_pids(profile_dir):
    return _list_profile_bound_browser_pids_impl(profile_dir)


def _terminate_pids(pids, term_wait=1.6, kill_wait=0.8):
    return _terminate_pids_impl(pids, term_wait=term_wait, kill_wait=kill_wait)


def _auto_cleanup_profile_runtime(profile_dir):
    return _auto_cleanup_profile_runtime_impl(profile_dir)


def _is_profile_locked_by_alive_process(profile_dir):
    return _is_profile_locked_by_alive_process_impl(profile_dir)


def init_global_browser():
    return _init_global_browser_impl(sys.modules[__name__])

def cleanup_global_browser():
    return _cleanup_global_browser_impl(sys.modules[__name__])

def restart_global_browser():
    return _restart_global_browser_impl(sys.modules[__name__])

def run_headful_soft_maintenance(blocked_users, notify_enabled):
    return _run_headful_soft_maintenance_impl(blocked_users, notify_enabled, sys.modules[__name__])


def monitoring_loop():
    return _monitoring_loop_impl(sys.modules[__name__])


def save_state():
    return _save_state_impl(sys.modules[__name__])

def load_state():
    return _load_state_impl(sys.modules[__name__])

def save_processed_users():
    return _save_processed_users_impl(sys.modules[__name__])


def _sanitize_template_list(raw_list, fallback_list):
    """清洗模板列表：去空、去重、保序；若为空则回退默认。"""
    return _sanitize_template_list_impl(raw_list, fallback_list)


def _normalize_keyword_lines(raw_text):
    """将多行/逗号分隔关键词清洗为去重后的列表。"""
    return _normalize_keyword_lines_impl(raw_text)


def _render_llm_prompt_template(template_text, content, fallback_prompt):
    return _render_llm_prompt_template_impl(template_text, content, fallback_prompt)


def _get_template_list_and_limit(template_type):
    """返回模板列表引用和长度限制。"""
    if template_type == "reply":
        return notify_reply_templates, 180
    if template_type == "dm":
        return dm_message_templates, 4000
    return None, None

# --- 日志 ---
logging.basicConfig(level=logging.INFO)
def log_to_ui(level, msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} [{level.upper()}] {msg}"
    print(line)
    try:
        with open(RUNTIME_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    msg_queue.put({"type": "log", "level": level, "msg": msg})


def publish_new_data_event(item):
    """发布前端增量事件（广播语义，多客户端互不抢占）。"""
    return _publish_new_data_event_impl(item, sys.modules[__name__])


def enqueue_new_data(item):
    """统一的新数据入前端通道。"""
    publish_new_data_event(item)


def drain_msg_queue(collect_new_data=False):
    """清理旧队列消息，避免日志消息堆积导致内存持续增长。"""
    return _drain_msg_queue_impl(sys.modules[__name__], collect_new_data=collect_new_data)


def is_headless_verbose_logging_enabled():
    return bool(headless_mode and HEADLESS_VERBOSE_LOG)


def log_headless_debug(msg):
    if is_headless_verbose_logging_enabled():
        log_to_ui("debug", f"🧪 [HEADLESS] {msg}")


def log_headless_exception(context, err):
    if not is_headless_verbose_logging_enabled():
        return
    log_to_ui("error", f"🧪 [HEADLESS] {context}异常: {err}")
    try:
        log_to_ui("debug", f"🧪 [HEADLESS][TRACE] {traceback.format_exc()}")
    except Exception:
        pass


def _as_json_safe(obj):
    return _as_json_safe_impl(obj)


def _probe_selectors_snapshot(tab, selectors):
    return _probe_selectors_snapshot_impl(tab, selectors)


def _capture_runtime_diagnostic(tab, stage, err=None, selectors=None, extra=None):
    return _capture_runtime_diagnostic_impl(
        tab,
        stage,
        sys.modules[__name__],
        err=err,
        selectors=selectors,
        extra=extra,
    )


def get_random_notification_interval():
    """生成通知扫描随机间隔，避免固定节奏。"""
    return _get_random_notification_interval_impl(sys.modules[__name__])


def get_random_notification_refresh_interval():
    """生成通知页刷新间隔（秒），避免每轮都刷新页面。"""
    return _get_random_notification_refresh_interval_impl(sys.modules[__name__])


def _schedule_next_notification_refresh_interval(previous_interval=None):
    """生成下一次通知刷新间隔，带惯性和冷却随机化。"""
    return _schedule_next_notification_refresh_interval_impl(previous_interval, sys.modules[__name__])


def get_random_maintenance_interval():
    """生成浏览器维护间隔（秒）。"""
    return _get_random_maintenance_interval_impl(sys.modules[__name__])


def get_random_task_parallel(task_count):
    """按任务数返回随机并发数，避免每轮固定并发模式。"""
    return _get_random_task_parallel_impl(task_count, sys.modules[__name__])


def reorder_articles_for_scan(articles):
    return _reorder_articles_for_scan_impl(articles, sys.modules[__name__])


def get_browser_proxy():
    """从环境变量读取代理配置。"""
    for key in PROXY_ENV_KEYS:
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return ""


EMOJI_UNICODE_RANGES = (
    (0x1F1E6, 0x1F1FF),  # flags
    (0x1F300, 0x1F5FF),
    (0x1F600, 0x1F64F),
    (0x1F680, 0x1F6FF),
    (0x1F700, 0x1F77F),
    (0x1F780, 0x1F7FF),
    (0x1F800, 0x1F8FF),
    (0x1F900, 0x1F9FF),
    (0x1FA00, 0x1FAFF),
    (0x2600, 0x26FF),
    (0x2700, 0x27BF),
)
EMOJI_JOINER_CHARS = {"\u200d", "\ufe0f", "\u20e3"}


def _normalize_content_for_filter(content):
    return _normalize_content_for_filter_impl(content)


def _contains_emoji_char(ch):
    return _contains_emoji_char_impl(ch, sys.modules[__name__])


def _is_emoji_only_content(content):
    return _is_emoji_only_content_impl(content, sys.modules[__name__])


def should_skip_content_by_policy(content, allow_llm_hard_filter=None):
    return _should_skip_content_by_policy_impl(
        content,
        sys.modules[__name__],
        allow_llm_hard_filter=allow_llm_hard_filter,
    )


def _llm_filter_endpoint(base_url=None):
    return _llm_filter_endpoint_impl(sys.modules[__name__], base_url=base_url)


def _llm_runtime_ready(base_url=None, model=None):
    return _llm_runtime_ready_impl(sys.modules[__name__], base_url=base_url, model=model)


def _llm_filter_is_ready(base_url=None, model=None, enabled=None):
    return _llm_filter_is_ready_impl(
        sys.modules[__name__],
        base_url=base_url,
        model=model,
        enabled=enabled,
    )


def _doubao_tts_is_ready():
    return _doubao_tts_is_ready_impl(sys.modules[__name__])


def _doubao_tts_mime_by_encoding(encoding):
    return _doubao_tts_mime_by_encoding_impl(encoding)


def _truncate_text_for_tts(text):
    return _truncate_text_for_tts_impl(text, sys.modules[__name__])


def _synthesize_doubao_tts_audio_base64(text):
    return _synthesize_doubao_tts_audio_base64_impl(text, sys.modules[__name__])


def _prune_llm_filter_cache(now_ts=None):
    return _prune_llm_filter_cache_impl(sys.modules[__name__], now_ts=now_ts)


def _parse_json_object_from_text(raw_text):
    return _parse_json_object_from_text_impl(raw_text)


def _call_openai_compatible_json(
    system_prompt,
    user_prompt,
    *,
    base_url=None,
    api_key=None,
    model=None,
    timeout_sec=None,
    max_tokens=120,
    temperature=0.0,
):
    return _call_openai_compatible_json_impl(
        system_prompt,
        user_prompt,
        sys.modules[__name__],
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_sec=timeout_sec,
        max_tokens=max_tokens,
        temperature=temperature,
    )


def _guess_ollama_native_endpoint(base_url):
    return _guess_ollama_native_endpoint_impl(base_url, sys.modules[__name__])


def _call_ollama_native_json(system_prompt, user_prompt, *, base_url=None, model=None, timeout_sec=None):
    return _call_ollama_native_json_impl(
        system_prompt,
        user_prompt,
        sys.modules[__name__],
        base_url=base_url,
        model=model,
        timeout_sec=timeout_sec,
    )


def _normalize_dm_rewrite_signature(text):
    return _normalize_dm_rewrite_signature_impl(text, sys.modules[__name__])


def _build_dm_llm_rewrite_prompt(template_text):
    return _build_dm_llm_rewrite_prompt_impl(template_text, sys.modules[__name__])


def _dm_rewrite_longest_common_substring_len(source_text, generated_text):
    return _dm_rewrite_longest_common_substring_len_impl(source_text, generated_text, sys.modules[__name__])


def _extract_dm_rewrite_forbidden_phrases(template_text, max_items=5):
    return _extract_dm_rewrite_forbidden_phrases_impl(template_text, sys.modules[__name__], max_items=max_items)


def _dm_rewrite_contains_forbidden_phrase(generated_text, forbidden_phrases):
    return _dm_rewrite_contains_forbidden_phrase_impl(generated_text, forbidden_phrases, sys.modules[__name__])


def _dm_rewrite_similarity_score(source_text, generated_text):
    return _dm_rewrite_similarity_score_impl(source_text, generated_text, sys.modules[__name__])


def _dm_rewrite_is_too_similar(source_text, generated_text):
    return _dm_rewrite_is_too_similar_impl(source_text, generated_text, sys.modules[__name__])


def _record_dm_llm_rewrite_signature(sig):
    return _record_dm_llm_rewrite_signature_impl(sig, sys.modules[__name__])


def _is_dm_llm_rewrite_duplicate(sig):
    return _is_dm_llm_rewrite_duplicate_impl(sig, sys.modules[__name__])


def _generate_dm_text_with_llm(template_text):
    return _generate_dm_text_with_llm_impl(template_text, sys.modules[__name__])


def _call_openai_compatible_filter_api(content):
    return _call_openai_compatible_filter_api_impl(content, sys.modules[__name__])


def _score_to_intent_level(score):
    val = int(max(0, min(100, int(score))))
    if val >= 75:
        return "high"
    if val >= 50:
        return "medium"
    if val >= 25:
        return "low"
    return "noise"


def _intent_level_rank(level):
    lv = str(level or "").strip().lower()
    if lv == "high":
        return 4
    if lv == "medium":
        return 3
    if lv == "low":
        return 2
    return 1


def _max_intent_level(*levels):
    best = "noise"
    best_rank = 0
    for lv in levels:
        r = _intent_level_rank(lv)
        if r > best_rank:
            best_rank = r
            best = str(lv or "").strip().lower() or "noise"
    return best


def _is_negative_intent_reason(reason_text):
    return _is_negative_intent_reason_impl(reason_text)


def _find_keyword_hits(text_lower, keywords):
    return _find_keyword_hits_impl(text_lower, keywords)


def _is_short_reply_intent_signal(content):
    return _is_short_reply_intent_signal_impl(content)


def _is_performance_consult_signal(content):
    return _is_performance_consult_signal_impl(content)


def _is_non_business_meme_signal(content):
    return _is_non_business_meme_signal_impl(content)


def _is_business_consult_signal(content):
    return _is_business_consult_signal_impl(content, sys.modules[__name__])


def _rule_based_intent_analysis(content):
    return _rule_based_intent_analysis_impl(content, sys.modules[__name__])


def _build_intent_analysis_prompt(content):
    return _build_intent_analysis_prompt_impl(content, sys.modules[__name__])


def _llm_intent_analysis(content, *, base_url=None, api_key=None, model=None, timeout_sec=None):
    return _llm_intent_analysis_impl(
        content,
        sys.modules[__name__],
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_sec=timeout_sec,
    )


def analyze_comment_intent(content, *, base_url=None, api_key=None, model=None, timeout_sec=None):
    return _analyze_comment_intent_impl(content, sys.modules[__name__], base_url=base_url, api_key=api_key, model=model, timeout_sec=timeout_sec)


def _should_notify_voice_by_intent(analysis):
    return _should_notify_voice_by_intent_impl(analysis)


def _should_skip_by_llm_filter(content):
    return _should_skip_by_llm_filter_impl(content, sys.modules[__name__])


def normalize_content_for_dedupe(content):
    return _normalize_content_for_dedupe_impl(content)


def make_content_signature(handle, content):
    return _make_content_signature_impl(handle, content, sys.modules[__name__])


def prune_content_dedupe(now_ts=None):
    return _prune_content_dedupe_impl(sys.modules[__name__], now_ts=now_ts)


def should_skip_duplicate_content(handle, content, now_ts=None):
    return _should_skip_duplicate_content_impl(handle, content, sys.modules[__name__], now_ts=now_ts)

# --- 辅助函数 ---
def get_browser_path():
    paths = ["/usr/bin/chromium", "/usr/bin/google-chrome-stable", "/usr/bin/google-chrome", "/snap/bin/chromium"]
    for p in paths:
        if os.path.exists(p): return p
    return None

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0)) 
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def is_port_available(port, host='127.0.0.1'):
    """检查端口是否可绑定。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, int(port)))
        return True
    except Exception:
        return False


def resolve_server_port():
    """解析服务端口。"""
    return _resolve_server_port_impl(
        os.environ.get('XMONITOR_PORT', ''),
        is_port_available_fn=is_port_available,
        get_free_port_fn=get_free_port,
        logging_module=logging,
    )

# --- 爬虫核心 ---
def init_browser_options(port, user_data_path, force_headless=None, safe_mode=False):
    return _init_browser_options_impl(
        port,
        user_data_path,
        sys.modules[__name__],
        force_headless=force_headless,
        safe_mode=safe_mode,
    )


def get_effective_delegated_account():
    """返回当前生效的委派账户（未启用时返回空字符串）。"""
    if not delegated_enabled:
        return ""
    return str(delegated_account or "").strip()


def get_current_account_handle(page):
    return _get_current_account_handle_impl(page)


def ensure_delegated_account_session(page, target_account):
    return _ensure_delegated_account_session_impl(page, target_account, sys.modules[__name__])

def scan_page_content(page, url, blocked_list):
    return _scan_page_content_impl(page, url, blocked_list, sys.modules[__name__])


def switch_to_delegated_account(page, target_account):
    return _switch_to_delegated_account_impl(page, target_account, sys.modules[__name__])


def _parse_notification_age_minutes(article):
    return _parse_notification_age_minutes_impl(article)

def _extract_notification_handle(article, article_text):
    return _extract_notification_handle_impl(article, article_text)

def _normalize_notification_text(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def _extract_notification_content(article, article_text, handle):
    """提取通知内容：多来源候选 + 过滤 + 打分，避免把用户名称误当正文。"""
    return _extract_notification_content_impl(
        article,
        article_text,
        handle,
        normalize_notification_text_fn=_normalize_notification_text,
        is_noise_notification_text_fn=_is_noise_notification_text,
        score_notification_candidate_fn=_score_notification_candidate,
    )

def _extract_status_from_href(href):
    """从单个 href 提取 status 用户和 status_id。"""
    return _extract_status_from_href_impl(href, pick_best_status_id_fn=_pick_best_status_id)

def _extract_notification_status_info(article):
    """提取通知关联的 status 用户和 status_id。"""
    return _extract_notification_status_info_impl(
        article,
        extract_status_from_href_fn=_extract_status_from_href,
        pick_best_status_id_fn=_pick_best_status_id,
    )

def _collect_notification_hrefs(article, max_links=4):
    """提取通知卡片中的链接样本，帮助定位 status_id 提取失败问题。"""
    return _collect_notification_hrefs_impl(article, max_links=max_links)

def _collect_notification_tweet_texts(article, max_items=2):
    return _collect_notification_tweet_texts_impl(article, max_items=max_items, normalize_one_line_fn=_normalize_one_line)

def scan_notifications_page(page, blocked_list, max_recent_minutes=None):
    return _scan_notifications_page_impl(page, blocked_list, max_recent_minutes, sys.modules[__name__])

def scan_persistent_notification_tab(blocked_users, max_recent_minutes=None):
    return _scan_persistent_notification_tab_impl(blocked_users, sys.modules[__name__], max_recent_minutes=max_recent_minutes)

def scan_task_worker(task, page, blocked_users):
    return _scan_task_worker_impl(task, page, blocked_users, sys.modules[__name__])


def scan_task_with_tab(task, blocked_users):
    return _scan_task_with_tab_impl(task, blocked_users, sys.modules[__name__])


def scan_page_content_with_tab(tab, url, blocked_list):
    return _scan_page_content_with_tab_impl(tab, url, blocked_list, sys.modules[__name__])


def init_notification_tab(blocked_users):
    return _init_notification_tab_impl(blocked_users, sys.modules[__name__])


def close_notification_tab():
    return _close_notification_tab_impl(sys.modules[__name__])


def ensure_notification_tab(blocked_users):
    return _ensure_notification_tab_impl(blocked_users, sys.modules[__name__])


def start_monitor_thread():
    return _start_monitor_thread_impl(sys.modules[__name__])


def stop_monitor_thread(wait_timeout=15):
    return _stop_monitor_thread_impl(sys.modules[__name__], wait_timeout=wait_timeout)


def extract_status_id_from_notification_item(item):
    return _extract_status_id_from_notification_item_impl(item, pick_best_status_id_fn=_pick_best_status_id)

def is_reply_to_me_notification_item(item):
    return _is_reply_to_me_notification_item_impl(item, reply_to_you_keywords=NOTIFICATION_REPLY_TO_YOU_KEYWORDS)

def _extract_status_ids_from_article(article):
    return _extract_status_ids_from_article_impl(article, pick_best_status_id_fn=_pick_best_status_id)

def _match_reply_target_article(page, status_id, handle, content):
    return _match_reply_target_article_impl(
        page,
        status_id,
        handle,
        content,
        extract_status_ids_from_article_fn=_extract_status_ids_from_article,
        normalize_handle_fn=normalize_handle,
        normalize_content_for_dedupe_fn=normalize_content_for_dedupe,
    )

def _match_notification_card_for_reply(page, status_id, handle, content):
    return _match_notification_card_for_reply_impl(
        page,
        status_id,
        handle,
        content,
        extract_notification_status_info_fn=_extract_notification_status_info,
        extract_notification_handle_fn=_extract_notification_handle,
        extract_notification_content_fn=_extract_notification_content,
        normalize_handle_fn=normalize_handle,
        normalize_content_for_dedupe_fn=normalize_content_for_dedupe,
    )

def ensure_reply_work_tab(force_recreate=False):
    """确保回复专用工作标签页可用（复用同一标签页）。"""
    return _ensure_reply_work_tab_impl(sys.modules[__name__], force_recreate=force_recreate)


def _set_reply_flow_active(active):
    return _set_reply_flow_active_deps_impl(active, sys.modules[__name__])


def _is_reply_flow_active():
    return _is_reply_flow_active_deps_impl(sys.modules[__name__])




def _get_humanize_multiplier():
    """根据模式与近期稳定性计算人类化延时倍率。"""
    return _get_humanize_multiplier_impl(
        headless_mode=headless_mode,
        base_multiplier=HUMANIZE_BASE_MULTIPLIER,
        headless_extra_multiplier=HUMANIZE_HEADLESS_EXTRA_MULTIPLIER,
        reply_metrics_lock=reply_metrics_lock,
        reply_failure_streak=lambda: reply_failure_streak,
    )


def _get_adaptive_reply_gap_factor():
    """计算回复节奏的动态倍率。>1 更慢，<1 更快。"""
    return _get_adaptive_reply_gap_factor_impl(
        adaptive_enabled=REPLY_ADAPTIVE_THROTTLE,
        acceleration_enabled=REPLY_ENABLE_ACCELERATION,
        reply_metrics_lock=reply_metrics_lock,
        reply_outcome_recent=reply_outcome_recent,
        reply_failure_streak=lambda: reply_failure_streak,
        queue_depth=notify_state_facade.get_pending_notify_count(),
        queue_accel_factor=REPLY_QUEUE_ACCEL_FACTOR,
    )


def _check_reply_failure_budget(handle):
    """失败预算熔断已关闭：始终允许继续尝试，不做冷却拦截。"""
    return True, ""

def _reserve_notify_dm_user_slot(handle, task_key=""):
    """同一用户短时间内只允许一个私信任务，避免重复触发。"""
    return _reserve_notify_dm_user_slot_impl(
        handle,
        task_key,
        normalize_handle_fn=normalize_handle,
        cooldown_dict=notify_dm_user_cooldown,
        cooldown_lock=notify_dm_user_cooldown_lock,
        cooldown_sec=DM_USER_COOLDOWN_SEC,
    )


def _record_reply_outcome(handle, ok, err=""):
    """记录回复结果，供自适应节流和失败熔断使用。"""
    return _record_reply_outcome_deps_impl(handle, ok, err, sys.modules[__name__])

def _should_use_share_link_quick_path():
    """是否启用快速链接路径：只在长队列且近期稳定时启用。"""
    return _should_use_share_link_quick_path_impl(sys.modules[__name__])


def _throttle_reply_action_if_needed():
    """限制回复动作速率，降低账号风控概率。"""
    return _throttle_reply_action_if_needed_impl(sys.modules[__name__])


def _throttle_dm_action_if_needed(stage_text="私信发送"):
    """限制私信发送节奏，避免短时间内固定频率动作。"""
    return _throttle_dm_action_if_needed_impl(sys.modules[__name__], stage_text=stage_text)


def _dm_humanized_idle(tab, low=0.08, high=0.28, stage_text="私信动作"):
    """私信流程的人类化随机停顿与轻微滚动。"""
    return _dm_humanized_idle_impl(tab, sys.modules[__name__], low=low, high=high, stage_text=stage_text)


def _humanized_type_dm_text(tab, editor, dm_text):
    return _humanized_type_dm_text_impl(
        tab,
        editor,
        dm_text,
        idle_func=_dm_humanized_idle,
        log_debug=log_headless_debug,
    )


def _paste_dm_text_exact(tab, editor, dm_text):
    return _paste_dm_text_exact_impl(
        tab,
        editor,
        dm_text,
        idle_func=_dm_humanized_idle,
        log_debug=log_headless_debug,
    )


def _refresh_dm_editor_state(tab, editor, dm_text):
    return _refresh_dm_editor_state_impl(tab, editor, dm_text)


def _poke_dm_editor_events(tab, editor):
    return _poke_dm_editor_events_impl(tab, editor)


def _humanized_gap_between_dm_messages(tab):
    return _humanized_gap_between_dm_messages_impl(
        tab,
        idle_func=_dm_humanized_idle,
        humanize_multiplier_fn=_get_humanize_multiplier,
        min_sec=DM_BETWEEN_MESSAGES_MIN_SEC,
        max_sec=DM_BETWEEN_MESSAGES_MAX_SEC,
        log_ui=log_to_ui,
        log_debug=log_headless_debug,
    )


def _is_unhandled_prompt_error(err):
    """判断是否属于浏览器未处理提示框导致的异常。"""
    err_text = str(err or "").lower()
    keywords = [
        "存在未处理的提示框",
        "未处理的提示框",
        "unhandled prompt",
        "unexpected alert open",
        "unexpectedalertpresent",
        "alert open",
    ]
    return any(k in err_text for k in keywords)


def _dismiss_pending_browser_prompt(tab, max_rounds=2):
    return _dismiss_pending_browser_prompt_impl(tab, sys.modules[__name__], max_rounds=max_rounds)


def _install_headless_dialog_guard(tab):
    return _install_headless_dialog_guard_impl(tab, sys.modules[__name__])


def _prepare_reply_prompt_guard(tab, stage=""):
    """回复流程中统一处理提示框，避免无头模式被未处理对话框打断。"""
    handled = _dismiss_pending_browser_prompt(tab, max_rounds=(4 if headless_mode else 2))
    _install_headless_dialog_guard(tab)
    if handled > 0:
        stage_text = f"{stage} " if stage else ""
        log_to_ui("debug", f"🧯 {stage_text}已自动处理提示框 {handled} 次")
    return handled


def _is_cross_world_click_error(err):
    msg = str(err or "").lower()
    return (
        "same javascript world" in msg
        or "argument should belong to the same javascript world" in msg
        or "object reference chain is too long" in msg
    )


def _click_first_actionable_by_selectors(tab, selectors):
    return _click_first_actionable_by_selectors_impl(tab, selectors)


def _click_with_prompt_guard(tab, element, action_name, refetch_selectors=None):
    return _click_with_prompt_guard_impl(
        tab,
        element,
        action_name,
        sys.modules[__name__],
        refetch_selectors=refetch_selectors,
    )


def _reply_humanized_idle(tab, low=0.16, high=0.46, stage_text='回复步骤'):
    return _reply_humanized_idle_impl(tab, sys.modules[__name__], low=low, high=high, stage_text=stage_text)


def _is_dm_unavailable_cached(handle):
    return _is_dm_unavailable_cached_impl(handle, sys.modules[__name__])


def _mark_dm_unavailable(handle):
    return _mark_dm_unavailable_impl(handle, sys.modules[__name__])


def _clear_dm_unavailable_cache(handle):
    return _clear_dm_unavailable_cache_impl(handle, sys.modules[__name__])


def _get_status_link_from_item(item, matched_status_handle=None, matched_status_id=None):
    return _get_status_link_from_item_impl(item, sys.modules[__name__], matched_status_handle=matched_status_handle, matched_status_id=matched_status_id)


def _click_share_copy_link(tab, target_article, fallback_link):
    return _click_share_copy_link_impl(tab, target_article, fallback_link, sys.modules[__name__])


def _handle_dm_passcode_prompt(tab):
    return _handle_dm_passcode_prompt_impl(tab, sys.modules[__name__])


def _warmup_dm_passcode_if_needed(tab, force=False):
    return _warmup_dm_passcode_if_needed_impl(tab, sys.modules[__name__], force=force)


def _open_dm_editor_for_handle(tab, handle, ignore_cached_unavailable=False):
    return _open_dm_editor_for_handle_impl(tab, handle, deps=sys.modules[__name__], ignore_cached_unavailable=ignore_cached_unavailable)

def _send_dm_message(tab, text):
    return _send_dm_message_impl(tab, text, sys.modules[__name__])


def _send_dm_message_with_retry(tab, text, handle=""):
    return _send_dm_message_with_retry_impl(tab, text, handle=handle, deps=sys.modules[__name__])


def _read_dm_session_state(tab, handle=""):
    return _read_dm_session_state_impl(tab, handle=handle, deps=sys.modules[__name__])


def _ensure_dm_session_ready_for_handle(tab, handle, allow_reopen=True):
    """发送前会话闸门：保证在目标私信会话中且编辑器可用。"""
    return _ensure_dm_session_ready_for_handle_impl(tab, handle, sys.modules[__name__], allow_reopen=allow_reopen)


def _ensure_dm_context_for_handle(tab, handle):
    """保证当前页面处于可发送私信的上下文，避免流程被跳回主页。"""
    return _ensure_dm_context_for_handle_impl(tab, handle, sys.modules[__name__])


def _confirm_dm_closed_dual_stage(tab, handle):
    return _confirm_dm_closed_dual_stage_impl(tab, handle, sys.modules[__name__])


def _run_dm_send_sequence_once(
    tab,
    dm_handle,
    share_link,
    dm_text,
    mark_func=None,
    progress=None,
    dm_text_supplier=None,
):
    return _run_dm_send_sequence_once_impl(
        tab,
        dm_handle,
        share_link,
        dm_text,
        sys.modules[__name__],
        mark_func=mark_func,
        progress=progress,
        dm_text_supplier=dm_text_supplier,
    )


def _run_dm_send_with_recovery(
    tab,
    dm_handle,
    share_link,
    dm_text,
    mark_func=None,
    best_effort=False,
    progress=None,
    dm_text_supplier=None,
):
    return _run_dm_send_with_recovery_impl(
        tab,
        dm_handle,
        share_link,
        dm_text,
        sys.modules[__name__],
        mark_func=mark_func,
        best_effort=best_effort,
        progress=progress,
        dm_text_supplier=dm_text_supplier,
    )


def send_notification_reply(item, message, dm_message=""):
    return _send_notification_reply_impl(item, message, sys.modules[__name__], dm_message=dm_message)


app = create_flask_app(__name__, sys.modules[__name__])

if __name__ == '__main__':
    # 清理残留浏览器进程
    os.system("killall chromium 2>/dev/null")
    os.system("killall google-chrome 2>/dev/null")

    # 确保数据目录存在
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
            print(f"📁 创建数据目录: {DATA_DIR}")
        else:
            print(f"📂 数据目录: {DATA_DIR}")
    except PermissionError:
        print(f"❌ 错误: 无权限创建数据目录 {DATA_DIR}")
        print(f"💡 请确保当前用户有写入权限，或使用相对路径")
        exit(1)
    except Exception as e:
        print(f"❌ 创建数据目录失败: {e}")
        exit(1)

    # 加载持久化数据
    print("=" * 60)
    print("🚀 X Monitor V10.4 (通知监控版) 启动中...")
    print("=" * 60)
    load_state()
    server_port, port_source = resolve_server_port()
    print("=" * 60)
    print(f"✅ 服务已启动: http://127.0.0.1:{server_port}")
    if port_source == "random":
        print("🔀 启动端口模式: 随机可用端口")
    else:
        print(f"📌 启动端口模式: 指定端口(XMONITOR_PORT={server_port})")
    print(f"📂 数据目录: {DATA_DIR}")
    print("=" * 60)

    try:
        # 关闭 werkzeug 的 HTTP 请求日志
        import logging as flask_logging
        log = flask_logging.getLogger('werkzeug')
        log.setLevel(flask_logging.ERROR)

        app.run(host='0.0.0.0', port=server_port, debug=False)
    except KeyboardInterrupt:
        print("\n🛑 正在停止服务...")
        save_state()
        save_processed_users()
        print("💾 数据已保存")
        print("👋 再见！")
