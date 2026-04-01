import os
import sys
import difflib
import hashlib
import logging
import threading
import time

DEPS = sys.modules[__name__]

from xmonitor.services.dm.common import (
    normalize_handle,
    normalize_text_for_compare as _normalize_text_for_compare,
    pick_best_status_id as _pick_best_status_id,
    sanitize_dm_message_text as _sanitize_dm_message_text,
)
from xmonitor.services.notify.text import (
    NOTIFICATION_REPLY_TO_YOU_KEYWORDS,
    is_noise_notification_text as _is_noise_notification_text,
    normalize_one_line as _normalize_one_line,
    score_notification_candidate as _score_notification_candidate,
)
from xmonitor.web.app_factory import create_flask_app
from xmonitor.services.audio.server_audio import detect_server_audio_player as _detect_server_audio_player_impl
from xmonitor.runtime.config_helpers import (
    get_data_dir as _get_data_dir_impl,
    get_default_user_data_dir as _get_default_user_data_dir_impl,
    parse_backoff_seconds as _parse_backoff_seconds_impl,
)
from xmonitor.runtime.app_context import initialize_app_context as _initialize_app_context_impl
from xmonitor.runtime.startup_support import (
    ensure_directory as _ensure_directory_impl,
    load_local_json_config as _load_local_json_config_impl,
    migrate_legacy_state_files as _migrate_legacy_state_files_impl,
    save_local_json_config as _save_local_json_config_impl,
)
from xmonitor.runtime.bootstrap_runtime import run_app_entry as _run_app_entry_impl
from xmonitor.runtime.settings.tts import (
    load_tts_runtime_settings as _load_tts_runtime_settings_impl,
    safe_float as _safe_float_impl,
    safe_int as _safe_int_impl,
)
from xmonitor.runtime.settings.llm import (
    clamp_llm_timeout as _clamp_llm_timeout_impl,
    load_llm_runtime_settings as _load_llm_runtime_settings_impl,
    parse_keywords_env as _parse_keywords_env_impl,
)
from xmonitor.runtime.settings.flow import load_flow_runtime_settings as _load_flow_runtime_settings_impl
from xmonitor.runtime.module_assembly import assemble_runtime_module as _assemble_runtime_module_impl
from xmonitor.runtime.settings.monitor import load_monitor_runtime_settings as _load_monitor_runtime_settings_impl

globals().update(
    _initialize_app_context_impl(
        DEPS,
        base_dir=os.path.dirname(os.path.abspath(__file__)),
        env=os.environ,
        logging_module=logging,
        get_default_user_data_dir_impl=_get_default_user_data_dir_impl,
        get_data_dir_impl=_get_data_dir_impl,
        ensure_directory_impl=_ensure_directory_impl,
        migrate_legacy_state_files_impl=_migrate_legacy_state_files_impl,
        load_local_json_config_impl=_load_local_json_config_impl,
        save_local_json_config_impl=_save_local_json_config_impl,
    )
)


# 模块加载即确保目录存在并迁移旧数据（Qt 导入 app.py 时也生效）
ensure_data_dir()
migrate_legacy_state_files()

_monitor_runtime_settings = _load_monitor_runtime_settings_impl(os.environ)
globals().update(_monitor_runtime_settings)

_flow_runtime_settings = _load_flow_runtime_settings_impl(
    os.environ,
    parse_backoff_seconds_fn=_parse_backoff_seconds_impl,
)
globals().update(_flow_runtime_settings)

def _parse_keywords_env(env_key, default_text=""):
    return _parse_keywords_env_impl(os.environ, env_key, default_text)

# 为空表示不按“正文包含@xxx”做内容拦截，避免误杀通知正文
CONTENT_FILTER_BLOCKED_MENTIONS = ()
_llm_runtime_settings = _load_llm_runtime_settings_impl(os.environ)
globals().update(_llm_runtime_settings)

_tts_runtime_settings = _load_tts_runtime_settings_impl(
    os.environ,
    LOCAL_TTS_CONFIG,
    detect_server_audio_player_fn=_detect_server_audio_player_impl,
)
globals().update(_tts_runtime_settings)

runtime_components = _assemble_runtime_module_impl(
    DEPS,
    safe_float_fn=_safe_float_impl,
    safe_int_fn=_safe_int_impl,
    clamp_llm_timeout_impl=_clamp_llm_timeout_impl,
    llm_timeout_default=_llm_runtime_settings["LLM_FILTER_TIMEOUT_SEC"],
    llm_timeout_max=_llm_runtime_settings["LLM_FILTER_TIMEOUT_MAX_SEC"],
    env_port_getter=lambda: os.environ.get('XMONITOR_PORT', ''),
    logging_module=logging,
    is_noise_notification_text_fn=_is_noise_notification_text,
    normalize_handle_fn=normalize_handle,
    normalize_one_line_fn=_normalize_one_line,
    pick_best_status_id_fn=_pick_best_status_id,
    reply_to_you_keywords=NOTIFICATION_REPLY_TO_YOU_KEYWORDS,
    score_notification_candidate_fn=_score_notification_candidate,
)


app = create_flask_app(__name__, DEPS)

if __name__ == '__main__':
    _run_app_entry_impl(
        app,
        DEPS,
        os_module=os,
        print_fn=print,
        logging_module=logging,
    )
