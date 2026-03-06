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
from collections import deque
from flask import Flask, request, render_template, jsonify
from DrissionPage import ChromiumPage, ChromiumOptions

app = Flask(__name__)
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
    xdg_data_home = str(os.environ.get("XDG_DATA_HOME", "")).strip()
    if xdg_data_home:
        root = os.path.abspath(os.path.expanduser(xdg_data_home))
    else:
        root = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(root, "x-monitor-pro")


def get_data_dir():
    """根据运行环境自动选择数据目录"""
    # 显式配置优先
    custom_data_dir = str(os.environ.get("XMONITOR_DATA_DIR", "")).strip()
    if custom_data_dir:
        return os.path.abspath(os.path.expanduser(custom_data_dir))

    # 检查是否在 Docker 容器中
    if os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV'):
        return "/app/data"

    # 兼容模式：显式要求继续使用项目内 data 目录
    use_project_data = str(os.environ.get("XMONITOR_USE_PROJECT_DATA", "0")).strip().lower() in {
        "1", "true", "yes", "on"
    }
    if use_project_data:
        return os.path.join(BASE_DIR, "data")

    # 默认：每个用户独立数据目录，避免跨机器路径问题
    return get_default_user_data_dir()

DATA_DIR = get_data_dir()
STATE_FILE = os.path.join(DATA_DIR, "spider_state.json")
PROCESSED_FILE = os.path.join(DATA_DIR, "processed_users.json")
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
    values = []
    text = str(raw or "").strip()
    if text:
        for part in re.split(r"[\s,，;；]+", text):
            if not part:
                continue
            try:
                sec = int(float(part))
            except Exception:
                continue
            if sec > 0:
                values.append(sec)
    if not values:
        values = list(default_values)
    out = []
    for sec in values:
        if sec not in out:
            out.append(sec)
    return tuple(out[:8]) or tuple(default_values)


DM_RETRY_BACKOFF_SEC = _parse_backoff_seconds(
    os.environ.get("XMONITOR_DM_RETRY_BACKOFF_SEC", "2,5,9,15")
)
NOTIFY_FLOW_STAGE_ORDER = {
    "reply_pending": 10,
    "match_card": 20,
    "share_link_ready": 30,
    "reply_sent": 40,
    "dm_opening": 50,
    "dm_link_sent": 60,
    "dm_text_generating": 65,
    "dm_text_sent": 70,
    "dm_closed_confirmed": 80,
    "done": 90,
    "retry_waiting": 95,
}
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
    payload = {
        "notify_tts_enabled": bool(DOUBAO_TTS_ENABLED),
        "notify_tts_ready": bool(_doubao_tts_is_ready()),
        "notify_tts_provider": ("doubao" if _doubao_tts_is_ready() else "browser"),
        "notify_tts_app_id": str(DOUBAO_TTS_APP_ID or ""),
        "notify_tts_voice_type": str(DOUBAO_TTS_VOICE_TYPE or ""),
        "notify_tts_cluster": str(DOUBAO_TTS_CLUSTER or "volcano_tts"),
        "notify_tts_endpoint": str(DOUBAO_TTS_ENDPOINT or "https://openspeech.bytedance.com/api/v1/tts"),
        "notify_tts_uid": str(DOUBAO_TTS_UID or "xmonitor-notify"),
        "notify_tts_encoding": str(DOUBAO_TTS_ENCODING or "mp3"),
        "notify_tts_speed_ratio": float(DOUBAO_TTS_SPEED_RATIO),
        "notify_tts_volume_ratio": float(DOUBAO_TTS_VOLUME_RATIO),
        "notify_tts_pitch_ratio": float(DOUBAO_TTS_PITCH_RATIO),
        "notify_tts_timeout_sec": float(DOUBAO_TTS_TIMEOUT_SEC),
        "notify_tts_text_max_chars": int(DOUBAO_TTS_TEXT_MAX_CHARS),
    }
    if include_secrets:
        payload["notify_tts_access_token"] = str(DOUBAO_TTS_ACCESS_TOKEN or "")
        payload["notify_tts_secret_key"] = str(DOUBAO_TTS_SECRET_KEY or "")
    return payload


def _normalize_notify_tts_config_from_payload(payload):
    payload = payload or {}
    enabled = bool(payload.get("enabled", DOUBAO_TTS_ENABLED))
    app_id = str(payload.get("app_id", DOUBAO_TTS_APP_ID) or "").strip()
    access_token = str(payload.get("access_token", DOUBAO_TTS_ACCESS_TOKEN) or "").strip()
    secret_key = str(payload.get("secret_key", DOUBAO_TTS_SECRET_KEY) or "").strip()
    voice_type = str(payload.get("voice_type", DOUBAO_TTS_VOICE_TYPE or "zh_female_vv_uranus_bigtts") or "zh_female_vv_uranus_bigtts").strip()
    cluster = str(payload.get("cluster", DOUBAO_TTS_CLUSTER or "volcano_tts") or "volcano_tts").strip()
    endpoint = str(
        payload.get("endpoint", DOUBAO_TTS_ENDPOINT or "https://openspeech.bytedance.com/api/v1/tts")
        or "https://openspeech.bytedance.com/api/v1/tts"
    ).strip()
    uid = str(payload.get("uid", DOUBAO_TTS_UID or "xmonitor-notify") or "xmonitor-notify").strip()
    encoding = str(payload.get("encoding", DOUBAO_TTS_ENCODING or "mp3") or "mp3").strip().lower()
    if encoding == "opus":
        encoding = "ogg"
    if encoding not in {"mp3", "wav", "ogg"}:
        encoding = "mp3"
    speed_ratio = max(0.5, min(2.0, _safe_float(payload.get("speed_ratio", DOUBAO_TTS_SPEED_RATIO), DOUBAO_TTS_SPEED_RATIO)))
    volume_ratio = max(0.2, min(3.0, _safe_float(payload.get("volume_ratio", DOUBAO_TTS_VOLUME_RATIO), DOUBAO_TTS_VOLUME_RATIO)))
    pitch_ratio = max(0.5, min(2.0, _safe_float(payload.get("pitch_ratio", DOUBAO_TTS_PITCH_RATIO), DOUBAO_TTS_PITCH_RATIO)))
    timeout_sec = max(3.0, min(30.0, _safe_float(payload.get("timeout_sec", DOUBAO_TTS_TIMEOUT_SEC), DOUBAO_TTS_TIMEOUT_SEC)))
    text_max_chars = max(20, min(500, _safe_int(payload.get("text_max_chars", DOUBAO_TTS_TEXT_MAX_CHARS), DOUBAO_TTS_TEXT_MAX_CHARS)))
    return {
        "enabled": bool(enabled),
        "app_id": app_id,
        "access_token": access_token,
        "secret_key": secret_key,
        "voice_type": voice_type,
        "cluster": cluster or "volcano_tts",
        "endpoint": endpoint or "https://openspeech.bytedance.com/api/v1/tts",
        "uid": uid or "xmonitor-notify",
        "encoding": encoding,
        "speed_ratio": float(speed_ratio),
        "volume_ratio": float(volume_ratio),
        "pitch_ratio": float(pitch_ratio),
        "timeout_sec": float(timeout_sec),
        "text_max_chars": int(text_max_chars),
    }


def _apply_notify_tts_config(cfg):
    global DOUBAO_TTS_ENABLED, DOUBAO_TTS_APP_ID, DOUBAO_TTS_ACCESS_TOKEN, DOUBAO_TTS_SECRET_KEY
    global DOUBAO_TTS_VOICE_TYPE, DOUBAO_TTS_CLUSTER, DOUBAO_TTS_ENDPOINT, DOUBAO_TTS_UID, DOUBAO_TTS_ENCODING
    global DOUBAO_TTS_SPEED_RATIO, DOUBAO_TTS_VOLUME_RATIO, DOUBAO_TTS_PITCH_RATIO, DOUBAO_TTS_TIMEOUT_SEC
    global DOUBAO_TTS_TEXT_MAX_CHARS, LOCAL_TTS_CONFIG
    DOUBAO_TTS_ENABLED = bool(cfg.get("enabled", False))
    DOUBAO_TTS_APP_ID = str(cfg.get("app_id", "") or "").strip()
    DOUBAO_TTS_ACCESS_TOKEN = str(cfg.get("access_token", "") or "").strip()
    DOUBAO_TTS_SECRET_KEY = str(cfg.get("secret_key", "") or "").strip()
    DOUBAO_TTS_VOICE_TYPE = str(cfg.get("voice_type", "zh_female_vv_uranus_bigtts") or "zh_female_vv_uranus_bigtts").strip()
    DOUBAO_TTS_CLUSTER = str(cfg.get("cluster", "volcano_tts") or "volcano_tts").strip()
    DOUBAO_TTS_ENDPOINT = str(cfg.get("endpoint", "https://openspeech.bytedance.com/api/v1/tts") or "https://openspeech.bytedance.com/api/v1/tts").strip()
    DOUBAO_TTS_UID = str(cfg.get("uid", "xmonitor-notify") or "xmonitor-notify").strip()
    DOUBAO_TTS_ENCODING = str(cfg.get("encoding", "mp3") or "mp3").strip().lower()
    DOUBAO_TTS_SPEED_RATIO = max(0.5, min(2.0, _safe_float(cfg.get("speed_ratio", 1.0), 1.0)))
    DOUBAO_TTS_VOLUME_RATIO = max(0.2, min(3.0, _safe_float(cfg.get("volume_ratio", 1.35), 1.35)))
    DOUBAO_TTS_PITCH_RATIO = max(0.5, min(2.0, _safe_float(cfg.get("pitch_ratio", 1.0), 1.0)))
    DOUBAO_TTS_TIMEOUT_SEC = max(3.0, min(30.0, _safe_float(cfg.get("timeout_sec", 12.0), 12.0)))
    DOUBAO_TTS_TEXT_MAX_CHARS = max(20, min(500, _safe_int(cfg.get("text_max_chars", 160), 160)))
    LOCAL_TTS_CONFIG = {
        "enabled": "1" if DOUBAO_TTS_ENABLED else "0",
        "app_id": DOUBAO_TTS_APP_ID,
        "access_token": DOUBAO_TTS_ACCESS_TOKEN,
        "secret_key": DOUBAO_TTS_SECRET_KEY,
        "voice_type": DOUBAO_TTS_VOICE_TYPE,
        "cluster": DOUBAO_TTS_CLUSTER,
        "endpoint": DOUBAO_TTS_ENDPOINT,
        "uid": DOUBAO_TTS_UID,
        "encoding": DOUBAO_TTS_ENCODING,
        "speed_ratio": DOUBAO_TTS_SPEED_RATIO,
        "volume_ratio": DOUBAO_TTS_VOLUME_RATIO,
        "pitch_ratio": DOUBAO_TTS_PITCH_RATIO,
        "timeout_sec": DOUBAO_TTS_TIMEOUT_SEC,
        "text_max_chars": DOUBAO_TTS_TEXT_MAX_CHARS,
    }
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


def _enter_dm_critical(section="dm_send"):
    """进入私信关键区，期间尽量避免通知页刷新/切换。"""
    global dm_critical_depth, dm_critical_started_at
    if not DM_CRITICAL_LOCK_ENABLED:
        return False
    dm_critical_lock.acquire()
    with dm_critical_state_lock:
        dm_critical_depth += 1
        if dm_critical_depth == 1:
            dm_critical_started_at = time.time()
    return True


def _leave_dm_critical():
    """退出私信关键区。"""
    global dm_critical_depth, dm_critical_started_at
    if not DM_CRITICAL_LOCK_ENABLED:
        return
    with dm_critical_state_lock:
        dm_critical_depth = max(0, int(dm_critical_depth) - 1)
        if dm_critical_depth == 0:
            dm_critical_started_at = 0.0
    try:
        dm_critical_lock.release()
    except Exception:
        pass


def _is_dm_critical_active():
    global dm_critical_last_timeout_warn_ts
    with dm_critical_state_lock:
        active = int(dm_critical_depth) > 0
        started = float(dm_critical_started_at or 0.0)
    if not active:
        return False
    # 防止异常路径导致关键区长期占用，超时后放行通知扫描
    if started > 0 and (time.time() - started) > float(DM_CRITICAL_MAX_HOLD_SEC):
        now = time.time()
        if (now - float(dm_critical_last_timeout_warn_ts or 0.0)) >= 15.0:
            dm_critical_last_timeout_warn_ts = now
            log_to_ui(
                "warn",
                f"⚠️ 私信关键区占用超过{int(DM_CRITICAL_MAX_HOLD_SEC)}s，临时放行通知扫描（不影响当前私信任务继续）"
            )
        return False
    return True


def _maybe_log_dm_critical_skip():
    """限频输出“因私信关键区跳过通知刷新”的日志。"""
    global dm_critical_last_skip_log_ts
    now = time.time()
    if (now - dm_critical_last_skip_log_ts) >= 3.0:
        dm_critical_last_skip_log_ts = now
        log_to_ui("debug", "📨 私信关键区进行中，已延后通知扫描/刷新")


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
    """判断进程是否存在。"""
    try:
        if not pid or int(pid) <= 0:
            return False
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def _extract_singleton_lock_pid(profile_dir):
    """从 Chromium SingletonLock 中提取 PID（若可解析）。"""
    lock_path = os.path.join(profile_dir, "SingletonLock")
    if not os.path.lexists(lock_path):
        return None

    target = ""
    try:
        if os.path.islink(lock_path):
            target = os.readlink(lock_path)
        else:
            with open(lock_path, "r", encoding="utf-8", errors="ignore") as f:
                target = f.read().strip()
    except Exception:
        return None

    m = re.search(r'(\d+)\s*$', str(target))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _cleanup_stale_profile_singletons(profile_dir):
    """清理陈旧的 Chromium profile 锁文件。"""
    names = ("SingletonLock", "SingletonCookie", "SingletonSocket")
    for name in names:
        p = os.path.join(profile_dir, name)
        try:
            if os.path.lexists(p):
                os.remove(p)
        except Exception:
            pass


def _list_profile_bound_browser_pids(profile_dir):
    """列出绑定到指定 user-data-dir 的 chrome/chromium 进程 PID。"""
    if not profile_dir:
        return []
    profile_dir = os.path.abspath(profile_dir)
    needle = f"--user-data-dir={profile_dir}"
    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid=,args="],
            capture_output=True,
            text=True,
            timeout=2.5,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []

    pids = []
    for raw in (proc.stdout or "").splitlines():
        line = raw.strip()
        if not line or needle not in line:
            continue
        low = line.lower()
        if ("chrome" not in low) and ("chromium" not in low):
            continue
        parts = line.split(None, 1)
        if not parts:
            continue
        try:
            pid = int(parts[0])
        except Exception:
            continue
        if pid > 0 and pid != os.getpid():
            pids.append(pid)
    return sorted(set(pids))


def _terminate_pids(pids, term_wait=1.6, kill_wait=0.8):
    """尝试先 TERM 后 KILL 终止进程，返回已终止的 PID 列表。"""
    if not pids:
        return []
    pending = [pid for pid in pids if _pid_exists(pid)]
    if not pending:
        return []

    def _wait_until_done(target_pids, timeout_sec):
        deadline = time.time() + max(0.1, float(timeout_sec))
        remain = list(target_pids)
        while time.time() < deadline and remain:
            remain = [pid for pid in remain if _pid_exists(pid)]
            if remain:
                time.sleep(0.08)
        return remain

    for pid in list(pending):
        try:
            os.kill(pid, 15)
        except Exception:
            pass
    pending = _wait_until_done(pending, term_wait)

    if pending:
        for pid in list(pending):
            try:
                os.kill(pid, 9)
            except Exception:
                pass
        pending = _wait_until_done(pending, kill_wait)

    return [pid for pid in pids if not _pid_exists(pid)]


def _auto_cleanup_profile_runtime(profile_dir):
    """
    自动清理 profile 运行时冲突：
    1) 结束绑定该 profile 的残留浏览器进程
    2) 清理 Singleton 锁文件
    """
    bound_pids = _list_profile_bound_browser_pids(profile_dir)
    killed_pids = _terminate_pids(bound_pids) if bound_pids else []
    _cleanup_stale_profile_singletons(profile_dir)
    return {
        "bound_total": len(bound_pids),
        "killed_total": len(killed_pids),
        "bound_pids": bound_pids,
        "killed_pids": killed_pids,
    }


def _is_profile_locked_by_alive_process(profile_dir):
    """
    判断固定 profile 是否被存活进程占用。
    返回 (locked: bool, pid: int|None)
    """
    pid = _extract_singleton_lock_pid(profile_dir)
    if pid and _pid_exists(pid):
        return True, pid
    return False, pid


def init_global_browser():
    """初始化全局浏览器实例"""
    global global_browser, global_browser_dir, browser_initialized, browser_force_temp_profile

    with browser_init_lock:
        if browser_initialized and global_browser:
            return global_browser

        max_attempts = 4
        last_error = None
        use_temp_profile_fallback = browser_force_temp_profile or (headless_mode and HEADLESS_FORCE_TEMP_PROFILE)
        force_headless_retry = False
        safe_mode_retry = False

        for attempt in range(1, max_attempts + 1):
            with browser_lock:
                if browser_initialized and global_browser:
                    return global_browser

                # 每次尝试前先清理残留资源
                if global_browser:
                    try:
                        global_browser.quit()
                    except Exception:
                        pass
                    global_browser = None

                if global_browser_dir:
                    cleanup_browser_user_data_dir(global_browser_dir)
                    global_browser_dir = None

                try:
                    effective_headless = True if force_headless_retry else headless_mode
                    if effective_headless and HEADLESS_FORCE_TEMP_PROFILE:
                        use_temp_profile_fallback = True

                    if BROWSER_PROFILE_PERSIST and not use_temp_profile_fallback:
                        locked, lock_pid = _is_profile_locked_by_alive_process(BROWSER_PROFILE_DIR)
                        if locked:
                            cleanup_info = _auto_cleanup_profile_runtime(BROWSER_PROFILE_DIR)
                            if cleanup_info["bound_total"] > 0:
                                log_to_ui(
                                    "warn",
                                    f"⚠️ 固定Profile被占用(pid={lock_pid})，已自动清理残留进程 {cleanup_info['killed_total']}/{cleanup_info['bound_total']}"
                                )
                            use_temp_profile_fallback = True
                            browser_force_temp_profile = True
                            log_to_ui("warn", f"⚠️ 固定Profile被占用(pid={lock_pid})，本次直接切换临时Profile启动")
                        else:
                            # 无存活占用时清理陈旧锁，避免误判冲突
                            _cleanup_stale_profile_singletons(BROWSER_PROFILE_DIR)

                    prefer_persistent_profile = not use_temp_profile_fallback
                    global_browser_dir = create_browser_user_data_dir(prefer_persistent=prefer_persistent_profile)
                    port = get_free_port()
                    co = init_browser_options(
                        port,
                        global_browser_dir,
                        force_headless=True if force_headless_retry else None,
                        safe_mode=safe_mode_retry
                    )
                    mode_text = "无头模式(连接失败自动兜底)" if force_headless_retry else ("无头模式" if effective_headless else "有头模式(调试)")
                    if safe_mode_retry:
                        mode_text = f"{mode_text}+安全参数"
                    profile_mode = "固定持久目录" if is_persistent_browser_profile_dir(global_browser_dir) else "临时目录"
                    log_to_ui("info", f"🖥️ 正在初始化浏览器: {mode_text} | Profile: {profile_mode}")
                    log_to_ui("debug", f"🗂️ 浏览器用户目录: {global_browser_dir}")
                    log_headless_debug(
                        f"init_attempt={attempt}/{max_attempts}, port={port}, "
                        f"profile_mode={profile_mode}, force_headless_retry={force_headless_retry}, safe_mode_retry={safe_mode_retry}, "
                        f"headless_force_temp_profile={HEADLESS_FORCE_TEMP_PROFILE}"
                    )
                    global_browser = ChromiumPage(co)

                    # 设置认证
                    global_browser.get("https://x.com")
                    cookie_dict = {'name': 'auth_token', 'value': global_token.strip(), 'domain': '.x.com', 'path': '/', 'secure': True}
                    global_browser.set.cookies(cookie_dict)
                    global_browser.refresh()
                    time.sleep(3)

                    browser_initialized = True
                    log_to_ui("success", "✅ 全局浏览器已初始化 (单浏览器多标签页模式)")
                    return global_browser
                except Exception as e:
                    last_error = e
                    browser_initialized = False
                    global_browser = None
                    log_headless_exception("浏览器初始化", e)
                    _capture_runtime_diagnostic(
                        None,
                        "init_global_browser_failed",
                        err=e,
                        extra={
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "global_browser_dir": global_browser_dir,
                            "headless_mode": bool(headless_mode),
                            "force_headless_retry": bool(force_headless_retry),
                            "safe_mode_retry": bool(safe_mode_retry),
                            "use_temp_profile_fallback": bool(use_temp_profile_fallback),
                            "headless_force_temp_profile": bool(HEADLESS_FORCE_TEMP_PROFILE),
                        }
                    )

                    err_text = str(e).lower()
                    persistent_profile_used = is_persistent_browser_profile_dir(global_browser_dir)
                    profile_conflict = any(k in err_text for k in [
                        "用户文件夹",
                        "user data",
                        "profile",
                        "already",
                        "conflict",
                    ])
                    if BROWSER_PROFILE_PERSIST and persistent_profile_used and profile_conflict:
                        use_temp_profile_fallback = True
                        browser_force_temp_profile = True
                        log_to_ui("warn", "⚠️ 固定Profile疑似被占用，后续尝试将自动回退临时Profile启动")
                    connection_failed = any(k in err_text for k in [
                        "浏览器连接失败",
                        "connection failed",
                        "cannot connect",
                        "timed out",
                        "timeout",
                    ])
                    if connection_failed and global_browser_dir:
                        cleanup_info = _auto_cleanup_profile_runtime(global_browser_dir)
                        if cleanup_info["bound_total"] > 0:
                            log_to_ui(
                                "warn",
                                f"⚠️ 检测到残留浏览器进程({cleanup_info['bound_total']})，已自动清理 {cleanup_info['killed_total']} 个并重试"
                            )
                    if connection_failed and not use_temp_profile_fallback:
                        use_temp_profile_fallback = True
                        browser_force_temp_profile = True
                        log_to_ui("warn", "⚠️ 连接浏览器失败，后续尝试将切换临时Profile重试")
                    if connection_failed and (not headless_mode) and (not force_headless_retry):
                        force_headless_retry = True
                        log_to_ui("warn", "⚠️ 当前有头模式连接失败，后续尝试将自动切换无头模式重试")
                    if connection_failed and not safe_mode_retry:
                        safe_mode_retry = True
                        log_to_ui("warn", "⚠️ 启用浏览器安全参数集重试，降低参数兼容性风险")

                    if global_browser_dir:
                        cleanup_browser_user_data_dir(global_browser_dir)
                        global_browser_dir = None

                    log_to_ui("warn", f"⚠️ 浏览器初始化失败({attempt}/{max_attempts}): {str(e)}")

            if attempt < max_attempts:
                time.sleep(1.5 * attempt)

        raise RuntimeError(f"浏览器初始化失败，已重试 {max_attempts} 次: {last_error}")


def cleanup_global_browser():
    """清理全局浏览器"""
    global global_browser, global_browser_dir, browser_initialized, delegated_account_active, delegated_switch_ok, reply_work_tab, dm_passcode_warmed, browser_force_temp_profile, last_dm_action_ts

    with browser_lock:
        with reply_work_tab_lock:
            if reply_work_tab:
                try:
                    reply_work_tab.close()
                except Exception:
                    pass
                reply_work_tab = None
        with dm_passcode_lock:
            dm_passcode_warmed = False

        if global_browser:
            try:
                global_browser.quit()
            except Exception:
                pass
            global_browser = None

        if global_browser_dir:
            cleanup_browser_user_data_dir(global_browser_dir)
            global_browser_dir = None

        browser_initialized = False
        delegated_account_active = ""
        delegated_switch_ok = False
        browser_force_temp_profile = False
        last_dm_action_ts = 0.0


def restart_global_browser():
    """重启全局浏览器"""
    log_to_ui("info", "🔄 正在重启浏览器...")
    cleanup_global_browser()
    time.sleep(1)
    browser = init_global_browser()

    # 切换委派账户
    delegated = get_effective_delegated_account()
    if delegated:
        browser.get("https://x.com/home")
        time.sleep(2)
        ensure_delegated_account_session(browser, delegated)
        time.sleep(2)

    log_to_ui("success", "✅ 浏览器已重启")
    return browser


def run_headful_soft_maintenance(blocked_users, notify_enabled):
    """
    有头模式轻量维护：
    - 默认不重启整浏览器，避免打断人工操作
    - 优先在通知标签页做保活
    """
    global notification_last_refresh_at, notification_refresh_interval

    if not notify_enabled:
        return True
    if _is_dm_critical_active():
        _maybe_log_dm_critical_skip()
        return True

    try:
        ensure_notification_tab(blocked_users)
        with notification_tab_lock:
            if not notification_tab:
                return False
            notification_tab.get("https://x.com/notifications")
            time.sleep(random.uniform(0.7, 1.6))
            try:
                tabs = notification_tab.eles('css:[role="tab"]', timeout=1.2)
                for tab in tabs:
                    tab_text = (tab.text or "").strip().lower()
                    if tab_text in ['全部', 'all']:
                        is_selected = tab.attr('aria-selected') == 'true'
                        if not is_selected:
                            tab.click()
                            time.sleep(random.uniform(0.3, 0.8))
                        break
            except Exception:
                pass
        notification_last_refresh_at = time.time()
        notification_refresh_interval = _schedule_next_notification_refresh_interval(notification_refresh_interval)
        return True
    except Exception as e:
        log_to_ui("warn", f"⚠️ 有头轻量维护失败: {e}")
        return False


def monitoring_loop():
    """
    主监控循环 - 单浏览器多标签页模式
    - 所有任务同时并行（每个任务一个标签页）
    - 通知标签页始终保持打开
    """
    global monitor_active, history_ids, global_browser, browser_initialized, notification_tab, monitor_thread

    log_to_ui("info", f">>> 🚀 引擎启动 ({ENGINE_VERSION} 全并行标签页版)...")
    log_to_ui("info", "🧩 build: 2026-02-27-headless-stability-suite")
    if is_headless_verbose_logging_enabled():
        log_to_ui("info", "🧪 [HEADLESS] 已启用超详细诊断日志")
    if headless_mode:
        profile_strategy = "临时Profile优先" if HEADLESS_FORCE_TEMP_PROFILE else "允许固定Profile"
        log_to_ui("info", f"🧪 [HEADLESS] Profile策略: {profile_strategy}")
    else:
        maint_mode = "允许自动重启" if HEADFUL_MAINTENANCE_RESTART else "默认仅轻量保活(不重启浏览器)"
        disconnect_mode = "允许断线后重启" if HEADFUL_NOTIFY_DISCONNECT_RESTART else "断线仅重建通知标签页"
        log_to_ui("info", f"🖥️ [HEADFUL] 维护策略: {maint_mode}")
        log_to_ui("info", f"🖥️ [HEADFUL] 断线恢复策略: {disconnect_mode}")
    if _llm_filter_is_ready():
        log_to_ui("info", f"🤖 [LLMFilter] 已启用模型过滤: model={LLM_FILTER_MODEL}, endpoint={_llm_filter_endpoint()}")
    elif LLM_FILTER_ENABLED:
        log_to_ui("warn", "⚠️ [LLMFilter] 已开启但配置不完整（需设置 XMONITOR_LLM_BASE_URL 与 XMONITOR_LLM_MODEL）")
    blocked_users = ["@manateelazycat", "@X", "@Twitter"]
    last_save_time = time.time()
    save_interval = 60
    last_maintenance_time = time.time()
    maintenance_interval = get_random_maintenance_interval()
    log_to_ui("info", f"🛠️ 浏览器维护策略：每 {int(MAINTENANCE_INTERVAL_MIN_SEC)}-{int(MAINTENANCE_INTERVAL_MAX_SEC)}s 随机维护（当前{int(maintenance_interval)}s）")

    try:
        # 初始化全局浏览器
        browser = init_global_browser()
        log_to_ui("success", "✅ 浏览器已初始化")

        # ===== 检查并切换到委派账户 =====
        delegated = get_effective_delegated_account()
        if delegated:
            log_to_ui("info", f"🔄 检测到委派账户配置已启用")
            log_to_ui("info", "🔄 正在切换到委派账户...")

            with browser_lock:
                browser.get("https://x.com/home")
                time.sleep(2)
                switch_success = ensure_delegated_account_session(browser, delegated)

            if switch_success:
                log_to_ui("success", f"✅ 已切换到委派账户，所有监控将使用委派账户身份")
            else:
                log_to_ui("warn", "⚠️ 委派账户切换失败，将使用主账户进行监控")

            time.sleep(2)
        else:
            log_to_ui("info", "ℹ️ 未配置委派账户，使用主账户进行监控")

        # ===== 创建持久通知标签页 =====
        with data_lock:
            notify_enabled = notification_monitoring

        if notify_enabled:
            init_notification_tab(blocked_users)

        # 通知扫描时间控制
        last_notification_scan = 0
        notification_interval = get_random_notification_interval()
        recent_window_minutes = NOTIFICATION_RECENT_WINDOW_MINUTES
        log_to_ui(
            "info",
            f"📬 通知刷新策略：每{NOTIFICATION_SCAN_INTERVAL_MIN_SEC}-{NOTIFICATION_SCAN_INTERVAL_MAX_SEC}秒随机拉取过去{recent_window_minutes}分钟内产生的通知（当前{notification_interval:.1f}s）"
        )
        log_to_ui(
            "info",
            f"🧭 行为随机化策略：任务并发{TASK_PARALLEL_MIN}-{TASK_PARALLEL_MAX}随机、提交抖动{TASK_SUBMIT_JITTER_MIN_SEC}-{TASK_SUBMIT_JITTER_MAX_SEC}s、标签页创建抖动{TAB_OPEN_JITTER_MIN_SEC}-{TAB_OPEN_JITTER_MAX_SEC}s"
        )

        while monitor_active:
            with data_lock:
                current_tasks = list(monitor_tasks)
                notify_enabled = notification_monitoring

            current_time = time.time()

            if not _is_dm_critical_active():
                retry_done = _process_notify_retry_queue(max_items=1)
                if retry_done > 0:
                    log_to_ui("debug", f"🔁 已自动处理到期重试任务: {retry_done} 条")

            # ===== 通知随机间隔刷新扫描 =====
            if notify_enabled and monitor_active and (current_time - last_notification_scan >= notification_interval):
                if _is_dm_critical_active():
                    _maybe_log_dm_critical_skip()
                else:
                    ensure_notification_tab(blocked_users)
                    scan_persistent_notification_tab(blocked_users, max_recent_minutes=recent_window_minutes)
                    last_notification_scan = current_time
                    notification_interval = get_random_notification_interval()
                    log_to_ui("debug", f"📬 下次通知扫描间隔: {notification_interval:.1f}s")

            # ===== 推文任务扫描（按原有间隔）=====
            if current_tasks:
                log_to_ui("info", "=" * 60)
                log_to_ui("info", f"🔄 开始推文扫描周期")
                task_queue = list(current_tasks)
                random.shuffle(task_queue)
                parallel_limit = get_random_task_parallel(len(task_queue))
                log_to_ui("info", f"📊 推文监控: 共 {len(task_queue)} 个任务 (本轮并发≈{parallel_limit})")

                # 分批并发，避免每轮都瞬时打开同数量标签页
                for start_idx in range(0, len(task_queue), parallel_limit):
                    if not monitor_active:
                        break
                    batch = task_queue[start_idx: start_idx + parallel_limit]
                    batch_futures = []
                    for i, task in enumerate(batch):
                        future = task_executor.submit(
                            scan_task_with_tab,
                            task,
                            blocked_users
                        )
                        batch_futures.append(future)
                        if i < len(batch) - 1:
                            time.sleep(random.uniform(TASK_SUBMIT_JITTER_MIN_SEC, TASK_SUBMIT_JITTER_MAX_SEC))

                    for future in concurrent.futures.as_completed(batch_futures):
                        try:
                            future.result()
                        except Exception as e:
                            log_to_ui("error", f"任务执行错误: {str(e)}")

                    if start_idx + parallel_limit < len(task_queue):
                        gap = random.uniform(TASK_BATCH_GAP_MIN_SEC, TASK_BATCH_GAP_MAX_SEC)
                        log_to_ui("debug", f"⏱️ 批次间隔: {gap:.1f}s")
                        time.sleep(gap)

                # 推文任务完成后休息
                rest = random.randint(20, 40)
                log_to_ui("info", f"⏱️ 推文扫描结束，将在 {rest}s 后开始下一轮...")

                # 休息期间继续扫描通知
                for i in range(rest):
                    if not monitor_active:
                        break

                    # 休息期间按随机间隔扫描通知
                    with data_lock:
                        notify_enabled = notification_monitoring
                    now_ts = time.time()
                    if notify_enabled and (now_ts - last_notification_scan >= notification_interval):
                        if _is_dm_critical_active():
                            _maybe_log_dm_critical_skip()
                        else:
                            ensure_notification_tab(blocked_users)
                            scan_persistent_notification_tab(blocked_users, max_recent_minutes=recent_window_minutes)
                            last_notification_scan = now_ts
                            notification_interval = get_random_notification_interval()
                            log_to_ui("debug", f"📬 下次通知扫描间隔: {notification_interval:.1f}s")

                    if not _is_dm_critical_active():
                        retry_done = _process_notify_retry_queue(max_items=1)
                        if retry_done > 0:
                            log_to_ui("debug", f"🔁 休息期已自动处理重试任务: {retry_done} 条")

                    if i % 10 == 0 and i > 0:
                        log_to_ui("info", f"⏳ 倒计时 {rest - i}s...")
                    time.sleep(1)

                log_to_ui("info", "=" * 60)

            elif not notify_enabled:
                # 没有任何任务
                log_to_ui("warn", "⏳ 无任务，等待中...")
                time.sleep(5)
            else:
                # 只有通知监控，短暂休息后继续
                time.sleep(1)

            # 浏览器维护重启（按时间随机，避免频繁重启导致登录态抖动）
            if (time.time() - last_maintenance_time) >= maintenance_interval:
                if _is_dm_critical_active():
                    _maybe_log_dm_critical_skip()
                    last_maintenance_time = time.time()
                    maintenance_interval = get_random_maintenance_interval()
                    continue
                if (not headless_mode) and (not HEADFUL_MAINTENANCE_RESTART):
                    # 有头模式默认不重启整浏览器，避免打断人工操作。
                    log_to_ui("info", "🛠️ 有头维护：执行轻量保活（不重启浏览器）")
                    run_headful_soft_maintenance(blocked_users, notify_enabled)
                else:
                    close_notification_tab()
                    delegated = get_effective_delegated_account()
                    if delegated and delegated_switch_ok and global_browser:
                        log_to_ui("info", "🔄 委派模式维护：仅刷新浏览器，避免重复登录")
                        try:
                            with browser_lock:
                                global_browser.get("https://x.com/home")
                                time.sleep(1.2)
                                global_browser.refresh()
                                time.sleep(1.2)
                        except Exception as refresh_err:
                            log_to_ui("warn", f"⚠️ 轻量刷新失败，回退为完整重启: {refresh_err}")
                            restart_global_browser()
                    else:
                        restart_global_browser()
                    if notify_enabled:
                        init_notification_tab(blocked_users)
                last_notification_scan = 0
                notification_interval = get_random_notification_interval()
                last_maintenance_time = time.time()
                maintenance_interval = get_random_maintenance_interval()
                log_to_ui("info", f"🛠️ 下次浏览器维护间隔: {int(maintenance_interval)}s")

            # 周期性保存数据
                if time.time() - last_save_time >= save_interval:
                    log_to_ui("info", "💾 执行定时数据保存...")
                    save_state()
                    last_save_time = time.time()

                # 内存清理：限制 history_ids 大小，防止内存泄漏
                max_history_size = 10000
                with data_lock:
                    if len(history_ids) > max_history_size:
                        history_list = list(history_ids)
                        history_ids.clear()
                        history_ids.update(history_list[-max_history_size:])
                        log_to_ui("info", f"🧹 历史记录已清理，保留最新 {max_history_size} 条")
                    before_dedupe = len(content_dedupe)
                    prune_content_dedupe()
                    after_dedupe = len(content_dedupe)
                    if after_dedupe < before_dedupe:
                        log_to_ui("info", f"🧹 内容签名已清理: {before_dedupe} -> {after_dedupe}")

    except Exception as e:
        log_to_ui("error", f"💥 Fatal Error: {str(e)}")
        traceback.print_exc()
    finally:
        monitor_active = False
        log_to_ui("info", ">>> 引擎停止中，保存数据...")
        save_state()
        log_to_ui("success", "💾 数据已保存，再见！")
        cleanup_global_browser()
        with monitor_thread_lock:
            if monitor_thread is threading.current_thread():
                monitor_thread = None


# --- 状态管理 (读写硬盘) ---
def save_state():
    """保存配置和待处理任务"""
    ensure_data_dir()
    state = {
        "token": global_token,
        "tasks": monitor_tasks,
        "is_running": monitor_active,
        "pending": pending_results, # 保存待处理列表
        "notification_monitoring": notification_monitoring,  # 保存通知监控状态
        "delegated_account": delegated_account,  # 保存委派账户
        "delegated_enabled": delegated_enabled,  # 保存委派开关
        "headless_mode": headless_mode,  # 保存有头/无头模式
        "history_ids": list(history_ids),  # 保存状态ID去重缓存
        "content_dedupe": content_dedupe,  # 保存同用户同内容去重缓存
        "notify_reply_templates": notify_reply_templates,  # 保存通知回复模板
        "dm_message_templates": dm_message_templates,  # 保存私信模板
        "llm_filter_enabled": bool(LLM_FILTER_ENABLED),
        "llm_filter_base_url": str(LLM_FILTER_BASE_URL or ""),
        "llm_filter_api_key": str(LLM_FILTER_API_KEY or ""),
        "llm_filter_model": str(LLM_FILTER_MODEL or ""),
        "llm_filter_timeout_sec": float(LLM_FILTER_TIMEOUT_SEC),
        "llm_filter_prompt_template": str(LLM_FILTER_PROMPT_TEMPLATE or ""),
        "llm_intent_prompt_template": str(LLM_INTENT_PROMPT_TEMPLATE or ""),
        "dm_llm_rewrite_enabled": bool(DM_LLM_REWRITE_ENABLED),
        "dm_llm_rewrite_prompt_template": str(DM_LLM_REWRITE_PROMPT_TEMPLATE or ""),
        "dm_llm_rewrite_max_chars": int(DM_LLM_REWRITE_MAX_CHARS),
        "dm_llm_rewrite_temperature": float(DM_LLM_REWRITE_TEMPERATURE),
        "dm_llm_rewrite_max_regen": int(DM_LLM_REWRITE_MAX_REGEN),
        "dm_llm_rewrite_dedupe_size": int(DM_LLM_REWRITE_DEDUPE_SIZE),
        "dm_llm_rewrite_history": list(dm_llm_rewrite_history),
        "notify_voice_block_keywords_text": str(NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT or ""),
    }
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
        logging.info(f"💾 状态已保存: {len(pending_results)} 条待处理，{len(history_ids)} 条历史ID，{len(content_dedupe)} 条内容签名")
    except Exception as e:
        logging.error(f"保存状态失败: {e}")

def load_state():
    global global_token, monitor_tasks, monitor_active, processed_users, pending_results, notification_monitoring, delegated_account, delegated_enabled, history_ids, headless_mode, content_dedupe, notify_reply_templates, dm_message_templates
    global LLM_FILTER_ENABLED, LLM_FILTER_BASE_URL, LLM_FILTER_API_KEY, LLM_FILTER_MODEL, LLM_FILTER_TIMEOUT_SEC
    global LLM_FILTER_PROMPT_TEMPLATE, LLM_INTENT_PROMPT_TEMPLATE
    global DM_LLM_REWRITE_ENABLED, DM_LLM_REWRITE_PROMPT_TEMPLATE, DM_LLM_REWRITE_MAX_CHARS
    global DM_LLM_REWRITE_TEMPERATURE, DM_LLM_REWRITE_MAX_REGEN, DM_LLM_REWRITE_DEDUPE_SIZE, dm_llm_rewrite_history
    global NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT, NOTIFY_VOICE_BLOCK_KEYWORDS
    ensure_data_dir()

    # 1. 加载主状态
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                global_token = data.get("token", "")
                monitor_tasks = data.get("tasks", [])
                pending_results = data.get("pending", []) # 恢复待处理列表
                notification_monitoring = data.get("notification_monitoring", False)  # 恢复通知监控状态
                delegated_account = str(data.get("delegated_account", "") or "").strip()  # 恢复委派账户
                delegated_enabled = bool(data.get("delegated_enabled", bool(delegated_account)))
                headless_mode = data.get("headless_mode", True)  # 恢复有头/无头模式
                notify_reply_templates = _sanitize_template_list(
                    data.get("notify_reply_templates", []),
                    DEFAULT_NOTIFY_REPLY_TEMPLATES
                )
                dm_message_templates = _sanitize_template_list(
                    data.get("dm_message_templates", []),
                    DEFAULT_DM_TEMPLATES
                )
                LLM_FILTER_ENABLED = bool(data.get("llm_filter_enabled", LLM_FILTER_ENABLED))
                LLM_FILTER_BASE_URL = str(data.get("llm_filter_base_url", LLM_FILTER_BASE_URL) or "").strip()
                LLM_FILTER_API_KEY = str(data.get("llm_filter_api_key", LLM_FILTER_API_KEY) or "").strip()
                LLM_FILTER_MODEL = str(data.get("llm_filter_model", LLM_FILTER_MODEL) or "").strip()
                try:
                    LLM_FILTER_TIMEOUT_SEC = clamp_llm_timeout(data.get("llm_filter_timeout_sec", LLM_FILTER_TIMEOUT_SEC))
                except Exception:
                    pass
                LLM_FILTER_PROMPT_TEMPLATE = str(
                    data.get("llm_filter_prompt_template", LLM_FILTER_PROMPT_TEMPLATE) or ""
                ).strip()
                LLM_INTENT_PROMPT_TEMPLATE = str(
                    data.get("llm_intent_prompt_template", LLM_INTENT_PROMPT_TEMPLATE) or ""
                ).strip()
                DM_LLM_REWRITE_ENABLED = bool(data.get("dm_llm_rewrite_enabled", DM_LLM_REWRITE_ENABLED))
                DM_LLM_REWRITE_PROMPT_TEMPLATE = str(
                    data.get("dm_llm_rewrite_prompt_template", DM_LLM_REWRITE_PROMPT_TEMPLATE) or ""
                ).strip() or DM_LLM_REWRITE_DEFAULT_PROMPT
                try:
                    DM_LLM_REWRITE_MAX_CHARS = int(data.get("dm_llm_rewrite_max_chars", DM_LLM_REWRITE_MAX_CHARS))
                except Exception:
                    pass
                DM_LLM_REWRITE_MAX_CHARS = max(80, min(1200, int(DM_LLM_REWRITE_MAX_CHARS)))
                try:
                    DM_LLM_REWRITE_TEMPERATURE = float(data.get("dm_llm_rewrite_temperature", DM_LLM_REWRITE_TEMPERATURE))
                except Exception:
                    pass
                DM_LLM_REWRITE_TEMPERATURE = max(0.0, min(1.2, float(DM_LLM_REWRITE_TEMPERATURE)))
                try:
                    DM_LLM_REWRITE_MAX_REGEN = int(data.get("dm_llm_rewrite_max_regen", DM_LLM_REWRITE_MAX_REGEN))
                except Exception:
                    pass
                DM_LLM_REWRITE_MAX_REGEN = max(0, min(5, int(DM_LLM_REWRITE_MAX_REGEN)))
                try:
                    loaded_dedupe_size = int(data.get("dm_llm_rewrite_dedupe_size", DM_LLM_REWRITE_DEDUPE_SIZE))
                except Exception:
                    loaded_dedupe_size = DM_LLM_REWRITE_DEDUPE_SIZE
                DM_LLM_REWRITE_DEDUPE_SIZE = max(50, min(1000, int(loaded_dedupe_size)))
                loaded_hist = data.get("dm_llm_rewrite_history", []) or []
                if not isinstance(loaded_hist, list):
                    loaded_hist = []
                dm_llm_rewrite_history = deque(
                    [str(x or "").strip() for x in loaded_hist if str(x or "").strip()],
                    maxlen=DM_LLM_REWRITE_DEDUPE_SIZE,
                )
                NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT = str(
                    data.get("notify_voice_block_keywords_text", NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT) or ""
                ).strip()
                NOTIFY_VOICE_BLOCK_KEYWORDS = tuple(
                    dict.fromkeys(
                        list(NOTIFY_VOICE_BLOCK_KEYWORDS_BUILTIN)
                        + [kw.lower() for kw in _normalize_keyword_lines(NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT)]
                    )
                )

                # 恢复去重ID（完整版）
                saved_history = data.get("history_ids", [])
                if saved_history:
                    history_ids.update(saved_history)
                    logging.info(f"✅ 已恢复 {len(saved_history)} 条历史去重记录")

                # 恢复“同用户同内容”签名
                saved_content_dedupe = data.get("content_dedupe", {})
                if isinstance(saved_content_dedupe, dict) and saved_content_dedupe:
                    for sig, ts in saved_content_dedupe.items():
                        try:
                            content_dedupe[str(sig)] = float(ts)
                        except Exception:
                            continue
                    prune_content_dedupe()
                    logging.info(f"✅ 已恢复 {len(content_dedupe)} 条内容去重签名")

                pending_changed = False

                # 从待处理列表中也恢复去重ID（双重保险），并迁移旧版回复状态字段
                for item in pending_results:
                    if item.get('source') == '通知页面':
                        migrated = False
                        if 'reply_checked' in item and 'notify_replied' not in item:
                            item['notify_replied'] = bool(item.get('reply_checked'))
                            migrated = True
                        if 'reply_text' in item and 'notify_reply_text' not in item:
                            item['notify_reply_text'] = str(item.get('reply_text') or "")
                            migrated = True
                        if 'reply_time' in item and 'notify_reply_time' not in item:
                            item['notify_reply_time'] = str(item.get('reply_time') or "")
                            migrated = True

                        # 统一只保留 notify_* 字段
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
                        history_ids.add(item['key'])
                    sig = make_content_signature(item.get('handle', ''), item.get('content', ''))
                    if sig:
                        content_dedupe[sig] = time.time()
                prune_content_dedupe()

                if pending_changed:
                    save_state()

                logging.info(f"✅ 状态加载成功:")
                logging.info(f"   - Token: {'已配置' if global_token else '未配置'}")
                logging.info(f"   - 监控任务: {len(monitor_tasks)} 个")
                logging.info(f"   - 待处理: {len(pending_results)} 条")
                logging.info(f"   - 历史记录: {len(history_ids)} 条")
                logging.info(f"   - 内容签名: {len(content_dedupe)} 条")
                logging.info(f"   - 通知监控: {'启用' if notification_monitoring else '禁用'}")
                delegated_label = f"{delegated_account} (启用)" if (delegated_enabled and delegated_account) else "未启用"
                logging.info(f"   - 委派账户: {delegated_label}")
                logging.info(f"   - 浏览器模式: {'无头' if headless_mode else '有头(调试)'}")
                logging.info(f"   - 回复模板: {len(notify_reply_templates)} 条")
                logging.info(f"   - 私信模板: {len(dm_message_templates)} 条")
                if LLM_FILTER_ENABLED:
                    logging.info(f"   - LLM过滤: 启用 ({LLM_FILTER_MODEL or '未配置模型'})")
                else:
                    logging.info("   - LLM过滤: 禁用")
                tts_status = "启用" if _doubao_tts_is_ready() else "禁用/未配置"
                logging.info(f"   - 豆包TTS: {tts_status} ({DOUBAO_TTS_VOICE_TYPE or '未配置音色'})")
                logging.info(f"   - 语音不播报关键词: {len(NOTIFY_VOICE_BLOCK_KEYWORDS)} 条")
                logging.info(f"   - 通知仅抓回复: {'启用' if NOTIFICATION_REPLY_ONLY_MODE else '禁用'}")

                if data.get("is_running", False):
                    start_monitor_thread()
        except Exception as e:
            logging.error(f"加载状态失败: {e}")
    else:
        logging.warning(f"⚠️ 状态文件不存在: {STATE_FILE}")

    # 2. 加载黑名单
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                saved_users = json.load(f)
                processed_users.update(saved_users)
                logging.info(f"✅ 已恢复 {len(processed_users)} 个已处理用户")
        except Exception as e:
            logging.error(f"加载黑名单失败: {e}")
    else:
        logging.warning(f"⚠️ 黑名单文件不存在: {PROCESSED_FILE}")

def save_processed_users():
    ensure_data_dir()
    try:
        with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
            json.dump(list(processed_users), f, indent=4, ensure_ascii=False)
        logging.info(f"💾 已保存 {len(processed_users)} 个已处理用户")
    except Exception as e:
        logging.error(f"保存黑名单失败: {e}")


def _sanitize_template_list(raw_list, fallback_list):
    """清洗模板列表：去空、去重、保序；若为空则回退默认。"""
    cleaned = []
    seen = set()
    if isinstance(raw_list, list):
        for item in raw_list:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            cleaned.append(text)
    if cleaned:
        return cleaned
    return list(fallback_list)


def _normalize_keyword_lines(raw_text):
    """将多行/逗号分隔关键词清洗为去重后的列表。"""
    cleaned = []
    seen = set()
    raw = str(raw_text or "")
    for part in re.split(r"[\n,，;；]+", raw):
        kw = str(part or "").strip()
        if not kw:
            continue
        low = kw.lower()
        if low in seen:
            continue
        seen.add(low)
        cleaned.append(kw)
    return cleaned


def _render_llm_prompt_template(template_text, content, fallback_prompt):
    """
    渲染可配置 prompt：
    - 支持 {content} 或 {{content}} 占位
    - 若未包含占位，自动在末尾追加评论内容
    """
    tpl = str(template_text or "").strip()
    content_text = str(content or "")
    if not tpl:
        return str(fallback_prompt or "")
    if "{content}" in tpl or "{{content}}" in tpl:
        return tpl.replace("{{content}}", content_text).replace("{content}", content_text)
    return f"{tpl}\n评论内容: {content_text}"


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
    global updates_event_seq
    if not isinstance(item, dict):
        return 0
    snapshot = dict(item)
    with data_lock:
        updates_event_seq += 1
        seq = int(updates_event_seq)
        updates_event_buffer.append({
            "seq": seq,
            "ts": time.time(),
            "data": snapshot,
        })
    return seq


def enqueue_new_data(item):
    """统一的新数据入前端通道。"""
    publish_new_data_event(item)


def drain_msg_queue(collect_new_data=False):
    """
    清理旧队列消息，避免日志消息堆积导致内存持续增长。
    仅用于兼容旧逻辑；新前端增量基于 updates_event_buffer。
    """
    out = []
    try:
        while True:
            m = msg_queue.get_nowait()
            if collect_new_data and isinstance(m, dict) and m.get("type") == "new_data":
                out.append(m.get("data"))
    except queue.Empty:
        pass
    return out


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
    """将对象转换为可 JSON 序列化内容。"""
    try:
        json.dumps(obj, ensure_ascii=False)
        return obj
    except Exception:
        return str(obj)


def _probe_selectors_snapshot(tab, selectors):
    """抓取一组选择器命中状态，便于定位无头偶发问题。"""
    snapshot = []
    for selector in selectors or []:
        item = {
            "selector": selector,
            "matched": False,
            "displayed": False,
            "disabled": False,
            "error": "",
        }
        try:
            node = tab.ele(selector, timeout=0.25)
            item["matched"] = bool(node)
            if node:
                try:
                    item["displayed"] = bool(node.states.is_displayed)
                except Exception:
                    item["displayed"] = False
                try:
                    aria_disabled = (node.attr("aria-disabled") or "").lower() == "true"
                    html_disabled = node.attr("disabled") is not None
                    item["disabled"] = bool(aria_disabled or html_disabled)
                except Exception:
                    item["disabled"] = False
        except Exception as e:
            item["error"] = str(e)
        snapshot.append(item)
    return snapshot


def _capture_runtime_diagnostic(tab, stage, err=None, selectors=None, extra=None):
    """落盘失败现场（json + screenshot），用于无头稳定性排查。"""
    try:
        os.makedirs(DIAG_DIR, exist_ok=True)
    except Exception:
        return ""

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    base = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(stage or "runtime"))[:64]
    prefix = f"{ts}-{base}-{random.randint(1000, 9999)}"
    json_path = os.path.join(DIAG_DIR, f"{prefix}.json")
    png_path = os.path.join(DIAG_DIR, f"{prefix}.png")

    payload = {
        "time": datetime.datetime.now().isoformat(),
        "stage": str(stage or ""),
        "error": str(err or ""),
        "headless_mode": bool(headless_mode),
        "selectors": _probe_selectors_snapshot(tab, selectors),
        "extra": _as_json_safe(extra or {}),
        "screenshot_saved": False,
        "screenshot_path": png_path,
        "screenshot_error": "",
    }

    if tab is not None:
        try:
            payload["url"] = str(tab.url or "")
        except Exception:
            payload["url"] = ""
        try:
            payload["ready_state"] = tab.run_js("return document.readyState")
        except Exception:
            payload["ready_state"] = ""
        try:
            payload["title"] = str(tab.run_js("return document.title || ''") or "")
        except Exception:
            payload["title"] = ""
        try:
            payload["dialog_guard_logs"] = _as_json_safe(
                tab.run_js("return Array.isArray(window.__xmonDialogGuardLogs) ? window.__xmonDialogGuardLogs : []") or []
            )
        except Exception:
            payload["dialog_guard_logs"] = []
        try:
            html_text = str(getattr(tab, "html", "") or "")
            max_chars = max(1000, int(HEADLESS_DIAG_MAX_HTML_CHARS))
            payload["html_head"] = html_text[:max_chars]
            payload["html_len"] = len(html_text)
        except Exception as e:
            payload["html_head"] = ""
            payload["html_len"] = -1
            payload["html_error"] = str(e)

        def _try_capture_screenshot_once():
            local_saved = False
            local_err = ""
            for method_name in ("get_screenshot", "save_screenshot"):
                method = getattr(tab, method_name, None)
                if not callable(method):
                    continue
                try:
                    try:
                        method(path=png_path, full_page=True)
                    except TypeError:
                        try:
                            method(path=png_path)
                        except TypeError:
                            method(png_path)
                    local_saved = os.path.exists(png_path)
                    if local_saved:
                        break
                except Exception as e:
                    local_err = str(e)
            return local_saved, local_err

        shot_saved, shot_err = _try_capture_screenshot_once()
        # 截图阶段若被原生提示框阻断，先清弹窗再二次截图
        if (not shot_saved) and _is_unhandled_prompt_error(shot_err):
            _dismiss_pending_browser_prompt(tab, max_rounds=(5 if headless_mode else 2))
            time.sleep(0.12)
            shot_saved, shot_err = _try_capture_screenshot_once()
        payload["screenshot_saved"] = shot_saved
        payload["screenshot_error"] = shot_err

    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        log_to_ui("warn", f"🧪 失败现场已落盘: {json_path}")
        if payload.get("screenshot_saved"):
            log_to_ui("warn", f"🧪 失败截图已保存: {png_path}")
    except Exception as e:
        log_to_ui("warn", f"⚠️ 写入失败诊断文件失败: {e}")
        return ""
    return json_path


def _wait_document_ready(tab, timeout=5.0):
    """等待页面进入 interactive/complete，减少无头竞态。"""
    deadline = time.time() + max(0.3, float(timeout))
    while time.time() < deadline:
        try:
            ready = str(tab.run_js("return document.readyState || ''") or "").lower()
            if ready in {"interactive", "complete"}:
                return True
        except Exception:
            pass
        time.sleep(0.08)
    return False


def _is_element_actionable(ele):
    """判断元素是否可点击。"""
    if not ele:
        return False
    try:
        if not ele.states.is_displayed:
            return False
    except Exception:
        return False
    try:
        aria_disabled = (ele.attr("aria-disabled") or "").strip().lower() == "true"
        html_disabled = ele.attr("disabled") is not None
        if aria_disabled or html_disabled:
            return False
    except Exception:
        pass
    return True


def _wait_first_actionable(tab, selectors, timeout=2.5, poll=0.12):
    """轮询返回首个可交互元素。"""
    deadline = time.time() + max(0.2, float(timeout))
    while time.time() < deadline:
        for selector in selectors:
            try:
                cands = tab.eles(selector, timeout=0.35)
            except Exception:
                cands = []
            for cand in cands:
                if _is_element_actionable(cand):
                    return cand
        time.sleep(max(0.04, float(poll)))
    return None


def get_random_notification_interval():
    """生成通知扫描随机间隔，避免固定节奏。"""
    low = max(1.0, float(NOTIFICATION_SCAN_INTERVAL_MIN_SEC))
    high = max(low, float(NOTIFICATION_SCAN_INTERVAL_MAX_SEC))
    base = random.uniform(low, high)
    # 长尾抖动：偶发拉长一轮，减少固定频率特征
    if random.random() < 0.12:
        base += random.uniform(high * 0.6, high * 1.8)
    # 轻微提速：偶发短间隔，避免“恒慢速”特征
    if random.random() < 0.06:
        base *= random.uniform(0.72, 0.92)
    upper = max(high * 3.2, high + 2.0)
    base = max(low * 0.85, min(base, upper))
    return round(base, 2)


def get_random_notification_refresh_interval():
    """生成通知页刷新间隔（秒），避免每轮都刷新页面。"""
    low = max(5.0, float(NOTIFICATION_REFRESH_INTERVAL_MIN_SEC))
    high = max(low, float(NOTIFICATION_REFRESH_INTERVAL_MAX_SEC))
    base = random.uniform(low, high)
    # 偶发冷却：显著拉长刷新间隔，降低风控触发概率
    if random.random() < 0.18:
        base += random.uniform(6.0, 22.0)
    # 偶发提前：保留少量随机提前刷新
    if random.random() < 0.08:
        base *= random.uniform(0.82, 0.95)
    upper = max(high * 2.2, high + 8.0)
    base = max(low * 0.9, min(base, upper))
    return round(base, 2)


def _schedule_next_notification_refresh_interval(previous_interval=None):
    """生成下一次通知刷新间隔，带惯性和冷却随机化。"""
    interval = float(get_random_notification_refresh_interval())
    if previous_interval is not None:
        try:
            prev = max(5.0, float(previous_interval))
        except Exception:
            prev = 0.0
        if prev > 0 and random.random() < 0.35:
            mix = random.uniform(0.35, 0.75)
            interval = (prev * mix) + (interval * (1 - mix))

    cooldown_prob = max(0.0, min(1.0, float(NOTIFICATION_REFRESH_COOLDOWN_PROB)))
    if random.random() < cooldown_prob:
        low = max(0.5, float(NOTIFICATION_REFRESH_COOLDOWN_MIN_SEC))
        high = max(low, float(NOTIFICATION_REFRESH_COOLDOWN_MAX_SEC))
        interval += random.uniform(low, high)

    return round(max(5.0, interval), 2)


def get_random_maintenance_interval():
    """生成浏览器维护间隔（秒）。"""
    low = max(60.0, float(MAINTENANCE_INTERVAL_MIN_SEC))
    high = max(low, float(MAINTENANCE_INTERVAL_MAX_SEC))
    return round(random.uniform(low, high), 2)


def get_random_task_parallel(task_count):
    """按任务数返回随机并发数，避免每轮固定并发模式。"""
    if task_count <= 1:
        return 1
    low = max(1, min(TASK_PARALLEL_MIN, task_count))
    high = max(low, min(TASK_PARALLEL_MAX, task_count))
    return random.randint(low, high)


def reorder_articles_for_scan(articles):
    """对文章进行分块随机重排，打散读取顺序但不丢数据。"""
    if not articles:
        return []

    reordered = []
    chunk_low = max(1, ARTICLE_REORDER_CHUNK_MIN)
    chunk_high = max(chunk_low, ARTICLE_REORDER_CHUNK_MAX)
    idx = 0
    items = list(articles)

    while idx < len(items):
        chunk_size = random.randint(chunk_low, chunk_high)
        chunk = items[idx: idx + chunk_size]
        if len(chunk) > 1 and random.random() < 0.75:
            random.shuffle(chunk)
        reordered.extend(chunk)
        idx += chunk_size

    return reordered


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
    text = str(content or "")
    text = text.replace("＠", "@")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _contains_emoji_char(ch):
    cp = ord(ch)
    for low, high in EMOJI_UNICODE_RANGES:
        if low <= cp <= high:
            return True
    return False


def _is_emoji_only_content(content):
    text = _normalize_content_for_filter(content)
    if not text:
        return False

    has_emoji = False
    for ch in text:
        if ch.isspace() or ch in EMOJI_JOINER_CHARS:
            continue
        if _contains_emoji_char(ch):
            has_emoji = True
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("S"):
            continue
        return False
    return has_emoji


def should_skip_content_by_policy(content, allow_llm_hard_filter=None):
    """统一内容过滤策略：返回 (should_skip, reason)。"""
    text = _normalize_content_for_filter(content)
    if not text:
        return False, ""

    lower_text = text.lower()
    for mention in CONTENT_FILTER_BLOCKED_MENTIONS:
        mention_norm = str(mention or "").strip().lower()
        if mention_norm and mention_norm in lower_text:
            return True, "blocked_mention"

    if _is_emoji_only_content(text):
        return True, "emoji_only"

    if allow_llm_hard_filter is None:
        allow_llm_hard_filter = bool(LLM_HARD_FILTER_ENABLED)
    if allow_llm_hard_filter:
        llm_skip, llm_reason = _should_skip_by_llm_filter(text)
        if llm_skip:
            return True, llm_reason or "llm_filter"

    return False, ""


def _llm_filter_endpoint(base_url=None):
    base = str(base_url if base_url is not None else LLM_FILTER_BASE_URL or "").strip()
    if not base:
        return ""
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    if base.endswith("/v1/"):
        return f"{base}chat/completions"
    return f"{base}/chat/completions"


def _llm_runtime_ready(base_url=None, model=None):
    model_name = str(model if model is not None else LLM_FILTER_MODEL or "").strip()
    return bool(model_name and _llm_filter_endpoint(base_url=base_url))


def _llm_filter_is_ready(base_url=None, model=None, enabled=None):
    enabled_flag = LLM_FILTER_ENABLED if enabled is None else bool(enabled)
    return bool(enabled_flag and _llm_runtime_ready(base_url=base_url, model=model))


def _doubao_tts_is_ready():
    return bool(
        DOUBAO_TTS_ENABLED
        and str(DOUBAO_TTS_APP_ID or "").strip()
        and str(DOUBAO_TTS_ACCESS_TOKEN or "").strip()
        and str(DOUBAO_TTS_VOICE_TYPE or "").strip()
    )


def _doubao_tts_mime_by_encoding(encoding):
    enc = str(encoding or "").strip().lower()
    if enc == "wav":
        return "audio/wav"
    if enc in {"ogg", "opus"}:
        return "audio/ogg"
    return "audio/mpeg"


def _truncate_text_for_tts(text):
    content = str(text or "").strip()
    max_chars = max(20, int(DOUBAO_TTS_TEXT_MAX_CHARS))
    if len(content) <= max_chars:
        return content
    return f"{content[:max_chars]}..."


def _synthesize_doubao_tts_audio_base64(text):
    if not _doubao_tts_is_ready():
        raise RuntimeError("豆包TTS未就绪：请配置 AppID/AccessToken/音色")

    text_payload = _truncate_text_for_tts(text)
    if not text_payload:
        raise RuntimeError("语音文本为空")

    req_obj = {
        "app": {
            "appid": str(DOUBAO_TTS_APP_ID),
            # 在线TTS接口要求 app.token 非空，这里复用 Access Token。
            "token": str(DOUBAO_TTS_ACCESS_TOKEN),
            "cluster": str(DOUBAO_TTS_CLUSTER),
        },
        "user": {"uid": str(DOUBAO_TTS_UID or "xmonitor-notify")},
        "audio": {
            "voice_type": str(DOUBAO_TTS_VOICE_TYPE),
            "encoding": str(DOUBAO_TTS_ENCODING or "mp3"),
            "speed_ratio": float(DOUBAO_TTS_SPEED_RATIO),
            "volume_ratio": float(DOUBAO_TTS_VOLUME_RATIO),
            "pitch_ratio": float(DOUBAO_TTS_PITCH_RATIO),
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": text_payload,
            "text_type": "plain",
            "operation": "query",
        },
    }
    body = json.dumps(req_obj, ensure_ascii=False).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer;{DOUBAO_TTS_ACCESS_TOKEN}",
    }
    req = urllib.request.Request(DOUBAO_TTS_ENDPOINT, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=max(3.0, float(DOUBAO_TTS_TIMEOUT_SEC))) as resp:
            raw_bytes = resp.read() or b""
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = (e.read() or b"").decode("utf-8", errors="ignore")
        except Exception:
            detail = ""
        raise RuntimeError(f"豆包TTS HTTP错误: {e.code} {detail[:200]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"豆包TTS网络错误: {e}") from e

    try:
        resp_obj = json.loads(raw_bytes.decode("utf-8", errors="ignore"))
    except Exception as e:
        raise RuntimeError(f"豆包TTS响应解析失败: {e}") from e

    code = int(resp_obj.get("code", 0) or 0)
    if code not in {0, 3000}:
        msg = str(resp_obj.get("message", "") or "").strip()
        raise RuntimeError(f"豆包TTS返回失败 code={code} msg={msg}")

    audio_b64 = resp_obj.get("data", "")
    if isinstance(audio_b64, dict):
        audio_b64 = audio_b64.get("audio", "")
    audio_b64 = str(audio_b64 or "").strip()
    if not audio_b64:
        raise RuntimeError("豆包TTS返回音频为空")

    # 快速校验base64合法性，避免前端播放报错
    try:
        base64.b64decode(audio_b64, validate=True)
    except Exception as e:
        raise RuntimeError(f"豆包TTS音频base64无效: {e}") from e

    return audio_b64


def _prune_llm_filter_cache(now_ts=None):
    if now_ts is None:
        now_ts = time.time()
    expire_before = now_ts - max(60, LLM_FILTER_CACHE_TTL_SEC)
    expired = [k for k, v in llm_filter_cache.items() if float(v.get("ts", 0)) < expire_before]
    for k in expired:
        llm_filter_cache.pop(k, None)
    if len(llm_filter_cache) > max(100, LLM_FILTER_CACHE_MAX_ENTRIES):
        overflow = len(llm_filter_cache) - max(100, LLM_FILTER_CACHE_MAX_ENTRIES)
        old_items = sorted(llm_filter_cache.items(), key=lambda x: float(x[1].get("ts", 0)))[:overflow]
        for k, _ in old_items:
            llm_filter_cache.pop(k, None)


def _parse_json_object_from_text(raw_text):
    text = str(raw_text or "").strip()
    if not text:
        return {}
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # 兼容模型输出 ```json ... ``` 或夹杂解释文本的场景
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except Exception:
            return {}
    return {}


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
    endpoint = _llm_filter_endpoint(base_url=base_url)
    model_name = str(model if model is not None else LLM_FILTER_MODEL or "").strip()
    if not endpoint:
        raise ValueError("LLM Base URL 未配置")
    if not model_name:
        raise ValueError("LLM 模型名未配置")

    api_key_val = str(api_key if api_key is not None else LLM_FILTER_API_KEY or "EMPTY").strip() or "EMPTY"
    timeout_val = clamp_llm_timeout(timeout_sec if timeout_sec is not None else LLM_FILTER_TIMEOUT_SEC)

    base_payload = {
        "model": model_name,
        "temperature": max(0.0, min(1.2, float(temperature))),
        "max_tokens": int(max(32, min(512, int(max_tokens)))),
        "messages": [
            {"role": "system", "content": str(system_prompt or "").strip()},
            {"role": "user", "content": str(user_prompt or "").strip()},
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key_val}",
    }

    data = {}
    last_err = None
    last_err_body = ""
    payload_variants = [
        {**base_payload, "response_format": {"type": "json_object"}},
        dict(base_payload),
    ]
    for payload in payload_variants:
        try:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout_val) as resp:
                raw_resp = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(raw_resp or "{}")
            last_err = None
            break
        except urllib.error.HTTPError as e:
            last_err = e
            try:
                last_err_body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                last_err_body = ""
            continue

    if last_err is not None and not data:
        # 兼容 Ollama 仅暴露 /api/chat 的场景：OpenAI兼容路由404时自动回退
        fallback_allowed = (
            int(getattr(last_err, "code", 0) or 0) == 404
            or ("404 page not found" in str(last_err_body or "").lower())
        )
        if fallback_allowed:
            native_obj, native_raw = _call_ollama_native_json(
                system_prompt,
                user_prompt,
                base_url=base_url,
                model=model_name,
                timeout_sec=timeout_val,
            )
            return native_obj, native_raw

        err_text = f"HTTP {getattr(last_err, 'code', 'error')}"
        if last_err_body:
            err_text = f"{err_text}: {last_err_body[:220]}"
        raise RuntimeError(err_text)

    content_text = ""
    try:
        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content_text = str(message.get("content") or "")
    except Exception:
        content_text = ""

    return _parse_json_object_from_text(content_text), content_text


def _guess_ollama_native_endpoint(base_url):
    base = str(base_url or LLM_FILTER_BASE_URL or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/v1/chat/completions"):
        base = base[: -len("/v1/chat/completions")]
    elif base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    elif base.endswith("/v1"):
        base = base[: -len("/v1")]
    return f"{base}/api/chat"


def _call_ollama_native_json(system_prompt, user_prompt, *, base_url=None, model=None, timeout_sec=None):
    endpoint = _guess_ollama_native_endpoint(base_url)
    model_name = str(model if model is not None else LLM_FILTER_MODEL or "").strip()
    if not endpoint:
        raise ValueError("Ollama endpoint 未配置")
    if not model_name:
        raise ValueError("LLM 模型名未配置")

    timeout_val = clamp_llm_timeout(timeout_sec if timeout_sec is not None else LLM_FILTER_TIMEOUT_SEC)

    payload = {
        "model": model_name,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": str(system_prompt or "").strip()},
            {"role": "user", "content": str(user_prompt or "").strip()},
        ],
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_val) as resp:
        raw_resp = resp.read().decode("utf-8", errors="ignore")

    data = json.loads(raw_resp or "{}")
    msg = data.get("message") or {}
    content_text = str(msg.get("content") or "")
    return _parse_json_object_from_text(content_text), content_text


def _normalize_dm_rewrite_signature(text):
    raw = normalize_content_for_dedupe(_normalize_text_for_compare(text or ""))
    if not raw:
        return ""
    raw = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", raw.lower())
    if not raw:
        return ""
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _build_dm_llm_rewrite_prompt(template_text):
    tpl = str(DM_LLM_REWRITE_PROMPT_TEMPLATE or "").strip() or DM_LLM_REWRITE_DEFAULT_PROMPT
    template_clean = _sanitize_dm_message_text(template_text)
    if "{template}" in tpl or "{{template}}" in tpl:
        return tpl.replace("{{template}}", template_clean).replace("{template}", template_clean)
    return f"{tpl}\n模板如下：\n{template_clean}"


def _dm_rewrite_longest_common_substring_len(source_text, generated_text):
    src = _normalize_text_for_compare(source_text or "")
    dst = _normalize_text_for_compare(generated_text or "")
    if not src or not dst:
        return 0
    # 联系方式、长数字是业务硬信息，允许保留，不参与“连续复用”判断
    src = re.sub(r"(工程师)?微信\s*[:：]?\s*[0-9a-zA-Z_-]{4,}", "<contact>", src, flags=re.IGNORECASE)
    dst = re.sub(r"(工程师)?微信\s*[:：]?\s*[0-9a-zA-Z_-]{4,}", "<contact>", dst, flags=re.IGNORECASE)
    src = re.sub(r"\d{6,}", "<num>", src)
    dst = re.sub(r"\d{6,}", "<num>", dst)
    rows = len(src) + 1
    cols = len(dst) + 1
    dp = [0] * cols
    max_len = 0
    for i in range(1, rows):
        prev = 0
        for j in range(1, cols):
            cur = dp[j]
            if src[i - 1] == dst[j - 1]:
                dp[j] = prev + 1
                if dp[j] > max_len:
                    max_len = dp[j]
            else:
                dp[j] = 0
            prev = cur
    return max_len


def _extract_dm_rewrite_forbidden_phrases(template_text, max_items=5):
    text = _sanitize_dm_message_text(template_text)
    if not text:
        return []
    items = []
    seen = set()
    parts = re.split(r"[，。！？；;,\n]+", text)
    for part in parts:
        p = str(part or "").strip()
        if len(p) < 9 or len(p) > 28:
            continue
        # 联系方式和数字串允许复用，避免误伤核心信息
        if re.search(r"\d{4,}", p):
            continue
        sig = normalize_content_for_dedupe(p.lower())
        if not sig or sig in seen:
            continue
        seen.add(sig)
        items.append(p)
        if len(items) >= max(1, int(max_items)):
            break
    return items


def _dm_rewrite_contains_forbidden_phrase(generated_text, forbidden_phrases):
    if not forbidden_phrases:
        return ""
    dst = normalize_content_for_dedupe(_normalize_text_for_compare(generated_text or ""))
    if not dst:
        return ""
    for phrase in forbidden_phrases:
        p = normalize_content_for_dedupe(_normalize_text_for_compare(phrase or ""))
        if p and p in dst:
            return phrase
    return ""


def _dm_rewrite_similarity_score(source_text, generated_text):
    src = _normalize_text_for_compare(source_text or "")
    dst = _normalize_text_for_compare(generated_text or "")
    if not src or not dst:
        return 0.0
    try:
        return float(difflib.SequenceMatcher(None, src, dst).ratio())
    except Exception:
        return 0.0


def _dm_rewrite_is_too_similar(source_text, generated_text):
    src = _normalize_text_for_compare(source_text or "")
    dst = _normalize_text_for_compare(generated_text or "")
    if not src or not dst:
        return False, 0.0, 0, 0
    score = _dm_rewrite_similarity_score(src, dst)
    diff_chars = abs(len(src) - len(dst))
    shared_run = _dm_rewrite_longest_common_substring_len(src, dst)
    if src == dst:
        return True, score, diff_chars, shared_run
    too_similar = (score >= float(DM_LLM_REWRITE_SIMILARITY_MAX)) and (diff_chars < int(DM_LLM_REWRITE_MIN_DIFF_CHARS))
    if shared_run >= int(DM_LLM_REWRITE_MAX_SHARED_RUN) and score >= 0.45:
        too_similar = True
    return bool(too_similar), score, diff_chars, shared_run


def _record_dm_llm_rewrite_signature(sig):
    if not sig:
        return
    with dm_llm_rewrite_lock:
        dm_llm_rewrite_history.append(sig)


def _is_dm_llm_rewrite_duplicate(sig):
    if not sig:
        return False
    with dm_llm_rewrite_lock:
        return sig in dm_llm_rewrite_history


def _generate_dm_text_with_llm(template_text):
    """根据模板生成第二条私信文案（总是生成，失败即返回错误）。"""
    template_clean = _sanitize_dm_message_text(template_text)
    if not template_clean:
        return False, "", {
            "error_code": "E_DM_LLM_TEMPLATE_EMPTY",
            "error_detail": "私信模板为空，无法生成",
            "llm_used": False,
            "latency_ms": 0,
        }
    if not _llm_runtime_ready():
        return False, "", {
            "error_code": "E_DM_LLM_NOT_READY",
            "error_detail": "LLM模型未就绪，请检查 Base URL 和模型名",
            "llm_used": False,
            "latency_ms": 0,
        }

    prompt = _build_dm_llm_rewrite_prompt(template_clean)
    forbidden_phrases = _extract_dm_rewrite_forbidden_phrases(template_clean)
    if forbidden_phrases:
        banned = "\n".join(f"- {x}" for x in forbidden_phrases)
        prompt = (
            f"{prompt}\n\n请避免原样复用下面这些模板短语（可同义改写）：\n"
            f"{banned}"
        )
    attempts = max(1, int(DM_LLM_REWRITE_MAX_REGEN) + 1)
    last_meta = {
        "error_code": "E_DM_LLM_GENERATE_FAILED",
        "error_detail": "未知错误",
        "llm_used": True,
        "latency_ms": 0,
    }
    style_hints = [
        "开头不要使用“您好，我是…”，换成自然一点的开场",
        "减少“感谢您的关注和支持”这种固定套话，改成同义表达",
        "一句一意，优先短句，读起来像真人即兴输入",
        "先给价值点，再给联系方式，结尾一句行动建议",
        "语气礼貌但干练，不要出现公文感",
        "保持销售目标明确，但像聊天而不是公告",
    ]

    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            style_hint = random.choice(style_hints)
            result_obj, raw_text = _call_openai_compatible_json(
                "你是私信改写助手。只输出JSON，不要输出模板原句。",
                (
                    prompt
                    + f"\n\n补充风格要求：{style_hint}。"
                    + "\n请输出JSON：{\"text\":\"改写后的私信正文\"}"
                ),
                max_tokens=min(512, max(96, int(DM_LLM_REWRITE_MAX_CHARS * 2))),
                timeout_sec=LLM_FILTER_TIMEOUT_SEC,
                temperature=DM_LLM_REWRITE_TEMPERATURE,
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            generated = ""
            if isinstance(result_obj, dict):
                generated = str(
                    result_obj.get("text")
                    or result_obj.get("message")
                    or result_obj.get("content")
                    or ""
                )
            if not generated:
                generated = str(raw_text or "")
            generated = _sanitize_dm_message_text(generated)
            if len(generated) > int(DM_LLM_REWRITE_MAX_CHARS):
                generated = generated[: int(DM_LLM_REWRITE_MAX_CHARS)].rstrip()

            if not generated:
                last_meta = {
                    "error_code": "E_DM_LLM_EMPTY_OUTPUT",
                    "error_detail": "LLM返回为空",
                    "llm_used": True,
                    "latency_ms": latency_ms,
                }
                continue

            copied_phrase = _dm_rewrite_contains_forbidden_phrase(generated, forbidden_phrases)
            if copied_phrase:
                last_meta = {
                    "error_code": "E_DM_LLM_COPY_PHRASE",
                    "error_detail": f"命中原句短语复用: {copied_phrase}",
                    "llm_used": True,
                    "latency_ms": latency_ms,
                }
                continue

            too_similar, sim_score, diff_chars, shared_run = _dm_rewrite_is_too_similar(template_clean, generated)
            if too_similar:
                last_meta = {
                    "error_code": "E_DM_LLM_TOO_SIMILAR",
                    "error_detail": (
                        f"改写与模板过于相似(sim={sim_score:.3f}, diff={diff_chars}, shared={shared_run})"
                    ),
                    "llm_used": True,
                    "latency_ms": latency_ms,
                }
                continue

            sig = _normalize_dm_rewrite_signature(generated)
            if _is_dm_llm_rewrite_duplicate(sig):
                last_meta = {
                    "error_code": "E_DM_LLM_DUPLICATE_TEXT",
                    "error_detail": f"生成文案命中最近{DM_LLM_REWRITE_DEDUPE_SIZE}条去重窗口",
                    "llm_used": True,
                    "latency_ms": latency_ms,
                }
                continue

            _record_dm_llm_rewrite_signature(sig)
            return True, generated, {
                "error_code": "",
                "error_detail": "",
                "llm_used": True,
                "latency_ms": latency_ms,
                "regen_attempt": attempt,
            }
        except Exception as e:
            latency_ms = int((time.perf_counter() - started) * 1000)
            err_text = str(e or "").strip()
            err_code = "E_DM_LLM_GENERATE_FAILED"
            if "timed out" in err_text.lower():
                err_code = "E_DM_LLM_TIMEOUT"
            last_meta = {
                "error_code": err_code,
                "error_detail": err_text or "LLM改写失败",
                "llm_used": True,
                "latency_ms": latency_ms,
            }

    return False, "", last_meta


def _call_openai_compatible_filter_api(content):
    default_prompt = (
        "你是评论过滤器。只输出JSON对象，不要输出其他文本。\n"
        "返回字段: skip(boolean), reason(string), intent_score(number 0-100)。\n"
        "规则:\n"
        "1) 只有在明显垃圾内容、纯表情或完全无意义字符时，才返回 skip=true。\n"
        "2) 其他情况统一返回 skip=false。\n"
        "3) reason 使用简短英文下划线词，例如 normal/spam/emoji_or_noise。\n"
        f"评论内容: {content}"
    )
    prompt = _render_llm_prompt_template(
        LLM_FILTER_PROMPT_TEMPLATE,
        content,
        default_prompt,
    )
    result_obj, _ = _call_openai_compatible_json(
        "You are a strict JSON classifier.",
        prompt,
        max_tokens=80,
    )
    if not isinstance(result_obj, dict) or not result_obj:
        return False, ""

    skip_raw = result_obj.get("skip", False)
    if isinstance(skip_raw, str):
        skip = skip_raw.strip().lower() in {"1", "true", "yes", "y"}
    else:
        skip = bool(skip_raw)
    reason = str(result_obj.get("reason", "") or "").strip().lower()
    if skip and not reason:
        reason = "llm_filter"
    return skip, reason


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
    """根据判定理由识别明显负向（非购买/噪声）语义。"""
    txt = str(reason_text or "").strip().lower()
    if not txt:
        return False
    negative_keywords = [
        "noise",
        "low",
        "噪声",
        "无意向",
        "无购买",
        "非购买",
        "无关",
        "不相关",
        "闲聊",
        "灌水",
        "段子",
        "调侃",
        "吐槽",
        "副厂配件",
        "极影相机",
        "手机壳",
        "fotorgear",
    ]
    return any(k in txt for k in negative_keywords)


def _find_keyword_hits(text_lower, keywords):
    hits = []
    src = str(text_lower or "").lower()
    if not src:
        return hits
    for kw in keywords:
        kw_norm = str(kw or "").strip().lower()
        if kw_norm and kw_norm in src and kw_norm not in hits:
            hits.append(kw_norm)
    return hits


def _is_short_reply_intent_signal(content):
    """
    识别“1/11/111/扣1”等短回复意向信号。
    这类文本在实际私信转化流程中常用来表达“有兴趣/请联系我”。
    """
    raw = str(content or "").strip()
    if not raw:
        return False
    # 统一全角/半角，减少“１/١”等形态漏判
    norm = unicodedata.normalize("NFKC", raw).lower()
    compact = re.sub(r"\s+", "", norm)
    compact = compact.replace("＋", "+")

    # 纯数字短回（常见: 1 / 11 / 111）
    if re.fullmatch(r"1{1,4}", compact):
        return True
    # +1 / +11
    if re.fullmatch(r"\+1{1,4}", compact):
        return True
    # 扣1 / 扣11 / 扣111 / 扣一
    if re.fullmatch(r"扣1{1,4}", compact) or compact == "扣一":
        return True
    return False


def _is_performance_consult_signal(content):
    """识别“性能/速度/算力规格”类购买前咨询。"""
    raw = str(content or "").strip()
    if not raw:
        return False
    norm = unicodedata.normalize("NFKC", raw).lower()
    compact = re.sub(r"\s+", "", norm)
    if not compact:
        return False

    intent_anchor = any(k in compact for k in ["算力舱", "算力仓", "算力", "配置", "规格", "机型", "cpu", "gpu"])
    perf_anchor = any(k in compact for k in ["速度", "性能", "跑", "并发", "吞吐", "延迟", "带宽"])
    ask_anchor = ("?" in norm) or ("？" in raw) or any(k in compact for k in ["多少", "几个", "能跑", "多快", "怎样", "怎么"])
    return bool((intent_anchor and perf_anchor) or (intent_anchor and ask_anchor))


def _is_non_business_meme_signal(content):
    """识别与业务无关的网络梗/段子，避免误触发意向播报。"""
    raw = str(content or "").strip()
    if not raw:
        return False
    norm = unicodedata.normalize("NFKC", raw).lower()
    compact = re.sub(r"\s+", "", norm)
    if not compact:
        return False
    business_anchors = [
        "懒猫",
        "lazycat",
        "微服",
        "算力舱",
        "云电脑",
        "内网穿透",
        "沙箱",
        "openclaw",
        "私有化",
        "部署",
    ]
    has_business_context = any(k in compact for k in business_anchors)
    has_business_question = any(
        k in compact for k in ["咨询", "了解", "购买", "报价", "价格", "多少钱", "试用", "部署", "合同", "发票", "联系", "怎么", "如何", "支持"]
    )

    hard_meme_patterns = [
        "压力给到了义乌",
        "压力给到义乌",
        "压力给到了",
        "压力给到",
    ]
    if any(p in compact for p in hard_meme_patterns):
        return True

    consumer_patterns = [
        "副厂配件",
        "极影相机",
        "vivo好",
        "iphone",
        "安卓",
        "诺基亚",
        "fotorgear",
        "手机壳",
        "镜头",
        "掌中宝",
        "v998",
        "338c",
    ]
    if any(p in compact for p in consumer_patterns) and not (has_business_context and has_business_question):
        return True

    # token 成本吐槽默认按非业务噪声处理；但若明确在咨询产品能力/采购，不在此处拦截。
    if "token" in compact and any(k in compact for k in ["vivo", "发点", "计费", "烧完", "耗尽", "星期几", "问天气"]):
        if has_business_context and has_business_question:
            return False
        return True
    return False


def _is_business_consult_signal(content):
    """识别业务咨询类文本，提升潜在商机召回。"""
    text = _normalize_content_for_filter(content)
    if not text:
        return False
    text_low = text.lower()
    consult_hits = _find_keyword_hits(text_low, INTENT_CONSULT_KEYWORDS)
    if not consult_hits:
        return False

    product_hits = _find_keyword_hits(text_low, INTENT_PRODUCT_KEYWORDS)
    contact_hits = _find_keyword_hits(text_low, INTENT_CONTACT_KEYWORDS)
    has_qmark = ("?" in text) or ("？" in text)

    if product_hits:
        return True
    if contact_hits and any(k in text_low for k in ["咨询", "了解", "报价", "价格", "购买", "试用", "部署", "开通", "合作"]):
        return True
    if has_qmark and any(k in text_low for k in ["企业版", "私有化", "部署", "试用", "采购", "算力", "性能"]):
        return True
    return False


def _rule_based_intent_analysis(content):
    text = _normalize_content_for_filter(content)
    if not text:
        return {
            "intent_score": 0,
            "intent_level": "noise",
            "signals": ["empty_content"],
            "force_notify": False,
            "block_intent": False,
            "force_keywords": [],
            "non_target_keywords": [],
        }
    if _is_emoji_only_content(text):
        return {
            "intent_score": 5,
            "intent_level": "noise",
            "signals": ["emoji_only"],
            "force_notify": False,
            "block_intent": False,
            "force_keywords": [],
            "non_target_keywords": [],
        }

    if _is_short_reply_intent_signal(text):
        return {
            "intent_score": 62,
            "intent_level": "medium",
            "signals": ["short_reply_intent_signal"],
            "force_notify": True,
            "block_intent": False,
            "force_keywords": ["short_reply_signal"],
            "non_target_keywords": [],
        }

    if _is_performance_consult_signal(text):
        return {
            "intent_score": 72,
            "intent_level": "medium",
            "signals": ["performance_consult_signal"],
            "force_notify": True,
            "block_intent": False,
            "force_keywords": ["performance_consult"],
            "non_target_keywords": [],
        }

    if _is_business_consult_signal(text):
        return {
            "intent_score": 68,
            "intent_level": "medium",
            "signals": ["business_consult_signal"],
            "force_notify": True,
            "block_intent": False,
            "force_keywords": ["business_consult"],
            "non_target_keywords": [],
        }

    if _is_non_business_meme_signal(text):
        return {
            "intent_score": 8,
            "intent_level": "noise",
            "signals": ["non_business_meme_signal"],
            "force_notify": False,
            "block_intent": True,
            "force_keywords": [],
            "non_target_keywords": ["meme"],
        }

    text_low = text.lower()
    force_hits = _find_keyword_hits(text_low, INTENT_FORCE_NOTIFY_KEYWORDS)
    product_hits = _find_keyword_hits(text_low, INTENT_PRODUCT_KEYWORDS)
    contact_hits = _find_keyword_hits(text_low, INTENT_CONTACT_KEYWORDS)
    consult_hits = _find_keyword_hits(text_low, INTENT_CONSULT_KEYWORDS)
    non_target_hits = _find_keyword_hits(text_low, INTENT_NON_TARGET_TOPIC_KEYWORDS)

    text_len = len(text)
    if text_len <= 2:
        score = 15
        signals = ["very_short_text"]
    elif text_len <= 6:
        score = 25
        signals = ["short_text"]
    elif text_len <= 20:
        score = 35
        signals = ["normal_text"]
    else:
        score = 45
        signals = ["long_text"]

    force_notify = False
    block_intent = False

    if force_hits:
        score = max(score, 74 if len(force_hits) == 1 else 82)
        force_notify = True
        signals.append("force_intent_keyword")

    if product_hits:
        score += min(15, 5 * len(product_hits))
        signals.append("product_keyword")

    if contact_hits:
        score += min(14, 7 * len(contact_hits))
        signals.append("contact_keyword")

    if consult_hits and product_hits:
        score = max(score, 58)
        force_notify = True
        signals.append("product_consult_signal")

    if product_hits and contact_hits:
        score = max(score, 68)
        force_notify = True
        signals.append("product_contact_combo")

    if non_target_hits and not force_hits and not (product_hits and contact_hits):
        score = min(score, 24)
        block_intent = True
        signals.append("non_target_topic")
    elif non_target_hits and not product_hits:
        # 非目标消费电子/品牌/型号讨论：即便出现“价格/想买”等词，也按噪声处理
        score = min(score, 18)
        force_notify = False
        block_intent = True
        signals.append("non_target_consumer_topic")

    score = max(0, min(100, int(score)))
    level = _score_to_intent_level(score)

    return {
        "intent_score": score,
        "intent_level": level,
        "signals": list(dict.fromkeys(signals))[:10],
        "force_notify": bool(force_notify),
        "block_intent": bool(block_intent),
        "force_keywords": list(force_hits)[:8],
        "non_target_keywords": list(non_target_hits)[:8],
    }


def _build_intent_analysis_prompt(content):
    default_prompt = (
        "你是销售线索意向识别器。请严格输出JSON对象，不要输出任何解释文本。\n"
        "字段:\n"
        "- intent_score: 0-100\n"
        "- intent_level: high|medium|low|noise\n"
        "- is_intent_user: true/false\n"
        "- force_notify: true/false\n"
        "- buying_signals: string[]\n"
        "- reason: string\n\n"
        "业务背景（来自 lazycat.cloud 官网）:\n"
        "懒猫微服（LazyCat）提供应用云电脑、内网穿透、沙箱隔离、一站式部署（含大模型部署）等能力，主打按需付费。\n"
        "常见购买场景包括：询价/报价、套餐选择、试用开通、企业或教育部署、售后与续费咨询。\n\n"
        "判定原则(销售线索优先):\n"
        "1) 明确购买/询价/报价/价格/下单/试用/部署/联系方式咨询（微信/vx/whatsapp）=> medium/high。\n"
        "2) 仅情绪表达、闲聊、纯表情、无意义灌水 => low/noise。\n"
        "2.1) 网络梗/段子（例如“压力给到了义乌”）按无业务相关处理，判定 noise。\n"
        "2.2) 对 token 计费的吐槽、手机品牌讨论（如 vivo）、副厂配件/极影相机等非购买讨论，判定 noise。\n"
        "2.3) 手机/数码消费品讨论（如 iPhone/安卓/诺基亚/Fotorgear/掌中宝/v998/338c/镜头/手机壳），即使出现价格词，也判定 noise。\n"
        "3) 出现“多少钱/什么价格/怎么买/购买方式/开票/合同/授权/代理/优惠”等词时，提高意向分。\n"
        "4) “1/11/111/+1/扣1”这类短回复在“回复你”通知中通常代表愿意沟通，至少判为 medium。\n"
        "5) force_notify 在强意向线索时设为 true（询价、采购、留联系方式、明确要买/试用/部署）。\n"
        "6) 若涉及本产品功能/性能/部署/试用等咨询但信息不完整，宁可判为 medium，也不要判 low/noise。\n"
        f"评论内容: {content}"
    )
    return _render_llm_prompt_template(
        LLM_INTENT_PROMPT_TEMPLATE,
        content,
        default_prompt,
    )


def _llm_intent_analysis(content, *, base_url=None, api_key=None, model=None, timeout_sec=None):
    prompt = _build_intent_analysis_prompt(content)
    result_obj, _ = _call_openai_compatible_json(
        "You are a strict JSON intent classifier.",
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
        score = int(float(result_obj.get("intent_score", 0)))
    except Exception:
        score = 0
    score = max(0, min(100, score))

    level = str(result_obj.get("intent_level", "") or "").strip().lower()
    if level not in {"high", "medium", "low", "noise"}:
        level = _score_to_intent_level(score)

    is_intent_user = result_obj.get("is_intent_user", None)
    if isinstance(is_intent_user, str):
        is_intent_user = is_intent_user.strip().lower() in {"1", "true", "yes", "y"}
    elif is_intent_user is None:
        is_intent_user = score >= 50
    else:
        is_intent_user = bool(is_intent_user)

    raw_signals = result_obj.get("buying_signals", [])
    if not isinstance(raw_signals, list):
        raw_signals = [raw_signals] if raw_signals else []
    buying_signals = [str(x).strip() for x in raw_signals if str(x).strip()][:8]
    reason = str(result_obj.get("reason", "") or "").strip()
    force_notify_raw = result_obj.get("force_notify", False)
    if isinstance(force_notify_raw, str):
        force_notify = force_notify_raw.strip().lower() in {"1", "true", "yes", "y"}
    else:
        force_notify = bool(force_notify_raw)

    # 纠正模型内部自相矛盾：reason/level 明确负向时，不允许高分与强提醒。
    if level in {"noise", "low"}:
        score = min(score, 24 if level == "noise" else 45)
        if score < 50:
            is_intent_user = False
        force_notify = False
    if _is_negative_intent_reason(reason):
        score = min(score, 30)
        level = "noise" if level == "noise" else "low"
        is_intent_user = False
        force_notify = False

    return {
        "intent_score": score,
        "intent_level": level,
        "is_intent_user": bool(is_intent_user),
        "force_notify": bool(force_notify),
        "buying_signals": buying_signals,
        "reason": reason,
    }


def analyze_comment_intent(content, *, base_url=None, api_key=None, model=None, timeout_sec=None):
    text = _normalize_content_for_filter(content)
    rule_result = _rule_based_intent_analysis(text)
    rule_score = int(rule_result.get("intent_score", 0))
    rule_level = str(rule_result.get("intent_level", "noise"))
    rule_signals = list(rule_result.get("signals", []))
    rule_force_notify = bool(rule_result.get("force_notify", False))
    rule_block_intent = bool(rule_result.get("block_intent", False))

    result = {
        "content": text,
        "intent_score": rule_score,
        "intent_level": rule_level,
        "is_intent_user": bool(rule_force_notify or rule_score >= 55),
        "force_notify": bool(rule_force_notify),
        "block_intent": bool(rule_block_intent),
        "signals": list(rule_signals),
        "reason": "rule_only",
        "rule_score": rule_score,
        "rule_level": rule_level,
        "rule_force_notify": bool(rule_force_notify),
        "rule_force_keywords": list(rule_result.get("force_keywords", [])),
        "rule_non_target_keywords": list(rule_result.get("non_target_keywords", [])),
        "llm_used": False,
        "llm_score": None,
        "llm_level": "",
        "llm_reason": "",
        "llm_error": "",
    }
    preview = _normalize_one_line(text, 120) if text else ""
    log_to_ui(
        "debug",
        f"🤖 [Intent] analyze_start len={len(text)} rule_score={rule_score} text={preview}"
    )

    if not _llm_runtime_ready(base_url=base_url, model=model):
        log_to_ui(
            "debug",
            "🤖 [Intent] llm_skip runtime_not_ready -> rule_only"
        )
        return result

    try:
        llm_result = _llm_intent_analysis(
            text,
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_sec=timeout_sec,
        )
        if not llm_result:
            log_to_ui(
                "debug",
                "🤖 [Intent] llm_empty_result -> rule_only"
            )
            return result
    except Exception as e:
        result["llm_error"] = str(e)
        log_to_ui("warn", f"🤖 [Intent] llm_error: {e}")
        return result

    llm_score = int(llm_result.get("intent_score", 0))
    llm_level = str(llm_result.get("intent_level", "noise"))
    llm_reason = str(llm_result.get("reason", "") or "").strip()
    llm_signals = list(llm_result.get("buying_signals", []))
    llm_force_notify = bool(llm_result.get("force_notify", False))
    llm_is_intent_user = bool(llm_result.get("is_intent_user", False))
    llm_reason_negative = _is_negative_intent_reason(llm_reason)

    # LLM 主导模式：除少量硬兜底外，最终判断以 LLM 为主，减少规则分支复杂度。
    if INTENT_LLM_PRIMARY_MODE:
        hard_rule_force = "short_reply_intent_signal" in set(rule_signals)
        hard_rule_block = "non_business_meme_signal" in set(rule_signals)

        final_score = max(0, min(100, int(llm_score)))
        final_level = str(llm_level or "").strip().lower()
        if final_level not in {"high", "medium", "low", "noise"}:
            final_level = _score_to_intent_level(final_score)
        final_force_notify = bool(llm_force_notify)
        final_is_intent = bool(
            llm_is_intent_user
            or final_force_notify
            or (final_score >= 60 and _intent_level_rank(final_level) >= _intent_level_rank("medium"))
        )
        final_block = bool(hard_rule_block)

        # LLM 给出负向结论时，直接压低并禁播，避免“理由是噪声但分数偏高”。
        if llm_reason_negative or final_level in {"low", "noise"}:
            cap = 30 if final_level == "noise" else 45
            final_score = min(final_score, cap)
            final_level = _score_to_intent_level(final_score)
            final_is_intent = False
            final_force_notify = False
            if _intent_level_rank(final_level) <= _intent_level_rank("low"):
                final_block = True

        # 仅保留“短回复强意向”这类硬兜底，确保 1/扣1 等不会漏播。
        if hard_rule_force:
            final_score = max(final_score, 62)
            final_level = _max_intent_level(final_level, "medium")
            final_is_intent = True
            final_force_notify = True
            final_block = False

        merged_signals = []
        for sig in (rule_signals + llm_signals):
            sig_text = str(sig).strip()
            if sig_text and sig_text not in merged_signals:
                merged_signals.append(sig_text)
        if llm_reason_negative and "llm_negative_reason" not in merged_signals:
            merged_signals.append("llm_negative_reason")

        result.update({
            "intent_score": int(final_score),
            "intent_level": str(final_level),
            "is_intent_user": bool(final_is_intent),
            "force_notify": bool(final_force_notify),
            "block_intent": bool(final_block),
            "signals": merged_signals[:12],
            "reason": llm_reason or "llm_primary",
            "llm_used": True,
            "llm_score": llm_score,
            "llm_level": llm_level,
            "llm_reason": llm_reason,
        })
        log_to_ui(
            "debug",
            f"🤖 [Intent] llm_primary score={result['intent_score']} level={result['intent_level']} "
            f"intent={result['is_intent_user']} force={result['force_notify']} block={result.get('block_intent', False)} "
            f"rule={rule_score} llm={llm_score}/{llm_level} reason={result['reason'] or '-'}"
        )
        return result

    llm_positive = bool(
        (not llm_reason_negative)
        and (
            llm_force_notify
            or (llm_is_intent_user and llm_score >= 55)
            or _intent_level_rank(llm_level) >= _intent_level_rank("medium")
            or bool(llm_signals)
        )
    )
    llm_weight = 0.65 if llm_positive else 0.20
    llm_score_for_blend = llm_score if llm_positive else min(llm_score, 45)

    blended_score = int(round(max(rule_score, (rule_score * (1.0 - llm_weight) + llm_score_for_blend * llm_weight))))
    if (not llm_positive) and _intent_level_rank(llm_level) <= _intent_level_rank("low") and rule_score < 55:
        blended_score = min(blended_score, 49)
    blended_score = max(0, min(100, blended_score))
    score_level = _score_to_intent_level(blended_score)
    llm_intent_hint = bool(
        (not llm_reason_negative)
        and
        llm_is_intent_user
        and llm_score >= 55
        and (
            _intent_level_rank(llm_level) >= _intent_level_rank("medium")
            or llm_force_notify
            or bool(llm_signals)
        )
    )
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
        "intent_score": blended_score,
        "intent_level": blended_level,
        "is_intent_user": bool(blended_score >= 55 or llm_intent_hint or blended_force_notify),
        "force_notify": bool(blended_force_notify),
        "signals": merged_signals[:12],
        "reason": llm_reason or "rule_llm_blended",
        "llm_used": True,
        "llm_score": llm_score,
        "llm_level": llm_level,
        "llm_reason": llm_reason,
    })

    # 规则层已判定为非目标场景时，强制压制最终结果，防止 LLM 误抬高意向。
    if rule_block_intent:
        blocked_score = min(int(result.get("intent_score", 0) or 0), 18)
        blocked_level = _score_to_intent_level(blocked_score)
        blocked_signals = list(result.get("signals", []))
        if "rule_block_intent" not in blocked_signals:
            blocked_signals.append("rule_block_intent")
        result.update({
            "intent_score": blocked_score,
            "intent_level": blocked_level,
            "is_intent_user": False,
            "force_notify": False,
            "block_intent": True,
            "signals": blocked_signals[:12],
        })

    # LLM 负向理由兜底：避免出现“理由是噪声，但综合分中高”的矛盾结果。
    if (not rule_force_notify) and llm_reason_negative and _intent_level_rank(llm_level) <= _intent_level_rank("low"):
        blocked_score = min(int(result.get("intent_score", 0) or 0), 30)
        blocked_signals = list(result.get("signals", []))
        if "llm_negative_reason" not in blocked_signals:
            blocked_signals.append("llm_negative_reason")
        result.update({
            "intent_score": blocked_score,
            "intent_level": _score_to_intent_level(blocked_score),
            "is_intent_user": False,
            "force_notify": False,
            "block_intent": True,
            "signals": blocked_signals[:12],
        })

    log_to_ui(
        "debug",
        f"🤖 [Intent] llm_done score={result['intent_score']} level={result['intent_level']} "
        f"intent={result['is_intent_user']} force={result['force_notify']} block={result.get('block_intent', False)} "
        f"rule={rule_score} llm={llm_score}/{llm_level} llm_intent={llm_is_intent_user} "
        f"hint={llm_intent_hint} reason={result['reason'] or '-'}"
    )
    return result


def _should_notify_voice_by_intent(analysis):
    """语音播报门槛：低意向/噪声不播报，强意向或中高分才播报。"""
    if not isinstance(analysis, dict):
        return False

    score = 0
    try:
        score = int(float(analysis.get("intent_score", 0)))
    except Exception:
        score = 0
    score = max(0, min(100, score))

    level = str(analysis.get("intent_level", "") or "").strip().lower()
    is_intent_user = bool(analysis.get("is_intent_user", False))
    force_notify = bool(analysis.get("force_notify", False))
    block_intent = bool(analysis.get("block_intent", False))

    if block_intent:
        return False
    if force_notify:
        return True
    if level in {"low", "noise"}:
        return False

    # 保守策略：中高意向且分数不低时才播报，避免误报/噪音。
    return bool(is_intent_user and score >= 55)


def _should_skip_by_llm_filter(content):
    if not _llm_filter_is_ready():
        return False, ""

    text = _normalize_content_for_filter(content)
    if not text:
        return False, ""

    sig_raw = normalize_content_for_dedupe(text)
    if not sig_raw:
        return False, ""
    sig = hashlib.md5(sig_raw.encode("utf-8")).hexdigest()
    now_ts = time.time()

    with llm_filter_cache_lock:
        cached = llm_filter_cache.get(sig)
        if cached and (now_ts - float(cached.get("ts", 0))) <= LLM_FILTER_CACHE_TTL_SEC:
            return bool(cached.get("skip", False)), str(cached.get("reason", "") or "")

    try:
        skip, reason = _call_openai_compatible_filter_api(text)
    except urllib.error.URLError as e:
        log_to_ui("debug", f"🤖 [LLMFilter] 接口不可达，已回退规则过滤: {e}")
        skip, reason = False, ""
    except Exception as e:
        log_to_ui("debug", f"🤖 [LLMFilter] 调用异常，已回退规则过滤: {e}")
        skip, reason = False, ""

    with llm_filter_cache_lock:
        llm_filter_cache[sig] = {"ts": now_ts, "skip": bool(skip), "reason": str(reason or "")}
        if len(llm_filter_cache) > LLM_FILTER_CACHE_MAX_ENTRIES:
            _prune_llm_filter_cache(now_ts)

    return bool(skip), str(reason or "")


def normalize_content_for_dedupe(content):
    """标准化内容用于重复检测。"""
    text = re.sub(r'\s+', ' ', content or '').strip().lower()
    text = re.sub(r'https?://\S+', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'www\.\S+', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def make_content_signature(handle, content):
    """构建同用户同内容签名。"""
    handle_norm = normalize_handle(handle)
    content_norm = normalize_content_for_dedupe(content)
    if not handle_norm or not content_norm:
        return ""
    raw = f"{handle_norm}|{content_norm}"
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def prune_content_dedupe(now_ts=None):
    """清理过期和超量的内容去重签名。"""
    global content_dedupe
    if now_ts is None:
        now_ts = time.time()

    expire_before = now_ts - CONTENT_DEDUPE_TTL_SEC
    expired_keys = [k for k, ts in content_dedupe.items() if ts < expire_before]
    for k in expired_keys:
        content_dedupe.pop(k, None)

    if len(content_dedupe) > CONTENT_DEDUPE_MAX_ENTRIES:
        # 按时间戳升序删除最旧项
        overflow = len(content_dedupe) - CONTENT_DEDUPE_MAX_ENTRIES
        old_keys = sorted(content_dedupe.items(), key=lambda x: x[1])[:overflow]
        for k, _ in old_keys:
            content_dedupe.pop(k, None)


def should_skip_duplicate_content(handle, content, now_ts=None):
    """同用户同内容去重：命中返回True，未命中则登记并返回False。"""
    if now_ts is None:
        now_ts = time.time()
    if len(content_dedupe) > CONTENT_DEDUPE_MAX_ENTRIES:
        prune_content_dedupe(now_ts)
    signature = make_content_signature(handle, content)
    if not signature:
        return False

    last_seen = content_dedupe.get(signature)
    if last_seen and (now_ts - last_seen) <= CONTENT_DEDUPE_TTL_SEC:
        return True

    content_dedupe[signature] = now_ts
    return False

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
    """
    解析服务端口：
    - 设置了 XMONITOR_PORT: 优先使用该端口；不可用则回退随机端口
    - 未设置: 默认使用随机可用端口，避免冲突
    """
    env_port = str(os.environ.get("XMONITOR_PORT", "")).strip()
    if env_port:
        try:
            preferred = int(env_port)
            if not (1 <= preferred <= 65535):
                raise ValueError("out_of_range")
            if is_port_available(preferred):
                return preferred, "env"
            logging.warning(f"配置端口不可用，自动回退随机端口: {preferred}")
        except Exception:
            logging.warning(f"无效的 XMONITOR_PORT={env_port}，自动回退随机端口")

    return get_free_port(), "random"

# --- 爬虫核心 ---
def init_browser_options(port, user_data_path, force_headless=None, safe_mode=False):
    co = ChromiumOptions()
    bp = get_browser_path()
    if bp: co.set_paths(browser_path=bp)

    proxy_server = get_browser_proxy()
    if proxy_server:
        co.set_argument(f'--proxy-server={proxy_server}')
        # 保留本机回环直连，避免影响本地服务访问
        co.set_argument('--proxy-bypass-list=localhost;127.0.0.1')
        log_to_ui("info", f"🌐 浏览器代理已启用: {proxy_server}")
    else:
        log_to_ui("warn", "⚠️ 未检测到代理配置，当前网络环境可能无法访问 x.com")

    # 无头模式 - 不显示浏览器窗口，后台运行
    effective_headless = headless_mode if force_headless is None else bool(force_headless)
    co.headless(effective_headless)  # 根据配置决定有头/无头模式
    if effective_headless:
        # 新版 Chromium 在容器/无界面环境下更稳定
        co.set_argument('--headless=new')

    # 安全参数模式：仅保留启动连接所需关键参数，降低兼容性问题
    if safe_mode:
        co.set_argument('--window-size=1400,900')
        co.set_argument('--mute-audio')
        co.set_argument('--disable-notifications')
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-dev-shm-usage')
        co.set_argument('--disable-setuid-sandbox')
        if effective_headless:
            co.set_argument('--disable-gpu')
        co.set_local_port(port)
        co.set_user_data_path(user_data_path)
        return co

    # --- 1. 基础优化 & 资源拦截 ---
    # 页面加载策略：eager (DOM加载完即算加载完成，不等待图片/样式/子框架)
    co.set_argument('--page-load-strategy=eager')
    # 统一桌面视口，避免无头模式落入小屏布局导致菜单元素缺失
    co.set_argument('--window-size=1400,900')

    # 禁用图片 (多重手段)
    co.set_argument('--blink-settings=imagesEnabled=false')
    co.set_argument('--disable-images')
    co.set_pref('profile.managed_default_content_settings.images', 2)

    # 禁用视频/音频/摄像头/通知/弹窗
    co.set_argument('--mute-audio')
    co.set_argument('--disable-notifications')
    co.set_pref('profile.managed_default_content_settings.notifications', 2)
    co.set_pref('profile.managed_default_content_settings.media_stream', 2)
    co.set_pref('profile.managed_default_content_settings.popups', 2)

    # 禁用自动播放
    co.set_argument('--autoplay-policy=user-gesture-required')
    co.set_argument('--disable-features=PreloadMediaEngagementData,MediaEngagementBypassAutoplayPolicies')

    # --- 2. 通用稳定参数 ---
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')  # 关键：Docker容器必需，使用/tmp替代/dev/shm
    co.set_argument('--disable-extensions') # 禁用扩展
    co.set_argument('--disable-plugins') # 禁用插件
    co.set_argument('--disable-infobars')
    co.set_argument('--disable-sync') # 禁用同步
    co.set_argument('--disable-translate') # 禁用翻译
    co.set_argument('--disable-default-apps')
    co.set_argument('--disable-setuid-sandbox')

    # --- 3. 按模式区分参数 ---
    if effective_headless:
        # 无头模式可激进优化
        co.set_argument('--disable-gpu')
        co.set_argument('--disable-software-rasterizer')
        co.set_argument('--disable-background-timer-throttling')
        co.set_argument('--disable-backgrounding-occluded-windows')
        co.set_argument('--disable-renderer-backgrounding')
    else:
        # 有头调试模式：避免影响窗口显示的参数
        co.set_argument('--start-maximized')
        co.set_argument('--window-size=1400,900')

    # 禁用崩溃报告等无关功能
    co.set_argument('--disable-breakpad')
    co.set_argument('--disable-component-update')
    co.set_argument('--disable-domain-reliability')

    co.set_local_port(port)
    co.set_user_data_path(user_data_path)
    return co


def normalize_handle(handle):
    """标准化用户名为不带@的小写形式。"""
    if not handle:
        return ""
    return handle.strip().lstrip('@').lower()


def _extract_status_id_candidates_from_text(text):
    """从任意文本中提取候选 status_id（只保留长数字，避免误匹配短数字）。"""
    raw = str(text or "")
    if not raw:
        return []
    candidates = []

    def _push_digit_candidate(d):
        sid = _normalize_status_id_digits(d)
        if sid:
            candidates.append(sid)

    patterns = [
        r'/status/(\d{8,80})',
        r'conversation_id=(\d{8,80})',
        r'(?<!\d)(\d{15,80})(?!\d)',
    ]
    for p in patterns:
        for m in re.findall(p, raw):
            _push_digit_candidate(m)
    return candidates


def _normalize_status_id_digits(digits):
    """把脏数字串规整为可用 status_id。"""
    d = re.sub(r'\D+', '', str(digits or ''))
    if len(d) < 15:
        return ""
    # 常见拼接: 两段相同 ID 直接拼在一起
    if len(d) % 2 == 0:
        half = len(d) // 2
        if half >= 15 and d[:half] == d[half:]:
            d = d[:half]
    # X status_id 常见为 18-20 位；太长通常是拼接，截取前 19 位更稳
    if len(d) > 20:
        d = d[:19]
    return d if len(d) >= 15 else ""


def _pick_best_status_id(*parts):
    """多来源挑选最可信 status_id：优先更长，再取最后出现。"""
    all_ids = []
    for part in parts:
        all_ids.extend(_extract_status_id_candidates_from_text(part))
    if not all_ids:
        return ""
    # 优先最长，再取末尾（通常后出现的是更完整链接）
    max_len = max(len(x) for x in all_ids)
    long_ids = [x for x in all_ids if len(x) == max_len]
    return long_ids[-1] if long_ids else all_ids[-1]


def _normalize_dm_share_link(raw_link, status_id="", status_handle="", fallback_url=""):
    """把要私信的链接规范化为稳定的 x.com status 链接（禁止拼接多来源字符串）。"""
    raw_link = str(raw_link or "").strip()
    fallback_url = str(fallback_url or "").strip()
    handle_norm = normalize_handle(status_handle)

    # 1) 先用原始链接（复制链接结果）
    if raw_link:
        sid_raw = _pick_best_status_id(raw_link)
        if sid_raw:
            m_raw = re.search(r'(?:https?://)?(?:www\.)?x\.com/([A-Za-z0-9_]+)/status/\d+', raw_link, flags=re.IGNORECASE)
            if m_raw:
                return f"https://x.com/{m_raw.group(1)}/status/{sid_raw}"
            m_raw_path = re.search(r'^/([A-Za-z0-9_]+)/status/\d+', raw_link)
            if m_raw_path:
                return f"https://x.com/{m_raw_path.group(1)}/status/{sid_raw}"
            if handle_norm:
                return f"https://x.com/{handle_norm}/status/{sid_raw}"
            return f"https://x.com/i/status/{sid_raw}"
        m_http = re.search(r'https?://[^\s<>"\']+', raw_link)
        if m_http:
            return m_http.group(0).strip()

    # 2) 再用 fallback（不与 raw 拼接）
    if fallback_url:
        sid_fb = _pick_best_status_id(fallback_url)
        if sid_fb:
            m_fb = re.search(r'(?:https?://)?(?:www\.)?x\.com/([A-Za-z0-9_]+)/status/\d+', fallback_url, flags=re.IGNORECASE)
            if m_fb:
                return f"https://x.com/{m_fb.group(1)}/status/{sid_fb}"
            if handle_norm:
                return f"https://x.com/{handle_norm}/status/{sid_fb}"
            return f"https://x.com/i/status/{sid_fb}"
        m_http_fb = re.search(r'https?://[^\s<>"\']+', fallback_url)
        if m_http_fb:
            return m_http_fb.group(0).strip()

    # 3) 最后才用明确 status_id
    sid = _pick_best_status_id(status_id)
    if sid and handle_norm:
        return f"https://x.com/{handle_norm}/status/{sid}"
    if sid:
        return f"https://x.com/i/status/{sid}"
    return ""


def _normalize_text_for_compare(text):
    s = str(text or "")
    s = s.replace("\u200b", "").replace("\ufeff", "")
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _sanitize_dm_message_text(text):
    """清洗私信文本：去脏字符、去重复段、规范空白。"""
    s = str(text or "")
    if not s:
        return ""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "")
    lines = [re.sub(r'[ \t]+', ' ', ln).strip() for ln in s.split("\n")]
    # 去掉连续重复行
    clean_lines = []
    for ln in lines:
        if not ln and (not clean_lines or clean_lines[-1] == ""):
            continue
        if clean_lines and ln and ln == clean_lines[-1]:
            continue
        clean_lines.append(ln)
    while clean_lines and clean_lines[0] == "":
        clean_lines.pop(0)
    while clean_lines and clean_lines[-1] == "":
        clean_lines.pop()
    s = "\n".join(clean_lines).strip()

    # 处理“整段重复两次”情况
    compact = _normalize_text_for_compare(s)
    if len(compact) >= 24 and len(compact) % 2 == 0:
        half = len(compact) // 2
        if compact[:half] == compact[half:]:
            s = compact[:half]
    return s


def _is_link_only_message(text):
    """判断是否为单链接消息（X 会自动转换预览，输入框可能暂时清空）。"""
    s = _normalize_text_for_compare(text).strip().lower()
    if not s:
        return False
    s = s.replace("https://", "").replace("http://", "")
    # 单链接或 link + 少量标点/空格
    return bool(re.fullmatch(r'(x\.com/[^\s]+|www\.x\.com/[^\s]+|[^\s]+/status/\d+)', s))


def get_effective_delegated_account():
    """返回当前生效的委派账户（未启用时返回空字符串）。"""
    if not delegated_enabled:
        return ""
    return str(delegated_account or "").strip()


def get_current_account_handle(page):
    """尝试从侧边栏读取当前账号 handle，失败返回空字符串。"""
    selectors = [
        'css:[data-testid="SideNav_AccountSwitcher_Button"]',
        'css:button[data-testid="SideNav_AccountSwitcher_Button"]',
        'css:div[data-testid="SideNav_AccountSwitcher_Button"]',
    ]

    for selector in selectors:
        try:
            btn = page.ele(selector, timeout=0.8)
            if not btn:
                continue
            text = (btn.text or '').strip()
            match = re.search(r'@([A-Za-z0-9_]{1,30})', text)
            if match:
                return match.group(1).lower()
        except Exception:
            pass

    try:
        profile_link = page.ele('css:a[data-testid="AppTabBar_Profile_Link"]', timeout=0.8)
        href = (profile_link.attr('href') or '').strip() if profile_link else ''
        match = re.search(r'/([A-Za-z0-9_]{1,30})/?$', href)
        if match:
            handle = match.group(1).lower()
            if handle not in {'home', 'notifications', 'explore', 'messages', 'compose', 'i'}:
                return handle
    except Exception:
        pass

    return ""


def ensure_delegated_account_session(page, target_account):
    """
    确保当前会话已在目标委派账户：
    - 已在目标账户：仅刷新，不重复切换
    - 当前会话已切换过：先刷新校验，仍命中则直接复用
    - 否则执行一次切换
    """
    global delegated_account_active, delegated_switch_ok

    target_clean = normalize_handle(target_account)
    if not target_clean:
        log_to_ui("error", "❌ 未指定委派账户用户名")
        return False

    current_handle = get_current_account_handle(page)
    if current_handle and current_handle == target_clean:
        delegated_account_active = target_clean
        delegated_switch_ok = True
        log_to_ui("success", f"✅ 当前已是委派账户 @{target_clean}，仅刷新页面复用会话")
        try:
            page.refresh()
            time.sleep(1.2)
        except Exception:
            pass
        return True

    if delegated_switch_ok and delegated_account_active == target_clean:
        log_to_ui("info", f"ℹ️ 会话内已切换过 @{target_clean}，先刷新校验，无需重复登录")
        try:
            page.refresh()
            time.sleep(1.2)
        except Exception:
            pass
        current_handle = get_current_account_handle(page)
        if current_handle and current_handle == target_clean:
            log_to_ui("success", "✅ 刷新后确认仍为目标委派账户，跳过重复切换")
            return True
        log_to_ui("warn", "⚠️ 刷新后未检测到目标委派账户，将执行一次重新切换")

    switch_success = switch_to_delegated_account(page, target_account)
    if switch_success:
        delegated_account_active = target_clean
        delegated_switch_ok = True
        try:
            page.refresh()
            time.sleep(1.2)
            log_to_ui("info", "🔄 委派账户切换完成，已刷新页面")
        except Exception:
            pass
        return True

    delegated_switch_ok = False
    return False

def scan_page_content(page, url, blocked_list):
    """
    优化版本的推文评论抓取
    - 增量处理articles，避免重复处理
    - 改进滚动和加载检测
    - 简化并稳定整体流程
    """
    results = []
    seen_in_page = set()
    processed_article_hashes = set()  # 记录已处理的article

    try:
        tweet_id_match = re.search(r'status/(\d+)', url)
        if not tweet_id_match:
            return [], "链接无效"

        main_tweet_id = tweet_id_match.group(1)
        log_to_ui("info", f"🎯 开始扫描推文: {main_tweet_id}")

        # 详细日志：准备访问页面
        log_to_ui("debug", f"🐛 [DEBUG] 准备执行 page.get(\"{url}\")")

        # 访问页面
        page.get(url)
        log_to_ui("debug", f"🐛 [DEBUG] page.get() 返回，当前URL: {page.url}")

        log_to_ui("info", f"⏳ 等待页面加载...")

        # 详细日志：等待元素加载
        try:
            page.wait.ele_displayed('tag:article', timeout=15)
            log_to_ui("debug", f"🐛 [DEBUG] tag:article 元素已显示")
        except Exception as wait_err:
            log_to_ui("error", f"❌ 等待页面加载超时或失败: {wait_err}")
            log_to_ui("debug", f"🐛 [DEBUG] 当前页面HTML前500字符: {page.html[:500]}")
            raise wait_err

        log_to_ui("success", f"✅ 页面已加载")
        time.sleep(2)

        # 配置参数
        max_scrolls = 50
        max_consecutive_empty = 8
        scroll_step = 800

        scroll_count = 0
        consecutive_empty = 0
        total_captured = 0
        total_processed = 0
        debug_skipped = {
            "no_user": 0,
            "no_handle": 0,
            "no_content": 0,
            "blacklist": 0,
            "duplicate": 0,
            "has_reply": 0,
            "emoji_only": 0,
            "blocked_mention": 0,
        }

        initial_articles = page.eles('tag:article')
        log_to_ui("info", f"📊 初始发现 {len(initial_articles)} 个article")

        while scroll_count < max_scrolls:
            scroll_count += 1

            # 检查URL
            if url not in page.url:
                log_to_ui("error", f"❌ 页面跳转，返回原页面...")
                page.get(url)
                time.sleep(2)

            # 获取当前所有articles
            try:
                articles = page.eles('tag:article', timeout=1)
            except Exception as e:
                log_to_ui("debug", f"获取articles失败: {e}")
                articles = []

            articles = reorder_articles_for_scan(articles)

            # 处理新的articles
            new_count = 0
            for article in articles:
                try:
                    if random.random() < 0.18:
                        time.sleep(random.uniform(0.02, 0.12))
                    article_html = article.html
                    article_hash = hash(article_html[:300])

                    # 跳过已处理过的article
                    if article_hash in processed_article_hashes:
                        continue

                    processed_article_hashes.add(article_hash)
                    new_count += 1
                    total_processed += 1

                    # 跳过原推文
                    if f'/status/{main_tweet_id}' in article_html and '<time' in article_html:
                        continue

                    # 提取handle
                    user_ele = article.ele('css:[data-testid="User-Name"]', timeout=0.01)
                    if not user_ele:
                        debug_skipped["no_user"] += 1
                        continue

                    handle_match = re.search(r'(@[\w_]+)', user_ele.text)
                    if not handle_match:
                        debug_skipped["no_handle"] += 1
                        continue
                    handle = handle_match.group(1)

                    # 过滤保护名单
                    if handle in blocked_list:
                        debug_skipped["blacklist"] += 1
                        continue

                    # 提取内容
                    text_ele = article.ele('css:[data-testid="tweetText"]', timeout=0.01)
                    content = text_ele.text.replace('\n', ' ').strip() if text_ele else ""

                    # 详细日志：打印提取到的原始内容，帮助调试
                    log_to_ui("debug", f"🔍 [DEBUG] Handle: {handle}, tweetText: '{content}', Raw: '{article.text[:50].replace(chr(10), ' ')}...'")

                    if not content:
                        debug_skipped["no_content"] += 1
                        continue
                    should_skip_policy, skip_reason = should_skip_content_by_policy(content)
                    if should_skip_policy:
                        if skip_reason == "emoji_only":
                            debug_skipped["emoji_only"] += 1
                        elif skip_reason == "blocked_mention":
                            debug_skipped["blocked_mention"] += 1
                        continue

                    # 去重
                    unique_key = f"{handle}_{content[:50]}"
                    if unique_key in seen_in_page or unique_key in history_ids:
                        debug_skipped["duplicate"] += 1
                        continue
                    seen_in_page.add(unique_key)

                    # 检查是否有回复
                    reply_btn = article.ele('css:[data-testid="reply"]', timeout=0.01)
                    has_reply = False
                    if reply_btn:
                        aria_label = (reply_btn.attr("aria-label") or "").lower()
                        reply_text = reply_btn.text.strip()
                        if re.search(r'(\d+)', aria_label):
                            match_num = re.search(r'(\d+)', aria_label)
                            if match_num and int(match_num.group(1)) > 0:
                                has_reply = True
                        elif reply_text.isdigit() and int(reply_text) > 0:
                            has_reply = True
                        elif 'k' in reply_text.lower() or 'm' in reply_text.lower():
                            has_reply = True

                    if has_reply:
                        debug_skipped["has_reply"] += 1
                        continue

                    # 捕获成功
                    total_captured += 1
                    log_to_ui("success", f"✅ 捕获 [{total_captured}]: {handle} 内容: {content[:30]}...")
                    results.append({
                        "handle": handle,
                        "content": content,
                        "key": unique_key,
                        "source": url,
                        "time": datetime.datetime.now().strftime("%H:%M:%S")
                    })

                except Exception as article_err:
                    log_to_ui("debug", f"处理article异常: {article_err}")
                    continue

            # 判断是否有新内容
            if new_count == 0:
                consecutive_empty += 1
                log_to_ui("info", f"⏳ 无新内容 ({consecutive_empty}/{max_consecutive_empty})")
                if consecutive_empty >= max_consecutive_empty:
                    log_to_ui("info", "🏁 扫描结束")
                    break
            else:
                consecutive_empty = 0
                log_to_ui("info", f"📝 第{scroll_count}次: {len(articles)} 个articles，新增 {new_count} 个")

            # 检查并点击"显示可能的垃圾信息"按钮
            try:
                # 查找所有可能的按钮和可点击元素
                all_elements = []
                try:
                    all_elements.extend(page.eles('tag:button', timeout=0.3))
                except:
                    pass
                try:
                    all_elements.extend(page.eles('tag:span', timeout=0.3))
                except:
                    pass
                try:
                    all_elements.extend(page.eles('tag:div[role="button"]', timeout=0.3))
                except:
                    pass

                for element in all_elements:
                    try:
                        element_text = (element.text or "").strip()

                        # 检测关键词（中英文）
                        spam_keywords = [
                            '显示可能的垃圾信息',
                            '显示更多回复',
                            '显示其他回复',
                            'Show additional replies',
                            'Show more replies',
                            'Show hidden replies'
                        ]

                        # 如果文本包含关键词，点击它
                        if any(keyword in element_text for keyword in spam_keywords):
                            if element.states.is_displayed:
                                log_to_ui("info", f"🔓 发现隐藏回复按钮: {element_text[:50]}")
                                page.run_js('arguments[0].click()', element)
                                time.sleep(2)  # 等待内容加载
                                log_to_ui("success", f"✅ 已展开隐藏的回复，继续扫描...")
                                # 展开后不break，继续检查是否还有其他按钮
                    except:
                        continue
            except:
                pass

            # 滚动
            try:
                prev_top = page.run_js('return window.scrollY || document.documentElement.scrollTop')
                page.run_js(f'window.scrollBy(0, {scroll_step}); void(0);')
                time.sleep(random.uniform(0.7, 1.0))
                new_top = page.run_js('return window.scrollY || document.documentElement.scrollTop')

                if new_top > prev_top:
                    log_to_ui("info", f"📜 滚动 {new_top - prev_top}px")
                else:
                    consecutive_empty += 1
                    log_to_ui("info", f"⏳ 无法滚动")
                    if consecutive_empty >= max_consecutive_empty:
                        break
            except Exception as scroll_err:
                log_to_ui("debug", f"滚动异常: {scroll_err}")
                consecutive_empty += 1

            # 进度
            if scroll_count % 10 == 0:
                log_to_ui("info", f"📊 进度: {scroll_count}/{max_scrolls}，捕获 {total_captured} 条")

        # 统计
        log_to_ui("info", f"📊 统计: 处理 {total_processed} 个articles")
        log_to_ui("info", f"   跳过: 无user({debug_skipped['no_user']}), 无handle({debug_skipped['no_handle']}), 无内容({debug_skipped['no_content']})")
        log_to_ui("info", f"   跳过: 保护名单({debug_skipped['blacklist']}), 重复({debug_skipped['duplicate']}), 有回复({debug_skipped['has_reply']})")
        log_to_ui("info", f"   跳过: 纯表情({debug_skipped['emoji_only']}), 指定@过滤({debug_skipped['blocked_mention']})")
        log_to_ui("success", f"✨ 扫描完成: 捕获 {len(results)} 条评论")

    except Exception as e:
        log_to_ui("error", f"扫描异常: {str(e)}")
        return [], str(e)

    return results, None

def switch_to_delegated_account(page, target_account):
    """
    切换到委派账户
    步骤：
    1. 点击左下角账户菜单按钮
    2. 等待菜单出现
    3. 找到匹配 target_account 的账户
    4. 点击该div
    5. 处理弹窗确认
    """
    try:
        log_to_ui("info", "=" * 60)
        log_to_ui("info", f"🔄 开始切换到委派账户: {target_account}")
        log_to_ui("info", "=" * 60)

        if not target_account:
            log_to_ui("error", "❌ 未指定委派账户用户名")
            return False

        target_clean = normalize_handle(target_account)
        current_handle = get_current_account_handle(page)
        if current_handle and current_handle == target_clean:
            log_to_ui("success", f"✅ 当前已是目标委派账户 @{target_clean}，跳过切换")
            return True

        # 步骤1: 点击左下角账户菜单
        log_to_ui("info", "🔍 步骤1: 点击左下角账户菜单...")
        try:
            # 无头模式下该按钮有时在视口外，先滚到底部
            try:
                page.run_js('window.scrollTo(0, document.body.scrollHeight);')
                time.sleep(0.4)
            except Exception:
                pass

            menu_btn = None
            menu_selectors = [
                'css:[data-testid="SideNav_AccountSwitcher_Button"]',
                'css:button[data-testid="SideNav_AccountSwitcher_Button"]',
                'css:div[data-testid="SideNav_AccountSwitcher_Button"]',
            ]

            # 多轮重试，适配无头渲染延迟
            for _ in range(3):
                for selector in menu_selectors:
                    try:
                        candidate = page.ele(selector, timeout=1.5)
                        if candidate and candidate.states.is_displayed:
                            menu_btn = candidate
                            break
                    except Exception:
                        pass
                if menu_btn:
                    break
                time.sleep(0.8)

            if not menu_btn:
                log_to_ui("error", "❌ 未找到账户菜单按钮")
                return False

            log_to_ui("success", "✅ 找到菜单按钮，点击中...")
            page.run_js('arguments[0].click()', menu_btn)
            log_to_ui("info", "⏳ 等待菜单内容加载...")
            time.sleep(4)  # 保持较长等待，确保菜单完全渲染
            log_to_ui("success", "✅ 菜单已打开，继续扫描...")
        except Exception as e:
            log_to_ui("error", f"❌ 点击菜单失败: {str(e)}")
            return False

        # 步骤2: 在菜单中查找匹配的账户
        log_to_ui("info", f"🔍 步骤2: 查找账户匹配 '{target_account}'...")

        found_delegated = None

        # 直接方法：查找所有 UserCell 按钮
        try:
            user_cells = []
            for _ in range(3):
                try:
                    user_cells = page.eles('css:[data-testid="UserCell"]', timeout=1.5)
                except Exception:
                    user_cells = []
                if user_cells:
                    break
                time.sleep(0.8)
            log_to_ui("info", f"   找到 {len(user_cells)} 个账户选项...")

            for cell in user_cells:
                try:
                    cell_text = (cell.text or '').strip()
                    cell_html = (cell.html or '').strip()
                    # 简单的调试日志
                    # log_to_ui("debug", f"   🔹 检查账户: {cell_text.replace(chr(10), ' ')}")

                    combined_text = f"{cell_text} {cell_html}".lower()
                    handle_match = re.search(r'@([a-zA-Z0-9_]{1,30})', combined_text)
                    cell_handle = handle_match.group(1).lower() if handle_match else ""

                    # 检查是否包含目标handle（优先精确匹配）
                    direct_hit = cell_handle == target_clean
                    fallback_hit = re.search(rf'@?{re.escape(target_clean)}\b', combined_text) is not None
                    if direct_hit or fallback_hit:
                        if cell.states.is_displayed:
                            found_delegated = cell
                            log_to_ui("success", f"   ✅ 找到目标账户: {cell_text.splitlines()[0]}")
                            break
                except:
                    pass

            if not found_delegated:
                log_to_ui("error", f"❌ 未找到匹配 '{target_account}' 的账户")
                # 打印所有找到的选项供调试
                for cell in user_cells:
                    cell_text = (cell.text or '').replace(chr(10), ' ')
                    handle_match = re.search(r'@([a-zA-Z0-9_]{1,30})', cell_text.lower())
                    handle_hint = f"@{handle_match.group(1)}" if handle_match else "无@handle"
                    log_to_ui("info", f"   - 可选: {handle_hint} | {cell_text[:60]}")
                return False

        except Exception as e:
            log_to_ui("error", f"❌ 查找 UserCell 失败: {str(e)}")
            return False

        # 步骤3: 点击委派账户div
        log_to_ui("info", "👆 步骤3: 点击委派账户...")
        try:
            time.sleep(0.5)
            page.run_js('arguments[0].click()', found_delegated)
            log_to_ui("success", "✅ 已点击委派账户")
            log_to_ui("info", "⏳ 等待弹窗出现...")
            time.sleep(3.5)  # 增加到3.5秒，等待弹窗加载
        except Exception as e:
            log_to_ui("error", f"❌ 点击委派账户失败: {str(e)}")
            return False

        # 步骤4: 处理弹窗
        log_to_ui("info", "🔍 步骤4: 处理弹窗...")
        time.sleep(2)  # 再等待2秒，确保弹窗完全加载

        try:
            # 查找弹窗中的确认按钮
            buttons = page.eles('tag:button', timeout=2)
            log_to_ui("info", f"   发现 {len(buttons)} 个按钮，查找确认按钮...")

            for btn in buttons:
                btn_text = (btn.text or '').strip()

                # 查找包含确认关键字的按钮
                confirm_keywords = ['切换', 'switch', '确认', 'confirm', '是', 'yes', '好的']
                if any(kw.lower() in btn_text.lower() for kw in confirm_keywords):
                    if btn.states.is_displayed:
                        log_to_ui("success", f"   ✅ 找到确认按钮: {btn_text}")
                        time.sleep(0.5)
                        page.run_js('arguments[0].click()', btn)
                        time.sleep(2)
                        log_to_ui("success", "✅ 确认按钮已点击")

                        log_to_ui("success", "=" * 60)
                        log_to_ui("success", "✅ 账户切换成功！")
                        log_to_ui("success", "=" * 60)
                        return True
        except Exception as e:
            log_to_ui("warn", f"⚠️ 处理弹窗出错: {str(e)}")
            return False

        log_to_ui("info", "=" * 60)
        log_to_ui("info", "ℹ️ 委派账户点击完成，但未找到确认按钮")
        log_to_ui("info", "=" * 60)
        return True

    except Exception as e:
        log_to_ui("error", "=" * 60)
        log_to_ui("error", f"❌ 切换过程异常: {str(e)}")
        log_to_ui("error", "=" * 60)
        return False

def _parse_notification_age_minutes(article):
    """解析通知年龄（分钟），解析失败返回 None。"""
    try:
        time_ele = article.ele('tag:time', timeout=0)
        if not time_ele:
            return None

        # 优先使用 datetime 属性，精度更高
        dt_attr = (time_ele.attr('datetime') or '').strip()
        if dt_attr:
            dt_text = dt_attr.replace('Z', '+00:00')
            dt = datetime.datetime.fromisoformat(dt_text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            age = (now_utc - dt.astimezone(datetime.timezone.utc)).total_seconds() / 60
            return max(age, 0)

        # 回退：解析相对时间文本
        time_text = (time_ele.text or '').strip().lower()
        if not time_text:
            return None

        num_match = re.search(r'(\d+)', time_text)
        num = int(num_match.group(1)) if num_match else 0

        if any(k in time_text for k in ['刚刚', 'now', '秒', ' sec', ' s']):
            return 0
        if any(k in time_text for k in ['分', ' min', 'm']):
            return num if num > 0 else 0
        if any(k in time_text for k in ['小时', ' hr', 'h']):
            return (num if num > 0 else 1) * 60
        if any(k in time_text for k in ['天', ' day', 'd']):
            return (num if num > 0 else 1) * 1440
    except Exception:
        return None

    return None


def _extract_notification_handle(article, article_text):
    """提取通知发起者 handle。"""
    # 优先从 User-Name 区域提取，避免误取正文中的 @ 提及
    try:
        user_ele = article.ele('css:[data-testid="User-Name"]', timeout=0)
        if user_ele:
            user_text = (user_ele.text or '').strip()
            m = re.search(r'(@[\w_]+)', user_text)
            if m:
                return m.group(1)
    except Exception:
        pass

    # 回退：从通知内链接解析 handle（比全文正则更稳）
    try:
        links = article.eles('tag:a', timeout=0)
        for link in links:
            href = (link.attr('href') or '').strip()
            if not href.startswith('/'):
                continue

            # /username/status/123...
            m_status = re.match(r'^/([A-Za-z0-9_]+)/status/\d+', href)
            if m_status:
                return f"@{m_status.group(1)}"

            # /username
            m_profile = re.match(r'^/([A-Za-z0-9_]+)$', href)
            if m_profile:
                username = m_profile.group(1).lower()
                if username not in {'home', 'notifications', 'explore', 'messages', 'compose', 'i'}:
                    return f"@{m_profile.group(1)}"
    except Exception:
        pass

    # 最后回退：全文匹配第一个 handle
    m = re.search(r'(@[\w_]+)', article_text or "")
    return m.group(1) if m else None


def _normalize_notification_text(text):
    return re.sub(r'\s+', ' ', text or '').strip()


NOTIFICATION_LIKE_REPLY_KEYWORDS = (
    '喜欢了你的回复',
    'liked your reply',
)

NOTIFICATION_INTERACTION_SKIP_KEYWORDS = (
    '点赞了', 'liked', 'liked your', '转发了', 'reposted', 'retweeted',
    '关注了你', 'followed you', '视频来源', '点赞了你的帖子', 'liked your post',
    '转发了你的帖子', 'reposted your', 'retweet了'
)

NOTIFICATION_REPLY_TO_YOU_KEYWORDS = (
    '回复了你',
    '回复了你的帖子',
    '回复了你的贴文',
    '回复了你的推文',
    'replied to you',
    'replied to your post',
    'replied to your tweet',
)

NOTIFICATION_MENTION_YOU_KEYWORDS = (
    '提到了你',
    '在帖子中提到了你',
    'mentioned you',
    'mentioned you in a post',
)


def _classify_notification_type(article_text):
    """识别通知类型，供回复过滤与结构化字段使用。"""
    normalized = _normalize_notification_text(article_text or "")
    low = normalized.lower()
    is_like_reply = any(k in low for k in NOTIFICATION_LIKE_REPLY_KEYWORDS)
    is_reply_to_me = any(k in low for k in NOTIFICATION_REPLY_TO_YOU_KEYWORDS)
    if not is_reply_to_me:
        reply_hint_patterns = (
            r'(^|\s)回复\s*@[\w_]{1,30}',
            r'\breplying to\s+@[\w_]{1,30}',
            r'\bin reply to\s+@[\w_]{1,30}',
        )
        is_reply_to_me = any(re.search(p, normalized, flags=re.IGNORECASE) for p in reply_hint_patterns)
    is_mention_to_me = any(k in low for k in NOTIFICATION_MENTION_YOU_KEYWORDS)
    is_reply_like = is_like_reply or is_reply_to_me or is_mention_to_me
    is_interaction_only = (not is_like_reply) and any(k in low for k in NOTIFICATION_INTERACTION_SKIP_KEYWORDS)

    if is_reply_to_me:
        notification_type = "reply_to_you"
    elif is_mention_to_me:
        notification_type = "mention_you"
    elif is_like_reply:
        notification_type = "liked_your_reply"
    elif is_interaction_only:
        notification_type = "interaction"
    else:
        notification_type = "unknown"

    return {
        "notification_type": notification_type,
        "is_reply_to_me": is_reply_to_me,
        "is_mention_to_me": is_mention_to_me,
        "is_reply_like": is_reply_like,
        "is_interaction_only": is_interaction_only,
        "normalized_text": normalized,
        "low_text": low,
    }


def _is_display_name_like(text, user_name_candidates):
    if text in user_name_candidates:
        return True
    return any(len(name) >= 4 and (text.startswith(name) or name.startswith(text)) for name in user_name_candidates)


def _is_noise_notification_text(text, handle, user_name_candidates):
    if not text:
        return True

    low = text.lower()
    if handle and low == handle.lower():
        return True
    if re.fullmatch(r'@\w+', text):
        return True
    if re.fullmatch(r'\d+[smhd]', low):
        return True
    if text in {'·', '-', '|'}:
        return True
    if _is_display_name_like(text, user_name_candidates):
        return True

    action_keywords = [
        'replied to you', 'mentioned you', 'liked', 'retweeted', 'reposted', 'followed you',
        '回复了你', '提到了你', '点赞了', '转发了', '关注了你'
    ]
    # 纯动作文案直接过滤；更长文本后续还会做评分
    if any(k in low for k in action_keywords) and len(text) <= 40:
        cleaned = re.sub(r'@\w+', ' ', low)
        cleaned = re.sub(r'\b\d+[smhd]\b', ' ', cleaned, flags=re.IGNORECASE)
        for k in action_keywords:
            cleaned = cleaned.replace(k, ' ')
        cleaned = re.sub(r'[\W_]+', ' ', cleaned).strip()
        if len(cleaned) < 2:
            return True

    return False


def _score_notification_candidate(text, source, user_name_candidates):
    low = text.lower()
    source_score = {
        "tweetText": 120,
        "lang": 95,
        "tail": 85,
        "line": 70,
        "cleaned": 60,
    }.get(source, 50)

    score = source_score
    length = len(text)
    if 6 <= length <= 180:
        score += 15
    elif length < 4:
        score -= 20
    elif length > 240:
        score -= 10

    if re.search(r'[\u4e00-\u9fffA-Za-z0-9]', text):
        score += 8
    if _is_display_name_like(text, user_name_candidates):
        score -= 80
    if re.match(r'^\s*@\w+\s*$', text):
        score -= 40
    if any(k in low for k in ['replied to you', 'mentioned you', '回复了你', '提到了你']):
        score -= 25

    return score


def _extract_notification_content(article, article_text, handle):
    """提取通知内容：多来源候选 + 过滤 + 打分，避免把用户名称误当正文。"""
    user_name_candidates = set()
    candidates = []
    tweet_text_candidates = []
    seen = set()

    def add_candidate(source, text):
        normalized = _normalize_notification_text(text)
        if not normalized:
            return
        key = normalized.lower()
        if key in seen:
            return
        seen.add(key)
        candidates.append((source, normalized))
        if source == "tweetText":
            tweet_text_candidates.append(normalized)

    # 1) 收集用户名称区域，供后续过滤
    try:
        user_ele = article.ele('css:[data-testid="User-Name"]', timeout=0)
        if user_ele:
            for seg in re.split(r'[\r\n]+', user_ele.text or ""):
                txt = _normalize_notification_text(seg)
                if not txt:
                    continue
                low = txt.lower()
                if re.fullmatch(r'@\w+', txt):
                    continue
                if re.fullmatch(r'\d+[smhd]', low):
                    continue
                if txt in {'·', '-', '|'}:
                    continue
                user_name_candidates.add(txt)
    except Exception:
        pass

    # 2) 高优先级：tweetText
    try:
        # timeout 过小会在无头模式下漏掉已存在的正文节点
        text_eles = article.eles('css:[data-testid="tweetText"]', timeout=0.25)
        for ele in text_eles:
            add_candidate("tweetText", ele.text or "")
    except Exception:
        pass

    # 3) 语言块候选（常见于通知卡片正文）
    try:
        lang_eles = article.eles('css:div[lang]', timeout=0)
        for ele in lang_eles:
            add_candidate("lang", ele.text or "")
    except Exception:
        pass

    # 4) 逐行回退候选
    try:
        for line in re.split(r'[\r\n]+', article_text or ""):
            add_candidate("line", line)
    except Exception:
        pass

    # 5) 文案尾部提取候选
    one_line = _normalize_notification_text(article_text or "")
    if one_line:
        tail_patterns = [
            r'(?:回复了你|replied to you)[:：]\s*(.+)$',
            r'(?:提到了你|mentioned you)[:：]\s*(.+)$',
        ]
        for pattern in tail_patterns:
            m = re.search(pattern, one_line, flags=re.IGNORECASE)
            if m:
                add_candidate("tail", m.group(1))

        cleaned = one_line
        cleaned = re.sub(r'@\w+', ' ', cleaned)
        cleaned = re.sub(r'(回复了你|提到了你|点赞了|转发了|关注了你)', ' ', cleaned)
        cleaned = re.sub(r'\b(replied to you|mentioned you|liked|retweeted|reposted|followed you)\b', ' ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b\d+[smhd]\b', ' ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip(' -:|')
        add_candidate("cleaned", cleaned)

    # 5.5) 若提取到了 tweetText，优先从 tweetText 中挑选正文，减少误拿整段卡片文案
    if tweet_text_candidates:
        best_tweet = ""
        best_tweet_score = -10**9
        for txt in tweet_text_candidates:
            if _is_noise_notification_text(txt, handle, user_name_candidates):
                continue
            score = _score_notification_candidate(txt, "tweetText", user_name_candidates)
            txt_low = txt.lower()
            txt_len = len(txt)
            # 通知正文一般偏短，适当提高短文本权重（比如“11”、“扣1”、“来了”）
            if txt_len <= 4:
                score += 26
            elif txt_len <= 20:
                score += 14
            elif txt_len <= 80:
                score += 8
            elif txt_len > 180:
                score -= 16
            if re.search(r'https?://|www\.', txt_low):
                score -= 8
            if score > best_tweet_score:
                best_tweet_score = score
                best_tweet = txt
        if best_tweet:
            return best_tweet[:280]

    # 6) 过滤+打分选择最佳正文
    best_text = ""
    best_score = -10**9
    for source, txt in candidates:
        if _is_noise_notification_text(txt, handle, user_name_candidates):
            continue
        score = _score_notification_candidate(txt, source, user_name_candidates)
        if score > best_score:
            best_score = score
            best_text = txt

    if best_text:
        return best_text[:280]
    return ""


def _extract_status_from_href(href):
    """从单个 href 提取 status 用户和 status_id。"""
    raw = str(href or "").strip()
    if not raw:
        return None, None

    # 新版路径：/i/status/123 或 /i/web/status/123
    m = re.search(r'/(?:i/(?:web/)?status|web/status)/(\d{6,25})', raw)
    if m:
        sid = _pick_best_status_id(m.group(1), raw)
        if sid:
            return None, sid

    # 标准路径：/username/status/123...
    user_matches = list(re.finditer(r'/([A-Za-z0-9_]+)/status/(\d{6,25})', raw))
    if user_matches:
        best = None
        best_len = -1
        for m in user_matches:
            uname = str(m.group(1) or "").strip().lower()
            if uname in {"i", "web"}:
                continue
            sid = _pick_best_status_id(m.group(2), raw)
            if sid and len(sid) > best_len:
                best = (m.group(1), sid)
                best_len = len(sid)
        if best:
            return f"@{best[0]}", best[1]

    # 某些跳转链接里会带 conversation_id
    m = re.search(r'conversation_id=(\d{6,25})', raw)
    if m:
        sid = _pick_best_status_id(m.group(1), raw)
        if sid:
            return None, sid

    return None, None


def _extract_notification_status_info(article):
    """提取通知关联的 status 用户和 status_id。"""
    try:
        links = article.eles('tag:a', timeout=0)
        for link in links:
            href = (link.attr('href') or '').strip()
            if not href:
                continue
            status_handle, status_id = _extract_status_from_href(href)
            if status_id:
                return status_handle, status_id
    except Exception:
        pass

    # 回退：某些卡片中 a 标签不可见/不完整时，直接从 article.html 抓取 status 线索
    try:
        raw_html = str(article.html or "")
        if raw_html:
            # 优先 time 锚点：与真实通知时间链接最接近，稳定性更高
            time_href_matches = re.findall(
                r'<a[^>]+href=[\'"]([^\'"]+)[\'"][^>]*>\s*<time\b',
                raw_html,
                flags=re.IGNORECASE | re.DOTALL,
            )
            for href in reversed(time_href_matches):
                status_handle, status_id = _extract_status_from_href(href)
                if status_id:
                    return status_handle, status_id

            href_matches = re.findall(r'href=[\'"]([^\'"]+)[\'"]', raw_html, flags=re.IGNORECASE)
            for href in reversed(href_matches):
                status_handle, status_id = _extract_status_from_href(href)
                if status_id:
                    return status_handle, status_id

            sid = _pick_best_status_id(raw_html)
            if sid:
                return None, sid
    except Exception:
        pass
    return None, None


def _normalize_one_line(text, limit=NOTIFICATION_TRACE_TEXT_LEN):
    """压缩文本为单行，便于诊断日志。"""
    if not text:
        return ""
    compact = re.sub(r'\s+', ' ', str(text)).strip()
    if len(compact) > limit:
        return compact[:limit] + "..."
    return compact


def _collect_notification_hrefs(article, max_links=4):
    """提取通知卡片中的链接样本，帮助定位 status_id 提取失败问题。"""
    hrefs = []
    try:
        links = article.eles('tag:a', timeout=0)
        for link in links:
            href = (link.attr('href') or '').strip()
            if href:
                hrefs.append(href)
            if len(hrefs) >= max_links:
                break
    except Exception:
        pass
    return hrefs


def _collect_notification_tweet_texts(article, max_items=2):
    samples = []
    try:
        text_eles = article.eles('css:[data-testid="tweetText"]', timeout=0)
        for ele in text_eles:
            txt = _normalize_one_line(ele.text or "", 80)
            if not txt:
                continue
            samples.append(txt)
            if len(samples) >= max_items:
                break
    except Exception:
        pass
    return samples


def scan_notifications_page(page, blocked_list, max_recent_minutes=None):
    """
    通知页面扫描（回复优先）：
    - 优先抓取“回复了你/提到了你”类通知
    - 支持 tweetText / div[lang] / 文本回退 多策略提取正文
    - 使用 status_id 去重，减少重复和漏抓
    - 支持仅抓“回复了你”模式（XMONITOR_NOTIFY_REPLY_ONLY）
    """
    results = []
    seen_in_page = set()

    try:
        if max_recent_minutes is None:
            max_recent_minutes = NOTIFICATION_RECENT_WINDOW_MINUTES
        max_scan_articles = NOTIFICATION_MAX_SCAN_ARTICLES

        # 检查是否在通知页面
        if "notifications" not in page.url:
            log_to_ui("info", "📬 正在访问通知页面...")
            page.get("https://x.com/notifications")
            try:
                page.wait.ele_displayed('tag:article', timeout=5)
            except Exception:
                pass
            time.sleep(1)

            # 快速切换到"全部"标签
            try:
                tabs = page.eles('css:[role="tab"]', timeout=0.5)
                for tab in tabs:
                    tab_text = (tab.text or "").strip().lower()
                    if tab_text in ['全部', 'all']:
                        tab.click()
                        time.sleep(0.5)
                        break
            except Exception:
                pass

        # 快速查找所有通知元素
        articles = page.eles('tag:article', timeout=0.8)
        total_articles = len(articles)

        # 只处理最新 N 条
        if len(articles) > max_scan_articles:
            articles = articles[:max_scan_articles]
            log_to_ui(
                "warn",
                f"⚠️ 通知列表过长(total={total_articles})，当前仅扫描前{max_scan_articles}条；可调大 XMONITOR_NOTIFY_MAX_ARTICLES"
            )
        articles = reorder_articles_for_scan(articles)

        new_captured = 0
        skipped_old = 0
        skipped_non_reply = 0
        skipped_no_status = 0
        skipped_no_content = 0
        skipped_blacklist = 0
        skipped_duplicate = 0
        skipped_no_handle = 0
        skipped_interaction = 0
        skipped_empty_text = 0
        policy_flagged_emoji_only = 0
        policy_flagged_blocked_mention = 0
        article_errors = 0
        trace_logs = []
        trace_limit = NOTIFICATION_TRACE_MAX_ARTICLES if NOTIFICATION_VERBOSE_TRACE else 0

        if NOTIFICATION_VERBOSE_TRACE:
            log_to_ui(
                "debug",
                f"🔎 [NotifyTrace] scan_start url={page.url} articles={len(articles)} recent_window={max_recent_minutes}min"
            )

        blocked_norm_set = set()
        for raw_handle in (blocked_list or []):
            norm = normalize_handle(raw_handle)
            if norm:
                blocked_norm_set.add(norm)
        delegated_now = get_effective_delegated_account()
        delegated_norm = normalize_handle(delegated_now)

        for idx, article in enumerate(articles, start=1):
            try:
                # 快速获取文章文本用于初步判断
                article_text = article.text or ""
                if not article_text:
                    skipped_empty_text += 1
                    if idx <= trace_limit:
                        trace_logs.append(f"A{idx:02d} skip=empty_text")
                    continue

                # ===== 0. 通知类型识别 =====
                trace_sample = _normalize_one_line(article_text)
                relation = _classify_notification_type(article_text)
                notification_type = relation["notification_type"]
                is_reply_like = relation["is_reply_like"]
                is_reply_to_me = relation["is_reply_to_me"]
                is_mention_to_me = relation["is_mention_to_me"]
                is_interaction_only = relation["is_interaction_only"]

                if is_interaction_only:
                    skipped_interaction += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f"A{idx:02d} skip=interaction type={notification_type} text={trace_sample}"
                        )
                    continue

                if NOTIFICATION_REPLY_ONLY_MODE and (not is_reply_to_me):
                    skipped_non_reply += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f"A{idx:02d} skip=reply_only_filter type={notification_type} text={trace_sample}"
                        )
                    continue

                # 必须是 status 类型（评论/提及相关），但对明确“回复/提及”做兜底
                status_handle, status_id = _extract_notification_status_info(article)
                if not status_id and not is_reply_like:
                    skipped_non_reply += 1
                    if idx <= trace_limit:
                        hrefs = _collect_notification_hrefs(article)
                        html_status_hints = _extract_status_id_candidates_from_text(article.html or "")
                        status_hint = html_status_hints[-1] if html_status_hints else ""
                        tweet_texts = _collect_notification_tweet_texts(article)
                        trace_logs.append(
                            f"A{idx:02d} skip=non_reply status_id=None is_reply_like={is_reply_like} "
                            f"status_hint={status_hint or '-'} tweetText={tweet_texts or '-'} hrefs={hrefs} text={trace_sample}"
                        )
                    continue
                if not status_id and is_reply_like:
                    skipped_no_status += 1
                    if idx <= trace_limit:
                        hrefs = _collect_notification_hrefs(article)
                        trace_logs.append(
                            f"A{idx:02d} keep=fallback_no_status type={notification_type} "
                            f"is_reply_like={is_reply_like} hrefs={hrefs} text={trace_sample}"
                        )

                # ===== 1. 快速检查时间 =====
                age_minutes = _parse_notification_age_minutes(article)
                if age_minutes is not None and age_minutes > max_recent_minutes:
                    skipped_old += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f"A{idx:02d} skip=old age={age_minutes:.1f}m status_id={status_id} text={trace_sample}"
                        )
                    continue

                # ===== 2. 提取用户名 =====
                handle = status_handle or _extract_notification_handle(article, article_text)
                if not handle:
                    skipped_no_handle += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f"A{idx:02d} skip=no_handle status_id={status_id} age={age_minutes} text={trace_sample}"
                        )
                    continue

                # 过滤保护名单
                handle_norm = handle.strip().lstrip('@').lower()

                # 如果被提取成了自己的账号，不要直接丢弃（这类误判在通知里比较常见）
                should_skip_block = (handle_norm in blocked_norm_set and (not delegated_norm or handle_norm != delegated_norm))
                if should_skip_block:
                    skipped_blacklist += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f"A{idx:02d} skip=blacklist handle={handle} status_id={status_id} text={trace_sample}"
                        )
                    continue

                # ===== 3. 提取回复内容 =====
                content = _extract_notification_content(article, article_text, handle)
                if not content:
                    skipped_no_content += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f"A{idx:02d} skip=no_content handle={handle} status_id={status_id} text={trace_sample}"
                        )
                    continue
                # 通知捕获必须展示完整数据：内容策略仅做“标记”，不拦截入库
                should_skip_policy, skip_reason = should_skip_content_by_policy(
                    content,
                    allow_llm_hard_filter=False,
                )
                if should_skip_policy:
                    if skip_reason == "emoji_only":
                        policy_flagged_emoji_only += 1
                    elif skip_reason == "blocked_mention":
                        policy_flagged_blocked_mention += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f"A{idx:02d} flag=content_policy reason={skip_reason} handle={handle} status_id={status_id} text={trace_sample}"
                        )

                # 明显是互动类且不是回复/提及时过滤
                if is_interaction_only and not is_reply_like:
                    skipped_non_reply += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f"A{idx:02d} skip=interaction_non_reply handle={handle} status_id={status_id} text={trace_sample}"
                        )
                    continue

                # ===== 4. 去重 =====
                if status_id:
                    unique_key = f"notif_status_{status_id}"
                else:
                    # 回退 key：用于兼容 X 的非标准通知链接（缺少 status_id）
                    time_ele = article.ele('tag:time', timeout=0)
                    time_token = ""
                    if time_ele:
                        time_token = ((time_ele.attr('datetime') or time_ele.text or "")).strip()
                    raw_key = f"{handle_norm}|{content}|{time_token}"
                    digest = hashlib.md5(raw_key.encode('utf-8')).hexdigest()[:20]
                    unique_key = f"notif_fallback_{digest}"
                if unique_key in seen_in_page or unique_key in history_ids:
                    skipped_duplicate += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f"A{idx:02d} skip=duplicate handle={handle} status_id={status_id} key={unique_key}"
                        )
                    continue
                seen_in_page.add(unique_key)

                # 成功捕获
                new_captured += 1
                results.append({
                    "handle": handle,
                    "content": content,
                    "key": unique_key,
                    "source": "通知页面",
                    "time": datetime.datetime.now().strftime("%H:%M:%S"),
                    "status_id": status_id or "",
                    "status_handle": (status_handle or "").strip(),
                    "notification_type": notification_type,
                    "is_reply_to_me": bool(is_reply_to_me),
                    "is_mention_to_me": bool(is_mention_to_me),
                    "notification_text": relation["normalized_text"][:600],
                    "notification_age_minutes": (round(float(age_minutes), 2) if age_minutes is not None else None),
                    "status_url": (
                        f"https://x.com/{normalize_handle(status_handle)}/status/{status_id}"
                        if status_id and status_handle else
                        (f"https://x.com/i/status/{status_id}" if status_id else "")
                    )
                })
                if NOTIFICATION_VERBOSE_TRACE:
                    log_to_ui("debug", f"📬 [NotifyCandidate][{notification_type}] {handle} - {content[:20]}...")
                if idx <= trace_limit:
                    trace_logs.append(
                        f"A{idx:02d} pass handle={handle} status_id={status_id} age={age_minutes} content={_normalize_one_line(content)}"
                    )

            except Exception as article_err:
                article_errors += 1
                if idx <= trace_limit:
                    trace_logs.append(f"A{idx:02d} skip=exception err={_normalize_one_line(article_err, 160)}")
                continue

        if skipped_old > 0:
            log_to_ui("debug", f"📋 [Notify] 跳过旧通知: {skipped_old}")
        if skipped_non_reply > 0:
            log_to_ui("debug", f"📋 [Notify] 跳过非回复: {skipped_non_reply}")
        if skipped_interaction > 0:
            log_to_ui("debug", f"📋 [Notify] 跳过互动通知: {skipped_interaction}")
        if skipped_no_status > 0:
            log_to_ui("debug", f"📋 [Notify] 回复/提及但无status_id(已兜底): {skipped_no_status}")
        if skipped_no_content > 0:
            log_to_ui("debug", f"📋 [Notify] 跳过无正文: {skipped_no_content}")
        if skipped_no_handle > 0:
            log_to_ui("debug", f"📋 [Notify] 跳过无用户: {skipped_no_handle}")
        if skipped_blacklist > 0:
            log_to_ui("debug", f"📋 [Notify] 跳过保护名单: {skipped_blacklist}")
        if skipped_duplicate > 0:
            log_to_ui("debug", f"📋 [Notify] 跳过重复: {skipped_duplicate}")
        if skipped_empty_text > 0:
            log_to_ui("debug", f"📋 [Notify] 跳过空文本: {skipped_empty_text}")
        if policy_flagged_emoji_only > 0:
            log_to_ui("debug", f"📋 [Notify] 内容标记(纯表情): {policy_flagged_emoji_only}")
        if policy_flagged_blocked_mention > 0:
            log_to_ui("debug", f"📋 [Notify] 内容标记(指定@): {policy_flagged_blocked_mention}")
        if article_errors > 0:
            log_to_ui("debug", f"📋 [Notify] article异常: {article_errors}")
        if new_captured == 0 and len(articles) > 0 and NOTIFICATION_VERBOSE_TRACE:
            log_to_ui("debug", f"📬 本轮扫描未捕获新通知（articles={len(articles)}）")
        if trace_logs and (NOTIFICATION_VERBOSE_TRACE and (new_captured == 0 or article_errors > 0)):
            for trace in trace_logs:
                log_to_ui("debug", f"🔎 [NotifyTrace] {trace}")

        return results, None

    except Exception as e:
        log_to_ui("error", f"❌ scan_notifications_page异常: {str(e)}")
        log_to_ui("debug", f"🔎 [NotifyTrace] traceback={traceback.format_exc()}")
        return [], str(e)
def scan_task_worker(task, page, blocked_users):
    """独立线程：处理单个任务的扫描"""
    try:
        url = task['url']
        short_url = url.split('/')[-1]
        log_to_ui("info", f"⏳ 开始扫描任务: {short_url}")

        # 详细日志：开始扫描页面内容前
        log_to_ui("debug", f"🐛 [DEBUG] scan_task_worker 调用 scan_page_content: url={url}")

        new_items, err = scan_page_content(page, url, blocked_users)

        # 详细日志：scan_page_content 返回后
        if err:
            log_to_ui("error", f"❌ {short_url} 扫描失败: {err}")
            # 记录更详细的错误信息
            log_to_ui("debug", f"🐛 [DEBUG] 错误详情: {err}")
            return 0

        log_to_ui("debug", f"🐛 [DEBUG] scan_page_content 成功返回，获取到 {len(new_items)} 条新数据")

        # 处理新数据
        count = 0
        skipped_dup_content = 0
        skipped_policy = 0
        for item in new_items:
            with data_lock:
                if item["key"] in history_ids:
                    continue
                should_skip_policy, _ = should_skip_content_by_policy(item.get("content", ""))
                if should_skip_policy:
                    history_ids.add(item["key"])
                    skipped_policy += 1
                    continue
                if should_skip_duplicate_content(item.get("handle", ""), item.get("content", "")):
                    history_ids.add(item["key"])
                    skipped_dup_content += 1
                    continue
                history_ids.add(item["key"])
                pending_results.append(item)
                enqueue_new_data(item)
                count += 1

        with data_lock:
            for t in monitor_tasks:
                if t['url'] == url: t['last_check'] = datetime.datetime.now().strftime("%H:%M:%S")

        if count > 0:
            log_to_ui("success", f"✅ {short_url} 完成: 新增 {count} 条")
        else:
            log_to_ui("info", f"⏸️ {short_url} 完成: 无新数据")
        if skipped_dup_content > 0:
            log_to_ui("debug", f"📋 [Tweet] 跳过同用户重复内容: {skipped_dup_content}")
        if skipped_policy > 0:
            log_to_ui("debug", f"📋 [Tweet] 跳过内容过滤: {skipped_policy}")

        save_state()
        return count
    except Exception as e:
        log_to_ui("error", f"任务线程错误: {str(e)}")
        return 0


def scan_task_with_tab(task, blocked_users):
    """
    使用新标签页扫描任务 - 单浏览器多标签页模式
    在全局浏览器中创建新标签页，完成后关闭
    """
    global global_browser

    if not global_browser or not browser_initialized:
        log_to_ui("error", "浏览器未初始化")
        return 0

    url = task['url']
    short_url = url.split('/')[-1]
    tab = None

    try:
        log_to_ui("info", f"📑 [标签页] 开始扫描: {short_url}")
        time.sleep(random.uniform(TAB_OPEN_JITTER_MIN_SEC, TAB_OPEN_JITTER_MAX_SEC))

        # 在浏览器中创建新标签页
        with tab_lock:
            tab = global_browser.new_tab()
            log_to_ui("info", f"📑 [标签页] 已创建新标签页")

        # 访问目标页面
        log_to_ui("info", f"📑 [标签页] 正在访问: {url}")
        tab.get(url)

        # 等待页面加载
        try:
            tab.wait.ele_displayed('tag:article', timeout=15)
            log_to_ui("success", f"📑 [标签页] 页面已加载: {short_url}")
        except Exception as e:
            log_to_ui("warn", f"⚠️ 页面加载超时: {short_url} - {e}")

        time.sleep(random.uniform(1.2, 2.8))

        # 检查当前URL
        log_to_ui("info", f"📑 [标签页] 当前URL: {tab.url}")

        # 扫描页面内容
        log_to_ui("info", f"📑 [标签页] 开始扫描页面内容...")
        new_items, err = scan_page_content_with_tab(tab, url, blocked_users)

        log_to_ui("info", f"📑 [标签页] 扫描返回: {len(new_items)} 条数据, 错误: {err}")

        if err:
            log_to_ui("error", f"❌ {short_url} 扫描失败: {err}")
            return 0

        # 处理新数据
        count = 0
        skipped_dup_content = 0
        skipped_policy = 0
        for item in new_items:
            with data_lock:
                if item["key"] in history_ids:
                    continue
                should_skip_policy, _ = should_skip_content_by_policy(item.get("content", ""))
                if should_skip_policy:
                    skipped_policy += 1
                    continue
                if should_skip_duplicate_content(item.get("handle", ""), item.get("content", "")):
                    skipped_dup_content += 1
                    continue
                history_ids.add(item["key"])
                pending_results.append(item)
                enqueue_new_data(item)
                count += 1
                log_to_ui("success", f"📥 已添加到队列: {item['handle']}")

        with data_lock:
            for t in monitor_tasks:
                if t['url'] == url:
                    t['last_check'] = datetime.datetime.now().strftime("%H:%M:%S")

        if count > 0:
            log_to_ui("success", f"✅ {short_url} 完成: 新增 {count} 条")
        else:
            log_to_ui("info", f"⏸️ {short_url} 完成: 无新数据")
        if skipped_dup_content > 0:
            log_to_ui("debug", f"📋 [TweetTab] 跳过同用户重复内容: {skipped_dup_content}")
        if skipped_policy > 0:
            log_to_ui("debug", f"📋 [TweetTab] 跳过内容过滤: {skipped_policy}")

        save_state()
        return count

    except Exception as e:
        log_to_ui("error", f"标签页任务错误: {str(e)}")
        return 0
    finally:
        # 关闭标签页
        if tab:
            try:
                tab.close()
            except Exception:
                pass


def scan_page_content_with_tab(tab, url, blocked_list):
    """
    使用标签页扫描页面内容 - 适配标签页模式
    """
    results = []
    seen_in_page = set()
    processed_article_hashes = set()

    try:
        tweet_id_match = re.search(r'status/(\d+)', url)
        if not tweet_id_match:
            return [], "链接无效"

        main_tweet_id = tweet_id_match.group(1)
        short_url = url.split('/')[-1]

        # 配置参数
        max_scrolls = 50
        max_consecutive_empty = 8
        scroll_step = 800

        scroll_count = 0
        consecutive_empty = 0
        total_captured = 0

        # 调试计数
        debug_stats = {
            "no_user": 0,
            "no_handle": 0,
            "no_content": 0,
            "blacklist": 0,
            "duplicate": 0,
            "has_reply": 0,
            "emoji_only": 0,
            "blocked_mention": 0,
        }

        while scroll_count < max_scrolls:
            scroll_count += 1

            # 检查URL
            if url not in tab.url:
                tab.get(url)
                time.sleep(2)

            # 获取当前所有articles
            try:
                articles = tab.eles('tag:article', timeout=1)
            except Exception:
                articles = []

            articles = reorder_articles_for_scan(articles)

            # 处理新的articles
            new_count = 0
            for article in articles:
                try:
                    if random.random() < 0.18:
                        time.sleep(random.uniform(0.02, 0.12))
                    article_html = article.html
                    article_hash = hash(article_html[:300])

                    if article_hash in processed_article_hashes:
                        continue

                    processed_article_hashes.add(article_hash)
                    new_count += 1

                    # 跳过原推文
                    if f'/status/{main_tweet_id}' in article_html and '<time' in article_html:
                        continue

                    # 提取handle
                    user_ele = article.ele('css:[data-testid="User-Name"]', timeout=0.01)
                    if not user_ele:
                        debug_stats["no_user"] += 1
                        continue

                    handle_match = re.search(r'(@[\w_]+)', user_ele.text)
                    if not handle_match:
                        debug_stats["no_handle"] += 1
                        continue
                    handle = handle_match.group(1)

                    # 过滤保护名单
                    if handle in blocked_list:
                        debug_stats["blacklist"] += 1
                        continue

                    # 提取内容
                    text_ele = article.ele('css:[data-testid="tweetText"]', timeout=0.01)
                    content = text_ele.text.replace('\n', ' ').strip() if text_ele else ""

                    if not content:
                        debug_stats["no_content"] += 1
                        continue
                    should_skip_policy, skip_reason = should_skip_content_by_policy(content)
                    if should_skip_policy:
                        if skip_reason == "emoji_only":
                            debug_stats["emoji_only"] += 1
                        elif skip_reason == "blocked_mention":
                            debug_stats["blocked_mention"] += 1
                        continue

                    # 去重
                    unique_key = f"{handle}_{content[:50]}"
                    if unique_key in seen_in_page or unique_key in history_ids:
                        debug_stats["duplicate"] += 1
                        continue
                    seen_in_page.add(unique_key)

                    # 检查是否已回复过该评论
                    # 通过检查后续articles是否来自当前登录用户来判断
                    delegated_now = get_effective_delegated_account()
                    if delegated_now:
                        my_handle = delegated_now.strip().lstrip('@').lower()
                        already_replied = False

                        try:
                            # 获取当前article在列表中的索引
                            current_idx = articles.index(article)

                            # 检查后续3条article（通常你的回复会紧跟在评论后面）
                            for check_idx in range(current_idx + 1, min(current_idx + 4, len(articles))):
                                check_article = articles[check_idx]
                                check_user_ele = check_article.ele('css:[data-testid="User-Name"]', timeout=0.01)
                                if check_user_ele:
                                    check_handle_match = re.search(r'(@[\w_]+)', check_user_ele.text)
                                    if check_handle_match:
                                        check_handle = check_handle_match.group(1).lower()
                                        # 如果后续article来自当前用户，说明已回复
                                        if check_handle == f'@{my_handle}' or check_handle == my_handle:
                                            already_replied = True
                                            break
                        except Exception:
                            pass

                        if already_replied:
                            debug_stats["already_replied"] = debug_stats.get("already_replied", 0) + 1
                            continue

                    # 捕获成功
                    total_captured += 1
                    log_to_ui("success", f"✅ 捕获: {handle} - {content[:30]}...")
                    results.append({
                        "handle": handle,
                        "content": content,
                        "key": unique_key,
                        "source": url,
                        "time": datetime.datetime.now().strftime("%H:%M:%S")
                    })

                except Exception as e:
                    log_to_ui("debug", f"处理article异常: {e}")
                    continue

            # 判断是否有新内容
            if new_count == 0:
                consecutive_empty += 1
                if consecutive_empty >= max_consecutive_empty:
                    break
            else:
                consecutive_empty = 0

            # 点击"显示更多回复"按钮
            try:
                buttons = tab.eles('tag:button', timeout=0.3)
                for btn in buttons:
                    btn_text = (btn.text or "").strip()
                    if any(kw in btn_text for kw in ['显示更多', 'Show more', '显示可能']):
                        if btn.states.is_displayed:
                            tab.run_js('arguments[0].click()', btn)
                            time.sleep(1)
                            break
            except Exception:
                pass

            # 滚动
            try:
                prev_top = tab.run_js('return window.scrollY || document.documentElement.scrollTop')
                tab.run_js(f'window.scrollBy(0, {scroll_step}); void(0);')
                time.sleep(random.uniform(0.5, 0.8))
                new_top = tab.run_js('return window.scrollY || document.documentElement.scrollTop')

                if new_top <= prev_top:
                    consecutive_empty += 1
                    if consecutive_empty >= max_consecutive_empty:
                        break
            except Exception:
                consecutive_empty += 1

        # 输出统计
        already_replied_count = debug_stats.get("already_replied", 0)
        log_to_ui("info", f"📊 [{short_url}] 扫描统计: 捕获 {total_captured} 条")
        log_to_ui("info", f"   跳过: 无用户({debug_stats['no_user']}), 无handle({debug_stats['no_handle']}), 无内容({debug_stats['no_content']})")
        log_to_ui("info", f"   跳过: 保护名单({debug_stats['blacklist']}), 重复({debug_stats['duplicate']}), 已回复({already_replied_count})")
        log_to_ui("info", f"   跳过: 纯表情({debug_stats['emoji_only']}), 指定@过滤({debug_stats['blocked_mention']})")

        return results, None

    except Exception as e:
        log_to_ui("error", f"扫描异常: {str(e)}")
        return [], str(e)


def init_notification_tab(blocked_users):
    """初始化持久通知标签页"""
    global notification_tab, global_browser, notification_last_refresh_at, notification_refresh_interval, notification_empty_article_streak

    if not global_browser or not browser_initialized:
        return

    with notification_tab_lock:
        if notification_tab is not None:
            return  # 已存在

        try:
            log_to_ui("info", "📬 创建持久通知标签页...")
            time.sleep(random.uniform(0.3, 1.1))
            notification_tab = global_browser.new_tab()
            notification_tab.get("https://x.com/notifications")

            try:
                notification_tab.wait.ele_displayed('tag:article', timeout=10)
            except Exception:
                pass

            time.sleep(2)

            # 点击"全部"标签（而不是默认的"优先"）
            try:
                # 查找标签栏中的"全部"或"All"按钮
                tabs = notification_tab.eles('css:[role="tab"]', timeout=2)
                for tab in tabs:
                    tab_text = (tab.text or "").strip().lower()
                    if tab_text in ['全部', 'all']:
                        tab.click()
                        log_to_ui("info", "📬 已切换到\"全部\"通知")
                        time.sleep(1)
                        break
            except Exception as e:
                log_to_ui("debug", f"切换全部标签失败: {e}")

            log_to_ui("success", "✅ 通知标签页已创建并保持打开")
            notification_last_refresh_at = 0.0
            notification_refresh_interval = _schedule_next_notification_refresh_interval(notification_refresh_interval)
            notification_empty_article_streak = 0
        except Exception as e:
            log_to_ui("error", f"创建通知标签页失败: {str(e)}")
            notification_tab = None


def close_notification_tab():
    """关闭持久通知标签页"""
    global notification_tab, notification_last_refresh_at, notification_empty_article_streak

    with notification_tab_lock:
        if notification_tab:
            try:
                notification_tab.close()
            except Exception:
                pass
            notification_tab = None
            notification_last_refresh_at = 0.0
            notification_empty_article_streak = 0
            log_to_ui("info", "📬 通知标签页已关闭")


def ensure_notification_tab(blocked_users):
    """确保通知标签页存在，如果不存在则重新创建"""
    global notification_tab

    with notification_tab_lock:
        if notification_tab is None:
            # 重新创建
            pass
        else:
            # 检查标签页是否还有效
            try:
                _ = notification_tab.url
                return  # 标签页有效
            except Exception:
                notification_tab = None

    # 需要重新创建
    init_notification_tab(blocked_users)


def scan_persistent_notification_tab(blocked_users, max_recent_minutes=None):
    """扫描持久通知标签页 - 快速扫描模式"""
    global notification_tab, notification_last_refresh_at, notification_refresh_interval, notification_disconnect_streak, notification_empty_article_streak

    if notification_tab is None:
        return

    try:
        def _article_count(tab_obj, timeout_sec=0.8):
            try:
                return len(tab_obj.eles('tag:article', timeout=timeout_sec))
            except Exception:
                return 0

        def _reload_notifications_view():
            """通知页空载时的轻量恢复：重新打开通知页并切到“全部”标签。"""
            global notification_last_refresh_at, notification_refresh_interval
            try:
                with notification_tab_lock:
                    if not notification_tab:
                        return 0
                    notification_tab.get("https://x.com/notifications")
                    try:
                        notification_tab.wait.ele_displayed('tag:article', timeout=6)
                    except Exception:
                        pass
                    time.sleep(random.uniform(0.9, 1.8))
                    try:
                        tabs = notification_tab.eles('css:[role="tab"]', timeout=1.2)
                        for tab in tabs:
                            tab_text = (tab.text or "").strip().lower()
                            if tab_text in ['全部', 'all']:
                                is_selected = tab.attr('aria-selected') == 'true'
                                if not is_selected:
                                    tab.click()
                                    time.sleep(random.uniform(0.35, 0.9))
                                break
                    except Exception:
                        pass
                    notification_last_refresh_at = time.time()
                    notification_refresh_interval = _schedule_next_notification_refresh_interval(notification_refresh_interval)
                    return _article_count(notification_tab, timeout_sec=1.0)
            except Exception as recover_err:
                log_to_ui("warn", f"⚠️ 通知页空载恢复失败: {recover_err}")
                return 0

        with notification_tab_lock:
            now_ts = time.time()
            need_refresh = (notification_last_refresh_at <= 0) or ((now_ts - notification_last_refresh_at) >= notification_refresh_interval)

            # 仅按随机周期刷新，避免固定高频刷新触发风控
            if need_refresh:
                try:
                    skip_prob = max(0.0, min(1.0, float(NOTIFICATION_REFRESH_SKIP_PROB)))
                    soft_prob = max(0.0, min(1.0, float(NOTIFICATION_REFRESH_SOFT_NAV_PROB)))
                    if skip_prob + soft_prob > 0.95:
                        soft_prob = max(0.0, 0.95 - skip_prob)

                    refresh_roll = random.random()
                    refresh_strategy = "hard_refresh"
                    if refresh_roll < skip_prob:
                        refresh_strategy = "skip_refresh"
                    elif refresh_roll < (skip_prob + soft_prob):
                        refresh_strategy = "soft_nav"

                    if refresh_strategy == "hard_refresh":
                        notification_tab.refresh()
                        time.sleep(random.uniform(0.9, 2.1))
                    elif refresh_strategy == "soft_nav":
                        notification_tab.get("https://x.com/notifications")
                        time.sleep(random.uniform(0.95, 2.35))
                    else:
                        # 本轮仅更新节奏，不做页面跳转，打散行为指纹
                        time.sleep(random.uniform(0.22, 0.7))

                    notification_last_refresh_at = now_ts
                    notification_refresh_interval = _schedule_next_notification_refresh_interval(notification_refresh_interval)
                    log_to_ui(
                        "debug",
                        f"📬 通知刷新策略={refresh_strategy}，下次刷新间隔: {notification_refresh_interval:.1f}s"
                    )
                except Exception:
                    pass

            # 快速确保在"全部"标签页
            try:
                tabs = notification_tab.eles('css:[role="tab"]', timeout=0.5)  # 减少timeout
                for tab in tabs:
                    tab_text = (tab.text or "").strip().lower()
                    if tab_text in ['全部', 'all']:
                        is_selected = tab.attr('aria-selected') == 'true'
                        if not is_selected:
                            tab.click()
                            time.sleep(random.uniform(0.35, 1.0))
                        break
            except Exception:
                pass

            # 随机滚动策略：大多数回到顶部，少数做小幅下滚，避免每轮一致动作
            try:
                if random.random() < 0.82:
                    notification_tab.run_js('window.scrollTo(0, 0);')
                else:
                    delta = int(random.uniform(80, 360))
                    notification_tab.run_js(f'window.scrollBy(0, {delta});')
                time.sleep(random.uniform(0.22, 0.95))
            except Exception:
                pass

        pre_article_count = _article_count(notification_tab, timeout_sec=0.6)
        if pre_article_count <= 0:
            notification_empty_article_streak += 1
            streak = int(notification_empty_article_streak)
            log_to_ui("warn", f"⚠️ 通知页疑似空载（articles=0，连续{streak}次）")

            soft_threshold = max(2, int(NOTIFICATION_EMPTY_RECOVER_SOFT_THRESHOLD))
            hard_threshold = max(soft_threshold + 1, int(NOTIFICATION_EMPTY_RECOVER_HARD_THRESHOLD))

            if streak >= soft_threshold:
                recovered_count = _reload_notifications_view()
                if recovered_count > 0:
                    notification_empty_article_streak = 0
                    pre_article_count = recovered_count
                    log_to_ui("info", f"✅ 通知页空载已恢复（articles={recovered_count}）")

            if pre_article_count <= 0 and streak >= hard_threshold:
                log_to_ui("warn", "⚠️ 通知页持续空载，重建通知标签页")
                with notification_tab_lock:
                    try:
                        if notification_tab:
                            notification_tab.close()
                    except Exception:
                        pass
                    notification_tab = None
                ensure_notification_tab(blocked_users)
                notification_empty_article_streak = 0
            if pre_article_count <= 0:
                return 0
        else:
            if notification_empty_article_streak > 0:
                log_to_ui("info", f"✅ 通知页已恢复正常（articles={pre_article_count}）")
            notification_empty_article_streak = 0

        # 扫描通知
        notif_items, notif_err = scan_notifications_page(
            notification_tab,
            blocked_users,
            max_recent_minutes=max_recent_minutes
        )

        if notif_err:
            log_to_ui("error", f"❌ 通知扫描错误: {notif_err}")
            # 尝试刷新页面
            try:
                # 连接断开时直接重建标签页，避免卡死在无效tab对象上
                err_text = str(notif_err).lower()
                disconnected = ("连接已断开" in str(notif_err)) or ("disconnected" in err_text)
                if disconnected:
                    notification_disconnect_streak += 1
                    log_to_ui("warn", f"⚠️ 通知标签页连接断开（连续{notification_disconnect_streak}次）")
                    log_to_ui("warn", "⚠️ 通知标签页连接断开，准备重建标签页")
                    with notification_tab_lock:
                        try:
                            if notification_tab:
                                notification_tab.close()
                        except Exception:
                            pass
                        notification_tab = None
                    ensure_notification_tab(blocked_users)
                    # 连续断开时执行一次浏览器级重建，缓解代理抖动导致的会话失联
                    if notification_disconnect_streak >= 3:
                        if (not headless_mode) and (not HEADFUL_NOTIFY_DISCONNECT_RESTART):
                            log_to_ui("warn", "⚠️ 连续断线达到阈值（有头模式），仅重建通知标签页，不重启浏览器")
                            ensure_notification_tab(blocked_users)
                        else:
                            log_to_ui("warn", "⚠️ 连续断线达到阈值，执行浏览器重建")
                            browser = restart_global_browser()
                            delegated = get_effective_delegated_account()
                            if delegated and browser:
                                try:
                                    with browser_lock:
                                        browser.get("https://x.com/home")
                                        time.sleep(1.5)
                                        ensure_delegated_account_session(browser, delegated)
                                except Exception as recover_err:
                                    log_to_ui("warn", f"⚠️ 浏览器重建后恢复委派账户失败: {recover_err}")
                            ensure_notification_tab(blocked_users)
                        notification_disconnect_streak = 0
                else:
                    notification_tab.refresh()
                    time.sleep(random.uniform(1.2, 2.5))
            except Exception:
                pass
            return 0
        else:
            notification_disconnect_streak = 0

        # 处理新数据
        new_count = 0
        skipped_dup_content = 0
        if notif_items:
            for item in notif_items:
                with data_lock:
                    if item["key"] in history_ids:
                        continue
                    if should_skip_duplicate_content(item.get("handle", ""), item.get("content", "")):
                        # 同用户重复内容会被过滤，仍记录key避免下一轮重复命中
                        history_ids.add(item["key"])
                        skipped_dup_content += 1
                        continue
                    history_ids.add(item["key"])

                # 通知入队前做一次意向分析（用于日志与前端展示，不做拦截）
                try:
                    runtime_base_url = LLM_FILTER_BASE_URL if LLM_FILTER_ENABLED else ""
                    runtime_model = LLM_FILTER_MODEL if LLM_FILTER_ENABLED else ""
                    runtime_api_key = LLM_FILTER_API_KEY if LLM_FILTER_ENABLED else ""
                    analysis = analyze_comment_intent(
                        item.get("content", ""),
                        base_url=runtime_base_url,
                        api_key=runtime_api_key,
                        model=runtime_model,
                        timeout_sec=LLM_FILTER_TIMEOUT_SEC,
                    )
                    item["intent_score"] = int(analysis.get("intent_score", 0))
                    item["intent_level"] = str(analysis.get("intent_level", "noise"))
                    item["is_intent_user"] = bool(analysis.get("is_intent_user", False))
                    item["force_notify"] = bool(analysis.get("force_notify", False))
                    item["llm_used"] = bool(analysis.get("llm_used", False))
                    item["intent_reason"] = str(analysis.get("reason", "") or "")
                    item["intent_signals"] = list(analysis.get("signals", []))[:8]
                    item["voice_should_notify"] = bool(_should_notify_voice_by_intent(analysis))
                    log_to_ui(
                        "info",
                        f"🤖 AI意向分析[notify_auto] handle={item.get('handle', '')} "
                        f"score={item['intent_score']} level={item['intent_level']} "
                        f"intent={item['is_intent_user']} voice={item['voice_should_notify']} llm_used={item['llm_used']}"
                    )
                    llm_error = str(analysis.get("llm_error", "") or "").strip()
                    if llm_error:
                        log_to_ui("warn", f"🤖 AI意向分析[notify_auto] LLM异常: {llm_error}")
                except Exception as analyze_err:
                    log_to_ui("warn", f"🤖 AI意向分析[notify_auto] 失败: {analyze_err}")

                with data_lock:
                    pending_results.append(item)
                enqueue_new_data(item)
                new_count += 1
            if new_count > 0:
                save_state()
                log_to_ui("success", f"📬 通知扫描: 新增 {new_count} 条")
            if skipped_dup_content > 0:
                log_to_ui("debug", f"📋 [Notify] 跳过同用户重复内容: {skipped_dup_content}")
        return new_count

    except Exception as e:
        log_to_ui("error", f"通知扫描错误: {str(e)}")
        log_to_ui("debug", f"🔎 [NotifyTrace] scan_persistent_notification_tab traceback={traceback.format_exc()}")
        return 0


def start_monitor_thread():
    global monitor_active, monitor_thread

    with monitor_thread_lock:
        if monitor_thread and monitor_thread.is_alive():
            monitor_active = True
            return False

        monitor_active = True
        monitor_thread = threading.Thread(target=monitoring_loop, daemon=True, name="monitoring_loop")
        monitor_thread.start()
        return True


def stop_monitor_thread(wait_timeout=15):
    """停止监控线程并等待退出，防止重启时竞态。"""
    global monitor_active, monitor_thread
    monitor_active = False

    with monitor_thread_lock:
        thread_ref = monitor_thread

    if thread_ref and thread_ref.is_alive():
        thread_ref.join(timeout=wait_timeout)
        if thread_ref.is_alive():
            log_to_ui("warn", "⚠️ 监控线程未在超时内退出，执行强制浏览器清理")
            close_notification_tab()
            cleanup_global_browser()
            return False

    with monitor_thread_lock:
        if monitor_thread and not monitor_thread.is_alive():
            monitor_thread = None

    return True


def extract_status_id_from_notification_item(item):
    """从通知记录中提取状态ID。"""
    if not isinstance(item, dict):
        return ""

    status_id = _pick_best_status_id(
        item.get("status_id", ""),
        item.get("status_url", ""),
        item.get("status_handle", ""),
        item.get("key", ""),
    )
    if status_id:
        return status_id

    key = str(item.get("key", "")).strip()
    m = re.match(r'^notif_status_(\d+)$', key)
    if m:
        sid = _pick_best_status_id(m.group(1))
        return sid or m.group(1)

    return ""


def is_reply_to_me_notification_item(item):
    """判断通知记录是否属于“回复了你”类型。"""
    if not isinstance(item, dict):
        return False
    if item.get("source") != "通知页面":
        return False

    notify_type = str(item.get("notification_type", "") or "").strip().lower()
    if notify_type:
        return notify_type == "reply_to_you"

    # 兼容旧数据：没有 notification_type 字段时按文本兜底判定
    text_blob = " ".join([
        str(item.get("notification_text", "") or ""),
        str(item.get("content", "") or ""),
    ]).lower()
    return any(k in text_blob for k in NOTIFICATION_REPLY_TO_YOU_KEYWORDS)


def _extract_status_ids_from_article(article):
    """提取单条 article 内出现的 status_id。"""
    ids = set()
    try:
        links = article.eles('tag:a', timeout=0)
    except Exception:
        links = []

    for link in links:
        try:
            href = (link.attr('href') or '').strip()
        except Exception:
            href = ""
        if not href:
            continue

        sid = _pick_best_status_id(href)
        if sid:
            ids.add(sid)
    return ids


def _match_reply_target_article(page, status_id, handle, content):
    """在会话页中定位“评论者那条卡片”。"""
    target_status_id = str(status_id or "").strip()
    handle_norm = normalize_handle(handle)
    content_norm = normalize_content_for_dedupe(content or "")

    best_article = None
    best_score = -1
    try:
        articles = page.eles('tag:article', timeout=2)
    except Exception:
        articles = []

    for article in articles[:40]:
        score = 0

        # 0) status_id 强匹配（最高优先级）
        article_status_ids = _extract_status_ids_from_article(article)
        if target_status_id:
            if target_status_id in article_status_ids:
                score += 220
            elif article_status_ids:
                # 该卡片明确是其它帖子，直接跳过，避免误点主帖
                continue

        # 1) 用户匹配（优先）
        try:
            user_ele = article.ele('css:[data-testid="User-Name"]', timeout=0)
            user_text = (user_ele.text or "").strip().lower() if user_ele else ""
            m = re.search(r'@([a-z0-9_]{1,30})', user_text)
            article_handle = m.group(1) if m else ""
            if handle_norm and article_handle:
                if article_handle == handle_norm:
                    score += 120
                elif handle_norm in article_handle:
                    score += 60
        except Exception:
            pass

        # 2) 内容匹配（辅助）
        article_content_norm = ""
        try:
            txt_ele = article.ele('css:[data-testid="tweetText"]', timeout=0)
            article_content = (txt_ele.text or "").strip() if txt_ele else ""
            article_content_norm = normalize_content_for_dedupe(article_content)
            if content_norm and article_content_norm:
                if content_norm in article_content_norm or article_content_norm in content_norm:
                    score += 90
                else:
                    pivot = content_norm[:12]
                    if len(pivot) >= 6 and pivot in article_content_norm:
                        score += 30
        except Exception:
            pass

        # 3) 必须有可点击回复按钮
        has_reply_btn = False
        try:
            rb = article.ele('css:[data-testid="reply"]', timeout=0)
            has_reply_btn = bool(rb and rb.states.is_displayed)
        except Exception:
            has_reply_btn = False
        if has_reply_btn:
            score += 10
        else:
            continue

        if score > best_score:
            best_score = score
            best_article = article

    if best_article is None:
        return None, 0
    return best_article, best_score


def _match_notification_card_for_reply(page, status_id, handle, content):
    """在通知页定位目标通知卡片及其左下角回复按钮。"""
    target_status_id = str(status_id or "").strip()
    handle_norm = normalize_handle(handle)
    content_norm = normalize_content_for_dedupe(content or "")

    best_article = None
    best_reply_btn = None
    best_score = -1
    try:
        articles = page.eles('tag:article', timeout=2)
    except Exception:
        articles = []

    for article in articles[:80]:
        try:
            article_text = article.text or ""
        except Exception:
            article_text = ""

        score = 0
        card_status_handle, card_status_id = _extract_notification_status_info(article)

        # 1) status_id 强匹配（最高优先级）
        if target_status_id:
            if card_status_id == target_status_id:
                score += 260
            elif card_status_id:
                continue

        # 2) 用户匹配
        card_handle = _extract_notification_handle(article, article_text) or card_status_handle or ""
        card_handle_norm = normalize_handle(card_handle)
        if handle_norm and card_handle_norm:
            if card_handle_norm == handle_norm:
                score += 100
            elif (handle_norm in card_handle_norm) or (card_handle_norm in handle_norm):
                score += 50

        # 3) 内容匹配
        try:
            card_content = _extract_notification_content(article, article_text, card_handle or "")
        except Exception:
            card_content = ""
        card_content_norm = normalize_content_for_dedupe(card_content or "")
        if content_norm and card_content_norm:
            if (content_norm in card_content_norm) or (card_content_norm in content_norm):
                score += 80
            else:
                pivot = content_norm[:12]
                if len(pivot) >= 6 and pivot in card_content_norm:
                    score += 35

        # 4) 必须有回复按钮
        try:
            reply_btn = article.ele('css:[data-testid="reply"]', timeout=0)
            if not (reply_btn and reply_btn.states.is_displayed):
                continue
        except Exception:
            continue
        score += 20

        if score > best_score:
            best_score = score
            best_article = article
            best_reply_btn = reply_btn

    return best_article, best_reply_btn, best_score


def ensure_reply_work_tab(force_recreate=False):
    """确保回复专用工作标签页可用（复用同一标签页）。"""
    global reply_work_tab

    tab = None
    with reply_work_tab_lock:
        if force_recreate and reply_work_tab:
            try:
                reply_work_tab.close()
            except Exception:
                pass
            reply_work_tab = None

        if reply_work_tab is not None:
            try:
                _ = reply_work_tab.url
                log_to_ui("debug", "💬 复用已有回复工作标签页")
                tab = reply_work_tab
            except Exception:
                reply_work_tab = None

        if tab is None:
            browser = init_global_browser()
            with tab_lock:
                reply_work_tab = browser.new_tab()
            tab = reply_work_tab
            log_to_ui("debug", "💬 已创建回复工作标签页（将持续复用）")

    _warmup_dm_passcode_if_needed(tab)
    return tab


def _wait_first_visible(tab, selectors, timeout=3.0, poll=0.12):
    """轮询选择器并返回首个可见元素。"""
    deadline = time.time() + max(0.2, float(timeout))
    while time.time() < deadline:
        for selector in selectors:
            try:
                cand = tab.ele(selector, timeout=0)
            except Exception:
                cand = None
            try:
                if cand and cand.states.is_displayed:
                    return cand
            except Exception:
                continue
        time.sleep(poll)
    return None


def _find_pending_notify_item_by_key(item_key):
    """按 key 定位通知项，返回索引与引用。"""
    key = str(item_key or "").strip()
    if not key:
        return -1, None
    with data_lock:
        for idx, row in enumerate(pending_results):
            if row.get("key") == key and row.get("source") == "通知页面":
                return idx, row
    return -1, None


def _normalize_notify_flow_stage(stage):
    text = str(stage or "").strip().lower()
    return text if text in NOTIFY_FLOW_STAGE_ORDER else ""


def _notify_stage_rank(stage):
    return int(NOTIFY_FLOW_STAGE_ORDER.get(_normalize_notify_flow_stage(stage), 0))


def _notify_stage_at_least(stage, baseline):
    return _notify_stage_rank(stage) >= _notify_stage_rank(baseline)


def _resolve_notify_resume_stage(row_like):
    """解析任务应从哪个阶段恢复，避免 retry_waiting/reply_pending 覆盖真实进度。"""
    row = row_like if isinstance(row_like, dict) else {}
    stage = _normalize_notify_flow_stage(row.get("notify_flow_stage", ""))
    resume_hint = _normalize_notify_flow_stage(row.get("notify_resume_stage", ""))
    if stage == "retry_waiting":
        return resume_hint or "reply_pending"
    if resume_hint and _notify_stage_rank(resume_hint) > _notify_stage_rank(stage):
        return resume_hint
    return stage or "reply_pending"


def _split_flow_error(error_text, default_code="E_REPLY_FAILED"):
    msg = str(error_text or "").strip()
    if not msg:
        return "", ""
    m = re.search(r"\b(E_[A-Z0-9_]+)\b", msg)
    if m:
        code = m.group(1).strip()
        detail = msg.replace(code, "", 1).strip(" :,-")
        return code, (detail or msg)
    return str(default_code or "E_REPLY_FAILED"), msg


def _update_notify_flow_state(
    item_key,
    stage=None,
    error="",
    retry_at=0.0,
    attempt=None,
    extra=None,
    save=False,
    error_code=None,
    error_detail=None,
):
    """更新通知回复任务状态，便于断点恢复与前端可视化。"""
    key = str(item_key or "").strip()
    if not key:
        return False

    stage_text = _normalize_notify_flow_stage(stage) or str(stage or "").strip()
    err_text = str(error or "").strip()
    code_text = str(error_code or "").strip()
    detail_text = str(error_detail or "").strip()
    if err_text and (not code_text or not detail_text):
        parsed_code, parsed_detail = _split_flow_error(err_text)
        if not code_text:
            code_text = parsed_code
        if not detail_text:
            detail_text = parsed_detail
    now = time.time()
    updated = False
    with data_lock:
        for row in pending_results:
            if row.get("key") != key or row.get("source") != "通知页面":
                continue
            if stage_text:
                row["notify_flow_stage"] = stage_text
            row["notify_flow_error"] = detail_text or err_text
            row["notify_flow_error_code"] = code_text
            row["notify_flow_error_detail"] = detail_text or err_text
            row["notify_flow_updated_at"] = now
            row["notify_flow_updated_time"] = datetime.datetime.fromtimestamp(now).strftime("%H:%M:%S")
            if attempt is not None:
                try:
                    row["notify_flow_attempt"] = int(attempt)
                except Exception:
                    row["notify_flow_attempt"] = attempt
            if retry_at:
                try:
                    retry_ts = float(retry_at)
                except Exception:
                    retry_ts = 0.0
                if retry_ts > 0:
                    row["notify_retry_at"] = retry_ts
                    row["notify_retry_time"] = datetime.datetime.fromtimestamp(retry_ts).strftime("%H:%M:%S")
            else:
                row["notify_retry_at"] = 0
                row["notify_retry_time"] = ""
            if not (detail_text or err_text):
                row["notify_flow_error"] = ""
                row["notify_flow_error_code"] = ""
                row["notify_flow_error_detail"] = ""
            if isinstance(extra, dict):
                for k, v in extra.items():
                    row[k] = v
            updated = True
            break
    if updated and save:
        save_state()
    return updated


def _clear_notify_flow_error(item_key, save=False):
    return _update_notify_flow_state(
        item_key,
        error="",
        retry_at=0.0,
        save=save,
        error_code="",
        error_detail="",
    )


def _resolve_notify_retry_backoff_sec(attempt):
    try:
        idx = max(0, int(attempt) - 1)
    except Exception:
        idx = 0
    if idx < len(DM_RETRY_BACKOFF_SEC):
        return int(DM_RETRY_BACKOFF_SEC[idx])
    return int(DM_RETRY_BACKOFF_SEC[-1]) if DM_RETRY_BACKOFF_SEC else 15


def _is_dm_unknown_failure_retryable(err_text):
    """未知失败是否允许进入重试队列。"""
    msg = str(err_text or "").strip()
    if not msg:
        return True
    if _is_dm_closed_error_text(msg):
        return False
    hard_stop_keywords = [
        "缺少可回复的状态id",
        "missing key",
        "通知记录不存在",
        "请先配置并验证 auth_token",
    ]
    lower_msg = msg.lower()
    return not any(k in lower_msg for k in hard_stop_keywords)


def _mark_notify_reply_success(key, message, dm_message, reply_time_text=None, save=True):
    """标记通知任务回复链路完成。"""
    key = str(key or "").strip()
    if not key:
        return False
    reply_time = str(reply_time_text or "").strip() or datetime.datetime.now().strftime("%H:%M:%S")
    updated = False
    with data_lock:
        for row in pending_results:
            if row.get("key") != key or row.get("source") != "通知页面":
                continue
            row["notify_replied"] = True
            row["notify_reply_text"] = str(message or "")
            row["notify_dm_text"] = str(dm_message or "")
            row["notify_reply_time"] = reply_time
            row["notify_flow_stage"] = "done"
            row["notify_flow_error"] = ""
            row["notify_flow_error_code"] = ""
            row["notify_flow_error_detail"] = ""
            row["notify_retry_at"] = 0
            row["notify_retry_time"] = ""
            row["notify_flow_updated_at"] = time.time()
            row["notify_flow_updated_time"] = datetime.datetime.now().strftime("%H:%M:%S")
            updated = True
            break
    if updated and save:
        save_state()
    return updated


def _schedule_notify_retry(item_key, err_text, attempt, reason="retry_queue", save=True):
    """
    按策略调度通知任务重试。
    返回: (scheduled, retry_at, message)
    """
    key = str(item_key or "").strip()
    err_msg = str(err_text or "").strip() or "E_REPLY_FAILED: 未知错误"
    _, cur_row = _find_pending_notify_item_by_key(key)
    resume_stage = _resolve_notify_resume_stage(cur_row or {})
    try:
        attempt_num = max(1, int(attempt))
    except Exception:
        attempt_num = 1

    code, detail = _split_flow_error(err_msg)
    if DM_UNKNOWN_FAILURE_POLICY != "retry_queue":
        _update_notify_flow_state(
            key,
            stage="retry_waiting",
            attempt=attempt_num,
            error=detail,
            error_code=code or "E_REPLY_FAILED",
            error_detail=detail or err_msg,
            retry_at=0,
            extra={
                "notify_retry_reason": f"{reason}:policy_disabled",
                "notify_resume_stage": resume_stage,
            },
            save=save,
        )
        return False, 0.0, "重试队列已禁用，请人工重试"

    if (not _is_dm_unknown_failure_retryable(err_msg)) or code == "E_DM_CLOSED_CONFIRMED":
        _update_notify_flow_state(
            key,
            stage="retry_waiting",
            attempt=attempt_num,
            error=detail,
            error_code=code or "E_REPLY_FAILED",
            error_detail=detail or err_msg,
            retry_at=0,
            extra={
                "notify_retry_reason": f"{reason}:not_retryable",
                "notify_resume_stage": resume_stage,
            },
            save=save,
        )
        return False, 0.0, "错误不可自动重试，请人工处理"

    if attempt_num >= DM_TASK_MAX_RETRY:
        _update_notify_flow_state(
            key,
            stage="retry_waiting",
            attempt=attempt_num,
            error=detail,
            error_code=code or "E_REPLY_FAILED",
            error_detail=detail or err_msg,
            retry_at=0,
            extra={
                "notify_retry_reason": f"{reason}:max_retry_reached",
                "notify_resume_stage": resume_stage,
            },
            save=save,
        )
        return False, 0.0, f"已达到最大重试次数({DM_TASK_MAX_RETRY})，请人工重试"

    backoff_sec = _resolve_notify_retry_backoff_sec(attempt_num)
    retry_at = time.time() + max(1, int(backoff_sec))
    _update_notify_flow_state(
        key,
        stage="retry_waiting",
        attempt=attempt_num,
        error=detail,
        error_code=code or "E_REPLY_FAILED",
        error_detail=detail or err_msg,
        retry_at=retry_at,
        extra={"notify_retry_reason": reason, "notify_resume_stage": resume_stage},
        save=save,
    )
    return True, retry_at, f"已加入重试队列，{int(backoff_sec)}s 后重试"


def _collect_due_notify_retry_items(limit=2):
    now = time.time()
    max_items = max(1, int(limit))
    items = []
    with data_lock:
        for row in pending_results:
            if row.get("source") != "通知页面":
                continue
            if bool(row.get("notify_replied", False)):
                continue
            if str(row.get("notify_flow_stage", "") or "").strip().lower() != "retry_waiting":
                continue
            retry_at = float(row.get("notify_retry_at", 0) or 0)
            if retry_at <= 0 or retry_at > now:
                continue
            items.append(dict(row))
            if len(items) >= max_items:
                break
    return items


def _process_notify_retry_queue(max_items=1):
    """后台自动处理到期的通知重试任务。"""
    due_items = _collect_due_notify_retry_items(limit=max_items)
    if not due_items:
        return 0

    done_count = 0
    for item in due_items:
        key = str(item.get("key", "") or "").strip()
        if not key:
            continue
        reply_text = str(item.get("notify_reply_text", "") or "").strip()
        dm_text = str(item.get("notify_dm_text", "") or "").strip()
        if not reply_text or not dm_text:
            _update_notify_flow_state(
                key,
                stage="retry_waiting",
                error="缺少重试模板：请手动在通知行重新选择回复与私信模板",
                error_code="E_MISSING_TEMPLATE",
                error_detail="missing notify_reply_text or notify_dm_text",
                retry_at=0,
                save=True,
            )
            continue

        try:
            current_attempt = int(item.get("notify_flow_attempt", 0) or 0) + 1
        except Exception:
            current_attempt = 1
        _, live_row = _find_pending_notify_item_by_key(key)
        resume_stage = _resolve_notify_resume_stage(live_row or item)
        _update_notify_flow_state(
            key,
            stage="reply_pending",
            attempt=current_attempt,
            error="",
            retry_at=0,
            extra={
                "notify_retry_reason": "auto_retry_execute",
                "notify_resume_stage": resume_stage,
            },
            save=True,
        )

        ok, err = send_notification_reply(item, reply_text, dm_message=dm_text)
        if ok:
            _record_reply_outcome(item.get("handle", ""), True, "")
            _mark_notify_reply_success(key, reply_text, dm_text, save=True)
            done_count += 1
            log_to_ui("success", f"✅ 自动重试成功: {item.get('handle', '')}")
            continue

        _record_reply_outcome(item.get("handle", ""), False, err or "")
        scheduled, _, schedule_msg = _schedule_notify_retry(
            key,
            err or "E_REPLY_FAILED: 自动重试失败",
            attempt=current_attempt,
            reason="auto_retry_queue",
            save=True,
        )
        if scheduled:
            log_to_ui("warn", f"⚠️ 自动重试失败，已重新排队: {item.get('handle', '')} - {schedule_msg}")
        else:
            log_to_ui("warn", f"⚠️ 自动重试失败，转人工处理: {item.get('handle', '')} - {schedule_msg}")

    return done_count


def _get_pending_notify_count():
    """返回当前待处理通知数量（粗略即可）。"""
    try:
        with data_lock:
            return sum(1 for r in pending_results if r.get("source") == "通知页面")
    except Exception:
        return 0


def _set_reply_flow_active(active):
    global reply_flow_active
    with reply_flow_state_lock:
        reply_flow_active = bool(active)


def _is_reply_flow_active():
    with reply_flow_state_lock:
        return bool(reply_flow_active)


def _clamp(v, low, high):
    return max(low, min(high, v))


def _get_humanize_multiplier():
    """根据模式与近期稳定性计算人类化延时倍率。"""
    base = max(0.85, float(HUMANIZE_BASE_MULTIPLIER))
    if headless_mode:
        base *= (1.0 + max(0.0, float(HUMANIZE_HEADLESS_EXTRA_MULTIPLIER)))
    try:
        with reply_metrics_lock:
            streak = int(reply_failure_streak)
    except Exception:
        streak = 0
    if streak > 0:
        base *= min(1.45, 1.0 + 0.07 * streak)
    return _clamp(base, 0.85, 2.8)


def _get_adaptive_reply_gap_factor():
    """计算回复节奏的动态倍率。>1 更慢，<1 更快。"""
    if not REPLY_ADAPTIVE_THROTTLE:
        return 1.0
    with reply_metrics_lock:
        outcomes = list(reply_outcome_recent)
        streak = int(reply_failure_streak)
    success_rate = (sum(outcomes) / len(outcomes)) if outcomes else 1.0
    queue_depth = _get_pending_notify_count()

    factor = 1.0
    if streak > 0:
        factor *= min(2.0, 1.0 + 0.16 * streak)
    if REPLY_ENABLE_ACCELERATION and len(outcomes) >= 8 and success_rate >= 0.9 and queue_depth >= 30 and streak == 0:
        # 仅在长队列且近期稳定时轻微提速，避免明显机器人节奏
        accel = _clamp(float(REPLY_QUEUE_ACCEL_FACTOR), 0.92, 1.0)
        factor *= accel
    return _clamp(factor, 0.92, 2.2)


def _check_reply_failure_budget(handle):
    """失败预算熔断已关闭：始终允许继续尝试，不做冷却拦截。"""
    return True, ""


def _reserve_notify_dm_user_slot(handle, task_key=""):
    """同一用户短时间内只允许一个私信任务，避免重复触发。"""
    handle_norm = normalize_handle(handle)
    if not handle_norm or DM_USER_COOLDOWN_SEC <= 0:
        return True, 0.0
    now = time.time()
    task_key_text = str(task_key or "").strip()
    with notify_dm_user_cooldown_lock:
        record = notify_dm_user_cooldown.get(handle_norm, {})
        next_ts = float(record.get("until", 0.0) or 0.0)
        owner_task = str(record.get("task_key", "") or "").strip()
        if next_ts > now and owner_task and owner_task != task_key_text:
            return False, max(0.0, next_ts - now)

        notify_dm_user_cooldown[handle_norm] = {
            "until": now + float(DM_USER_COOLDOWN_SEC),
            "task_key": task_key_text,
        }

        # 限制内存占用，顺便清理过期项
        if len(notify_dm_user_cooldown) > 2048:
            expired_handles = [
                h for h, meta in notify_dm_user_cooldown.items()
                if float((meta or {}).get("until", 0.0) or 0.0) <= now
            ]
            for h in expired_handles[:1024]:
                notify_dm_user_cooldown.pop(h, None)
    return True, 0.0


def _record_reply_outcome(handle, ok, err=""):
    """记录回复结果，供自适应节流和失败熔断使用。"""
    global reply_failure_streak
    handle_norm = normalize_handle(handle)
    now = time.time()
    err_text = str(err or "")
    with reply_metrics_lock:
        reply_outcome_recent.append(1 if ok else 0)
        if ok:
            reply_failure_streak = 0
            if handle_norm and handle_norm in reply_handle_failures:
                reply_handle_failures.pop(handle_norm, None)
            return

        reply_failure_streak += 1
        if not handle_norm:
            return
        record = reply_handle_failures.get(handle_norm, {})
        first_ts = float(record.get("first_ts", now))
        count = int(record.get("count", 0))
        if (now - first_ts) > REPLY_FAILURE_WINDOW_SEC:
            first_ts = now
            count = 0
        count += 1
        cooldown_until = float(record.get("cooldown_until", 0.0))
        if count >= max(1, REPLY_FAILURE_BUDGET_MAX):
            cooldown_until = now + max(60, REPLY_FAILURE_COOLDOWN_SEC)
        reply_handle_failures[handle_norm] = {
            "count": count,
            "first_ts": first_ts,
            "cooldown_until": cooldown_until,
            "last_err": err_text[:260],
        }


def _should_use_share_link_quick_path():
    """是否启用快速链接路径：只在长队列且近期稳定时启用。"""
    mode = str(SHARE_LINK_QUICK_PATH_MODE or "always").strip().lower()
    if mode == "off":
        return False
    if mode == "always":
        return True
    if not SHARE_LINK_QUICK_PATH:
        return False
    queue_depth = _get_pending_notify_count()
    if queue_depth < 16:
        return False
    with reply_metrics_lock:
        outcomes = list(reply_outcome_recent)
        streak = int(reply_failure_streak)
    if streak > 0:
        return False
    if len(outcomes) < 8:
        return False
    success_rate = sum(outcomes) / len(outcomes)
    return success_rate >= 0.9


def _throttle_reply_action_if_needed():
    """限制回复动作速率，降低账号风控概率。"""
    global last_reply_action_ts
    now = time.time()
    jitter_gap = random.uniform(REPLY_ACTION_GAP_MIN_SEC, REPLY_ACTION_GAP_MAX_SEC)
    jitter_gap *= _get_adaptive_reply_gap_factor()
    jitter_gap *= _get_humanize_multiplier()
    wait_sec = 0.0
    with reply_rate_limit_lock:
        elapsed = now - last_reply_action_ts
        if elapsed < jitter_gap:
            wait_sec = jitter_gap - elapsed
        if wait_sec > 0:
            time.sleep(wait_sec)
        last_reply_action_ts = time.time()
    if wait_sec > 0.25:
        log_to_ui("debug", f"🕒 发送前节流等待 {wait_sec:.2f}s（风控保护）")


def _throttle_dm_action_if_needed(stage_text="私信发送"):
    """限制私信发送节奏，避免短时间内固定频率动作。"""
    global last_dm_action_ts
    now = time.time()
    human_mult = _get_humanize_multiplier()
    jitter_gap = random.uniform(DM_ACTION_GAP_MIN_SEC, DM_ACTION_GAP_MAX_SEC) * human_mult
    wait_sec = 0.0
    with dm_rate_limit_lock:
        elapsed = now - last_dm_action_ts
        if elapsed < jitter_gap:
            wait_sec = jitter_gap - elapsed
        if wait_sec > 0:
            time.sleep(wait_sec)
        last_dm_action_ts = time.time()
    if wait_sec > 0.15:
        log_to_ui("debug", f"📨 {stage_text}前防抖等待 {wait_sec:.2f}s")
        log_headless_debug(f"{stage_text}节流完成，等待={wait_sec:.2f}s")


def _dm_humanized_idle(tab, low=0.08, high=0.28, stage_text="私信动作"):
    """私信流程的人类化随机停顿与轻微滚动。"""
    mult = _get_humanize_multiplier()
    low_v = max(0.02, float(low) * mult)
    high_v = max(low_v, float(high) * mult)
    if tab and random.random() < DM_HUMAN_SCROLL_CHANCE:
        delta = random.randint(-220, 220)
        if abs(delta) < 40:
            delta = 80 if delta >= 0 else -80
        try:
            tab.run_js("window.scrollBy(0, arguments[0]);", delta)
            time.sleep(random.uniform(0.04, 0.16))
            if random.random() < 0.35:
                tab.run_js("window.scrollBy(0, arguments[0]);", -int(delta * random.uniform(0.2, 0.6)))
        except Exception:
            pass
    pause = random.uniform(low_v, high_v)
    time.sleep(pause)
    log_headless_debug(f"{stage_text}随机停顿 {pause:.2f}s")


def _humanized_type_dm_text(tab, editor, dm_text):
    """整段输入私信文本（不使用分段打字）。"""
    text = str(dm_text or "")
    if not text:
        return False

    target = editor
    try:
        inner = editor.ele('css:div[role="textbox"][contenteditable="true"]', timeout=0)
        if inner and inner.states.is_displayed:
            target = inner
    except Exception:
        pass
    if target is editor:
        try:
            inner = editor.ele('css:[contenteditable="true"]', timeout=0)
            if inner and inner.states.is_displayed:
                target = inner
        except Exception:
            pass
    if target is editor:
        try:
            inner = editor.ele('css:textarea', timeout=0)
            if inner and inner.states.is_displayed:
                target = inner
        except Exception:
            pass

    try:
        target.click()
    except Exception:
        pass

    _dm_humanized_idle(tab, 0.06, 0.22, "私信输入前")
    try:
        target.input(text, clear=True)
        log_headless_debug(f"私信输入完成(整段模式, len={len(text)})")
        return True
    except Exception:
        return False


def _paste_dm_text_exact(tab, editor, dm_text):
    """把文本一次性写入编辑器（用于链接消息，避免分段输入导致内容变形）。"""
    text = str(dm_text or "")
    if not text:
        return False
    try:
        editor.click()
    except Exception:
        pass
    _dm_humanized_idle(tab, 0.04, 0.12, "私信粘贴前")
    try:
        ok = tab.run_js(
            """
            const root = arguments[0];
            const text = String(arguments[1] || '');
            if (!root) return false;
            const resolveTarget = (el) => {
              if (!el) return null;
              if (el.value !== undefined || el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
                return el;
              }
              const inner = el.querySelector(
                'div[role="textbox"][contenteditable="true"],[data-testid="dmComposerTextInput"] [contenteditable="true"],textarea[data-testid="dm-composer-textarea"],textarea'
              );
              if (inner) return inner;
              return null;
            };
            let el = resolveTarget(root);
            if (!el) return false;
            const dispatchInput = () => {
              try {
                el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText' }));
              } catch (e) {
                el.dispatchEvent(new Event('input', { bubbles: true }));
              }
              try { el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Enter', code: 'Enter' })); } catch (e) {}
              el.dispatchEvent(new Event('change', { bubbles: true }));
            };
            const setValue = (val) => {
              if (el.value !== undefined) {
                const proto = Object.getPrototypeOf(el);
                const desc = proto ? Object.getOwnPropertyDescriptor(proto, 'value') : null;
                if (desc && typeof desc.set === 'function') {
                  desc.set.call(el, val);
                } else {
                  el.value = val;
                }
              } else if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
                el.textContent = val;
              } else {
                el.textContent = val;
              }
              dispatchInput();
            };
            el.focus();
            setValue('');
            try {
              if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
                document.execCommand('insertText', false, text);
                dispatchInput();
              } else {
                setValue(text);
              }
            } catch (e) {
              setValue(text);
            }
            return true;
            """,
            editor,
            text,
        )
        if ok:
            log_headless_debug(f"私信输入完成(粘贴模式, len={len(text)})")
            return True
    except Exception:
        pass

    try:
        editor.input(text, clear=True)
        log_headless_debug(f"私信输入完成(input整段兜底, len={len(text)})")
        return True
    except Exception:
        return False


def _refresh_dm_editor_state(tab, editor, dm_text):
    """强制触发编辑器输入事件，促使发送按钮状态刷新。"""
    text = str(dm_text or "")
    if not text:
        return False
    try:
        return bool(tab.run_js(
            """
            const root = arguments[0];
            const text = String(arguments[1] || '');
            if (!root) return false;
            const resolveTarget = (el) => {
                if (!el) return null;
                if (el.value !== undefined || el.isContentEditable || el.getAttribute('contenteditable') === 'true') return el;
                return el.querySelector(
                    'div[role="textbox"][contenteditable="true"],[data-testid="dmComposerTextInput"] [contenteditable="true"],textarea[data-testid="dm-composer-textarea"],textarea'
                );
            };
            let el = resolveTarget(root);
            if (!el) return false;
            const dispatchInput = () => {
                try {
                    el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText'}));
                } catch (e) {
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                }
                el.dispatchEvent(new Event('change', {bubbles: true}));
            };
            const setValue = (val) => {
                if (el.value !== undefined) {
                    const proto = Object.getPrototypeOf(el);
                    const desc = proto ? Object.getOwnPropertyDescriptor(proto, 'value') : null;
                    if (desc && typeof desc.set === 'function') {
                        desc.set.call(el, val);
                    } else {
                        el.value = val;
                    }
                } else {
                    el.textContent = val;
                }
                dispatchInput();
            };
            el.focus();
            setValue(text + ' ');
            setValue(text);
            return true;
            """,
            editor,
            text,
        ))
    except Exception:
        return False


def _poke_dm_editor_events(tab, editor):
    """仅触发输入事件，不改写编辑器内容，避免链接被二次清空重填。"""
    if not tab or not editor:
        return False
    try:
        return bool(tab.run_js(
            """
            const el = arguments[0];
            if (!el) return false;
            try { el.focus(); } catch (e) {}
            try {
              el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText' }));
            } catch (e) {
              el.dispatchEvent(new Event('input', { bubbles: true }));
            }
            try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
            return true;
            """,
            editor,
        ))
    except Exception:
        return False


def _humanized_gap_between_dm_messages(tab):
    """两条私信之间增加随机间隔，避免固定节奏。"""
    _dm_humanized_idle(tab, 0.08, 0.26, "两条私信间")
    gap = random.uniform(DM_BETWEEN_MESSAGES_MIN_SEC, DM_BETWEEN_MESSAGES_MAX_SEC) * _get_humanize_multiplier()
    time.sleep(gap)
    log_to_ui("debug", f"📨 两条私信间隔 {gap:.2f}s")
    log_headless_debug(f"两条私信间隔完成 {gap:.2f}s")


def _build_dm_message_probes(text):
    """构建用于发送后确认的探针文本列表。"""
    raw = _sanitize_dm_message_text(text)
    if not raw:
        return []
    compact = _normalize_text_for_compare(raw)
    probes = []
    urls = re.findall(r"https?://\S+", compact, flags=re.IGNORECASE)
    for u in urls:
        u = u.strip()
        if u and u not in probes:
            probes.append(u.lower())
    if len(compact) >= 20:
        probes.append(compact[:48].lower())
        probes.append(compact[-36:].lower())
    else:
        probes.append(compact.lower())
    # 去重
    uniq = []
    seen = set()
    for p in probes:
        if not p or p in seen:
            continue
        seen.add(p)
        uniq.append(p)
    return uniq


def _count_dm_probe_occurrence(tab, probe_text):
    """统计探针文本在右侧当前会话消息区中的出现次数，排除左侧列表、草稿框和提示条。"""
    if not tab or not probe_text:
        return 0
    needle = str(probe_text).lower()
    try:
        convo_text = str(tab.run_js(
            """
            const isVisible = (el) => {
              if (!el) return false;
              const st = window.getComputedStyle(el);
              if (!st) return false;
              if (st.display === 'none' || st.visibility === 'hidden') return false;
              const r = el.getBoundingClientRect();
              return r.width > 0 && r.height > 0;
            };
            const root =
              document.querySelector('[data-testid="DmActivityViewport"]') ||
              document.querySelector('[data-testid="DmActivityContainer"]') ||
              document.querySelector('section[role="region"]');
            if (!root) return '';
            const clone = root.cloneNode(true);
            clone.querySelectorAll(
              'aside, header, [role="status"], [data-testid="dmComposerTextInput"], [data-testid="dmComposerTextInputRichTextInputContainer"], [data-testid="dmComposerTextInput_label"], [data-xm-dm-root], [data-xm-dm-target], [data-xm-dm-send-target], textarea, [role="textbox"], [contenteditable="true"], [contenteditable="plaintext-only"], input, button, [role="button"]'
            ).forEach((node) => {
              try { node.remove(); } catch (e) {}
            });
            const parts = [];
            const selectors = [
              '[data-testid="cellInnerDiv"]',
              '[data-testid="messageEntry"]',
              '[data-testid="DmScrollerContainer"] [dir="auto"]',
              '[data-testid="DmScrollerContainer"] article',
            ];
            for (const sel of selectors) {
              let nodes = [];
              try { nodes = Array.from(clone.querySelectorAll(sel)); } catch (e) { nodes = []; }
              for (const node of nodes) {
                if (!isVisible(node)) continue;
                const txt = String(node.innerText || node.textContent || '').trim();
                if (!txt) continue;
                parts.push(txt);
              }
            }
            if (!parts.length) {
              return String(clone.innerText || clone.textContent || '');
            }
            return parts.join('\n');
            """
        ) or "")
    except Exception:
        convo_text = ""
    if not convo_text:
        return 0
    return convo_text.lower().count(needle)


def _confirm_dm_message_sent(tab, before_counts, probes, wait_sec=1.15):
    """
    发送后确认消息是否落库：
    - 任一探针出现次数增加，视为已发送成功
    """
    if not probes:
        return False
    deadline = time.time() + max(0.2, float(wait_sec))
    while time.time() < deadline:
        for p in probes:
            prev = int(before_counts.get(p, 0))
            now = _count_dm_probe_occurrence(tab, p)
            if now > prev:
                return True
        time.sleep(0.1)
    return False


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
    """
    尝试清理浏览器原生提示框（alert/confirm/prompt）。
    兼容不同 DrissionPage 版本的 handle_alert 参数签名。
    """
    handler = getattr(tab, "handle_alert", None)
    if not callable(handler):
        return 0

    handled_count = 0
    last_prompt_text = ""
    for _ in range(max_rounds):
        result = None
        called = False
        for kwargs in (
            {"accept": True, "timeout": 0.6},
            {"accept": True},
            {"ok": True, "timeout": 0.6},
            {"ok": True},
            {"timeout": 0.6},
            {},
        ):
            try:
                result = handler(**kwargs)
                called = True
                break
            except TypeError:
                continue
            except Exception as e:
                # 某些版本在无提示框时会直接抛错，按“未命中提示框”处理
                if not _is_unhandled_prompt_error(e):
                    called = True
                    result = False
                    break
                result = False
                called = True
                break
        if not called:
            # 兼容少量版本仅支持位置参数
            for args in ((True, 0.6), (True,), tuple()):
                try:
                    result = handler(*args)
                    called = True
                    break
                except TypeError:
                    continue
                except Exception as e:
                    if not _is_unhandled_prompt_error(e):
                        called = True
                        result = False
                        break
                    result = False
                    called = True
                    break
        if not called:
            break

        if isinstance(result, str):
            last_prompt_text = result.strip()

        if result not in (None, False, "", 0):
            handled_count += 1
            time.sleep(0.08)
            continue
        break
    if handled_count > 0 and last_prompt_text:
        log_headless_debug(f"提示框内容: {last_prompt_text[:160]}")
    return handled_count


def _install_headless_dialog_guard(tab):
    """无头模式下注入 JS，对页面 alert/confirm/prompt 做无阻塞兜底。"""
    if not headless_mode:
        return False
    try:
        return bool(tab.run_js(
            """
            (() => {
              if (window.__xmonDialogGuardInstalled) return true;
              window.__xmonDialogGuardInstalled = true;
              window.__xmonDialogGuardLogs = [];
              const pushLog = (type, msg) => {
                try {
                  window.__xmonDialogGuardLogs.push({
                    t: Date.now(),
                    type,
                    msg: String(msg || '')
                  });
                  if (window.__xmonDialogGuardLogs.length > 20) {
                    window.__xmonDialogGuardLogs.shift();
                  }
                } catch (e) {}
              };
              window.alert = (msg) => { pushLog('alert', msg); return true; };
              window.confirm = (msg) => { pushLog('confirm', msg); return true; };
              window.prompt = (msg, defVal) => {
                pushLog('prompt', msg);
                return (defVal === undefined || defVal === null) ? '' : String(defVal);
              };
              // 屏蔽 beforeunload 触发的原生确认框（无头环境高发）
              try { window.onbeforeunload = null; } catch (e) {}
              try { document.onbeforeunload = null; } catch (e) {}
              const _rawWinAdd = window.addEventListener.bind(window);
              window.addEventListener = function(type, listener, options) {
                if (String(type || '').toLowerCase() === 'beforeunload') {
                  pushLog('beforeunload_blocked', 'window.addEventListener');
                  return;
                }
                return _rawWinAdd(type, listener, options);
              };
              const _rawDocAdd = document.addEventListener.bind(document);
              document.addEventListener = function(type, listener, options) {
                if (String(type || '').toLowerCase() === 'beforeunload') {
                  pushLog('beforeunload_blocked', 'document.addEventListener');
                  return;
                }
                return _rawDocAdd(type, listener, options);
              };
              return true;
            })();
            """
        ))
    except Exception:
        return False


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
    """通过 CSS 选择器在当前文档重新定位并点击元素，避免跨 JS world 的句柄失效。"""
    if not tab or not selectors:
        return False
    css_list = []
    for sel in (selectors or []):
        s = str(sel or "").strip()
        if not s:
            continue
        if s.startswith("css:"):
            s = s[4:]
        if not s:
            continue
        css_list.append(s)
    if not css_list:
        return False
    try:
        clicked = tab.run_js(
            """
            const selectors = arguments[0] || [];
            const isVisible = (el) => {
              if (!el) return false;
              const st = window.getComputedStyle(el);
              if (!st) return false;
              if (st.display === 'none' || st.visibility === 'hidden') return false;
              const r = el.getBoundingClientRect();
              return r.width > 0 && r.height > 0;
            };
            for (const s of selectors) {
              let nodes = [];
              try { nodes = Array.from(document.querySelectorAll(s)); } catch (e) { nodes = []; }
              for (const el of nodes) {
                if (!isVisible(el)) continue;
                if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                try { el.click(); return true; } catch (e) {}
              }
            }
            return false;
            """,
            css_list,
        )
        return bool(clicked)
    except Exception:
        return False


def _click_with_prompt_guard(tab, element, action_name, refetch_selectors=None):
    """点击元素时自动处理未处理提示框并重试。"""
    last_err = None
    max_retry = REPLY_PROMPT_GUARD_MAX_RETRY + (1 if headless_mode else 0)
    for attempt in range(max_retry):
        _prepare_reply_prompt_guard(tab, f"{action_name}前")
        try:
            element.click()
            return True, ""
        except Exception as e_click:
            last_err = e_click
            if _is_unhandled_prompt_error(e_click):
                _prepare_reply_prompt_guard(tab, f"{action_name}重试")
                time.sleep(random.uniform(0.15, 0.35))
                continue
            if refetch_selectors and _is_cross_world_click_error(e_click):
                if _click_first_actionable_by_selectors(tab, refetch_selectors):
                    return True, ""
            try:
                if refetch_selectors and _click_first_actionable_by_selectors(tab, refetch_selectors):
                    return True, ""
                # 兜底：仅点击当前文档焦点元素，避免跨世界 objectId
                focused_clicked = bool(tab.run_js(
                    """
                    const el = document.activeElement;
                    if (!el) return false;
                    if (el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
                    try { el.click(); return true; } catch (e) { return false; }
                    """
                ))
                if focused_clicked:
                    return True, ""
            except Exception as e_js:
                last_err = e_js
                if _is_unhandled_prompt_error(e_js):
                    _prepare_reply_prompt_guard(tab, f"{action_name}JS重试")
                    time.sleep(random.uniform(0.15, 0.35))
                    continue
                if refetch_selectors and _is_cross_world_click_error(e_js):
                    if _click_first_actionable_by_selectors(tab, refetch_selectors):
                        return True, ""
                break
    return False, f"{action_name}失败: {last_err}"


def _reply_humanized_idle(tab, low=0.16, high=0.46, stage_text="回复步骤"):
    """回复流程随机慢速等待，并在等待前后主动清理提示框。"""
    _prepare_reply_prompt_guard(tab, f"{stage_text}前")
    mult = _get_humanize_multiplier()
    low_v = max(0.05, float(low) * mult)
    high_v = max(low_v, float(high) * mult)
    pause = random.uniform(low_v, high_v)
    if headless_mode:
        pause += random.uniform(0.08, 0.26)
    time.sleep(pause)
    _prepare_reply_prompt_guard(tab, f"{stage_text}后")
    log_headless_debug(f"{stage_text}等待 {pause:.2f}s")


def _is_dm_unavailable_cached(handle):
    """检查某用户私信不可达缓存。"""
    handle_norm = normalize_handle(handle)
    if not handle_norm:
        return False
    now = time.time()
    with dm_unavailable_cache_lock:
        expire_ts = dm_unavailable_cache.get(handle_norm, 0.0)
        if expire_ts > now:
            return True
        if handle_norm in dm_unavailable_cache:
            dm_unavailable_cache.pop(handle_norm, None)
    return False


def _mark_dm_unavailable(handle):
    handle_norm = normalize_handle(handle)
    if not handle_norm:
        return
    with dm_unavailable_cache_lock:
        dm_unavailable_cache[handle_norm] = time.time() + DM_UNAVAILABLE_CACHE_TTL_SEC


def _clear_dm_unavailable_cache(handle):
    handle_norm = normalize_handle(handle)
    if not handle_norm:
        return
    with dm_unavailable_cache_lock:
        dm_unavailable_cache.pop(handle_norm, None)


def _get_status_link_from_item(item, matched_status_handle=None, matched_status_id=None):
    status_handle = normalize_handle(
        matched_status_handle or item.get("status_handle") or item.get("handle") or ""
    )
    status_id = _pick_best_status_id(
        matched_status_id or "",
        item.get("status_id", ""),
        item.get("status_url", ""),
        item.get("key", ""),
    )
    raw_url = str(item.get("status_url", "")).strip()
    return _normalize_dm_share_link(raw_url, status_id=status_id, status_handle=status_handle, fallback_url=raw_url)


def _click_share_copy_link(tab, target_article, fallback_link):
    """在目标卡片点击分享->复制链接，返回可用链接（优先真实复制，失败回退）。"""
    # 优先从当前卡片直接提取链接，减少使用脏回退数据概率
    try:
        anchors = target_article.eles('tag:a', timeout=0.4)
    except Exception:
        anchors = []
    article_link = ""
    for a in anchors:
        try:
            href = (a.attr('href') or '').strip()
        except Exception:
            href = ""
        if not href:
            continue
        if "/status/" not in href:
            continue
        article_link = _normalize_dm_share_link(href, fallback_url=fallback_link)
        if article_link:
            break
    if article_link:
        fallback_link = article_link

    share_btn = None
    share_selectors = [
        'css:button[aria-label*="分享"]',
        'css:button[aria-label*="Share"]',
        'css:[data-testid="share"]',
    ]
    for selector in share_selectors:
        try:
            share_btn = target_article.ele(selector, timeout=0.8)
            if share_btn and share_btn.states.is_displayed:
                break
        except Exception:
            continue
    if not share_btn:
        return fallback_link, "未找到分享按钮"

    clicked_share, share_click_err = _click_with_prompt_guard(tab, share_btn, "点击分享按钮")
    if not clicked_share:
        return fallback_link, share_click_err
    _ = _wait_first_visible(tab, ['css:[role="menuitem"]', 'css:div[role="menu"]'], timeout=1.4, poll=0.1)

    copy_btn = None
    copy_keyword_list = ["复制链接", "copy link", "link to post", "link to tweet"]
    copy_selectors = ['css:[role="menuitem"]', 'tag:button', 'css:div[role="button"]', 'tag:span']
    for selector in copy_selectors:
        try:
            candidates = tab.eles(selector, timeout=0.8)
        except Exception:
            candidates = []
        for cand in candidates:
            try:
                txt = (cand.text or "").strip().lower()
                if txt and any(k in txt for k in copy_keyword_list):
                    copy_btn = cand
                    break
            except Exception:
                continue
        if copy_btn:
            break

    if not copy_btn:
        return fallback_link, "未找到复制链接按钮"

    clicked_copy, copy_click_err = _click_with_prompt_guard(tab, copy_btn, "点击复制链接按钮")
    if not clicked_copy:
        return fallback_link, copy_click_err

    # X 菜单复制通常写入系统剪贴板，自动读取常被权限限制；这里稳妥回退为已识别链接
    return fallback_link, ""


def _handle_dm_passcode_prompt(tab):
    """处理 X 私信 Enter Passcode 页面。成功通过后返回 True。"""
    global dm_passcode_warmed
    if not tab:
        return False

    passcode_digits = re.sub(r"\D+", "", str(DM_PASSCODE or ""))
    if len(passcode_digits) < 4:
        return False
    passcode_digits = passcode_digits[:8]

    def _is_passcode_page():
        def _is_visible_passcode_ui():
            try:
                state = tab.run_js(
                    """
                    const isVisible = (el) => {
                      if (!el) return false;
                      const st = window.getComputedStyle(el);
                      if (!st) return false;
                      if (st.display === 'none' || st.visibility === 'hidden') return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width > 0 && rect.height > 0;
                    };
                    const norm = (s) => String(s || '').replace(/\\s+/g, ' ').trim().toLowerCase();

                    const nodes = Array.from(document.querySelectorAll('h1,h2,h3,p,span,div,button,a'));
                    let hasEnter = false;
                    let hasForgot = false;
                    for (const el of nodes) {
                      if (!isVisible(el)) continue;
                      const txt = norm(el.innerText || el.textContent || '');
                      if (!txt) continue;
                      if (txt.includes('enter passcode') || txt.includes('输入口令') || txt.includes('输入密码')) {
                        hasEnter = true;
                      }
                      if (txt.includes('forgot passcode') || txt.includes('忘记口令') || txt.includes('忘记密码')) {
                        hasForgot = true;
                      }
                      if (hasEnter && hasForgot) break;
                    }

                    const inputCandidates = Array.from(document.querySelectorAll(
                      'input[type="password"],input[type="tel"],input[inputmode="numeric"],input[autocomplete="one-time-code"],input[maxlength="1"],[data-testid*="passcode"] input,[data-testid*="pin"] input'
                    ));
                    const visibleInputs = inputCandidates.filter((el) => isVisible(el) && !el.disabled).length;
                    const allInputs = inputCandidates.filter((el) => !el.disabled).length;

                    return {
                      visible: Boolean(hasEnter && (hasForgot || visibleInputs >= 1 || allInputs >= 4)),
                      hasEnter: Boolean(hasEnter),
                      hasForgot: Boolean(hasForgot),
                      visibleInputs: Number(visibleInputs),
                      allInputs: Number(allInputs),
                    };
                    """
                ) or {}
                return bool(state.get("visible", False))
            except Exception:
                return False

        try:
            now_url = str(tab.url or "").lower()
        except Exception:
            now_url = ""
        if "/i/chat/pin/recovery" in now_url or "/i/chat/pin" in now_url:
            return True
        # 避免误判：仅在可见口令 UI 存在时才认定为口令页
        return _is_visible_passcode_ui()

    def _wait_passcode_cleared(timeout_sec=8.6):
        deadline = time.time() + max(1.0, float(timeout_sec))
        while time.time() < deadline:
            _wait_document_ready(tab, timeout=1.2)
            if not _is_passcode_page():
                return True
            time.sleep(random.uniform(0.18, 0.36))
        return False

    def _fallback_type_passcode_via_body():
        """兜底：向当前焦点逐位输入数字，兼容圆圈口令 UI。"""
        try:
            body = tab.ele('tag:body', timeout=0.8)
        except Exception:
            body = None
        if not body:
            return False
        typed = 0
        for ch in passcode_digits:
            if not ch.isdigit():
                continue
            try:
                body.input(ch, clear=False)
                typed += 1
            except Exception:
                try:
                    tab.run_js(
                        """
                        const d = String(arguments[0] || '');
                        const t = document.activeElement || document.body;
                        if (!t) return false;
                        const ev = { key: d, code: 'Digit' + d, which: Number(d), keyCode: Number(d), bubbles: true };
                        try { t.dispatchEvent(new KeyboardEvent('keydown', ev)); } catch (e) {}
                        try { t.dispatchEvent(new KeyboardEvent('keypress', ev)); } catch (e) {}
                        try {
                          if (t.isContentEditable || t.getAttribute('contenteditable') === 'true') {
                            document.execCommand('insertText', false, d);
                          } else if (t.value !== undefined) {
                            t.value = String(t.value || '') + d;
                            t.dispatchEvent(new Event('input', { bubbles: true }));
                            t.dispatchEvent(new Event('change', { bubbles: true }));
                          }
                        } catch (e) {}
                        try { t.dispatchEvent(new KeyboardEvent('keyup', ev)); } catch (e) {}
                        return true;
                        """,
                        ch
                    )
                    typed += 1
                except Exception:
                    continue
            time.sleep(random.uniform(0.08, 0.22))
        return typed >= 4

    def _fill_passcode_once():
        try:
            result = tab.run_js(
                """
                const code = String(arguments[0] || '');
                const isVisible = (el) => {
                    if (!el) return false;
                    const st = window.getComputedStyle(el);
                    if (!st) return false;
                    const hidden = st.display === 'none' || st.visibility === 'hidden';
                    if (hidden) return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };
                const dispatchInput = (el) => {
                    try {
                        el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText' }));
                    } catch (e) {
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                };
                const setValue = (el, val) => {
                    if (!el) return;
                    el.focus();
                    if (el.value !== undefined) {
                        const proto = Object.getPrototypeOf(el);
                        const desc = proto ? Object.getOwnPropertyDescriptor(proto, 'value') : null;
                        if (desc && typeof desc.set === 'function') {
                            desc.set.call(el, val);
                        } else {
                            el.value = val;
                        }
                    } else if (el.textContent !== undefined) {
                        el.textContent = val;
                    }
                    dispatchInput(el);
                };

                const inputSelectors = [
                    'input[type="password"]',
                    'input[type="tel"]',
                    'input[inputmode="numeric"]',
                    'input[autocomplete="one-time-code"]',
                    'input[name*="passcode"]',
                    'input[name*="pin"]',
                    '[data-testid*="passcode"] input',
                    '[data-testid*="Passcode"] input',
                    '[data-testid*="pin"] input',
                    '[data-testid*="Pin"] input',
                ];
                const nodes = [];
                const allInputs = [];
                const seen = new Set();
                for (const s of inputSelectors) {
                    for (const el of Array.from(document.querySelectorAll(s))) {
                        if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                        if (!seen.has(el)) allInputs.push(el);
                        if (!isVisible(el)) continue;
                        if (seen.has(el)) continue;
                        seen.add(el);
                        nodes.push(el);
                    }
                }

                let filled = 0;
                const singleInputs = (nodes.length ? nodes : allInputs).filter((el) => {
                    const ml = Number(el.maxLength || el.getAttribute('maxlength') || 0);
                    return ml === 1;
                });
                if (singleInputs.length >= 4) {
                    for (let i = 0; i < Math.min(code.length, singleInputs.length); i += 1) {
                        setValue(singleInputs[i], code[i]);
                    }
                    filled = Math.min(code.length, singleInputs.length);
                } else if (nodes.length > 0) {
                    setValue(nodes[0], code);
                    filled = code.length;
                } else if (allInputs.length > 0) {
                    setValue(allInputs[0], code);
                    filled = code.length;
                }

                // 圆圈口令页兜底：先尝试点击数字按钮（每次点一位）
                if (filled < 4) {
                    const clickDigitBtn = (digit) => {
                        const directSelectors = [
                            `button[aria-label="${digit}"]`,
                            `[role="button"][aria-label="${digit}"]`,
                            `button[data-value="${digit}"]`,
                            `[role="button"][data-value="${digit}"]`,
                        ];
                        for (const s of directSelectors) {
                            const cands = Array.from(document.querySelectorAll(s));
                            for (const el of cands) {
                                if (!isVisible(el)) continue;
                                if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                                try { el.click(); } catch (e) {}
                                return true;
                            }
                        }

                        const allBtn = Array.from(document.querySelectorAll('button, [role="button"]'));
                        for (const el of allBtn) {
                            if (!isVisible(el)) continue;
                            if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                            const txt = String(el.innerText || el.textContent || '').trim();
                            const aria = String(el.getAttribute('aria-label') || '').trim();
                            const title = String(el.getAttribute('title') || '').trim();
                            if (txt === digit || aria === digit || title === digit) {
                                try { el.click(); } catch (e) {}
                                return true;
                            }
                        }
                        return false;
                    };

                    let keypadClicked = 0;
                    for (const ch of code.split('')) {
                        if (!/\\d/.test(ch)) continue;
                        if (clickDigitBtn(ch)) keypadClicked += 1;
                    }
                    if (keypadClicked >= 4) filled = Math.max(filled, keypadClicked);
                }

                // 圆圈口令页兜底：按钮点击仍失败时，改用全局逐位键盘输入
                if (filled < 4) {
                    const focusSelectors = [
                        '[data-testid*="passcode"] input',
                        '[data-testid*="Passcode"] input',
                        '[data-testid*="passcode"]',
                        '[data-testid*="Passcode"]',
                        '[data-testid*="pin"] input',
                        '[data-testid*="Pin"] input',
                        '[data-testid*="pin"]',
                        '[data-testid*="Pin"]',
                        'input[inputmode="numeric"]',
                        'input[type="tel"]',
                        'main',
                        'body'
                    ];
                    let focusEl = null;
                    for (const s of focusSelectors) {
                        const cands = Array.from(document.querySelectorAll(s));
                        for (const el of cands) {
                            if (!el) continue;
                            if (!isVisible(el) && s !== 'body') continue;
                            focusEl = el;
                            break;
                        }
                        if (focusEl) break;
                    }
                    try { if (focusEl) focusEl.click(); } catch (e) {}
                    try { if (focusEl) focusEl.focus(); } catch (e) {}

                    const sendDigit = (digit) => {
                        const target = document.activeElement || focusEl || document.body;
                        if (!target) return;
                        const evInit = { key: digit, code: 'Digit' + digit, which: Number(digit), keyCode: Number(digit), bubbles: true };
                        try { target.dispatchEvent(new KeyboardEvent('keydown', evInit)); } catch (e) {}
                        try { target.dispatchEvent(new KeyboardEvent('keypress', evInit)); } catch (e) {}
                        if (target.value !== undefined) {
                            const cur = String(target.value || '');
                            setValue(target, cur + digit);
                        } else if (target.isContentEditable || target.getAttribute('contenteditable') === 'true') {
                            try {
                                document.execCommand('insertText', false, digit);
                            } catch (e) {
                                target.textContent = String(target.textContent || '') + digit;
                            }
                            dispatchInput(target);
                        } else {
                            try {
                                document.dispatchEvent(new KeyboardEvent('keydown', evInit));
                                document.dispatchEvent(new KeyboardEvent('keypress', evInit));
                                document.dispatchEvent(new KeyboardEvent('keyup', evInit));
                            } catch (e) {}
                        }
                        try { target.dispatchEvent(new KeyboardEvent('keyup', evInit)); } catch (e) {}
                    };

                    for (const ch of code.split('')) {
                        if (!/\\d/.test(ch)) continue;
                        sendDigit(ch);
                    }

                    // 再尝试读取填充结果
                    let filledCount = 0;
                    for (const el of (singleInputs.length ? singleInputs : allInputs)) {
                        try {
                            const v = String((el.value !== undefined) ? (el.value || '') : (el.textContent || '')).trim();
                            if (v) filledCount += Math.min(v.length, 1);
                        } catch (e) {}
                    }
                    if (filledCount >= 4) filled = Math.max(filled, 4);
                }

                let clicked = false;
                const btnSelectors = [
                    'button[type="submit"]',
                    '[data-testid*="confirm"]',
                    '[data-testid*="Confirm"]',
                    '[data-testid*="continue"]',
                    '[data-testid*="Continue"]',
                    'button',
                    '[role="button"]',
                ];
                const btnKeywords = ['continue', 'confirm', 'submit', 'verify', 'unlock', 'next', '继续', '确认', '提交', '验证', '下一步', '解锁'];
                for (const s of btnSelectors) {
                    for (const el of Array.from(document.querySelectorAll(s))) {
                        if (!isVisible(el)) continue;
                        if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                        const txt = String((el.innerText || el.textContent || '')).trim().toLowerCase();
                        if (!txt) continue;
                        if (!btnKeywords.some((k) => txt.includes(k))) continue;
                        el.click();
                        clicked = true;
                        break;
                    }
                    if (clicked) break;
                }

                try {
                    const ae = document.activeElement;
                    if (ae) {
                        ae.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
                        ae.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
                    }
                } catch (e) {}

                return { filled, clicked, inputCount: allInputs.length };
                """,
                passcode_digits
            ) or {}
            return {
                "ok": int(result.get("filled", 0)) >= 4,
                "filled": int(result.get("filled", 0)),
                "clicked": bool(result.get("clicked", False)),
                "inputCount": int(result.get("inputCount", 0)),
            }
        except Exception:
            return {"ok": False, "filled": 0, "clicked": False, "inputCount": 0}

    if not _is_passcode_page():
        return False

    log_to_ui("warn", "🔐 检测到 Enter Passcode，尝试自动输入口令...")
    for attempt in range(1, 4):
        _prepare_reply_prompt_guard(tab, f"口令页处理{attempt}")
        fill_result = _fill_passcode_once()
        filled_ok = bool(fill_result.get("ok", False))
        try:
            now_url = str(tab.url or "")
        except Exception:
            now_url = ""
        log_headless_debug(
            f"Enter Passcode尝试{attempt}: filled={fill_result.get('filled', 0)}, "
            f"clicked={fill_result.get('clicked', False)}, inputCount={fill_result.get('inputCount', 0)}, "
            f"ok={filled_ok}, url={now_url}"
        )
        if filled_ok and _wait_passcode_cleared(timeout_sec=8.8):
            with dm_passcode_lock:
                dm_passcode_warmed = True
            log_to_ui("info", "🔓 Enter Passcode 自动通过，私信通道已恢复")
            return True

        if not filled_ok:
            typed_ok = _fallback_type_passcode_via_body()
            log_headless_debug(f"Enter Passcode尝试{attempt}: body_input_fallback={typed_ok}")
            if typed_ok and _wait_passcode_cleared(timeout_sec=8.8):
                with dm_passcode_lock:
                    dm_passcode_warmed = True
                log_to_ui("info", "🔓 Enter Passcode 自动通过，私信通道已恢复")
                return True

        # 仍未通过时，短暂停后进入下一轮
        time.sleep(random.uniform(0.25, 0.55))

    session_state = _read_dm_session_state(tab, "")
    _capture_runtime_diagnostic(
        tab,
        "dm_passcode_prompt_blocking",
        err="Enter Passcode 自动处理失败",
        selectors=[
            'css:input[type="password"]',
            'css:input[type="tel"]',
            'css:input[inputmode="numeric"]',
            'css:input[autocomplete="one-time-code"]',
            'css:[role="dialog"]',
            'css:[role="alertdialog"]',
            'css:button[type="submit"]',
        ],
        extra={"url": str(getattr(tab, "url", "") or ""), "passcode_len": len(passcode_digits)}
    )
    log_to_ui("warn", "⚠️ Enter Passcode 自动输入未通过，请检查口令或手工输入一次")
    return False


def _warmup_dm_passcode_if_needed(tab, force=False):
    """在会话内预热一次 Enter Passcode，避免首条私信被拦截。"""
    passcode_digits = re.sub(r"\D+", "", str(DM_PASSCODE or ""))
    if len(passcode_digits) < 4:
        return
    if not tab:
        return

    global dm_passcode_warmed
    with dm_passcode_lock:
        if dm_passcode_warmed and not force:
            return

    try:
        now_url = str(tab.url or "")
    except Exception:
        now_url = ""

    def _is_passcode_blocking_now():
        try:
            u = str(tab.url or "").lower()
        except Exception:
            u = ""
        if "/i/chat/pin/recovery" in u or "/i/chat/pin" in u:
            return True
        try:
            state = tab.run_js(
                """
                const isVisible = (el) => {
                  if (!el) return false;
                  const st = window.getComputedStyle(el);
                  if (!st) return false;
                  if (st.display === 'none' || st.visibility === 'hidden') return false;
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                };
                const norm = (s) => String(s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                let hasEnter = false;
                let hasForgot = false;
                for (const el of Array.from(document.querySelectorAll('h1,h2,h3,p,span,div,a,button'))) {
                  if (!isVisible(el)) continue;
                  const txt = norm(el.innerText || el.textContent || '');
                  if (!txt) continue;
                  if (txt.includes('enter passcode') || txt.includes('输入口令') || txt.includes('输入密码')) hasEnter = true;
                  if (txt.includes('forgot passcode') || txt.includes('忘记口令') || txt.includes('忘记密码')) hasForgot = true;
                  if (hasEnter && hasForgot) break;
                }
                return Boolean(hasEnter && hasForgot);
                """
            )
        except Exception:
            state = False
        return bool(state)

    try:
        # 预热时进入消息页，让口令页尽早出现并完成一次输入
        if "/i/chat/" not in now_url and "/messages" not in now_url:
            tab.get("https://x.com/messages")
            _wait_document_ready(tab, timeout=6.0)
            time.sleep(random.uniform(0.3, 0.7))

        handled = _handle_dm_passcode_prompt(tab)
        if handled:
            with dm_passcode_lock:
                dm_passcode_warmed = True
            return

        # 未出现口令页视为预热完成；仍被口令页拦截则保持未预热状态
        if not _is_passcode_blocking_now():
            with dm_passcode_lock:
                dm_passcode_warmed = True
        else:
            log_to_ui("warn", "⚠️ 口令预热未通过，后续私信流程将继续尝试自动输入")
    except Exception as e:
        log_headless_debug(f"口令预热异常: {e}")


def _open_dm_editor_for_handle(tab, handle, ignore_cached_unavailable=False):
    """打开某用户私信编辑框，返回编辑框元素。"""
    handle_norm = normalize_handle(handle)
    if not handle_norm:
        return None, "缺少目标用户handle"
    if (not ignore_cached_unavailable) and _is_dm_unavailable_cached(handle_norm):
        return None, "该用户当前不可私信（缓存命中）"
    entry_path = "init"
    entry_stage = "init"

    dm_btn_selectors = [
        'css:[data-testid="sendDMFromProfile"]',
        'css:[data-testid="sendDM"]',
        'css:button[data-testid="sendDMFromProfile"]',
        'css:button[data-testid="sendDM"]',
        'css:button[aria-label*="私信"]',
        'css:button[aria-label*="发消息"]',
        'css:button[aria-label*="Message"]',
    ]
    editor = None
    dm_btn_seen = False
    profile_opened_rounds = 0
    editor_selectors = [
        'css:textarea[data-testid="dm-composer-textarea"]',
        'css:textarea[placeholder="Message"]',
        'css:textarea[placeholder*="消息"]',
        'css:[data-testid="dmComposerTextInput"] [contenteditable]:not([contenteditable="false"])',
        'css:[data-testid="dmComposerTextInput"] [contenteditable="true"]',
        'css:div[role="textbox"][contenteditable]:not([contenteditable="false"])',
        'css:div[role="textbox"][contenteditable="true"]',
        'css:[data-testid="dmComposerTextInput"]',
    ]
    cannot_dm_keywords = [
        "cannot send direct messages",
        "can't be messaged",
        "unable to message",
        "you can’t message this account",
        "该用户无法接收私信",
        "无法向该用户发送私信",
        "不能给该用户发私信",
        "无法发送私信",
    ]

    def _get_body_text():
        try:
            return (tab.ele('tag:body', timeout=0.6).text or "").lower()
        except Exception:
            return ""

    def _has_cannot_dm_hint():
        body = _get_body_text()
        return any(k in body for k in cannot_dm_keywords)

    def _find_dm_btn():
        return _wait_first_actionable(tab, dm_btn_selectors, timeout=1.8, poll=0.1)

    def _is_valid_dm_editor(cand):
        try:
            ok = tab.run_js(
                """
                const el = arguments[0];
                const rejectOverlay = !!arguments[1];
                if (!el) return false;
                const low = (s) => String(s || '').toLowerCase();
                const attrText = [
                  el.getAttribute('aria-label'),
                  el.getAttribute('placeholder'),
                  el.getAttribute('data-testid'),
                  el.getAttribute('name')
                ].map(low).join(' ');
                const rejectKeys = [
                  'search', '搜索', 'people', 'person', 'group', 'groups',
                  'recipient', '收件人', 'to', 'new message', '新消息'
                ];
                if (rejectKeys.some((k) => attrText.includes(k))) return false;
                const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : { top: 0, width: 0, height: 0 };
                const url = low(window.location.href || '');
                if (url.includes('/i/chat/')) return true;
                const root = el.closest('[role="dialog"]') || document;
                const rootText = low((root.innerText || root.textContent || '').slice(0, 800));
                const hasSearchScene = (
                  rootText.includes('搜索私信') ||
                  rootText.includes('创建一条私信') ||
                  rootText.includes('创建私信') ||
                  rootText.includes('new message') ||
                  rootText.includes('search direct messages') ||
                  rootText.includes('recipient')
                );
                const hasComposer = !!root.querySelector(
                  '[data-testid="dmComposerTextInput"],textarea[data-testid="dm-composer-textarea"]'
                );
                const hasSend = !!root.querySelector(
                  '[data-testid="dm-composer-send-button"],[data-testid="dmComposerSendButton"],button[data-testid*="dm-composer-send"]'
                );
                if (rejectOverlay) {
                  // 新私信搜索浮层：只允许进入带发送区的真实会话编辑器
                  if (hasSearchScene && !hasSend) return false;
                  // 顶部搜索输入框通常位于页面上半区且没有发送区，过滤掉
                  if (!hasSend && rect && Number(rect.top || 0) < (window.innerHeight * 0.45)) return false;
                }
                if (hasComposer) return true;
                if (hasSend) return true;
                return false;
                """,
                cand,
                DM_REJECT_NEW_MESSAGE_OVERLAY,
            )
            return bool(ok)
        except Exception:
            return False

    def _find_editor(timeout_each=2.5):
        for selector in editor_selectors:
            try:
                cand = tab.ele(selector, timeout=timeout_each)
                if cand and cand.states.is_displayed and _is_valid_dm_editor(cand):
                    return cand
            except Exception:
                continue
        return None

    def _wait_editor_or_closed(timeout_sec=3.2):
        deadline = time.time() + max(0.6, float(timeout_sec))
        while time.time() < deadline:
            if _has_cannot_dm_hint():
                return None, "closed"
            editor_now = _find_editor(timeout_each=0.5)
            if editor_now:
                return editor_now, ""
            time.sleep(0.08)
        return None, ""

    def _try_open_dm_via_direct_compose():
        """优先走 messages/compose 直达会话，避免资料页按钮点击后落到消息列表小窗。"""
        nonlocal entry_path, entry_stage
        compose_urls = ["https://x.com/messages/compose", "https://x.com/messages"]
        recipient_input_selectors = [
            'css:[role="dialog"] input[placeholder*="Search"]',
            'css:[role="dialog"] input[placeholder*="搜索"]',
            'css:[role="dialog"] input[aria-label*="Search"]',
            'css:[role="dialog"] input[aria-label*="搜索"]',
            'css:[data-testid*="typeahead"] input',
            'css:[data-testid*="Typeahead"] input',
            'css:main input[placeholder*="Search"]',
            'css:main input[placeholder*="搜索"]',
        ]
        next_btn_selectors = [
            'css:button[data-testid="nextButton"]',
            'css:[role="dialog"] [data-testid*="next"]',
            'css:[data-testid*="DM"] [data-testid*="next"]',
            'css:[role="dialog"] button[aria-label*="Next"]',
            'css:[role="dialog"] button[aria-label*="下一步"]',
            'css:[role="dialog"] button[aria-label*="继续"]',
        ]
        new_msg_btn_selectors = [
            'css:a[href*="/messages/compose"]',
            'css:[data-testid*="NewDM"]',
            'css:[data-testid*="newDM"]',
            'css:button[aria-label*="新消息"]',
            'css:button[aria-label*="New message"]',
        ]

        def _page_mentions_handle():
            try:
                hit = tab.run_js(
                    """
                    const handle = String(arguments[0] || '').replace(/^@+/, '').toLowerCase();
                    if (!handle) return false;
                    const isVisible = (el) => {
                      if (!el) return false;
                      const st = window.getComputedStyle(el);
                      if (!st) return false;
                      if (st.display === 'none' || st.visibility === 'hidden') return false;
                      const r = el.getBoundingClientRect();
                      return r.width > 0 && r.height > 0;
                    };
                    const roots = Array.from(document.querySelectorAll('[role="dialog"],main,[data-testid*="DM"],[data-testid*="dm"]'));
                    for (const root of roots) {
                      if (!isVisible(root)) continue;
                      const txt = String(root.innerText || root.textContent || '').toLowerCase();
                      if (!txt) continue;
                      if (txt.includes('@' + handle) || txt.includes(handle)) return true;
                    }
                    return false;
                    """,
                    handle_norm,
                )
                return bool(hit)
            except Exception:
                return False

        for idx, url in enumerate(compose_urls, start=1):
            entry_path = "direct_compose"
            entry_stage = f"open_{idx}"
            try:
                tab.get(url)
                _wait_document_ready(tab, timeout=5.2)
                _dm_humanized_idle(tab, 0.2, 0.45, f"直达私信入口加载{idx}")
            except Exception as e_open:
                log_headless_debug(f"直达私信入口打开失败({idx}): {e_open}")
                continue

            handled = _handle_dm_passcode_prompt(tab)
            if handled:
                _dm_humanized_idle(tab, 0.2, 0.45, "直达私信入口口令处理后等待")

            editor_now, editor_state = _wait_editor_or_closed(timeout_sec=1.2)
            if editor_now and _page_mentions_handle():
                entry_stage = f"compose_ready_{idx}"
                return editor_now, ""
            if editor_state == "closed":
                return None, "closed"

            # messages 首页场景：主动点“新消息”
            new_btn = _wait_first_actionable(tab, new_msg_btn_selectors, timeout=1.6, poll=0.1)
            if new_btn:
                _click_with_prompt_guard(tab, new_btn, "直达入口点击新消息")
                _dm_humanized_idle(tab, 0.12, 0.28, "点击新消息后等待")

            recipient_input = _wait_first_visible(tab, recipient_input_selectors, timeout=2.8, poll=0.1)
            if not recipient_input:
                entry_stage = f"recipient_input_missing_{idx}"
                continue

            try:
                recipient_input.click()
            except Exception:
                pass
            typed_ok = False
            try:
                recipient_input.input(f"@{handle_norm}", clear=True)
                typed_ok = True
            except Exception:
                try:
                    tab.run_js(
                        """
                        const el = arguments[0];
                        const text = String(arguments[1] || '');
                        if (!el) return false;
                        el.focus();
                        if (el.value !== undefined) {
                          el.value = text;
                          el.dispatchEvent(new Event('input', { bubbles: true }));
                          el.dispatchEvent(new Event('change', { bubbles: true }));
                          return true;
                        }
                        return false;
                        """,
                        recipient_input,
                        f"@{handle_norm}",
                    )
                    typed_ok = True
                except Exception:
                    typed_ok = False
            if not typed_ok:
                entry_stage = f"recipient_input_failed_{idx}"
                continue

            _dm_humanized_idle(tab, 0.2, 0.42, "输入收件人后等待候选")

            selected = False
            try:
                pick_state = tab.run_js(
                    """
                    const handle = String(arguments[0] || '').replace(/^@+/, '').toLowerCase();
                    const isVisible = (el) => {
                      if (!el) return false;
                      const st = window.getComputedStyle(el);
                      if (!st) return false;
                      if (st.display === 'none' || st.visibility === 'hidden') return false;
                      const r = el.getBoundingClientRect();
                      return r.width > 0 && r.height > 0;
                    };
                    const clickNode = (el) => {
                      if (!el) return false;
                      const node = el.closest('a,button,[role="button"],[role="option"],[role="link"]') || el;
                      if (!isVisible(node)) return false;
                      try { node.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                      try { node.click(); } catch (e) { return false; }
                      return true;
                    };
                    const roots = Array.from(document.querySelectorAll('[role="dialog"],[data-testid*="typeahead"],[data-testid*="Typeahead"],main'));
                    for (const root of roots) {
                      if (!isVisible(root)) continue;
                      const nodes = Array.from(root.querySelectorAll('[role="option"],[data-testid*="TypeaheadUser"],[data-testid*="conversation"],a,button,[role="button"]'));
                      for (const n of nodes) {
                        if (!isVisible(n)) continue;
                        const txt = String(n.innerText || n.textContent || '').trim().toLowerCase();
                        if (!txt) continue;
                        if (!txt.includes('@' + handle) && !txt.includes(handle)) continue;
                        if (clickNode(n)) return { selected: true };
                      }
                    }
                    return { selected: false };
                    """,
                    handle_norm,
                ) or {}
                selected = bool(pick_state.get("selected", False))
            except Exception:
                selected = False

            if not selected:
                try:
                    recipient_input.input('\n', clear=False)
                except Exception:
                    pass

            next_btn = _wait_first_actionable(tab, next_btn_selectors, timeout=1.3, poll=0.1)
            if next_btn:
                _click_with_prompt_guard(tab, next_btn, "直达入口点击下一步")
                _dm_humanized_idle(tab, 0.12, 0.3, "点击下一步后等待")
            else:
                try:
                    tab.run_js(
                        """
                        const isVisible = (el) => {
                          if (!el) return false;
                          const st = window.getComputedStyle(el);
                          if (!st) return false;
                          if (st.display === 'none' || st.visibility === 'hidden') return false;
                          const r = el.getBoundingClientRect();
                          return r.width > 0 && r.height > 0;
                        };
                        const keys = ['next', '下一步', '继续', '开始'];
                        for (const btn of Array.from(document.querySelectorAll('[role="dialog"] button,[role="dialog"] [role="button"]'))) {
                          if (!isVisible(btn)) continue;
                          if (btn.disabled || btn.getAttribute('aria-disabled') === 'true') continue;
                          const txt = String(btn.innerText || btn.textContent || '').trim().toLowerCase();
                          if (!txt) continue;
                          if (!keys.some((k) => txt.includes(k))) continue;
                          btn.click();
                          return true;
                        }
                        return false;
                        """
                    )
                except Exception:
                    pass

            editor_now, editor_state = _wait_editor_or_closed(timeout_sec=3.8)
            if editor_now:
                entry_stage = f"compose_editor_ready_{idx}"
                return editor_now, ""
            if editor_state == "closed":
                return None, "closed"

        return None, ""

    def _try_rescue_dm_popup():
        """
        私信入口点击后若未直接出现输入框，尝试点击消息小窗中的“新消息/目标会话”入口。
        兼容 X 新版点击私信后先弹出会话列表而非直接进入 composer 的场景。
        """
        try:
            result = tab.run_js(
                """
                const handle = String(arguments[0] || '').replace(/^@+/, '').trim().toLowerCase();
                const isVisible = (el) => {
                  if (!el) return false;
                  const st = window.getComputedStyle(el);
                  if (!st) return false;
                  if (st.display === 'none' || st.visibility === 'hidden') return false;
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                };
                const isClickable = (el) => {
                  if (!el) return false;
                  if (el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
                  const role = String(el.getAttribute('role') || '').toLowerCase();
                  const tag = String(el.tagName || '').toLowerCase();
                  if (tag === 'button' || tag === 'a') return true;
                  if (role === 'button' || role === 'link') return true;
                  return !!el.closest('a,button,[role="button"],[role="link"]');
                };
                const clickEl = (el) => {
                  if (!el) return false;
                  const node = (isClickable(el) ? el : (el.closest('a,button,[role="button"],[role="link"]') || el));
                  if (!node || !isVisible(node)) return false;
                  try { node.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                  const evOpts = { bubbles: true, cancelable: true, composed: true, view: window };
                  try { node.dispatchEvent(new MouseEvent('pointerdown', evOpts)); } catch (e) {}
                  try { node.dispatchEvent(new MouseEvent('mousedown', evOpts)); } catch (e) {}
                  try { node.dispatchEvent(new MouseEvent('mouseup', evOpts)); } catch (e) {}
                  try { node.click(); } catch (e) { return false; }
                  return true;
                };

                const dmSelectors = [
                  '[data-testid="sendDMFromProfile"]',
                  'button[data-testid="sendDMFromProfile"]',
                  '[data-testid="sendDM"]',
                  'button[data-testid="sendDM"]',
                  'a[href*="/messages/compose"]',
                  '[data-testid*="NewDM"]',
                  '[data-testid*="newDM"]',
                  'button[aria-label*="新消息"]',
                  'button[aria-label*="Message"]',
                  '[role="button"][aria-label*="Message"]'
                ];
                for (const s of dmSelectors) {
                  const nodes = Array.from(document.querySelectorAll(s));
                  for (const n of nodes) {
                    if (!isVisible(n)) continue;
                    if (!clickEl(n)) continue;
                    return { clicked: true, path: 'selector', selector: s };
                  }
                }

                const convoRoots = Array.from(document.querySelectorAll(
                  '[role="dialog"],[data-testid*="DM"],[data-testid*="dm"],[data-testid*="sheet"],[aria-label*="Messages"],[aria-label*="消息"]'
                )).filter(isVisible);
                for (const root of convoRoots) {
                  const convoNodes = Array.from(root.querySelectorAll(
                    '[data-testid*="conversation"],a[href*="/messages/"],div[role="link"],button,[role="button"]'
                  ));
                  for (const n of convoNodes) {
                    if (!isVisible(n)) continue;
                    const txt = String(n.innerText || n.textContent || '').toLowerCase();
                    if (!txt) continue;
                    if (handle && !txt.includes(handle)) continue;
                    if (!clickEl(n)) continue;
                    return { clicked: true, path: 'conversation', selector: 'conversation_node' };
                  }
                }

                const dialogButtons = Array.from(document.querySelectorAll(
                  '[role="dialog"] button,[role="dialog"] [role="button"],[data-testid*="sheet"] button,[data-testid*="DM"] button'
                ));
                const btnKeywords = ['message', '发消息', '私信', 'new message', '新消息', 'next', '继续', 'chat'];
                for (const n of dialogButtons) {
                  if (!isVisible(n)) continue;
                  const txt = String(n.innerText || n.textContent || '').trim().toLowerCase();
                  if (!txt) continue;
                  if (!btnKeywords.some((k) => txt.includes(k))) continue;
                  if (!clickEl(n)) continue;
                  return { clicked: true, path: 'dialog_button', selector: 'dialog_btn' };
                }
                return { clicked: false, path: 'none' };
                """,
                handle_norm,
            ) or {}
        except Exception as e:
            log_headless_debug(f"私信弹窗兜底点击异常: {e}")
            return False

        if bool(result.get("clicked")):
            log_to_ui(
                "debug",
                f"📨 私信弹窗兜底点击成功: path={result.get('path', '')} selector={result.get('selector', '')}"
            )
            time.sleep(random.uniform(0.2, 0.45))
            return True
        return False

    if DM_ENTRY_MODE in {"direct_compose_first", "dual_probe"}:
        editor_direct, direct_state = _try_open_dm_via_direct_compose()
        if editor_direct:
            return editor_direct, ""
        if direct_state == "closed":
            _mark_dm_unavailable(handle_norm)
            return None, "该用户当前不可私信（平台限制或对方未开放私信）"

    entry_path = "profile_click"
    open_attempts = DM_EDITOR_OPEN_RETRY_HEADLESS if headless_mode else DM_EDITOR_OPEN_RETRY_NORMAL
    for attempt in range(open_attempts):
        if attempt == 0:
            profile_opened_rounds += 1
            tab.get(f"https://x.com/{handle_norm}")
            _wait_document_ready(tab, timeout=5.5)
            try:
                tab.wait.ele_displayed('tag:main', timeout=8)
            except Exception:
                pass
            time.sleep(random.uniform(0.45, 0.85))
        elif attempt == 1:
            # 第一次失败后重进资料页，规避临时页面状态拦截
            handled = _handle_dm_passcode_prompt(tab)
            if handled:
                time.sleep(random.uniform(0.35, 0.7))
            profile_opened_rounds += 1
            tab.get(f"https://x.com/{handle_norm}")
            _wait_document_ready(tab, timeout=5.2)
            try:
                tab.wait.ele_displayed('tag:main', timeout=6)
            except Exception:
                pass
            time.sleep(random.uniform(0.4, 0.8))
        else:
            try:
                tab.refresh()
                _wait_document_ready(tab, timeout=4.6)
                time.sleep(random.uniform(0.5, 1.0))
            except Exception:
                pass

        if _has_cannot_dm_hint():
            _mark_dm_unavailable(handle_norm)
            return None, "该用户当前不可私信（平台限制或对方未开放私信）"

        dm_btn = _find_dm_btn()
        if not dm_btn:
            continue
        dm_btn_seen = True

        clicked_dm_btn, click_dm_err = _click_with_prompt_guard(
            tab,
            dm_btn,
            "点击私信入口按钮",
            refetch_selectors=dm_btn_selectors,
        )
        if not clicked_dm_btn:
            log_to_ui("debug", f"📨 私信入口点击失败(尝试{attempt + 1}/{open_attempts}): {click_dm_err}")
            continue
        time.sleep(random.uniform(0.28, 0.62))

        # 第一轮快速检查：若未进入编辑框，尝试识别并点击消息小窗会话入口。
        editor, editor_state = _wait_editor_or_closed(timeout_sec=1.4)
        if editor:
            return editor, ""
        if editor_state == "closed":
            _mark_dm_unavailable(handle_norm)
            return None, "该用户当前不可私信（平台限制或对方未开放私信）"
        if _try_rescue_dm_popup():
            editor, editor_state = _wait_editor_or_closed(timeout_sec=2.2)
            if editor:
                return editor, ""
            if editor_state == "closed":
                _mark_dm_unavailable(handle_norm)
                return None, "该用户当前不可私信（平台限制或对方未开放私信）"

        handled_after_click = _handle_dm_passcode_prompt(tab)
        if handled_after_click:
            # 保留二次点击兜底，兼容被打断后回到资料页的场景
            try:
                tab.get(f"https://x.com/{handle_norm}")
                _wait_document_ready(tab, timeout=4.8)
                time.sleep(random.uniform(0.4, 0.8))
            except Exception:
                pass
            dm_btn_retry = _find_dm_btn()
            if dm_btn_retry:
                _click_with_prompt_guard(
                    tab,
                    dm_btn_retry,
                    "重试点击私信入口按钮",
                    refetch_selectors=dm_btn_selectors,
                )
                time.sleep(random.uniform(0.4, 0.8))

        editor, editor_state = _wait_editor_or_closed(timeout_sec=3.6)
        if editor:
            return editor, ""
        if editor_state == "closed":
            _mark_dm_unavailable(handle_norm)
            return None, "该用户当前不可私信（平台限制或对方未开放私信）"
        if _has_cannot_dm_hint():
            _mark_dm_unavailable(handle_norm)
            return None, "该用户当前不可私信（平台限制或对方未开放私信）"

    if _has_cannot_dm_hint():
        _mark_dm_unavailable(handle_norm)
        return None, "该用户当前不可私信（平台限制或对方未开放私信）"

    if (
        DM_PROFILE_NO_BUTTON_AS_CLOSED
        and profile_opened_rounds > 0
        and (not dm_btn_seen)
    ):
        _mark_dm_unavailable(handle_norm)
        return None, "该用户当前不可私信（资料页无私信入口）"

    # profile_first 模式下，只有在资料页入口失败时才回退到直达私信搜索路径。
    if DM_ENTRY_MODE == "profile_first":
        editor_direct_fallback, direct_state = _try_open_dm_via_direct_compose()
        if editor_direct_fallback:
            log_to_ui("debug", f"📨 资料页私信入口失败，已回退直达私信入口: @{handle_norm}")
            return editor_direct_fallback, ""
        if direct_state == "closed":
            _mark_dm_unavailable(handle_norm)
            return None, "该用户当前不可私信（平台限制或对方未开放私信）"

    _capture_runtime_diagnostic(
        tab,
        "open_dm_editor_failed",
        err=f"handle={handle_norm}",
        selectors=dm_btn_selectors + editor_selectors,
        extra={
            "handle": handle_norm,
            "open_attempts": open_attempts,
            "headless_mode": bool(headless_mode),
            "dm_entry_mode": DM_ENTRY_MODE,
            "entry_path": entry_path,
            "entry_stage": entry_stage,
        }
    )
    return None, "未打开私信输入框（可能被页面状态打断）"


def _send_dm_message(tab, text):
    """在当前私信弹窗发送一条消息。"""
    if not text:
        return False, "空消息"

    editor_selectors = [
        'css:textarea[data-testid="dm-composer-textarea"]',
        'css:textarea[placeholder="Message"]',
        'css:textarea[placeholder*="消息"]',
        'css:[data-testid="dmComposerTextInput"] [contenteditable]:not([contenteditable="false"])',
        'css:[data-testid="dmComposerTextInput"] [contenteditable="true"]',
        'css:div[role="textbox"][contenteditable]:not([contenteditable="false"])',
        'css:div[role="textbox"][contenteditable="true"]',
        'css:[data-testid="dmComposerTextInput"]',
    ]
    send_btn_selectors = [
        'css:button[data-testid="dm-composer-send-button"]',
        'css:[data-testid="dm-composer-send-button"]',
        'css:button[data-testid*="dm-composer-send"]',
        'css:[data-testid*="dm-composer-send"]',
        'css:[data-testid="dmComposerSendButton"]',
        'css:button[data-testid="dmComposerSendButton"]',
        'css:button[aria-label*="发送"]',
        'css:button[aria-label*="Send"]',
    ]
    editor_css_selectors = [
        s[4:] if str(s).startswith('css:') else str(s)
        for s in editor_selectors
    ]
    send_btn_css_selectors = [
        s[4:] if str(s).startswith('css:') else str(s)
        for s in send_btn_selectors
    ]

    def _clear_dm_binding_marks():
        try:
            tab.run_js(
                """
                document.querySelectorAll('[data-xm-dm-target],[data-xm-dm-send-target],[data-xm-dm-root]').forEach((el) => {
                  try { el.removeAttribute('data-xm-dm-target'); } catch (e) {}
                  try { el.removeAttribute('data-xm-dm-send-target'); } catch (e) {}
                  try { el.removeAttribute('data-xm-dm-root'); } catch (e) {}
                });
                return true;
                """
            )
        except Exception:
            pass

    def _bind_dm_composer_target():
        """通过发送按钮反向绑定当前会话编辑器，避免误写到上层“新消息/搜索”输入框。"""
        try:
            ok = tab.run_js(
                """
                const editorSels = arguments[0] || [];
                const sendSels = arguments[1] || [];
                const rejectOverlay = !!arguments[2];
                const isVisible = (el) => {
                  if (!el) return false;
                  const st = window.getComputedStyle(el);
                  if (!st) return false;
                  if (st.display === 'none' || st.visibility === 'hidden') return false;
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                };
                const isBadScene = (text) => {
                  const t = String(text || '').toLowerCase();
                  return (
                    t.includes('搜索私信') ||
                    t.includes('创建一条私信') ||
                    t.includes('创建私信') ||
                    t.includes('new message') ||
                    t.includes('search direct messages') ||
                    t.includes('recipient')
                  );
                };

                document.querySelectorAll('[data-xm-dm-target],[data-xm-dm-send-target]').forEach((el) => {
                  try { el.removeAttribute('data-xm-dm-target'); } catch (e) {}
                  try { el.removeAttribute('data-xm-dm-send-target'); } catch (e) {}
                });

                const sendButtons = [];
                for (const s of sendSels) {
                  let nodes = [];
                  try { nodes = Array.from(document.querySelectorAll(s)); } catch (e) { nodes = []; }
                  for (const n of nodes) {
                    if (!isVisible(n)) continue;
                    if (!sendButtons.includes(n)) sendButtons.push(n);
                  }
                }
                if (!sendButtons.length) return false;

                const editorScore = (editor, btn, root) => {
                  if (!editor || !btn) return -1e9;
                  const er = editor.getBoundingClientRect();
                  const br = btn.getBoundingClientRect();
                  const rr = root && root.getBoundingClientRect ? root.getBoundingClientRect() : { width: 0, height: 0 };
                  const editableSelf = !!(
                    editor.value !== undefined ||
                    editor.isContentEditable ||
                    editor.getAttribute('contenteditable') === 'true' ||
                    editor.getAttribute('contenteditable') === 'plaintext-only'
                  );
                  const width = Number(er.width || 0);
                  const height = Number(er.height || 0);
                  const top = Number(er.top || 0);
                  const bottom = Number(er.bottom || 0);
                  const nearFooterBand = top >= (window.innerHeight * 0.55);
                  const verticalGap = Math.abs(bottom - br.top);
                  const aboveBtn = bottom <= (br.bottom + 24);
                  const closeToBtn = verticalGap <= 220;
                  const leftOfBtn = (Number(er.left || 0) <= Number(br.left || 0) + 48);
                  const rootArea = Math.max(1, Number(rr.width || 0) * Number(rr.height || 0));
                  let score = 0;
                  if (editableSelf) score += 500;
                  if (nearFooterBand) score += 420;
                  if (aboveBtn) score += 220;
                  if (closeToBtn) score += Math.max(0, 260 - verticalGap);
                  if (leftOfBtn) score += 120;
                  if (width >= 180) score += 160;
                  if (height >= 24) score += 80;
                  score += Math.min(240, Math.max(0, bottom));
                  score -= Math.min(180, Math.max(0, top < (window.innerHeight * 0.45) ? 160 : 0));
                  score -= Math.min(120, Math.log10(rootArea + 1) * 16);
                  return score;
                };

                const pickEditorByBtn = (btn) => {
                  const chain = [];
                  let node = btn;
                  for (let i = 0; i < 12 && node; i++) {
                    chain.push(node);
                    node = node.parentElement;
                  }
                  let best = null;
                  for (const root of chain) {
                    if (!root || root.nodeType !== 1) continue;
                    const rootText = String(root.innerText || root.textContent || '').slice(0, 800);
                    if (rejectOverlay && isBadScene(rootText)) continue;
                    let editors = [];
                    for (const s of editorSels) {
                      let found = [];
                      try { found = Array.from(root.querySelectorAll(s)); } catch (e) { found = []; }
                      for (const e of found) {
                        if (!isVisible(e)) continue;
                        if (!editors.includes(e)) editors.push(e);
                      }
                    }
                    if (!editors.length) continue;
                    for (const editor of editors) {
                      const score = editorScore(editor, btn, root);
                      if (!best || score > best.score) {
                        best = { editor, root, score };
                      }
                    }
                  }
                  return best;
                };

                const candidates = [];
                for (const btn of sendButtons) {
                  const picked = pickEditorByBtn(btn);
                  if (!picked || !picked.editor || !picked.root) continue;
                  const r = btn.getBoundingClientRect();
                  const enabled = !(btn.disabled || btn.getAttribute('aria-disabled') === 'true');
                  candidates.push({ btn, editor: picked.editor, root: picked.root, enabled, top: Number(r.top || 0), score: Number(picked.score || 0) });
                }
                if (!candidates.length) return false;
                candidates.sort((a, b) => {
                  if (a.enabled !== b.enabled) return Number(b.enabled) - Number(a.enabled);
                  if (a.score !== b.score) return Number(b.score || 0) - Number(a.score || 0);
                  return Number(b.top || 0) - Number(a.top || 0);
                });
                const target = candidates[0];
                try { target.root.setAttribute('data-xm-dm-root', '1'); } catch (e) {}
                try { target.editor.setAttribute('data-xm-dm-target', '1'); } catch (e) {}
                try { target.btn.setAttribute('data-xm-dm-send-target', '1'); } catch (e) {}
                try { target.editor.focus(); } catch (e) {}
                return true;
                """,
                editor_css_selectors,
                send_btn_css_selectors,
                DM_REJECT_NEW_MESSAGE_OVERLAY,
            )
            return bool(ok)
        except Exception:
            return False

    def _get_bound_editor():
        try:
            cand = tab.ele('css:[data-xm-dm-target="1"]', timeout=0.25)
            if cand and cand.states.is_displayed:
                return cand
        except Exception:
            pass
        return None

    def _get_bound_send_btn(require_enabled=True):
        try:
            cand = tab.ele('css:[data-xm-dm-send-target="1"]', timeout=0.25)
            if not cand:
                return None
            if not cand.states.is_displayed:
                return None
            if require_enabled and (not _is_element_actionable(cand)):
                return None
            return cand
        except Exception:
            return None

    def _editor_matches_bound_send(editor_el):
        if not editor_el:
            return False
        try:
            ok = tab.run_js(
                """
                const ed = arguments[0];
                const btn = document.querySelector('[data-xm-dm-send-target="1"]');
                const root = document.querySelector('[data-xm-dm-root="1"]');
                if (!ed) return false;
                if (!btn) return true;
                if (!root) return false;
                return root.contains(ed);
                """,
                editor_el,
            )
            return bool(ok)
        except Exception:
            return False

    def _has_any_visible_send_btn():
        try:
            has_btn = tab.run_js(
                """
                const selectors = arguments[0] || [];
                const isVisible = (el) => {
                  if (!el) return false;
                  const st = window.getComputedStyle(el);
                  if (!st) return false;
                  if (st.display === 'none' || st.visibility === 'hidden') return false;
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                };
                for (const s of selectors) {
                  let nodes = [];
                  try { nodes = Array.from(document.querySelectorAll(s)); } catch (e) { nodes = []; }
                  for (const n of nodes) {
                    if (isVisible(n)) return true;
                  }
                }
                return false;
                """,
                send_btn_css_selectors,
            )
            return bool(has_btn)
        except Exception:
            return False

    def _is_valid_dm_editor(editor_el):
        try:
            ok = tab.run_js(
                """
                const el = arguments[0];
                const rejectOverlay = !!arguments[1];
                if (!el) return false;
                const low = (s) => String(s || '').toLowerCase();
                const attrs = [
                  el.getAttribute('aria-label'),
                  el.getAttribute('placeholder'),
                  el.getAttribute('data-testid'),
                  el.getAttribute('name')
                ].map(low).join(' ');
                const rejectKeys = [
                  'search', '搜索', 'recipient', '收件人', 'people', 'group', 'new message', '新消息'
                ];
                if (rejectKeys.some((k) => attrs.includes(k))) return false;
                const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : { top: 0, width: 0, height: 0 };
                const editable = !!(
                  el.value !== undefined ||
                  el.isContentEditable ||
                  el.getAttribute('contenteditable') === 'true' ||
                  el.querySelector('textarea,[contenteditable="true"]')
                );
                if (!editable) return false;
                const url = low(window.location.href || '');
                if (url.includes('/i/chat/')) return true;
                const root = el.closest('[role="dialog"]') || document;
                const rootText = low((root.innerText || root.textContent || '').slice(0, 800));
                const hasSearchScene = (
                  rootText.includes('搜索私信') ||
                  rootText.includes('创建一条私信') ||
                  rootText.includes('创建私信') ||
                  rootText.includes('new message') ||
                  rootText.includes('search direct messages') ||
                  rootText.includes('recipient')
                );
                const hasSend = !!root.querySelector(
                  '[data-testid="dm-composer-send-button"],[data-testid="dmComposerSendButton"],button[data-testid*="dm-composer-send"]'
                );
                if (rejectOverlay) {
                  if (hasSearchScene && !hasSend) return false;
                  if (!hasSend && rect && Number(rect.top || 0) < (window.innerHeight * 0.45)) return false;
                }
                if (root.querySelector('[data-testid="dmComposerTextInput"],textarea[data-testid="dm-composer-textarea"]')) {
                  return true;
                }
                return hasSend;
                """,
                editor_el,
                DM_REJECT_NEW_MESSAGE_OVERLAY,
            )
            return bool(ok)
        except Exception:
            return False

    def _promote_dm_editor_candidate(cand):
        """若命中外层容器，优先提升到真正可编辑节点。"""
        if not cand:
            return cand
        try:
            inner = cand.ele('css:div[role="textbox"][contenteditable]:not([contenteditable="false"])', timeout=0)
            if inner and inner.states.is_displayed:
                return inner
        except Exception:
            pass
        try:
            inner = cand.ele('css:[contenteditable]:not([contenteditable="false"])', timeout=0)
            if inner and inner.states.is_displayed:
                return inner
        except Exception:
            pass
        try:
            inner = cand.ele('css:[contenteditable="true"]', timeout=0)
            if inner and inner.states.is_displayed:
                return inner
        except Exception:
            pass
        return cand

    def _find_editor(rounds=2, timeout_each=1.5):
        for _ in range(max(1, rounds)):
            if DM_FORCE_COMPOSER_BINDING:
                bound_ok = _bind_dm_composer_target()
                bound = _get_bound_editor()
                if bound and _is_valid_dm_editor(bound):
                    return bound
                # 强绑定模式下，如果页面已有发送按钮但无法绑定到编辑器，直接判失败以触发会话重开
                if (not bound_ok) and _has_any_visible_send_btn():
                    return None
            for selector in editor_selectors:
                try:
                    cand = tab.ele(selector, timeout=timeout_each)
                    cand = _promote_dm_editor_candidate(cand)
                    if cand and cand.states.is_displayed and _is_valid_dm_editor(cand):
                        return cand
                except Exception:
                    continue
            time.sleep(random.uniform(0.08, 0.22))
        return None

    def _find_send_btn(rounds=2, timeout_each=1.2, require_enabled=True):
        for _ in range(max(1, rounds)):
            if DM_FORCE_COMPOSER_BINDING:
                _bind_dm_composer_target()
                bound_btn = _get_bound_send_btn(require_enabled=require_enabled)
                if bound_btn:
                    return bound_btn
            if require_enabled:
                cand = _wait_first_actionable(tab, send_btn_selectors, timeout=timeout_each, poll=0.08)
            else:
                cand = _wait_first_visible(tab, send_btn_selectors, timeout=timeout_each, poll=0.08)
            if cand:
                return cand
            time.sleep(random.uniform(0.05, 0.18))
        return None

    def _composer_cleared(editor_el):
        try:
            remain = tab.run_js(
                """
                const el = arguments[0];
                if (!el) return '';
                const val = (el.value !== undefined) ? el.value : (el.textContent || '');
                return String(val || '').trim();
                """,
                editor_el
            )
            return len(str(remain or "").strip()) == 0
        except Exception:
            # 发送后编辑器常被重建，读取失败可视为已提交
            return True

    def _editor_has_text(editor_el, expected_text):
        try:
            remain = tab.run_js(
                """
                const el = arguments[0];
                if (!el) return '';
                const val = (el.value !== undefined) ? el.value : (el.textContent || '');
                return String(val || '');
                """,
                editor_el
            )
            current = _normalize_text_for_compare(remain)
            exp = _normalize_text_for_compare(expected_text)
            if not exp:
                return True
            if _is_link_only_message(exp):
                # 链接消息在 X 私信框里会被自动转成预览卡片，输入框可能瞬时变空
                if not current:
                    btn = _find_send_btn(rounds=1, timeout_each=0.8)
                    return bool(btn)
                if exp in current or current in exp:
                    return True
                if "x.com/" in current or "twitter.com/" in current:
                    return True
                return False
            if current == exp:
                return True
            # 命中次数>=2 说明发生了拼接/重复，不视为成功
            if current.count(exp) >= 2:
                return False
            # DraftJS 常出现少量空白/换行差异，放宽“包含”判定
            if exp and (exp in current):
                return True
            if current and (current in exp) and len(current) >= max(12, int(len(exp) * 0.72)):
                return True
            # 长文仅允许很小偏差（如末尾标点/空格）
            if current.endswith(exp) and (len(current) - len(exp)) <= 6:
                return True
            return False
        except Exception:
            return False

    def _force_fill_dm_editor_text(editor_el, expected_text):
        """DraftJS 文本框强制回填：选择全量后写入，适配 contenteditable 输入丢失场景。"""
        text = str(expected_text or "")
        if not text:
            return False
        try:
            ok = tab.run_js(
                """
                const root = arguments[0];
                const text = String(arguments[1] || '');
                if (!root) return false;
                const resolveTarget = (el) => {
                  if (!el) return null;
                  if (el.value !== undefined || el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
                    return el;
                  }
                  return el.querySelector(
                    'div[role="textbox"][contenteditable="true"],[data-testid="dmComposerTextInput"] [contenteditable="true"],textarea[data-testid="dm-composer-textarea"],textarea'
                  );
                };
                let el = resolveTarget(root);
                if (!el) return false;
                const dispatchAll = () => {
                  try {
                    el.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, inputType: 'insertText', data: text }));
                  } catch (e) {}
                  try {
                    el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
                  } catch (e) {
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                  }
                  try { el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Process', code: 'Process' })); } catch (e) {}
                  try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                };
                const setValue = (val) => {
                  if (el.value !== undefined) {
                    const proto = Object.getPrototypeOf(el);
                    const desc = proto ? Object.getOwnPropertyDescriptor(proto, 'value') : null;
                    if (desc && typeof desc.set === 'function') {
                      desc.set.call(el, val);
                    } else {
                      el.value = val;
                    }
                  } else {
                    el.textContent = val;
                  }
                  dispatchAll();
                };
                try { el.focus(); } catch (e) {}
                if (el.value !== undefined) {
                  setValue(text);
                  return true;
                }
                try {
                  const sel = window.getSelection && window.getSelection();
                  if (sel) {
                    sel.removeAllRanges();
                    const range = document.createRange();
                    range.selectNodeContents(el);
                    sel.addRange(range);
                  }
                } catch (e) {}
                let done = false;
                try {
                  done = !!document.execCommand('insertText', false, text);
                } catch (e) {}
                if (!done || !String(el.textContent || '').trim()) {
                  setValue(text);
                } else {
                  dispatchAll();
                }
                return true;
                """,
                editor_el,
                text
            )
            if ok and _editor_has_text(editor_el, text):
                return True
        except Exception:
            pass

        try:
            editor_el.input(text, clear=True)
        except Exception:
            return False
        return _editor_has_text(editor_el, text)

    def _wait_send_button_after_input(editor_el, expected_text, link_mode=False):
        """输入后等待发送按钮可点击；链接模式下进行额外状态唤醒。"""
        def _has_disabled_send_button():
            bound_disabled = _get_bound_send_btn(require_enabled=False)
            if bound_disabled:
                try:
                    if not _is_element_actionable(bound_disabled):
                        return True
                except Exception:
                    pass
            try:
                state = tab.run_js(
                    """
                    const sels = [
                      'button[data-testid="dm-composer-send-button"]',
                      '[data-testid="dm-composer-send-button"]',
                      'button[data-testid*="dm-composer-send"]',
                      '[data-testid*="dm-composer-send"]',
                      '[data-testid="dmComposerSendButton"]',
                      'button[data-testid="dmComposerSendButton"]',
                      'button[aria-label*="Send"]',
                      'button[aria-label*="发送"]'
                    ];
                    const isVisible = (el) => {
                      if (!el) return false;
                      const st = window.getComputedStyle(el);
                      if (!st) return false;
                      if (st.display === 'none' || st.visibility === 'hidden') return false;
                      const r = el.getBoundingClientRect();
                      return r.width > 0 && r.height > 0;
                    };
                    for (const s of sels) {
                      for (const el of Array.from(document.querySelectorAll(s))) {
                        if (!isVisible(el)) continue;
                        if (el.disabled || el.getAttribute('aria-disabled') === 'true') return true;
                      }
                    }
                    return false;
                    """
                )
                return bool(state)
            except Exception:
                return False

        def _nudge_editor_for_send_enable():
            try:
                _refresh_dm_editor_state(tab, editor_el, expected_text)
                _poke_dm_editor_events(tab, editor_el)
            except Exception:
                pass
            try:
                tab.run_js(
                    """
                    const el = arguments[0];
                    const text = String(arguments[1] || '');
                    if (!el) return false;
                    try { el.focus(); } catch (e) {}
                    const dispatchAll = () => {
                      try { el.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, inputType: 'insertText', data: ' ' })); } catch (e) {}
                      try { el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: ' ' })); } catch (e) {
                        try { el.dispatchEvent(new Event('input', { bubbles: true })); } catch (_) {}
                      }
                      try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                    };
                    if (el.value !== undefined) {
                      const v = String(el.value || '');
                      el.value = v + ' ';
                      dispatchAll();
                      el.value = v;
                      dispatchAll();
                      return true;
                    }
                    if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
                      try {
                        const sel = window.getSelection && window.getSelection();
                        if (sel) {
                          sel.removeAllRanges();
                          const range = document.createRange();
                          range.selectNodeContents(el);
                          range.collapse(false);
                          sel.addRange(range);
                        }
                      } catch (e) {}
                      let changed = false;
                      try { changed = !!document.execCommand('insertText', false, ' '); } catch (e) {}
                      dispatchAll();
                      try { document.execCommand('delete'); } catch (e) {}
                      dispatchAll();
                      if (!changed) {
                        el.textContent = text;
                        dispatchAll();
                      }
                      return true;
                    }
                    return false;
                    """,
                    editor_el,
                    expected_text,
                )
            except Exception:
                pass

        def _wait_link_preview_ready(timeout_sec=2.8):
            """链接消息发送前，等待上方预览/卡片渲染就绪。"""
            deadline = time.time() + max(1.0, float(timeout_sec))
            status_id = _pick_best_status_id(expected_text)
            while time.time() < deadline:
                btn = _find_send_btn(rounds=1, timeout_each=0.45)
                try:
                    state = tab.run_js(
                        """
                        const el = arguments[0];
                        const raw = String(arguments[1] || '');
                        const sid = String(arguments[2] || '');
                        if (!el) return {hasPreview: false, inputEmpty: false, hasInputLink: false};
                        const text = ((el.value !== undefined) ? el.value : (el.textContent || '')).trim();
                        const inputEmpty = text.length === 0;
                        const lower = text.toLowerCase();
                        const hasInputLink = (
                            lower.includes('x.com/') ||
                            lower.includes('twitter.com/') ||
                            lower.includes('https://') ||
                            lower.includes('http://')
                        );

                        const root =
                            el.closest('[role="dialog"]') ||
                            el.closest('[data-testid*="Dm"]') ||
                            el.closest('[data-testid*="dm"]') ||
                            document.body;
                        const nodes = Array.from(root.querySelectorAll(
                            '[data-testid*="card"],[data-testid*="preview"],[data-testid*="attachment"],a[href*="/status/"],a[href*="x.com/"],a[href*="twitter.com/"]'
                        ));
                        let hasPreview = false;
                        for (const n of nodes) {
                            const st = window.getComputedStyle(n);
                            if (st.display === 'none' || st.visibility === 'hidden') continue;
                            if (sid) {
                                const href = (n.getAttribute && n.getAttribute('href')) ? String(n.getAttribute('href')) : '';
                                if (href.includes('/status/' + sid)) {
                                    hasPreview = true;
                                    break;
                                }
                            } else {
                                hasPreview = true;
                                break;
                            }
                        }
                        return {hasPreview, inputEmpty, hasInputLink};
                        """,
                        editor_el,
                        expected_text,
                        status_id,
                    ) or {}
                except Exception:
                    state = {}

                has_preview = bool(state.get("hasPreview"))
                input_empty = bool(state.get("inputEmpty"))
                has_input_link = bool(state.get("hasInputLink"))
                if has_preview or has_input_link or (input_empty and btn):
                    return True
                _dm_humanized_idle(tab, 0.06, 0.14, "等待链接预览加载")
            return False

        if link_mode:
            _wait_link_preview_ready(timeout_sec=3.0)
        btn = _find_send_btn(rounds=2, timeout_each=1.0, require_enabled=True)
        if btn:
            return btn
        if not link_mode:
            deadline = time.time() + max(0.6, float(DM_TEXT_VERIFY_TIMEOUT_SEC))
            while time.time() < deadline:
                if _editor_has_text(editor_el, expected_text):
                    _poke_dm_editor_events(tab, editor_el)
                btn = _find_send_btn(rounds=1, timeout_each=0.6, require_enabled=True)
                if btn:
                    return btn
                _dm_humanized_idle(tab, 0.03, 0.1, "文本消息等待发送按钮")
            # DraftJS 常见“可见文本已写入但发送按钮仍禁用”，追加一次状态唤醒后再尝试
            if _editor_has_text(editor_el, expected_text) and _has_disabled_send_button():
                _nudge_editor_for_send_enable()
                _dm_humanized_idle(tab, 0.04, 0.12, "文本消息发送按钮唤醒后等待")
                btn = _find_send_btn(rounds=2, timeout_each=0.8, require_enabled=True)
                if btn:
                    return btn
            return None

        for _ in range(2):
            _dm_humanized_idle(tab, 0.06, 0.14, "链接消息等待发送按钮")
            if _poke_dm_editor_events(tab, editor_el):
                _dm_humanized_idle(tab, 0.03, 0.08, "链接消息状态刷新后等待")
            try:
                current_text = tab.run_js(
                    """
                    const el = arguments[0];
                    if (!el) return '';
                    return String((el.value !== undefined) ? (el.value || '') : (el.textContent || ''));
                    """,
                    editor_el
                )
            except Exception:
                current_text = ""
            if not _normalize_text_for_compare(current_text):
                # 链接在 X 里偶发被异步清空，按钮不会出现；仅在空输入框时回填一次。
                _paste_dm_text_exact(tab, editor_el, expected_text)
                _dm_humanized_idle(tab, 0.05, 0.12, "链接回填后等待按钮")
            btn = _find_send_btn(rounds=2, timeout_each=1.0, require_enabled=True)
            if btn:
                return btn
        return None

    max_attempts = DM_SEND_RETRY_HEADLESS if headless_mode else DM_SEND_RETRY_NORMAL
    last_err = ""
    dm_text = _sanitize_dm_message_text(text)
    link_only_mode = _is_link_only_message(dm_text)
    probes = _build_dm_message_probes(dm_text)

    session_state = _read_dm_session_state(tab, "")
    for attempt in range(1, max_attempts + 1):
        _throttle_dm_action_if_needed(f"私信发送尝试{attempt}")
        _prepare_reply_prompt_guard(tab, f"私信发送尝试{attempt}")
        _dm_humanized_idle(tab, 0.04, 0.16, f"私信发送尝试{attempt}")
        before_counts = {p: _count_dm_probe_occurrence(tab, p) for p in probes}

        editor = _find_editor(rounds=2, timeout_each=1.4)
        if not editor:
            _handle_dm_passcode_prompt(tab)
            editor = _find_editor(rounds=2, timeout_each=1.6)
        if not editor:
            last_err = "未找到私信输入框"
            time.sleep(random.uniform(0.05, 0.12))
            continue
        if DM_FORCE_COMPOSER_BINDING and not _editor_matches_bound_send(editor):
            last_err = "E_DM_WRONG_COMPOSER_TARGET: 编辑器与当前会话发送按钮不在同一容器"
            _dm_humanized_idle(tab, 0.06, 0.16, "检测到输入框映射异常后等待")
            continue

        try:
            editor.click()
        except Exception:
            pass

        # X 的 DraftJS 在私信场景下对 editor.input() 兼容性更好；
        # JS 粘贴路径容易出现“文本可见但发送按钮不激活”的假输入。
        typed_ok = _humanized_type_dm_text(tab, editor, dm_text)
        if not typed_ok:
            typed_ok = _paste_dm_text_exact(tab, editor, dm_text)
        if not typed_ok:
            last_err = "输入私信内容失败"
            time.sleep(random.uniform(0.05, 0.12))
            continue
        if DM_FORCE_COMPOSER_BINDING and not _editor_matches_bound_send(editor):
            last_err = "E_DM_WRONG_COMPOSER_TARGET: 文本写入疑似落在上层浮层输入框"
            _dm_humanized_idle(tab, 0.06, 0.16, "检测到文本映射异常后等待")
            continue
        if not _editor_has_text(editor, dm_text):
            if link_only_mode:
                _poke_dm_editor_events(tab, editor)
                if not _editor_has_text(editor, dm_text):
                    last_err = "输入后链接状态未稳定写入编辑器"
                    _dm_humanized_idle(tab, 0.08, 0.2, "链接输入校验失败后等待")
                    continue
            else:
                _dm_humanized_idle(tab, 0.04, 0.12, "私信文本二次回填前")
                recovered = _force_fill_dm_editor_text(editor, dm_text)
                if not recovered and not _editor_has_text(editor, dm_text):
                    # 最后一次走常规 input，避免 JS 注入与 DraftJS 状态机不同步
                    recovered = _humanized_type_dm_text(tab, editor, dm_text)
                if not recovered and not _editor_has_text(editor, dm_text):
                    last_err = "输入后文本未稳定写入编辑器"
                    _dm_humanized_idle(tab, 0.08, 0.2, "私信输入校验失败后等待")
                    continue

        _dm_humanized_idle(tab, 0.04, 0.12, "私信发送前")
        send_btn = _wait_send_button_after_input(editor, dm_text, link_mode=link_only_mode)
        if send_btn:
            clicked_send, click_err = _click_with_prompt_guard(tab, send_btn, "点击私信发送按钮")
            if clicked_send:
                _dm_humanized_idle(tab, 0.06, 0.16, "私信发送后确认")
                if _composer_cleared(editor):
                    return True, ""
                if _confirm_dm_message_sent(tab, before_counts, probes, wait_sec=DM_SEND_CONFIRM_WAIT_SEC):
                    log_headless_debug("私信发送后输入框未清空，但已确认消息落库，按成功处理")
                    return True, ""
                if DM_ASSUME_SUCCESS_AFTER_CLICK:
                    log_to_ui("warn", "⚠️ 私信点击发送后状态不确定，但当前配置禁止按成功处理")
                last_err = "点击私信发送后输入框未清空"
                continue
            last_err = click_err
        elif _editor_has_text(editor, dm_text):
            # 发送按钮偶发未渲染/未激活时，尝试 Enter 直发（仅在编辑器确有内容时触发）。
            _dm_humanized_idle(tab, 0.02, 0.08, "私信发送Enter兜底前")
            try:
                enter_sent = bool(tab.run_js(
                    """
                    const el = arguments[0];
                    if (!el) return false;
                    try { el.focus(); } catch (e) {}
                    const ev = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true };
                    try { el.dispatchEvent(new KeyboardEvent('keydown', ev)); } catch (e) {}
                    try { el.dispatchEvent(new KeyboardEvent('keypress', ev)); } catch (e) {}
                    try { el.dispatchEvent(new KeyboardEvent('keyup', ev)); } catch (e) {}
                    return true;
                    """,
                    editor
                ))
            except Exception:
                enter_sent = False
            if enter_sent:
                _dm_humanized_idle(tab, 0.06, 0.16, "私信发送Enter兜底后")
                if _composer_cleared(editor):
                    return True, ""
                if _confirm_dm_message_sent(tab, before_counts, probes, wait_sec=DM_SEND_CONFIRM_WAIT_SEC):
                    return True, ""
            last_err = "发送按钮未出现或未激活，且Enter兜底未确认发送"

        # 兜底：直接用 DOM 点击私信发送按钮
        _dm_humanized_idle(tab, 0.06, 0.18, "私信发送DOM兜底前")
        try:
            clicked = tab.run_js(
                """
                const selectors = [
                  'button[data-testid="dm-composer-send-button"]',
                  '[data-testid="dm-composer-send-button"]',
                  'button[data-testid*="dm-composer-send"]',
                  '[data-testid*="dm-composer-send"]',
                  '[data-testid="dmComposerSendButton"]',
                  'button[data-testid="dmComposerSendButton"]',
                  'button[aria-label*="Send"]',
                  'button[aria-label*="发送"]',
                  '[role="button"][aria-label*="Send"]',
                  '[role="button"][aria-label*="发送"]',
                ];
                for (const s of selectors) {
                  const nodes = Array.from(document.querySelectorAll(s));
                  for (const el of nodes) {
                    const style = window.getComputedStyle(el);
                    const hidden = style.display === 'none' || style.visibility === 'hidden';
                    const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
                    if (!hidden && !disabled) {
                      el.click();
                      return true;
                    }
                  }
                }
                return false;
                """
            )
            if clicked:
                _dm_humanized_idle(tab, 0.06, 0.16, "私信发送DOM兜底后")
                if _composer_cleared(editor):
                    return True, ""
                if _confirm_dm_message_sent(tab, before_counts, probes, wait_sec=DM_SEND_CONFIRM_WAIT_SEC):
                    log_headless_debug("DOM发送后已确认消息落库，按成功处理")
                    return True, ""
                if DM_ASSUME_SUCCESS_AFTER_CLICK:
                    log_to_ui("warn", "⚠️ 私信DOM发送后状态不确定，但当前配置禁止按成功处理")
                last_err = "DOM点击发送后输入框未清空"
                continue
        except Exception:
            pass

        if not last_err:
            last_err = "未找到可点击的私信发送按钮（可能输入框内容被清空）"

        time.sleep(random.uniform(0.06, 0.16))

        _capture_runtime_diagnostic(
        tab,
        "send_dm_message_failed",
        err=last_err,
        selectors=editor_selectors + send_btn_selectors,
        extra={
            "max_attempts": max_attempts,
            "message_len": len(dm_text),
            "headless_mode": bool(headless_mode),
            "dm_error_class": _classify_dm_error_text(last_err),
            "dm_url_ok": bool(session_state.get("url_ok")),
            "dm_conversation_ok": bool(session_state.get("conversation_ok")),
            "dm_editor_ok": bool(session_state.get("editor_ok")),
            "dm_send_btn_enabled": bool(session_state.get("send_button_enabled")),
        }
    )
    return False, last_err


def _send_dm_message_with_retry(tab, text, handle=""):
    """私信发送增强重试（无头模式更激进），必要时重开私信编辑器。"""
    max_attempts = DM_SEND_RETRY_HEADLESS if headless_mode else DM_SEND_RETRY_NORMAL
    last_err = "发送私信失败"
    handle_norm = normalize_handle(handle)
    last_session_state = {}

    for attempt in range(1, max_attempts + 1):
        if handle_norm:
            session_state = _ensure_dm_session_ready_for_handle(tab, handle_norm, allow_reopen=True)
            last_session_state = dict(session_state or {})
            if not session_state.get("ready"):
                last_err = (
                    "E_DM_CONTEXT_LOST: 当前页面不在可发送私信会话上下文，"
                    f"url_ok={int(bool(session_state.get('url_ok')))}, "
                    f"conversation_ok={int(bool(session_state.get('conversation_ok')))}, "
                    f"editor_ok={int(bool(session_state.get('editor_ok')))}"
                )
                if attempt < max_attempts:
                    _dm_humanized_idle(tab, 0.22, 0.56, f"私信上下文恢复失败等待{attempt}")
                    continue
                break

        ok, err = _send_dm_message(tab, text)
        if ok:
            return True, ""
        last_err = str(err or last_err)
        log_headless_debug(f"私信发送重试触发 attempt={attempt}/{max_attempts}, err={last_err}")
        if attempt >= max_attempts:
            break

        _prepare_reply_prompt_guard(tab, f"私信重试准备{attempt}")
        need_reopen = _is_dm_context_or_editor_error_text(last_err)
        if need_reopen and handle_norm:
            _dm_humanized_idle(tab, 0.08, 0.18, f"私信重试{attempt}重开编辑器前")
            _open_dm_editor_for_handle(tab, handle_norm)
        if _is_dm_soft_send_error_text(last_err):
            _dm_humanized_idle(tab, DM_SOFT_RETRY_MIN_SEC, DM_SOFT_RETRY_MAX_SEC, f"私信重试{attempt}快速间隔")
        else:
            _dm_humanized_idle(tab, 0.16, 0.42, f"私信重试{attempt}间隔")

    _capture_runtime_diagnostic(
        tab,
        "send_dm_with_retry_failed",
        err=last_err,
        selectors=[
            'css:textarea[data-testid="dm-composer-textarea"]',
            'css:[data-testid="dmComposerTextInput"]',
            'css:[data-testid="dm-composer-send-button"]',
            'css:[data-testid="dmComposerSendButton"]',
        ],
        extra={
            "handle": handle_norm,
            "max_attempts": max_attempts,
            "message_len": len(str(text or "")),
            "headless_mode": bool(headless_mode),
            "dm_error_class": _classify_dm_error_text(last_err),
            "dm_url_ok": bool(last_session_state.get("url_ok")),
            "dm_conversation_ok": bool(last_session_state.get("conversation_ok")),
            "dm_editor_ok": bool(last_session_state.get("editor_ok")),
            "dm_send_btn_enabled": bool(last_session_state.get("send_button_enabled")),
        }
    )
    return False, last_err


def _is_dm_closed_error_text(dm_err_text):
    dm_err_text = str(dm_err_text or "")
    return any(k in dm_err_text for k in [
        "不可私信",
        "未开放私信",
        "无法接收私信",
        "无法向该用户发送私信",
        "不能给该用户发私信",
        "当前不可私信",
        "资料页无私信入口",
        "cannot send direct messages",
        "can't be messaged",
        "unable to message",
    ])


def _is_dm_soft_send_error_text(err_text):
    """发送阶段软错误：更适合当前会话快速重试，不进入慢恢复链路。"""
    text = str(err_text or "")
    if not text:
        return False
    keywords = [
        "发送按钮未出现",
        "未找到可点击的私信发送按钮",
        "输入后文本未稳定写入编辑器",
        "输入后链接状态未稳定写入编辑器",
        "点击私信发送后输入框未清空",
        "DOM点击发送后输入框未清空",
        "Enter兜底未确认发送",
        "输入私信内容失败",
    ]
    return any(k in text for k in keywords)


def _is_dm_context_or_editor_error_text(err_text):
    """上下文/编辑器错误：适合重开编辑器或重建页面恢复。"""
    text = str(err_text or "")
    if not text:
        return False
    keywords = [
        "未找到私信输入框",
        "E_DM_CONTEXT_LOST",
        "当前页面不在私信上下文",
        "当前页面不在可发送私信会话上下文",
        "打开私信失败",
        "未打开私信输入框",
        "E_DM_EDITOR_NOT_FOUND",
        "E_DM_WRONG_COMPOSER_TARGET",
        "映射异常",
    ]
    return any(k in text for k in keywords)


def _is_dm_context_url(url_text):
    low = str(url_text or "").lower()
    return ("/messages" in low) or ("/i/chat/" in low)


def _classify_dm_error_text(err_text):
    text = str(err_text or "")
    if not text:
        return "unknown"
    if _is_dm_closed_error_text(text):
        return "closed"
    if _is_dm_soft_send_error_text(text):
        return "soft_send"
    if _is_dm_context_or_editor_error_text(text):
        return "context"
    return "unknown"


def _is_dm_llm_fallback_allowed(err_code, err_detail):
    code = str(err_code or "").strip().upper()
    detail = str(err_detail or "").strip().lower()
    if not code.startswith("E_DM_LLM_"):
        return False
    if code in {"E_DM_LLM_TEMPLATE_EMPTY", "E_DM_TEXT_EMPTY"}:
        return False
    # 网络/可用性波动、模型服务异常时允许降级到模板直发
    network_hints = [
        "no route to host",
        "dial tcp",
        "timed out",
        "timeout",
        "connection refused",
        "temporarily unavailable",
        "http 400",
        "http 401",
        "http 403",
        "http 404",
        "http 429",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
    ]
    return any(k in detail for k in network_hints) or code in {
        "E_DM_LLM_GENERATE_FAILED",
        "E_DM_LLM_TIMEOUT",
        "E_DM_LLM_NOT_READY",
    }


def _read_dm_session_state(tab, handle=""):
    """读取当前私信会话状态，用于发送前闸门判断。"""
    handle_norm = normalize_handle(handle)
    try:
        url = str(tab.url or "")
    except Exception:
        url = ""
    url_ok = _is_dm_context_url(url)
    out = {
        "url": url,
        "url_ok": bool(url_ok),
        "conversation_ok": bool(not handle_norm),
        "editor_ok": False,
        "send_button_present": False,
        "send_button_enabled": False,
        "ready": False,
    }
    try:
        state = tab.run_js(
            """
            const target = String(arguments[0] || '').toLowerCase();
            const lower = (v) => String(v || '').toLowerCase();
            const text = lower((document.body && document.body.innerText) ? document.body.innerText : '');
            const conversationOk = !target || text.includes('@' + target) || text.includes(target);
            const editor = document.querySelector(
              'textarea[data-testid="dm-composer-textarea"],textarea[placeholder="Message"],textarea[placeholder*="消息"],[data-testid="dmComposerTextInput"] [contenteditable]:not([contenteditable="false"]),div[role="textbox"][contenteditable]:not([contenteditable="false"]),[data-testid="dmComposerTextInput"] [contenteditable="true"],div[role="textbox"][contenteditable="true"]'
            );
            const sendBtn = document.querySelector(
              'button[data-testid="dm-composer-send-button"],[data-testid="dm-composer-send-button"],button[data-testid*="dm-composer-send"],[data-testid*="dm-composer-send"],[data-testid="dmComposerSendButton"],button[data-testid="dmComposerSendButton"],button[aria-label*="发送"],button[aria-label*="Send"]'
            );
            const sendDisabled = !!(sendBtn && (sendBtn.disabled || sendBtn.getAttribute('aria-disabled') === 'true'));
            return {
              conversationOk: !!(conversationOk || editor),
              editorOk: !!editor,
              sendPresent: !!sendBtn,
              sendEnabled: !!(sendBtn && !sendDisabled),
            };
            """,
            handle_norm,
        ) or {}
        out["conversation_ok"] = bool(state.get("conversationOk", out["conversation_ok"]))
        out["editor_ok"] = bool(state.get("editorOk"))
        out["send_button_present"] = bool(state.get("sendPresent"))
        out["send_button_enabled"] = bool(state.get("sendEnabled"))
    except Exception:
        pass
    out["ready"] = bool(out["url_ok"] and out["editor_ok"] and out["conversation_ok"])
    return out


def _ensure_dm_session_ready_for_handle(tab, handle, allow_reopen=True):
    """发送前会话闸门：保证在目标私信会话中且编辑器可用。"""
    handle_norm = normalize_handle(handle)
    state = _read_dm_session_state(tab, handle_norm)
    if state.get("ready"):
        return state
    if not allow_reopen:
        return state
    editor, err = _open_dm_editor_for_handle(tab, handle_norm)
    state2 = _read_dm_session_state(tab, handle_norm)
    state2["reopen_err"] = str(err or "")
    state2["reopen_editor_found"] = bool(editor)
    state2["ready"] = bool(state2.get("url_ok") and state2.get("editor_ok") and state2.get("conversation_ok"))
    return state2


def _ensure_dm_context_for_handle(tab, handle):
    """保证当前页面处于可发送私信的上下文，避免流程被跳回主页。"""
    handle_norm = normalize_handle(handle)
    try:
        current_url = str(tab.url or "")
    except Exception:
        current_url = ""
    if _is_dm_context_url(current_url):
        return True
    if not handle_norm:
        return False

    editor, dm_err = _open_dm_editor_for_handle(tab, handle_norm)
    if editor:
        return True
    log_to_ui(
        "debug",
        f"📨 DM上下文守卫未恢复会话: handle=@{handle_norm}, err={dm_err or '-'}, url={current_url or '-'}"
    )
    return False


def _confirm_dm_closed_dual_stage(tab, handle):
    """
    双阶段确认“不可私信”：
    - strict_hint_only: 看到明确禁发文案即判定关闭
    - dual_stage_confirm: 在忽略缓存后再探测一次，仍命中关闭才确认
    """
    handle_norm = normalize_handle(handle)
    if not handle_norm:
        return False, "missing_handle"

    if DM_CLOSED_DETECT_MODE == "strict_hint_only":
        return True, "strict_hint_only"

    _clear_dm_unavailable_cache(handle_norm)
    try:
        retry_editor, retry_err = _open_dm_editor_for_handle(
            tab,
            handle_norm,
            ignore_cached_unavailable=True
        )
    except Exception as e:
        retry_editor, retry_err = None, f"confirm_exception:{e}"

    if retry_editor:
        return False, "editor_opened_on_confirm"

    retry_err_text = str(retry_err or "")
    if _is_dm_closed_error_text(retry_err_text):
        return True, "closed_hint_confirmed_twice"

    return False, f"confirm_not_closed:{retry_err_text[:80]}"


def _run_dm_send_sequence_once(
    tab,
    dm_handle,
    share_link,
    dm_text,
    mark_func=None,
    progress=None,
    dm_text_supplier=None,
):
    """执行一次完整私信发送（开私信 -> 发链接 -> 发文案）。"""
    if progress is None:
        progress = {"link_sent": False, "text_sent": False}
    dm_editor, dm_err = _open_dm_editor_for_handle(tab, dm_handle)
    if not dm_editor:
        dm_err_text = str(dm_err or "")
        if _is_dm_closed_error_text(dm_err_text):
            confirmed_closed, close_reason = _confirm_dm_closed_dual_stage(tab, dm_handle)
            if confirmed_closed:
                log_to_ui("info", f"📨 私信关闭已确认: @{normalize_handle(dm_handle)} ({close_reason})")
                return False, dm_err_text, True
            log_to_ui(
                "warn",
                f"⚠️ 私信关闭判定未通过二次确认，改为重试队列: @{normalize_handle(dm_handle)} ({close_reason})"
            )
            return False, f"E_DM_EDITOR_NOT_FOUND: 二次确认未判定关闭 ({close_reason})", False
        return False, f"打开私信失败: {dm_err}", False
    if callable(mark_func):
        mark_func("open_dm")

    if not progress.get("link_sent"):
        ok_dm_1, err_dm_1 = _send_dm_message_with_retry(tab, share_link, handle=dm_handle)
        if not ok_dm_1:
            return False, f"发送私信链接失败: {err_dm_1}", False
        progress["link_sent"] = True
        if callable(mark_func):
            mark_func("send_dm_link")
        log_to_ui("debug", "📨 已发送私信链接")
    else:
        log_to_ui("debug", "📨 跳过重复发送私信链接（本流程已成功发送）")

    if not progress.get("text_sent"):
        dm_text_final = _sanitize_dm_message_text(dm_text)
        llm_fallback_used = False
        if callable(dm_text_supplier):
            ok_gen, dm_text_generated, gen_meta = dm_text_supplier()
            if not ok_gen:
                err_code = str((gen_meta or {}).get("error_code", "E_DM_LLM_GENERATE_FAILED") or "E_DM_LLM_GENERATE_FAILED")
                err_detail = str((gen_meta or {}).get("error_detail", "") or "第二条私信文案生成失败")
                if DM_LLM_DOWN_FALLBACK_TEMPLATE and dm_text_final and _is_dm_llm_fallback_allowed(err_code, err_detail):
                    llm_fallback_used = True
                    log_to_ui(
                        "warn",
                        f"⚠️ 二条私信LLM不可用，已降级发送模板文案: {err_code}"
                    )
                else:
                    return False, f"{err_code}: {err_detail}", False
            else:
                dm_text_final = _sanitize_dm_message_text(dm_text_generated)
        if not dm_text_final:
            return False, "E_DM_TEXT_EMPTY: 第二条私信文案为空", False
        _prepare_reply_prompt_guard(tab, "第二条私信前")
        _humanized_gap_between_dm_messages(tab)
        ok_dm_2, err_dm_2 = _send_dm_message_with_retry(tab, dm_text_final, handle=dm_handle)
        if not ok_dm_2:
            return False, f"发送私信文案失败: {err_dm_2}", False
        progress["text_sent"] = True
        if callable(mark_func):
            mark_func("send_dm_text")
        if llm_fallback_used:
            log_to_ui("debug", "📨 已发送私信文案（模板降级）")
        else:
            log_to_ui("debug", "📨 已发送私信文案")
    else:
        log_to_ui("debug", "📨 跳过重复发送私信文案（本流程已成功发送）")
    return True, "", False


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
    """私信发送恢复策略：原标签页 -> 重建标签页 -> 重启浏览器 -> 有头兜底。"""
    global headless_mode
    handle_norm = normalize_handle(dm_handle)
    last_err = "发送私信失败"
    work_tab = tab
    entered_critical = _enter_dm_critical("dm_send_recovery")
    progress = dict(progress or {})
    progress.setdefault("link_sent", False)
    progress.setdefault("text_sent", False)
    context_failure_count = 0

    strategies = [("当前标签页", lambda: work_tab)]
    if (not best_effort) and DM_RECOVERY_ENABLE_RECREATE_TAB:
        strategies.append(("重建回复标签页", lambda: ensure_reply_work_tab(force_recreate=True)))

    try:
        for idx, (label, tab_provider) in enumerate(strategies, start=1):
            try:
                work_tab = tab_provider()
            except Exception as e:
                last_err = f"{label}失败: {e}"
                log_to_ui("warn", f"⚠️ 私信恢复步骤失败({idx}/{len(strategies)}): {last_err}")
                continue

            ok, err, dm_closed = _run_dm_send_sequence_once(
                work_tab,
                handle_norm,
                share_link,
                dm_text,
                mark_func=mark_func,
                progress=progress,
                dm_text_supplier=dm_text_supplier,
            )
            if ok:
                if idx > 1:
                    log_to_ui("success", f"✅ 私信发送已通过恢复策略成功: {label}")
                return True, "", False, work_tab
            if dm_closed:
                return False, err, True, work_tab

            last_err = str(err or last_err)
            err_class = _classify_dm_error_text(last_err)
            if err_class == "context":
                context_failure_count += 1
            else:
                context_failure_count = 0

            log_to_ui("warn", f"⚠️ 私信发送失败({label}): {last_err}")
            if _is_dm_soft_send_error_text(last_err):
                log_to_ui("debug", f"📨 软错误快速返回（跳过慢恢复）: {last_err[:80]}")
                return False, last_err, False, work_tab
            _capture_runtime_diagnostic(
                work_tab,
                f"dm_recovery_{idx}",
                err=last_err,
                selectors=[
                    'css:[data-testid="sendDMFromProfile"]',
                    'css:[data-testid="sendDM"]',
                    'css:textarea[data-testid="dm-composer-textarea"]',
                    'css:[data-testid="dmComposerTextInput"]',
                    'css:[data-testid="dm-composer-send-button"]',
                ],
                extra={
                    "strategy": label,
                    "strategy_idx": idx,
                    "headless_mode": bool(headless_mode),
                    "handle": handle_norm,
                    "message_len": len(str(dm_text or "")),
                    "progress": dict(progress),
                    "dm_error_class": err_class,
                    "dm_context_failure_count": context_failure_count,
                }
            )

        if (
            (not best_effort)
            and DM_RECOVERY_ENABLE_RESTART_BROWSER
            and context_failure_count >= DM_CONTEXT_RESTART_THRESHOLD
        ):
            try:
                log_to_ui("warn", f"⚠️ 触发上下文阈值恢复：重启浏览器并重建标签页（count={context_failure_count}）")
                restart_global_browser()
                work_tab = ensure_reply_work_tab(force_recreate=True)
                ok, err, dm_closed = _run_dm_send_sequence_once(
                    work_tab,
                    handle_norm,
                    share_link,
                    dm_text,
                    mark_func=mark_func,
                    progress=progress,
                    dm_text_supplier=dm_text_supplier,
                )
                if ok:
                    return True, "", False, work_tab
                if dm_closed:
                    return False, err, True, work_tab
                last_err = str(err or last_err)
                _capture_runtime_diagnostic(
                    work_tab,
                    "dm_recovery_restart_failed",
                    err=last_err,
                    selectors=[
                        'css:[data-testid="sendDMFromProfile"]',
                        'css:textarea[data-testid="dm-composer-textarea"]',
                        'css:[data-testid="dm-composer-send-button"]',
                    ],
                    extra={
                        "headless_mode": bool(headless_mode),
                        "handle": handle_norm,
                        "dm_error_class": _classify_dm_error_text(last_err),
                        "dm_context_failure_count": context_failure_count,
                    }
                )
            except Exception as e:
                last_err = f"重启浏览器恢复异常: {e}"

        if (not best_effort) and headless_mode and DM_RECOVERY_ENABLE_HEADFUL_FALLBACK:
            display_ok = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
            if DM_RECOVERY_HEADFUL_REQUIRE_DISPLAY and not display_ok:
                log_to_ui("warn", "⚠️ 有头兜底已启用但未检测到 DISPLAY，跳过本次有头兜底")
            else:
                prev_headless = bool(headless_mode)
                switched = False
                try:
                    if prev_headless:
                        headless_mode = False
                        switched = True
                        log_to_ui("warn", "⚠️ 无头私信多次失败，临时切换有头模式执行本条私信兜底")
                        restart_global_browser()
                    work_tab = ensure_reply_work_tab(force_recreate=True)
                    ok, err, dm_closed = _run_dm_send_sequence_once(
                        work_tab,
                        handle_norm,
                        share_link,
                        dm_text,
                        mark_func=mark_func,
                        progress=progress,
                        dm_text_supplier=dm_text_supplier,
                    )
                    if ok:
                        log_to_ui("success", "✅ 有头兜底私信发送成功")
                        return True, "", False, work_tab
                    if dm_closed:
                        return False, err, True, work_tab
                    last_err = str(err or last_err)
                    _capture_runtime_diagnostic(
                        work_tab,
                        "dm_recovery_headful_fallback_failed",
                        err=last_err,
                        selectors=[
                            'css:[data-testid="sendDMFromProfile"]',
                            'css:textarea[data-testid="dm-composer-textarea"]',
                            'css:[data-testid="dm-composer-send-button"]',
                        ],
                        extra={"headless_mode": bool(headless_mode), "handle": handle_norm}
                    )
                except Exception as e:
                    last_err = f"有头兜底异常: {e}"
                    log_to_ui("warn", f"⚠️ {last_err}")
                finally:
                    if switched:
                        headless_mode = prev_headless
                        try:
                            restart_global_browser()
                            log_to_ui("info", "🔄 私信兜底结束，已恢复无头浏览器运行")
                        except Exception as restore_err:
                            log_to_ui("warn", f"⚠️ 恢复无头浏览器失败，请手动重启: {restore_err}")
        return False, last_err, False, work_tab
    finally:
        if entered_critical:
            _leave_dm_critical()


def send_notification_reply(item, message, dm_message=""):
    """针对通知记录发送回复。"""
    global last_reply_prepare_refresh_ts
    if not global_token.strip():
        return False, "请先配置并验证 auth_token 后再回复"

    status_id = extract_status_id_from_notification_item(item)
    if not status_id:
        return False, "该通知缺少可回复的状态ID（可能是兜底通知记录）"

    handle_hint = item.get("handle", "")
    task_key = str(item.get("key", "") or "").strip()

    with reply_action_lock:
        _throttle_reply_action_if_needed()
        _set_reply_flow_active(True)
        flow_started_at = time.perf_counter()
        stage_marks = {}

        def _mark(stage_name):
            stage_marks[stage_name] = time.perf_counter() - flow_started_at
            stage_map = {
                "match_card": "match_card",
                "prepare_share_link": "share_link_ready",
                "send_reply": "reply_sent",
                "open_dm": "dm_opening",
                "send_dm_link": "dm_link_sent",
                "send_dm_text": "dm_text_sent",
                "fallback_reply": "dm_closed_confirmed",
            }
            mapped = stage_map.get(str(stage_name or "").strip())
            if mapped:
                _mark_stage(mapped)

        def _mark_stage(stage_name, error="", retry_at=0.0, extra=None, save=False):
            if not task_key:
                return
            _update_notify_flow_state(
                task_key,
                stage=stage_name,
                error=error,
                retry_at=retry_at,
                extra=extra,
                save=save,
            )

        try:
            tab = ensure_reply_work_tab()
        except Exception as e:
            _set_reply_flow_active(False)
            return False, f"回复工作标签页初始化失败: {e}"

        try:
            _prepare_reply_prompt_guard(tab, "回复流程启动")
            log_to_ui("info", f"💬 开始执行通知回复(复用全局浏览器): {handle_hint} -> status {status_id}")
            _, row_live = _find_pending_notify_item_by_key(task_key)
            row_snapshot = dict(row_live or {})
            resume_stage = _resolve_notify_resume_stage(row_snapshot)
            if resume_stage == "reply_pending":
                _mark_stage("reply_pending", error="", extra={"notify_resume_stage": resume_stage})
            else:
                # 断点续跑场景保持原阶段，不回退到 reply_pending，避免重复发消息。
                _mark_stage(resume_stage, error="", retry_at=0.0, extra={"notify_resume_stage": resume_stage})

            saved_share_link = _normalize_dm_share_link(
                str(row_snapshot.get("notify_share_link", "") or "").strip(),
                status_id=status_id,
                status_handle=item.get("status_handle", "") or item.get("handle", ""),
                fallback_url=_get_status_link_from_item(item),
            )
            need_reply = not _notify_stage_at_least(resume_stage, "reply_sent")
            need_share = not _notify_stage_at_least(resume_stage, "share_link_ready")
            dm_progress = {
                "link_sent": _notify_stage_at_least(resume_stage, "dm_link_sent"),
                "text_sent": _notify_stage_at_least(resume_stage, "dm_text_sent"),
            }
            if dm_progress["text_sent"] and (not need_reply) and (not need_share):
                _mark_stage("done", error="", retry_at=0.0, save=True)
                return True, ""

            _reply_humanized_idle(tab, 0.18, 0.42, "回复流程启动")

            try:
                current_url = str(tab.url or "")
            except Exception:
                current_url = ""
            if "x.com/notifications" not in current_url:
                tab.get("https://x.com/notifications")
                _wait_document_ready(tab, timeout=5.0)
                _reply_humanized_idle(tab, 0.22, 0.52, "进入通知页后稳定等待")
            log_to_ui("debug", "💬 已进入通知页，准备定位目标通知卡片")
            try:
                tab.wait.ele_displayed('tag:article', timeout=5)
            except Exception:
                pass

            def _prepare_notifications_view(force_refresh=False):
                """准备通知视图；默认不刷新，仅在必要时刷新。"""
                global last_reply_prepare_refresh_ts
                did_refresh = False
                _prepare_reply_prompt_guard(tab, "准备通知视图")
                if force_refresh:
                    now_ts = time.time()
                    should_refresh = (now_ts - last_reply_prepare_refresh_ts) >= REPLY_PREPARE_REFRESH_MIN_GAP_SEC
                    if should_refresh:
                        try:
                            tab.refresh()
                            did_refresh = True
                            last_reply_prepare_refresh_ts = now_ts
                            _reply_humanized_idle(tab, 0.35, 0.9, "通知页刷新后等待")
                        except Exception:
                            pass
                    else:
                        log_to_ui("debug", "💬 跳过重复刷新通知页（风控保护）")

                try:
                    tabs = tab.eles('css:[role="tab"]', timeout=0.9)
                    for notify_tab in tabs:
                        tab_text = (notify_tab.text or "").strip().lower()
                        if tab_text not in {'全部', 'all'}:
                            continue
                        is_selected = (notify_tab.attr('aria-selected') or '').lower() == 'true'
                        if not is_selected:
                            try:
                                notify_tab.click()
                            except Exception:
                                tab.run_js('arguments[0].click()', notify_tab)
                            _reply_humanized_idle(tab, 0.24, 0.52, "通知Tab切换后等待")
                        break
                except Exception:
                    pass

                if force_refresh or did_refresh:
                    try:
                        tab.run_js('window.scrollTo(0, 0);')
                    except Exception:
                        pass

            def _match_target_card():
                """在通知页匹配目标卡片并返回匹配结果。"""
                def _should_allow_status_fallback():
                    """根据策略和意向强度判断是否允许回退到 status 页面。"""
                    policy = str(REPLY_STATUS_FALLBACK_POLICY or "high_priority_only").strip().lower()
                    if policy == "always":
                        return True, "policy=always"
                    if policy == "off":
                        return False, "policy=off"

                    intent_level = str(item.get("intent_level", "") or "").strip().lower()
                    try:
                        intent_score = int(float(item.get("intent_score", 0) or 0))
                    except Exception:
                        intent_score = 0

                    force_notify_raw = item.get("force_notify", False)
                    if isinstance(force_notify_raw, str):
                        force_notify = force_notify_raw.strip().lower() in {"1", "true", "yes", "y", "on"}
                    else:
                        force_notify = bool(force_notify_raw)
                    if force_notify:
                        return True, "force_notify=true"

                    if intent_level == "high":
                        return True, "intent_level=high"

                    if intent_score >= int(REPLY_STATUS_FALLBACK_MIN_SCORE):
                        return True, f"intent_score={intent_score}"

                    strong_signal_keys = {
                        "short_reply_intent_signal",
                        "performance_consult_signal",
                        "business_consult_signal",
                        "force_intent_keyword",
                        "product_consult_signal",
                        "product_contact_combo",
                    }
                    raw_signals = item.get("intent_signals", [])
                    if not isinstance(raw_signals, (list, tuple)):
                        raw_signals = [raw_signals]
                    signal_hits = []
                    for sig in raw_signals:
                        sig_norm = str(sig or "").strip().lower()
                        if sig_norm in strong_signal_keys and sig_norm not in signal_hits:
                            signal_hits.append(sig_norm)
                    if signal_hits:
                        return True, f"signal={'|'.join(signal_hits[:3])}"

                    content_low = _normalize_content_for_filter(item.get("content", "")).lower()
                    keyword_hits = _find_keyword_hits(content_low, INTENT_FORCE_NOTIFY_KEYWORDS)
                    if keyword_hits:
                        return True, f"keyword={'|'.join(keyword_hits[:3])}"

                    return False, (
                        f"policy=high_priority_only, unmet "
                        f"(force={force_notify}, level={intent_level or '-'}, score={intent_score})"
                    )

                def _fallback_match_on_status_page():
                    """通知页匹配失败时，回退到 status 会话页定位评论者卡片并回复。"""
                    fallback_urls = []
                    for cand in [
                        str(item.get("status_url", "") or "").strip(),
                        _get_status_link_from_item(item),
                        (
                            f"https://x.com/{normalize_handle(item.get('status_handle', ''))}/status/{status_id}"
                            if status_id and normalize_handle(item.get("status_handle", ""))
                            else ""
                        ),
                        (f"https://x.com/i/status/{status_id}" if status_id else ""),
                    ]:
                        c = str(cand or "").strip()
                        if not c:
                            continue
                        if c.startswith("/"):
                            c = f"https://x.com{c}"
                        elif c.startswith("x.com/"):
                            c = f"https://{c}"
                        if c not in fallback_urls:
                            fallback_urls.append(c)

                    if not fallback_urls:
                        return None, None, 0, None, None, "通知页未命中，且缺少可用 status 链接兜底"

                    for idx, url in enumerate(fallback_urls, start=1):
                        _prepare_reply_prompt_guard(tab, f"会话页兜底匹配{idx}")
                        try:
                            tab.get(url)
                            _wait_document_ready(tab, timeout=5.2)
                            _reply_humanized_idle(tab, 0.24, 0.56, f"会话页兜底加载{idx}")
                        except Exception:
                            continue

                        try:
                            tab.wait.ele_displayed('tag:article', timeout=4)
                        except Exception:
                            pass

                        for sweep in range(3):
                            target_article_fb, target_score_fb = _match_reply_target_article(
                                tab,
                                status_id,
                                item.get("handle", ""),
                                item.get("content", ""),
                            )
                            if target_article_fb and target_score_fb >= 120:
                                try:
                                    target_reply_btn_fb = target_article_fb.ele('css:[data-testid="reply"]', timeout=0.6)
                                except Exception:
                                    target_reply_btn_fb = None
                                if target_reply_btn_fb and target_reply_btn_fb.states.is_displayed:
                                    matched_handle_fb = normalize_handle(
                                        item.get("status_handle", "") or item.get("handle", "")
                                    )
                                    matched_status_id_fb = str(status_id or "")
                                    log_to_ui(
                                        "info",
                                        f"💬 通知页未命中，已回退会话页定位成功(score={target_score_fb}, url={url})"
                                    )
                                    return (
                                        target_article_fb,
                                        target_reply_btn_fb,
                                        target_score_fb,
                                        matched_handle_fb,
                                        matched_status_id_fb,
                                        "",
                                    )

                            try:
                                tab.run_js('window.scrollBy(0, 760);')
                                _reply_humanized_idle(tab, 0.16, 0.4, f"会话页兜底滚动{sweep + 1}")
                            except Exception:
                                pass

                    return None, None, 0, None, None, "未在通知页定位到目标评论卡片，且会话页兜底未命中"

                target_article = None
                target_reply_btn = None
                target_score = 0
                required_score = 260 if status_id else 120
                for attempt in range(3):
                    _prepare_reply_prompt_guard(tab, f"匹配通知卡片尝试{attempt + 1}")
                    if attempt == 2 and not target_article:
                        _prepare_notifications_view(force_refresh=True)
                        log_to_ui("debug", "💬 匹配未命中，执行一次刷新后重试")
                    target_article, target_reply_btn, target_score = _match_notification_card_for_reply(
                        tab,
                        status_id,
                        item.get("handle", ""),
                        item.get("content", "")
                    )
                    if target_article and target_reply_btn and target_score >= required_score:
                        break
                    try:
                        if attempt < 2:
                            tab.run_js('window.scrollBy(0, 640);')
                        else:
                            tab.run_js('window.scrollTo(0, 0);')
                        _reply_humanized_idle(tab, 0.18, 0.46, f"匹配卡片滚动等待{attempt + 1}")
                    except Exception:
                        pass

                if not target_article:
                    allow_fallback, fallback_reason = _should_allow_status_fallback()
                    if not allow_fallback:
                        log_to_ui("debug", f"💬 状态页兜底已跳过: {fallback_reason}")
                        return (
                            None,
                            None,
                            0,
                            None,
                            None,
                            f"未在通知页定位到目标评论卡片（已跳过状态页兜底: {fallback_reason}）",
                        )
                    log_to_ui("debug", f"💬 通知页未命中，执行状态页兜底: {fallback_reason}")
                    return _fallback_match_on_status_page()

                if target_score < required_score:
                    # 通知页低置信度时，尝试会话页兜底，避免通知结构变动导致误丢单。
                    allow_fallback, fallback_reason = _should_allow_status_fallback()
                    if not allow_fallback:
                        log_to_ui(
                            "debug",
                            f"💬 状态页兜底已跳过: {fallback_reason}, score={target_score}, required={required_score}"
                        )
                        return (
                            None,
                            None,
                            target_score,
                            None,
                            None,
                            "通知页命中低置信目标且状态页兜底被策略跳过: "
                            f"{fallback_reason} (score={target_score}, required={required_score})",
                        )
                    log_to_ui(
                        "debug",
                        f"💬 通知页低置信命中，执行状态页兜底: {fallback_reason}, "
                        f"score={target_score}, required={required_score}"
                    )
                    return _fallback_match_on_status_page()

                try:
                    matched_handle, matched_status_id = _extract_notification_status_info(target_article)
                except Exception:
                    matched_handle, matched_status_id = None, None

                return target_article, target_reply_btn, target_score, matched_handle, matched_status_id, ""

            def _send_reply_from_button(target_reply_btn, target_score, reply_text):
                """点击卡片左下角回复并发送文本。"""
                _prepare_reply_prompt_guard(tab, "点击回复入口前")
                _reply_humanized_idle(tab, 0.16, 0.4, "点击回复入口前")
                try:
                    tab.run_js('arguments[0].scrollIntoView({block:"center"});', target_reply_btn)
                except Exception:
                    pass

                clicked_reply, click_reply_err = _click_with_prompt_guard(tab, target_reply_btn, "点击左下角回复按钮")
                if not clicked_reply:
                    return False, click_reply_err
                log_to_ui("debug", f"💬 已点击通知卡片左下角回复按钮(score={target_score})，等待回复输入框")
                _reply_humanized_idle(tab, 0.22, 0.56, "等待回复输入框弹出")

                editor_selectors = [
                    'css:[data-testid="tweetTextarea_0"] [role="textbox"]',
                    'css:[data-testid="tweetTextarea_0"]',
                    'css:div[role="textbox"][contenteditable="true"]',
                ]
                editor = _wait_first_visible(tab, editor_selectors, timeout=4.2, poll=0.1)
                if not editor:
                    return False, "未弹出回复输入框"

                def _read_reply_editor_text():
                    try:
                        val = tab.run_js(
                            """
                            const el = arguments[0];
                            if (!el) return '';
                            if (el.value !== undefined) return String(el.value || '');
                            return String(el.innerText || el.textContent || '');
                            """,
                            editor
                        )
                        return str(val or "")
                    except Exception:
                        return ""

                def _reply_input_stable(expected_text):
                    expected_norm = _normalize_text_for_compare(expected_text)
                    current_norm = _normalize_text_for_compare(_read_reply_editor_text())
                    if not expected_norm:
                        return bool(current_norm)
                    if not current_norm:
                        return False
                    if current_norm == expected_norm:
                        return True
                    if expected_norm in current_norm or current_norm in expected_norm:
                        return True
                    return False

                typed_ok = False
                _prepare_reply_prompt_guard(tab, "填充回复内容前")
                _reply_humanized_idle(tab, 0.14, 0.36, "填充回复内容前")
                try:
                    editor.click()
                except Exception:
                    pass

                try:
                    editor.input(reply_text, clear=True)
                    typed_ok = True
                except Exception:
                    try:
                        tab.run_js(
                            """
                            const el = arguments[0];
                            const text = arguments[1];
                            el.focus();
                            if (el.textContent !== undefined) el.textContent = '';
                            document.execCommand('insertText', false, text);
                            el.dispatchEvent(new Event('input', {bubbles: true}));
                            """,
                            editor,
                            reply_text,
                        )
                        typed_ok = True
                    except Exception:
                        typed_ok = False
                if not typed_ok:
                    return False, "输入回复内容失败"
                if not _reply_input_stable(reply_text):
                    try:
                        tab.run_js(
                            """
                            const el = arguments[0];
                            const text = String(arguments[1] || '');
                            if (!el) return false;
                            el.focus();
                            try {
                              if (el.value !== undefined) {
                                el.value = text;
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                                return true;
                              }
                            } catch (e) {}
                            try {
                              const sel = window.getSelection();
                              const range = document.createRange();
                              range.selectNodeContents(el);
                              sel.removeAllRanges();
                              sel.addRange(range);
                            } catch (e) {}
                            try {
                              document.execCommand('insertText', false, text);
                            } catch (e) {
                              el.textContent = text;
                            }
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                            """,
                            editor,
                            reply_text,
                        )
                    except Exception:
                        pass

                editor_now_text = _read_reply_editor_text()
                if not _reply_input_stable(reply_text):
                    _capture_runtime_diagnostic(
                        tab,
                        "reply_input_not_stable",
                        err="回复框填充后文本未稳定",
                        selectors=editor_selectors + [
                            'css:[data-testid="tweetButton"]',
                            'css:button[data-testid="tweetButton"]',
                            'css:[data-testid="tweetButtonInline"]',
                            'css:button[data-testid="tweetButtonInline"]',
                        ],
                        extra={
                            "status_id": status_id,
                            "handle_hint": handle_hint,
                            "target_score": target_score,
                            "expected_len": len(_normalize_text_for_compare(reply_text)),
                            "current_len": len(_normalize_text_for_compare(editor_now_text)),
                            "current_preview": _normalize_text_for_compare(editor_now_text)[:180],
                        }
                    )
                    return False, f"回复输入后文本未生效(当前长度={len(_normalize_text_for_compare(editor_now_text))})"

                log_to_ui("debug", f"💬 已填充回复内容(len={len(_normalize_text_for_compare(editor_now_text))})")
                _reply_humanized_idle(tab, 0.1, 0.26, "回复输入后等待按钮激活")

                send_btn = None
                send_selectors = [
                    'css:[data-testid="tweetButton"]',
                    'css:button[data-testid="tweetButton"]',
                    'css:[data-testid="tweetButtonInline"]',
                ]
                send_btn = _wait_first_actionable(tab, send_selectors, timeout=1.4, poll=0.08)
                if not send_btn:
                    try:
                        tab.run_js(
                            """
                            const el = arguments[0];
                            const text = String(arguments[1] || '');
                            if (!el) return;
                            el.focus();
                            if (el.textContent !== undefined) el.textContent = text + ' ';
                            el.dispatchEvent(new Event('input', {bubbles: true}));
                            if (el.textContent !== undefined) el.textContent = text;
                            el.dispatchEvent(new Event('input', {bubbles: true}));
                            el.dispatchEvent(new Event('change', {bubbles: true}));
                            """,
                            editor,
                            reply_text,
                        )
                    except Exception:
                        pass
                    _reply_humanized_idle(tab, 0.08, 0.22, "回复发送按钮二次等待")
                    send_btn = _wait_first_actionable(tab, send_selectors, timeout=1.2, poll=0.08)

                if not send_btn:
                    # 兜底：仅在当前回复弹窗上下文里点击发送，避免误点页面其它按钮
                    try:
                        clicked_inline = tab.run_js(
                            """
                            const editor = arguments[0];
                            if (!editor) return false;
                            const isVisible = (el) => {
                              if (!el) return false;
                              const st = window.getComputedStyle(el);
                              if (!st) return false;
                              if (st.display === 'none' || st.visibility === 'hidden') return false;
                              const r = el.getBoundingClientRect();
                              return r.width > 0 && r.height > 0;
                            };
                            const root = editor.closest('[role="dialog"]') || editor.closest('[data-testid*="sheet"]') || document;
                            const selectors = [
                              '[data-testid="tweetButton"]',
                              'button[data-testid="tweetButton"]',
                              '[data-testid="tweetButtonInline"]',
                              'button[data-testid="tweetButtonInline"]',
                            ];
                            for (const s of selectors) {
                              const nodes = Array.from(root.querySelectorAll(s));
                              for (const n of nodes) {
                                if (!isVisible(n)) continue;
                                if (n.disabled || n.getAttribute('aria-disabled') === 'true') continue;
                                n.click();
                                return true;
                              }
                            }
                            return false;
                            """,
                            editor
                        )
                    except Exception:
                        clicked_inline = False
                    if clicked_inline:
                        log_to_ui("debug", "💬 已通过弹窗内DOM兜底点击回复发送按钮")
                        _reply_humanized_idle(tab, 0.08, 0.2, "回复发送后稳定等待")
                        return True, ""
                    _capture_runtime_diagnostic(
                        tab,
                        "reply_send_button_missing",
                        err="回复发送按钮不可用",
                        selectors=editor_selectors + send_selectors + [
                            'css:[role="dialog"]',
                            'css:[role="alertdialog"]',
                        ],
                        extra={
                            "status_id": status_id,
                            "handle_hint": handle_hint,
                            "target_score": target_score,
                            "reply_len": len(_normalize_text_for_compare(reply_text)),
                            "editor_len": len(_normalize_text_for_compare(_read_reply_editor_text())),
                        }
                    )
                    return False, "未找到可点击的右下角回复按钮"

                _reply_humanized_idle(tab, 0.05, 0.14, "点击右下角回复按钮前")
                clicked_send, click_send_err = _click_with_prompt_guard(tab, send_btn, "点击右下角回复发送按钮")
                if not clicked_send:
                    return False, click_send_err
                log_to_ui("debug", "💬 已点击右下角回复按钮")
                _reply_humanized_idle(tab, 0.08, 0.2, "回复发送后稳定等待")
                return True, ""

            target_article = None
            target_reply_btn = None
            target_score = 0
            matched_handle = normalize_handle(item.get("status_handle", "") or item.get("handle", ""))
            matched_status_id = str(status_id or "")

            if need_reply or need_share:
                _prepare_notifications_view(force_refresh=False)
                log_to_ui("debug", "💬 已准备通知视图，开始定位目标通知卡片")
                _reply_humanized_idle(tab, 0.1, 0.26, "定位通知卡片前")

                # 在通知页中定位目标通知卡片（只点该卡片左下角回复）
                target_article, target_reply_btn, target_score, matched_handle, matched_status_id, match_err = _match_target_card()
                if match_err:
                    _capture_runtime_diagnostic(
                        tab,
                        "match_target_card_failed",
                        err=match_err,
                        selectors=['tag:article', 'css:[data-testid="reply"]'],
                        extra={"status_id": status_id, "handle_hint": handle_hint}
                    )
                    return False, match_err
                _mark("match_card")
                _mark_stage("match_card")
                log_to_ui(
                    "debug",
                    f"💬 已定位通知卡片 score={target_score}, status_id={matched_status_id}, handle={matched_handle or ''}"
                )
                _reply_humanized_idle(tab, 0.08, 0.22, "定位卡片后稳定等待")
            else:
                log_to_ui("info", f"🔁 断点续跑：跳过通知卡片匹配（stage={resume_stage}）")

            share_link = str(saved_share_link or "").strip()
            if need_share:
                share_link_fallback = _get_status_link_from_item(item, matched_handle, matched_status_id)
                use_quick_share_link = bool(
                    share_link_fallback and "/status/" in share_link_fallback and _should_use_share_link_quick_path()
                )
                if use_quick_share_link:
                    share_link, share_err = share_link_fallback, ""
                    log_to_ui("debug", "🔗 已启用快速链接路径（长队列稳定模式）")
                else:
                    _prepare_reply_prompt_guard(tab, "复制分享链接前")
                    _reply_humanized_idle(tab, 0.06, 0.18, "复制分享链接前")
                    share_link, share_err = _click_share_copy_link(tab, target_article, share_link_fallback)
                if share_err:
                    log_to_ui("warn", f"⚠️ 分享复制链接失败，使用回退链接: {share_err}")
                if not share_link:
                    _capture_runtime_diagnostic(
                        tab,
                        "share_link_missing",
                        err="无法确定要发送的链接",
                        selectors=[
                            'css:button[aria-label*="分享"]',
                            'css:button[aria-label*="Share"]',
                            'css:[data-testid="share"]',
                        ],
                        extra={"status_id": matched_status_id, "handle": matched_handle}
                    )
                    return False, "无法确定要发送的链接"
                # 直接使用复制得到的链接，不做手动拼接；只做最小格式清洗
                share_link_raw = str(share_link or "").strip()
                m_url = re.search(r'https?://[^\s<>"\']+', share_link_raw, flags=re.IGNORECASE)
                if m_url:
                    share_link = m_url.group(0).strip()
                elif share_link_raw.startswith("x.com/"):
                    share_link = f"https://{share_link_raw}"
                elif share_link_raw.startswith("/"):
                    share_link = f"https://x.com{share_link_raw}"
                else:
                    share_link = (share_link_raw.split() or [""])[0].strip()
                if not re.match(r'^https?://', share_link, flags=re.IGNORECASE):
                    return False, f"复制链接格式异常: {share_link[:80]}"
                _mark("prepare_share_link")
                _mark_stage("share_link_ready", extra={"notify_share_link": share_link}, save=True)
                log_to_ui("debug", f"🔗 已准备分享链接: {share_link}")
                _reply_humanized_idle(tab, 0.08, 0.2, "发送回复前")
            else:
                share_link = _normalize_dm_share_link(
                    share_link,
                    status_id=matched_status_id or status_id,
                    status_handle=matched_handle or item.get("handle", ""),
                    fallback_url=_get_status_link_from_item(item, matched_handle, matched_status_id),
                )
                if not share_link:
                    return False, "断点续跑缺少可用分享链接，请重新执行本条通知"
                log_to_ui("info", f"🔁 断点续跑：复用已生成链接（stage={resume_stage}）")

            if need_reply:
                ok_reply, err_reply = _send_reply_from_button(target_reply_btn, target_score, message)
                if not ok_reply:
                    return False, err_reply
                _mark("send_reply")
                _mark_stage("reply_sent", extra={"notify_share_link": share_link}, save=True)
            else:
                log_to_ui("info", f"🔁 断点续跑：跳过公开回复发送（stage={resume_stage}）")

            dm_handle = item.get("handle", "")
            dm_template_text = _sanitize_dm_message_text(dm_message)
            if not dm_template_text:
                dm_template_text = (dm_message_templates[0] if dm_message_templates else DM_FOLLOWUP_TEXT)
            dm_template_text = _sanitize_dm_message_text(dm_template_text)

            def _build_dm_text_supplier():
                def _supplier():
                    if not DM_LLM_REWRITE_ENABLED:
                        return True, dm_template_text, {
                            "error_code": "",
                            "error_detail": "",
                            "llm_used": False,
                            "latency_ms": 0,
                        }
                    _mark_stage(
                        "dm_text_generating",
                        error="",
                        extra={
                            "notify_share_link": share_link,
                            "notify_dm_template_text": dm_template_text,
                            "notify_dm_llm_used": True,
                        },
                        save=True,
                    )
                    ok_gen, dm_text_generated, meta = _generate_dm_text_with_llm(dm_template_text)
                    meta = meta or {}
                    if ok_gen:
                        _update_notify_flow_state(
                            task_key,
                            stage="dm_text_generating",
                            error="",
                            retry_at=0.0,
                            extra={
                                "notify_share_link": share_link,
                                "notify_dm_template_text": dm_template_text,
                                "notify_dm_text_generated": dm_text_generated,
                                "notify_dm_llm_used": bool(meta.get("llm_used", True)),
                                "notify_dm_llm_latency_ms": int(meta.get("latency_ms", 0) or 0),
                                "notify_dm_llm_regen_attempt": int(meta.get("regen_attempt", 1) or 1),
                                "notify_dm_llm_error_code": "",
                                "notify_dm_llm_error_detail": "",
                            },
                            save=True,
                        )
                    else:
                        err_code = str(meta.get("error_code", "E_DM_LLM_GENERATE_FAILED") or "E_DM_LLM_GENERATE_FAILED")
                        err_detail = str(meta.get("error_detail", "") or "第二条私信文案生成失败")
                        _update_notify_flow_state(
                            task_key,
                            stage="dm_text_generating",
                            error=f"{err_code}: {err_detail}",
                            retry_at=0.0,
                            extra={
                                "notify_share_link": share_link,
                                "notify_dm_template_text": dm_template_text,
                                "notify_dm_llm_used": bool(meta.get("llm_used", True)),
                                "notify_dm_llm_latency_ms": int(meta.get("latency_ms", 0) or 0),
                                "notify_dm_llm_error_code": err_code,
                                "notify_dm_llm_error_detail": err_detail,
                            },
                            save=True,
                        )
                    return ok_gen, dm_text_generated, meta

                return _supplier

            slot_ok, slot_wait = _reserve_notify_dm_user_slot(dm_handle, task_key=task_key)
            if not slot_ok:
                return False, f"E_DM_USER_COOLDOWN: @{normalize_handle(dm_handle)} 私信冷却中，请 {slot_wait:.1f}s 后重试"
            _mark_stage("dm_opening", extra={"notify_share_link": share_link}, save=True)
            ok_dm, dm_err, dm_closed, dm_tab = _run_dm_send_with_recovery(
                tab,
                dm_handle,
                share_link,
                dm_template_text,
                mark_func=_mark,
                progress=dm_progress,
                dm_text_supplier=_build_dm_text_supplier(),
            )
            if dm_tab:
                tab = dm_tab
            if not ok_dm:
                if dm_closed:
                    _mark_stage("dm_closed_confirmed", extra={"notify_share_link": share_link}, save=True)
                    _mark("dm_open_failed")
                    log_to_ui("warn", "⚠️ 目标用户未开启私信，准备发送补充评论后结束私信流程")
                    try:
                        now_url = str(tab.url or "")
                    except Exception:
                        now_url = ""
                    if "x.com/notifications" not in now_url:
                        tab.get("https://x.com/notifications")
                        _wait_document_ready(tab, timeout=5.5)
                    _prepare_notifications_view(force_refresh=True)
                    fb_article, fb_reply_btn, fb_score, _, _, fb_match_err = _match_target_card()
                    if fb_match_err:
                        return False, f"用户不可私信，且补充评论失败: {fb_match_err}"
                    ok_fb, err_fb = _send_reply_from_button(fb_reply_btn, fb_score, DM_CLOSED_FALLBACK_REPLY_TEXT)
                    if not ok_fb:
                        return False, f"用户不可私信，且补充评论失败: {err_fb}"
                    _mark("fallback_reply")
                    total_cost = time.perf_counter() - flow_started_at
                    log_to_ui(
                        "debug",
                        f"⏱️ 回复流程耗时(私信关闭): 匹配{stage_marks.get('match_card', 0):.2f}s, "
                        f"链接{stage_marks.get('prepare_share_link', 0):.2f}s, "
                        f"首评{stage_marks.get('send_reply', 0):.2f}s, 补评{stage_marks.get('fallback_reply', 0):.2f}s, "
                        f"总计{total_cost:.2f}s"
                    )
                    log_to_ui("info", "💬 用户私信关闭，已发送补充评论并结束私信发送流程")
                    _mark_stage("done", save=True)
                    return True, ""
                return False, dm_err

            total_cost = time.perf_counter() - flow_started_at
            log_to_ui(
                "debug",
                f"⏱️ 回复流程耗时: 匹配{stage_marks.get('match_card', 0):.2f}s, "
                f"链接{stage_marks.get('prepare_share_link', 0):.2f}s, 首评{stage_marks.get('send_reply', 0):.2f}s, "
                f"开私信{stage_marks.get('open_dm', 0):.2f}s, 发链接{stage_marks.get('send_dm_link', 0):.2f}s, "
                f"发文案{stage_marks.get('send_dm_text', 0):.2f}s, 总计{total_cost:.2f}s"
            )
            _mark_stage("done", save=True)
            return True, ""
        except Exception as e:
            if _is_unhandled_prompt_error(e):
                diag_before = _capture_runtime_diagnostic(
                    tab,
                    "unhandled_prompt_before_clear",
                    err=e,
                    selectors=[
                        'css:[role="alertdialog"]',
                        'css:[role="dialog"]',
                        'css:[data-testid="confirmationSheetDialog"]',
                        'css:[data-testid="modal"]',
                        'css:[data-testid="reply"]',
                        'css:[data-testid="tweetButton"]',
                        'css:[data-testid="dm-composer-send-button"]',
                    ],
                    extra={"status_id": status_id, "handle_hint": handle_hint, "phase": "before_clear"}
                )
                _prepare_reply_prompt_guard(tab, "异常恢复")
                diag_after = _capture_runtime_diagnostic(
                    tab,
                    "unhandled_prompt_after_clear",
                    err=e,
                    selectors=[
                        'css:[role="alertdialog"]',
                        'css:[role="dialog"]',
                        'css:[data-testid="reply"]',
                        'css:[data-testid="tweetButton"]',
                        'css:[data-testid="dm-composer-send-button"]',
                    ],
                    extra={"status_id": status_id, "handle_hint": handle_hint, "phase": "after_clear"}
                )
                diag_ref = diag_before or diag_after
                if diag_ref:
                    return False, f"检测到未处理提示框，已自动清理，请重试一次（已截图留档: {diag_ref}）"
                return False, "检测到未处理提示框，已自动清理，请重试一次"
            _capture_runtime_diagnostic(
                tab,
                "send_notification_reply_exception",
                err=e,
                selectors=['tag:article', 'css:[data-testid="reply"]', 'css:[data-testid="dm-composer-send-button"]'],
                extra={"status_id": status_id, "handle_hint": handle_hint}
            )
            return False, f"回复发送失败: {e}"
        finally:
            # 无论成功/失败都回到通知页，且保持当前工作标签页不关闭，减少页面抖动
            try:
                final_url = str(tab.url or "")
            except Exception:
                final_url = ""
            try:
                if "x.com/notifications" not in final_url:
                    tab.get("https://x.com/notifications")
                    time.sleep(random.uniform(0.3, 0.7))
            except Exception:
                pass
            _set_reply_flow_active(False)

# --- API 路由 ---
@app.route('/')
def index(): return render_template('index.html')

# 核心：加载状态时，返回待处理列表 pending
@app.route('/api/state')
def state():
    with data_lock:
        return jsonify({
            "token": global_token,
            "tasks": list(monitor_tasks),
            "is_running": monitor_active,
            "pending": list(pending_results),
            "updates_last_seq": int(updates_event_seq),
            "updates_buffer_size": len(updates_event_buffer),
            "notification_monitoring": notification_monitoring,
            "delegated_account": delegated_account,
            "delegated_enabled": delegated_enabled,
            "headless_mode": headless_mode,
            "notify_reply_templates": list(notify_reply_templates),
            "dm_message_templates": list(dm_message_templates),
            "llm_filter_enabled": bool(LLM_FILTER_ENABLED),
            "llm_filter_base_url": str(LLM_FILTER_BASE_URL or ""),
            "llm_filter_api_key": str(LLM_FILTER_API_KEY or ""),
            "llm_filter_model": str(LLM_FILTER_MODEL or ""),
            "llm_filter_timeout_sec": float(LLM_FILTER_TIMEOUT_SEC),
            "llm_filter_timeout_max_sec": float(LLM_FILTER_TIMEOUT_MAX_SEC),
            "llm_filter_prompt_template": str(LLM_FILTER_PROMPT_TEMPLATE or ""),
            "llm_intent_prompt_template": str(LLM_INTENT_PROMPT_TEMPLATE or ""),
            "dm_llm_rewrite_enabled": bool(DM_LLM_REWRITE_ENABLED),
            "dm_llm_rewrite_prompt_template": str(DM_LLM_REWRITE_PROMPT_TEMPLATE or ""),
            "dm_llm_rewrite_max_chars": int(DM_LLM_REWRITE_MAX_CHARS),
            "dm_llm_rewrite_temperature": float(DM_LLM_REWRITE_TEMPERATURE),
            "dm_llm_rewrite_max_regen": int(DM_LLM_REWRITE_MAX_REGEN),
            "dm_llm_rewrite_dedupe_size": int(DM_LLM_REWRITE_DEDUPE_SIZE),
            "notify_voice_block_keywords_text": str(NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT or ""),
            "notification_reply_only_mode": bool(NOTIFICATION_REPLY_ONLY_MODE),
            **_build_notify_tts_runtime_payload(include_secrets=True),
        })

@app.route('/api/task/add', methods=['POST'])
def add_t():
    u = request.json['url']
    with data_lock:
        if not any(t['url']==u for t in monitor_tasks): monitor_tasks.append({"url":u, "last_check": "等待"})
    save_state()
    return jsonify({"status":"ok", "tasks":monitor_tasks})

@app.route('/api/task/remove', methods=['POST'])
def rem_t():
    global monitor_tasks
    u = request.json['url']
    with data_lock:
        monitor_tasks = [t for t in monitor_tasks if t['url']!=u]
    save_state()
    return jsonify({"status":"ok", "tasks":monitor_tasks})

@app.route('/api/mark_done', methods=['POST'])
def mark_done():
    key = request.json.get('key')
    handle = request.json.get('handle', '')
    with data_lock:
        global pending_results
        before_count = len(pending_results)
        if key:
            # 方案2：仅移除当前记录，不按用户屏蔽
            pending_results = [r for r in pending_results if r.get('key') != key]
        elif handle:
            # 兼容旧前端请求
            pending_results = [r for r in pending_results if r.get('handle') != handle]
        removed = before_count - len(pending_results)

    save_state() # 立即保存状态更新
    if key:
        log_to_ui("info", f"✅ 记录已处理: key={key}（移除{removed}条）")
    else:
        log_to_ui("info", f"✅ 记录已处理: handle={handle}（兼容模式移除{removed}条）")
    return jsonify({"status":"ok", "removed": removed})

@app.route('/api/clear_results', methods=['POST'])
def clear_results():
    """清空捕获结果（支持按类型清空）"""
    result_type = request.json.get('type', 'all')  # 'notify', 'tweet', 或 'all'
    with data_lock:
        global pending_results
        if result_type == 'notify':
            pending_results = [r for r in pending_results if r.get('source') != '通知页面']
            log_to_ui("info", "🗑️ 已清空通知捕获结果")
        elif result_type == 'tweet':
            pending_results = [r for r in pending_results if r.get('source') == '通知页面']
            log_to_ui("info", "🗑️ 已清空推文捕获结果")
        else:
            pending_results = []
            log_to_ui("info", "🗑️ 已清空所有捕获结果")
    save_state()
    return jsonify({"status":"ok"})

@app.route('/api/clear_blocklist', methods=['POST'])
def clear_blocklist():
    """清空黑名单（兼容旧接口；当前主要去重策略为内容签名）"""
    with data_lock:
        processed_users.clear()
    save_processed_users()
    log_to_ui("info", "⛔ 已清空黑名单（当前抓取不再按用户屏蔽）")
    return jsonify({"status":"ok"})

@app.route('/api/notify_replies')
def get_notify_replies():
    """返回通知中“回复了你”的结构化记录。"""
    try:
        limit = int(request.args.get('limit', 200))
    except Exception:
        limit = 200
    limit = max(1, min(limit, 2000))

    with data_lock:
        reply_items = [dict(item) for item in pending_results if is_reply_to_me_notification_item(item)]

    # pending_results 为时间顺序，接口默认返回最新在前
    reply_items.reverse()
    if limit:
        reply_items = reply_items[:limit]

    return jsonify({
        "status": "ok",
        "count": len(reply_items),
        "reply_only_mode": bool(NOTIFICATION_REPLY_ONLY_MODE),
        "items": reply_items,
    })

@app.route('/api/toggle_notification', methods=['POST'])
def toggle_notification():
    """切换通知监控开关"""
    global notification_monitoring
    enabled = request.json.get('enabled', False)
    with data_lock:
        notification_monitoring = enabled
    save_state()
    status_text = "启用" if enabled else "禁用"
    log_to_ui("info", f"📬 通知监控已{status_text}")
    return jsonify({"status":"ok", "notification_monitoring": notification_monitoring})

@app.route('/api/notify_reply', methods=['POST'])
def notify_reply():
    """对通知捕获项执行快速回复。"""
    key = request.json.get('key', '').strip()
    message = request.json.get('message', '').strip()
    dm_message = request.json.get('dm_message', '').strip()
    if not key:
        return jsonify({"status": "err", "msg": "missing key"}), 400
    if not message:
        return jsonify({"status": "err", "msg": "missing message"}), 400

    with data_lock:
        target = None
        for item in pending_results:
            if item.get('key') == key and item.get('source') == '通知页面':
                target = dict(item)
                break

    if not target:
        return jsonify({"status": "err", "msg": "通知记录不存在"}), 404

    with data_lock:
        for row in pending_results:
            if row.get("key") == key and row.get("source") == "通知页面":
                row["notify_reply_text"] = message
                row["notify_dm_text"] = dm_message
                row["notify_dm_text_generated"] = ""
                row["notify_dm_llm_used"] = bool(DM_LLM_REWRITE_ENABLED)
                row["notify_dm_llm_latency_ms"] = 0
                row["notify_dm_llm_regen_attempt"] = 0
                row["notify_dm_llm_error_code"] = ""
                row["notify_dm_llm_error_detail"] = ""
                if not str(row.get("notify_flow_stage", "")).strip():
                    row["notify_flow_stage"] = "reply_pending"
                break
    save_state()

    target_handle = target.get('handle', '')
    allowed, budget_msg = _check_reply_failure_budget(target_handle)
    if not allowed:
        log_to_ui("warn", f"⏸️ 触发失败预算熔断: {target_handle} - {budget_msg}")
        return jsonify({"status": "err", "msg": budget_msg}), 429

    base_attempt = 0
    try:
        base_attempt = int(target.get("notify_flow_attempt", 0) or 0)
    except Exception:
        base_attempt = 0
    cur_attempt = max(1, base_attempt + 1)
    # 手动点击“回复”属于显式业务动作：必须从公开回复重新开始，
    # 不能沿用旧的 dm_opening 断点，否则会出现“未先回复就私信”。
    resume_stage = "reply_pending"
    _update_notify_flow_state(
        key,
        stage="reply_pending",
        attempt=cur_attempt,
        error="",
        retry_at=0,
        extra={
            "notify_resume_stage": resume_stage,
            "notify_retry_reason": "manual_notify_reply_execute",
            # 强制重新走一遍“匹配卡片 -> 公开回复 -> 复制链接 -> 私信”链路
            "notify_share_link": "",
        },
        save=True,
    )

    max_attempts = 1 + (max(0, int(UNHANDLED_PROMPT_AUTO_RETRY)) if headless_mode else 0)
    ok, err = False, "通知回复失败"
    for attempt in range(1, max_attempts + 1):
        ok, err = send_notification_reply(target, message, dm_message=dm_message)
        if ok:
            break

        if _is_unhandled_prompt_error(err) and attempt < max_attempts:
            remaining = max_attempts - attempt
            log_to_ui("warn", f"⚠️ 检测到未处理提示框，自动恢复后重试（剩余{remaining}次）")
            try:
                recover_tab = ensure_reply_work_tab(force_recreate=(attempt >= 2))
                _prepare_reply_prompt_guard(recover_tab, f"自动恢复重试{attempt}")
                try:
                    now_url = str(recover_tab.url or "")
                except Exception:
                    now_url = ""
                if "x.com/notifications" not in now_url:
                    recover_tab.get("https://x.com/notifications")
                    _wait_document_ready(recover_tab, timeout=5.0)
            except Exception as recover_err:
                log_to_ui("warn", f"⚠️ 提示框自动恢复失败: {recover_err}")
            time.sleep(random.uniform(0.45, 1.1))
            continue
        break

    _record_reply_outcome(target_handle, ok, err if not ok else "")
    if not ok:
        flow_err_code, flow_err_detail = _split_flow_error(err)
        scheduled, retry_at, schedule_msg = _schedule_notify_retry(
            key,
            err,
            attempt=cur_attempt,
            reason="manual_notify_reply",
            save=True,
        )
        log_to_ui("warn", f"⚠️ 通知回复失败: {err}")
        if scheduled:
            return jsonify({
                "status": "retry_waiting",
                "msg": schedule_msg,
                "flow_stage": "retry_waiting",
                "flow_error_code": flow_err_code,
                "flow_error_detail": flow_err_detail,
                "retry_at": retry_at,
                "retry_time": datetime.datetime.fromtimestamp(retry_at).strftime("%H:%M:%S"),
                "attempt": cur_attempt,
            }), 202
        return jsonify({
            "status": "err",
            "msg": f"{err}（{schedule_msg}）",
            "flow_stage": "retry_waiting",
            "flow_error_code": flow_err_code,
            "flow_error_detail": flow_err_detail,
            "retry_at": 0,
            "retry_time": "",
            "attempt": cur_attempt,
        }), 500

    reply_time_text = datetime.datetime.now().strftime("%H:%M:%S")
    _mark_notify_reply_success(key, message, dm_message, reply_time_text=reply_time_text, save=True)

    log_to_ui("success", f"✅ 已发送通知回复: {target_handle} -> {message[:30]}")
    return jsonify({
        "status": "ok",
        "reply_time": reply_time_text,
        "flow_stage": "done",
        "retry_at": 0,
        "retry_time": "",
        "attempt": cur_attempt,
    })


@app.route('/api/notify_retry', methods=['POST'])
def notify_retry():
    """手动触发 retry_waiting 通知任务立即重试。"""
    key = str(request.json.get('key', '') or '').strip()
    if not key:
        return jsonify({"status": "err", "msg": "missing key"}), 400

    _, row = _find_pending_notify_item_by_key(key)
    if not row:
        return jsonify({"status": "err", "msg": "通知记录不存在"}), 404

    item = dict(row)
    if bool(item.get("notify_replied", False)):
        return jsonify({"status": "ok", "msg": "该任务已完成", "flow_stage": "done"})

    reply_text = str(item.get("notify_reply_text", "") or "").strip()
    dm_text = str(item.get("notify_dm_text", "") or "").strip()
    if not reply_text or not dm_text:
        return jsonify({"status": "err", "msg": "缺少回复或私信模板，请先在该行重新选择后点击回复"}), 400

    try:
        attempt = int(item.get("notify_flow_attempt", 0) or 0) + 1
    except Exception:
        attempt = 1
    resume_stage = _resolve_notify_resume_stage(item)
    _update_notify_flow_state(
        key,
        stage="reply_pending",
        attempt=attempt,
        error="",
        retry_at=0,
        extra={
            "notify_resume_stage": resume_stage,
            "notify_retry_reason": "manual_retry_execute",
        },
        save=True,
    )

    ok, err = send_notification_reply(item, reply_text, dm_message=dm_text)
    _record_reply_outcome(item.get("handle", ""), ok, err if not ok else "")
    if ok:
        reply_time_text = datetime.datetime.now().strftime("%H:%M:%S")
        _mark_notify_reply_success(key, reply_text, dm_text, reply_time_text=reply_time_text, save=True)
        return jsonify({
            "status": "ok",
            "msg": "重试成功",
            "flow_stage": "done",
            "reply_time": reply_time_text,
            "retry_at": 0,
            "retry_time": "",
            "attempt": attempt,
        })

    scheduled, retry_at, schedule_msg = _schedule_notify_retry(
        key,
        err,
        attempt=attempt,
        reason="manual_retry_api",
        save=True,
    )
    flow_err_code, flow_err_detail = _split_flow_error(err)
    if scheduled:
        return jsonify({
            "status": "retry_waiting",
            "msg": schedule_msg,
            "flow_stage": "retry_waiting",
            "flow_error_code": flow_err_code,
            "flow_error_detail": flow_err_detail,
            "retry_at": retry_at,
            "retry_time": datetime.datetime.fromtimestamp(retry_at).strftime("%H:%M:%S"),
            "attempt": attempt,
        }), 202
    return jsonify({
        "status": "err",
        "msg": f"{err}（{schedule_msg}）",
        "flow_stage": "retry_waiting",
        "flow_error_code": flow_err_code,
        "flow_error_detail": flow_err_detail,
        "retry_at": 0,
        "retry_time": "",
        "attempt": attempt,
    }), 500


@app.route('/api/template/add', methods=['POST'])
def template_add():
    template_type = str(request.json.get('type', '')).strip().lower()
    content = str(request.json.get('content', '')).strip()
    tpl_list, max_len = _get_template_list_and_limit(template_type)
    if tpl_list is None:
        return jsonify({"status": "err", "msg": "invalid template type"}), 400
    if not content:
        return jsonify({"status": "err", "msg": "missing content"}), 400
    if len(content) > max_len:
        return jsonify({"status": "err", "msg": f"content too long (max {max_len})"}), 400

    with data_lock:
        if content in tpl_list:
            return jsonify({"status": "err", "msg": "模板已存在"}), 409
        tpl_list.append(content)
    save_state()
    return jsonify({
        "status": "ok",
        "notify_reply_templates": list(notify_reply_templates),
        "dm_message_templates": list(dm_message_templates),
    })


@app.route('/api/template/update', methods=['POST'])
def template_update():
    template_type = str(request.json.get('type', '')).strip().lower()
    content = str(request.json.get('content', '')).strip()
    index_raw = request.json.get('index', None)
    tpl_list, max_len = _get_template_list_and_limit(template_type)
    if tpl_list is None:
        return jsonify({"status": "err", "msg": "invalid template type"}), 400
    if not content:
        return jsonify({"status": "err", "msg": "missing content"}), 400
    if len(content) > max_len:
        return jsonify({"status": "err", "msg": f"content too long (max {max_len})"}), 400
    try:
        index = int(index_raw)
    except Exception:
        return jsonify({"status": "err", "msg": "invalid index"}), 400

    with data_lock:
        if index < 0 or index >= len(tpl_list):
            return jsonify({"status": "err", "msg": "index out of range"}), 400
        if content in tpl_list and tpl_list[index] != content:
            return jsonify({"status": "err", "msg": "模板已存在"}), 409
        tpl_list[index] = content
    save_state()
    return jsonify({
        "status": "ok",
        "notify_reply_templates": list(notify_reply_templates),
        "dm_message_templates": list(dm_message_templates),
    })


@app.route('/api/template/delete', methods=['POST'])
def template_delete():
    template_type = str(request.json.get('type', '')).strip().lower()
    index_raw = request.json.get('index', None)
    tpl_list, _ = _get_template_list_and_limit(template_type)
    if tpl_list is None:
        return jsonify({"status": "err", "msg": "invalid template type"}), 400
    try:
        index = int(index_raw)
    except Exception:
        return jsonify({"status": "err", "msg": "invalid index"}), 400

    fallback = DEFAULT_NOTIFY_REPLY_TEMPLATES if template_type == "reply" else DEFAULT_DM_TEMPLATES
    with data_lock:
        if index < 0 or index >= len(tpl_list):
            return jsonify({"status": "err", "msg": "index out of range"}), 400
        tpl_list.pop(index)
        if not tpl_list:
            tpl_list.extend(fallback)
    save_state()
    return jsonify({
        "status": "ok",
        "notify_reply_templates": list(notify_reply_templates),
        "dm_message_templates": list(dm_message_templates),
    })

@app.route('/api/set_delegated_account', methods=['POST'])
def set_delegated_account():
    """设置委派账户"""
    global delegated_account, delegated_enabled, delegated_account_active, delegated_switch_ok
    payload = request.get_json(silent=True) or {}
    account = str(payload.get('account', '') or '').strip()
    old_norm = normalize_handle(delegated_account)
    new_norm = normalize_handle(account)
    with data_lock:
        delegated_account = account
        delegated_enabled = bool(account)
        # 账号变更或禁用时，清空会话内委派切换状态
        if (old_norm != new_norm) or (not delegated_enabled):
            delegated_account_active = ""
            delegated_switch_ok = False
    save_state()
    if delegated_enabled:
        log_to_ui("info", f"👤 已设置委派账户: {account}")
    else:
        log_to_ui("info", "👤 已清除委派账户")
    return jsonify({
        "status":"ok",
        "delegated_account": delegated_account,
        "delegated_enabled": delegated_enabled,
    })


@app.route('/api/open_user_replies_page', methods=['POST'])
def open_user_replies_page():
    """在程序控制浏览器中打开目标用户回复页（新标签）。"""
    payload = request.get_json(silent=True) or {}
    raw_handle = str(payload.get('handle', '') or '').strip()
    handle = normalize_handle(raw_handle)
    if not handle:
        return jsonify({"status": "err", "msg": "请输入有效的推特 @ID"}), 400
    if not re.fullmatch(r"[a-z0-9_]{1,30}", handle):
        return jsonify({"status": "err", "msg": "推特ID格式不合法"}), 400

    target_url = f"https://x.com/{handle}/with_replies"

    try:
        with browser_lock:
            browser = global_browser if (browser_initialized and global_browser) else None

        if browser is None:
            if not global_token.strip():
                return jsonify({"status": "err", "msg": "请先配置 Token 并启动监控后再跳转"}), 400
            browser = init_global_browser()

        with browser_lock:
            tab = browser.new_tab()
            tab.get(target_url)

        log_to_ui("info", f"🔗 已打开用户回复页: @{handle}")
        return jsonify({
            "status": "ok",
            "handle": f"@{handle}",
            "url": target_url,
        })
    except Exception as e:
        log_to_ui("warn", f"⚠️ 打开用户回复页失败 @{handle}: {e}")
        return jsonify({"status": "err", "msg": f"打开失败: {e}"}), 500


def _extract_llm_runtime_from_payload(payload):
    payload = payload or {}
    base_url = str(payload.get("base_url", LLM_FILTER_BASE_URL) or "").strip()
    api_key = str(payload.get("api_key", LLM_FILTER_API_KEY) or "").strip() or "EMPTY"
    model = str(payload.get("model", LLM_FILTER_MODEL) or "").strip()
    timeout_sec = clamp_llm_timeout(payload.get("timeout_sec", LLM_FILTER_TIMEOUT_SEC))
    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "timeout_sec": timeout_sec,
    }


@app.route('/api/llm_filter/test', methods=['POST'])
def llm_filter_test():
    """测试OpenAI兼容LLM接口可用性。"""
    payload = request.get_json(silent=True) or {}
    runtime = _extract_llm_runtime_from_payload(payload)
    if not runtime["base_url"] or not runtime["model"]:
        return jsonify({"status": "err", "msg": "请先填写 Base URL 和模型名"}), 400

    start_ts = time.perf_counter()
    try:
        result_obj, raw_text = _call_openai_compatible_json(
            "You are a strict JSON classifier.",
            "请返回JSON: {\"ok\":true,\"message\":\"pong\"}",
            base_url=runtime["base_url"],
            api_key=runtime["api_key"],
            model=runtime["model"],
            timeout_sec=runtime["timeout_sec"],
            max_tokens=48,
        )
        latency_ms = int((time.perf_counter() - start_ts) * 1000)
        ok_flag = True
        if isinstance(result_obj, dict) and "ok" in result_obj:
            ok_raw = result_obj.get("ok")
            if isinstance(ok_raw, str):
                ok_flag = ok_raw.strip().lower() in {"1", "true", "yes", "y"}
            else:
                ok_flag = bool(ok_raw)

        return jsonify({
            "status": "ok" if ok_flag else "err",
            "model": runtime["model"],
            "endpoint": _llm_filter_endpoint(base_url=runtime["base_url"]),
            "latency_ms": latency_ms,
            "result": result_obj if isinstance(result_obj, dict) else {},
            "raw": str(raw_text or "")[:180],
            "msg": "模型可用" if ok_flag else "模型返回异常",
        })
    except Exception as e:
        return jsonify({
            "status": "err",
            "model": runtime["model"],
            "endpoint": _llm_filter_endpoint(base_url=runtime["base_url"]),
            "msg": f"模型不可用: {e}",
        }), 500


@app.route('/api/llm_filter/analyze', methods=['POST'])
def llm_filter_analyze():
    """分析评论意向用户。"""
    payload = request.get_json(silent=True) or {}
    content = str(payload.get("content", "") or "").strip()
    analyze_source = str(payload.get("analyze_source", "") or "").strip() or "unknown"
    if not content:
        return jsonify({"status": "err", "msg": "评论内容不能为空"}), 400

    runtime = _extract_llm_runtime_from_payload(payload)
    log_to_ui(
        "debug",
        f"🤖 [IntentAPI] request source={analyze_source} content={_normalize_one_line(content, 120)}"
    )
    analysis = analyze_comment_intent(
        content,
        base_url=runtime["base_url"],
        api_key=runtime["api_key"],
        model=runtime["model"],
        timeout_sec=runtime["timeout_sec"],
    )
    analysis["voice_should_notify"] = bool(_should_notify_voice_by_intent(analysis))
    log_to_ui(
        "debug",
        f"🤖 [IntentAPI] result source={analyze_source} score={analysis.get('intent_score', 0)} "
        f"level={analysis.get('intent_level', '')} intent={bool(analysis.get('is_intent_user', False))} "
        f"voice={bool(analysis.get('voice_should_notify', False))} "
        f"llm_used={bool(analysis.get('llm_used', False))} reason={analysis.get('reason', '') or '-'}"
    )
    # 提升到 info，确保在常规运行日志中可见分析结果
    log_to_ui(
        "info",
        f"🤖 AI意向分析[{analyze_source}] score={analysis.get('intent_score', 0)} "
        f"level={analysis.get('intent_level', '')} intent={bool(analysis.get('is_intent_user', False))} "
        f"voice={bool(analysis.get('voice_should_notify', False))} llm_used={bool(analysis.get('llm_used', False))}"
    )
    return jsonify({
        "status": "ok",
        "analysis": analysis,
    })


@app.route('/api/set_llm_filter_config', methods=['POST'])
def set_llm_filter_config():
    """设置LLM内容过滤配置（OpenAI兼容接口）。"""
    global LLM_FILTER_ENABLED, LLM_FILTER_BASE_URL, LLM_FILTER_API_KEY, LLM_FILTER_MODEL, LLM_FILTER_TIMEOUT_SEC
    global LLM_FILTER_PROMPT_TEMPLATE, LLM_INTENT_PROMPT_TEMPLATE
    global DM_LLM_REWRITE_ENABLED, DM_LLM_REWRITE_PROMPT_TEMPLATE, DM_LLM_REWRITE_MAX_CHARS
    global DM_LLM_REWRITE_TEMPERATURE, DM_LLM_REWRITE_MAX_REGEN, DM_LLM_REWRITE_DEDUPE_SIZE, dm_llm_rewrite_history
    global NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT, NOTIFY_VOICE_BLOCK_KEYWORDS
    payload = request.get_json(silent=True) or {}

    enabled = bool(payload.get('enabled', False))
    base_url = str(payload.get('base_url', '') or '').strip()
    api_key = str(payload.get('api_key', '') or '').strip()
    model = str(payload.get('model', '') or '').strip()
    filter_prompt_template = str(
        payload.get('llm_filter_prompt_template', LLM_FILTER_PROMPT_TEMPLATE) or ''
    ).strip()
    intent_prompt_template = str(
        payload.get('llm_intent_prompt_template', LLM_INTENT_PROMPT_TEMPLATE) or ''
    ).strip()
    notify_voice_block_keywords_text = str(
        payload.get('notify_voice_block_keywords_text', NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT) or ''
    ).strip()
    dm_llm_rewrite_enabled = bool(payload.get('dm_llm_rewrite_enabled', DM_LLM_REWRITE_ENABLED))
    dm_llm_rewrite_prompt_template = str(
        payload.get('dm_llm_rewrite_prompt_template', DM_LLM_REWRITE_PROMPT_TEMPLATE) or ''
    ).strip() or DM_LLM_REWRITE_DEFAULT_PROMPT
    try:
        dm_llm_rewrite_max_chars = int(payload.get('dm_llm_rewrite_max_chars', DM_LLM_REWRITE_MAX_CHARS))
    except Exception:
        dm_llm_rewrite_max_chars = DM_LLM_REWRITE_MAX_CHARS
    dm_llm_rewrite_max_chars = max(80, min(1200, int(dm_llm_rewrite_max_chars)))
    try:
        dm_llm_rewrite_temperature = float(payload.get('dm_llm_rewrite_temperature', DM_LLM_REWRITE_TEMPERATURE))
    except Exception:
        dm_llm_rewrite_temperature = DM_LLM_REWRITE_TEMPERATURE
    dm_llm_rewrite_temperature = max(0.0, min(1.2, float(dm_llm_rewrite_temperature)))
    try:
        dm_llm_rewrite_max_regen = int(payload.get('dm_llm_rewrite_max_regen', DM_LLM_REWRITE_MAX_REGEN))
    except Exception:
        dm_llm_rewrite_max_regen = DM_LLM_REWRITE_MAX_REGEN
    dm_llm_rewrite_max_regen = max(0, min(5, int(dm_llm_rewrite_max_regen)))
    try:
        dm_llm_rewrite_dedupe_size = int(payload.get('dm_llm_rewrite_dedupe_size', DM_LLM_REWRITE_DEDUPE_SIZE))
    except Exception:
        dm_llm_rewrite_dedupe_size = DM_LLM_REWRITE_DEDUPE_SIZE
    dm_llm_rewrite_dedupe_size = max(50, min(1000, int(dm_llm_rewrite_dedupe_size)))
    timeout_sec = clamp_llm_timeout(payload.get('timeout_sec', LLM_FILTER_TIMEOUT_SEC))
    if len(filter_prompt_template) > 12000:
        return jsonify({"status": "err", "msg": "过滤 Prompt 过长（最大12000字符）"}), 400
    if len(intent_prompt_template) > 12000:
        return jsonify({"status": "err", "msg": "意向 Prompt 过长（最大12000字符）"}), 400
    if len(dm_llm_rewrite_prompt_template) > 12000:
        return jsonify({"status": "err", "msg": "私信改写 Prompt 过长（最大12000字符）"}), 400

    notify_voice_block_keywords = tuple(
        dict.fromkeys(
            list(NOTIFY_VOICE_BLOCK_KEYWORDS_BUILTIN)
            + [kw.lower() for kw in _normalize_keyword_lines(notify_voice_block_keywords_text)]
        )
    )

    if enabled and (not base_url or not model):
        return jsonify({"status": "err", "msg": "启用LLM过滤时必须填写 Base URL 和模型名"}), 400

    with data_lock:
        LLM_FILTER_ENABLED = enabled
        LLM_FILTER_BASE_URL = base_url
        LLM_FILTER_API_KEY = api_key or "EMPTY"
        LLM_FILTER_MODEL = model
        LLM_FILTER_TIMEOUT_SEC = timeout_sec
        LLM_FILTER_PROMPT_TEMPLATE = filter_prompt_template
        LLM_INTENT_PROMPT_TEMPLATE = intent_prompt_template
        DM_LLM_REWRITE_ENABLED = dm_llm_rewrite_enabled
        DM_LLM_REWRITE_PROMPT_TEMPLATE = dm_llm_rewrite_prompt_template
        DM_LLM_REWRITE_MAX_CHARS = dm_llm_rewrite_max_chars
        DM_LLM_REWRITE_TEMPERATURE = dm_llm_rewrite_temperature
        DM_LLM_REWRITE_MAX_REGEN = dm_llm_rewrite_max_regen
        if DM_LLM_REWRITE_DEDUPE_SIZE != dm_llm_rewrite_dedupe_size:
            DM_LLM_REWRITE_DEDUPE_SIZE = dm_llm_rewrite_dedupe_size
            dm_llm_rewrite_history = deque(list(dm_llm_rewrite_history), maxlen=DM_LLM_REWRITE_DEDUPE_SIZE)
        else:
            DM_LLM_REWRITE_DEDUPE_SIZE = dm_llm_rewrite_dedupe_size
        NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT = notify_voice_block_keywords_text
        NOTIFY_VOICE_BLOCK_KEYWORDS = notify_voice_block_keywords
    with llm_filter_cache_lock:
        llm_filter_cache.clear()

    save_state()

    if LLM_FILTER_ENABLED and _llm_filter_is_ready():
        log_to_ui("info", f"🤖 [LLMFilter] 配置已更新并启用: model={LLM_FILTER_MODEL}")
    elif LLM_FILTER_ENABLED:
        log_to_ui("warn", "⚠️ [LLMFilter] 已启用但配置不完整")
    else:
        log_to_ui("info", "🤖 [LLMFilter] 已禁用")
    log_to_ui("info", f"🔇 [NotifyVoice] 不播报关键词已更新: {len(NOTIFY_VOICE_BLOCK_KEYWORDS)} 条")

    return jsonify({
        "status": "ok",
        "llm_filter_enabled": bool(LLM_FILTER_ENABLED),
        "llm_filter_base_url": str(LLM_FILTER_BASE_URL or ""),
        "llm_filter_api_key": str(LLM_FILTER_API_KEY or ""),
        "llm_filter_model": str(LLM_FILTER_MODEL or ""),
        "llm_filter_timeout_sec": float(LLM_FILTER_TIMEOUT_SEC),
        "llm_filter_timeout_max_sec": float(LLM_FILTER_TIMEOUT_MAX_SEC),
        "llm_filter_prompt_template": str(LLM_FILTER_PROMPT_TEMPLATE or ""),
        "llm_intent_prompt_template": str(LLM_INTENT_PROMPT_TEMPLATE or ""),
        "dm_llm_rewrite_enabled": bool(DM_LLM_REWRITE_ENABLED),
        "dm_llm_rewrite_prompt_template": str(DM_LLM_REWRITE_PROMPT_TEMPLATE or ""),
        "dm_llm_rewrite_max_chars": int(DM_LLM_REWRITE_MAX_CHARS),
        "dm_llm_rewrite_temperature": float(DM_LLM_REWRITE_TEMPERATURE),
        "dm_llm_rewrite_max_regen": int(DM_LLM_REWRITE_MAX_REGEN),
        "dm_llm_rewrite_dedupe_size": int(DM_LLM_REWRITE_DEDUPE_SIZE),
        "notify_voice_block_keywords_text": str(NOTIFY_VOICE_BLOCK_KEYWORDS_TEXT or ""),
        "notify_voice_block_keywords": list(NOTIFY_VOICE_BLOCK_KEYWORDS),
    })


@app.route('/api/set_notify_tts_config', methods=['POST'])
def set_notify_tts_config():
    """设置通知豆包TTS配置并立即生效。"""
    payload = request.get_json(silent=True) or {}
    cfg = _normalize_notify_tts_config_from_payload(payload)
    if cfg["enabled"] and (not cfg["app_id"] or not cfg["access_token"] or not cfg["voice_type"]):
        return jsonify({"status": "err", "msg": "启用豆包TTS时必须填写 AppID / Access Token / 音色"}), 400

    with data_lock:
        _apply_notify_tts_config(cfg)
        save_ok, save_err = _save_local_tts_config(LOCAL_TTS_CONFIG)
    save_state()

    if _doubao_tts_is_ready():
        log_to_ui(
            "info",
            f"🔊 [NotifyTTS] 配置已更新并生效: voice={DOUBAO_TTS_VOICE_TYPE} encoding={DOUBAO_TTS_ENCODING}"
        )
    else:
        log_to_ui("warn", "⚠️ [NotifyTTS] 配置已保存，但当前仍未就绪（请检查必填项）")
    if not save_ok:
        log_to_ui("warn", f"⚠️ [NotifyTTS] 本地配置落盘失败: {save_err}")

    resp = {"status": "ok", "saved_to_local_file": bool(save_ok), "save_error": str(save_err or "")}
    resp.update(_build_notify_tts_runtime_payload(include_secrets=True))
    return jsonify(resp)


@app.route('/api/notify_tts/test', methods=['POST'])
def notify_tts_test():
    """测试豆包TTS配置可用性。"""
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "") or "").strip() or "这是一条豆包语音测试"
    if not _doubao_tts_is_ready():
        return jsonify({
            "status": "err",
            "msg": "豆包TTS未就绪，请先保存有效配置",
            **_build_notify_tts_runtime_payload(include_secrets=False),
        }), 400

    started_at = time.perf_counter()
    try:
        audio_b64 = _synthesize_doubao_tts_audio_base64(text)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        return jsonify({
            "status": "ok",
            "msg": "豆包TTS测试通过",
            "latency_ms": elapsed_ms,
            "audio_b64_len": len(str(audio_b64 or "")),
            **_build_notify_tts_runtime_payload(include_secrets=False),
        })
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        return jsonify({
            "status": "err",
            "msg": f"豆包TTS测试失败: {e}",
            "latency_ms": elapsed_ms,
            **_build_notify_tts_runtime_payload(include_secrets=False),
        }), 500


@app.route('/api/tts/synthesize', methods=['POST'])
def tts_synthesize():
    """通知语音合成：优先使用豆包TTS，供前端播放。"""
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "") or "").strip()
    if not text:
        return jsonify({"status": "err", "msg": "text不能为空"}), 400

    if not _doubao_tts_is_ready():
        return jsonify({
            "status": "err",
            "msg": "豆包TTS未配置或未启用",
            "provider": "browser",
        }), 503

    try:
        audio_b64 = _synthesize_doubao_tts_audio_base64(text)
        return jsonify({
            "status": "ok",
            "provider": "doubao",
            "voice_type": str(DOUBAO_TTS_VOICE_TYPE or ""),
            "encoding": str(DOUBAO_TTS_ENCODING or "mp3"),
            "mime": _doubao_tts_mime_by_encoding(DOUBAO_TTS_ENCODING),
            "audio_base64": audio_b64,
        })
    except Exception as e:
        err_msg = str(e)
        log_to_ui("warn", f"🔊 豆包TTS合成失败: {err_msg}")
        return jsonify({
            "status": "err",
            "msg": err_msg,
            "provider": "doubao",
        }), 500


@app.route('/api/toggle_headless', methods=['POST'])
def toggle_headless():
    """切换有头/无头模式"""
    global headless_mode
    payload = request.get_json(silent=True) or {}
    enabled = bool(payload.get('enabled', True))
    mode_text = "无头模式" if enabled else "有头模式(调试)"
    was_running = bool(monitor_active)

    with data_lock:
        headless_mode = enabled
    save_state()
    log_to_ui("info", f"🖥️ 浏览器模式已切换为: {mode_text}")

    if not was_running:
        return jsonify({
            "status": "ok",
            "headless_mode": headless_mode,
            "auto_restarted": False,
        })

    log_to_ui("info", "🔄 监控运行中，正在自动重启以应用新浏览器模式...")
    stopped = stop_monitor_thread(wait_timeout=20)
    started = start_monitor_thread()
    save_state()

    if started:
        log_to_ui("success", f"✅ 已应用{mode_text}并自动重启监控")
        return jsonify({
            "status": "ok",
            "headless_mode": headless_mode,
            "auto_restarted": True,
            "stopped": bool(stopped),
        })

    msg = "浏览器模式已切换，但监控自动重启失败，请手动点击启动监控"
    log_to_ui("error", f"❌ {msg}")
    return jsonify({
        "status": "err",
        "msg": msg,
        "headless_mode": headless_mode,
        "auto_restarted": False,
        "stopped": bool(stopped),
    })

@app.route('/api/start', methods=['POST'])
def start_rt():
    global monitor_active, global_token
    if monitor_active:
        return jsonify({"status":"err", "msg": "监控已在运行"})
    global_token = request.json['token']
    started = start_monitor_thread()
    if not started:
        return jsonify({"status":"err", "msg": "监控线程正在运行"})
    save_state()
    return jsonify({"status":"ok"})

@app.route('/api/stop', methods=['POST'])
def stop_rt():
    global monitor_active
    log_to_ui("info", "🛑 停止监控，保存数据...")
    stopped = stop_monitor_thread(wait_timeout=15)
    save_state()
    save_processed_users()
    log_to_ui("success", "💾 数据已保存")
    return jsonify({"status":"ok", "stopped": stopped})

@app.route('/api/updates')
def up():
    raw_since = str(request.args.get('since_seq', '') or '').strip()
    has_since = raw_since != ''

    # 兼容老版本前端：未传 since_seq 时继续使用单次消费语义。
    if not has_since:
        new_items = drain_msg_queue(collect_new_data=True)
        with data_lock:
            tasks_copy = list(monitor_tasks)
            last_seq = int(updates_event_seq)
            if (not new_items) and updates_event_buffer:
                # 回退到最近窗口，避免旧前端因队列语义变化出现“完全看不到新增”。
                new_items = [
                    evt.get("data")
                    for evt in list(updates_event_buffer)[-120:]
                    if isinstance(evt.get("data"), dict)
                ]
        return jsonify({
            "new_items": new_items,
            "tasks": tasks_copy,
            "last_seq": last_seq,
            "dropped": False,
        })

    try:
        since_seq = max(0, int(raw_since))
    except Exception:
        since_seq = 0

    # 新版前端：增量广播流；同时清理旧日志队列防堆积。
    drain_msg_queue(collect_new_data=False)

    with data_lock:
        tasks_copy = list(monitor_tasks)
        last_seq = int(updates_event_seq)
        buffer_snapshot = list(updates_event_buffer)

    dropped = False
    if buffer_snapshot:
        oldest_seq = int(buffer_snapshot[0].get("seq", 0) or 0)
        if since_seq > 0 and oldest_seq > (since_seq + 1):
            dropped = True

    new_items = [
        evt.get("data")
        for evt in buffer_snapshot
        if int(evt.get("seq", 0) or 0) > since_seq and isinstance(evt.get("data"), dict)
    ]

    return jsonify({
        "new_items": new_items,
        "tasks": tasks_copy,
        "last_seq": last_seq,
        "dropped": dropped,
    })

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
