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
import concurrent.futures
import subprocess
import urllib.request
import urllib.error
from collections import deque
from flask import Flask, request, render_template, jsonify
from DrissionPage import ChromiumPage, ChromiumOptions

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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
NOTIFICATION_SCAN_INTERVAL_MIN_SEC = 4
NOTIFICATION_SCAN_INTERVAL_MAX_SEC = 9
NOTIFICATION_RECENT_WINDOW_MINUTES = 30
NOTIFICATION_MAX_SCAN_ARTICLES = 60
NOTIFICATION_VERBOSE_TRACE = True
NOTIFICATION_TRACE_MAX_ARTICLES = 12
NOTIFICATION_TRACE_TEXT_LEN = 120
NOTIFICATION_REFRESH_INTERVAL_MIN_SEC = 12
NOTIFICATION_REFRESH_INTERVAL_MAX_SEC = 25
ENGINE_VERSION = "v11.3"
REPLY_ACTION_GAP_MIN_SEC = 3.8
REPLY_ACTION_GAP_MAX_SEC = 7.2
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
DM_ACTION_GAP_MIN_SEC = 2.1
DM_ACTION_GAP_MAX_SEC = 5.0
DM_BETWEEN_MESSAGES_MIN_SEC = 1.2
DM_BETWEEN_MESSAGES_MAX_SEC = 3.2
DM_HUMAN_SCROLL_CHANCE = 0.32
DM_SEND_FOLLOWUP_TEXT = str(
    os.environ.get("XMONITOR_DM_SEND_FOLLOWUP_TEXT", "1")
).strip().lower() not in {"0", "false", "no", "off"}
SHARE_LINK_QUICK_PATH = str(
    os.environ.get("XMONITOR_SHARE_LINK_QUICK_PATH", "0")
).strip().lower() not in {"0", "false", "no", "off"}
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
    os.environ.get("XMONITOR_DM_ASSUME_SUCCESS_AFTER_CLICK", "1")
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
DM_CLOSED_FALLBACK_REPLY_TEXT = "大佬 您的私信是关闭的，如果有需要可以给我私信呀"
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
CONTENT_FILTER_BLOCKED_MENTIONS = ("@manateelazycat",)
LLM_FILTER_ENABLED = str(
    os.environ.get("XMONITOR_LLM_FILTER_ENABLED", "0")
).strip().lower() in {"1", "true", "yes", "on"}
LLM_FILTER_BASE_URL = str(os.environ.get("XMONITOR_LLM_BASE_URL", "") or "").strip()
LLM_FILTER_API_KEY = str(os.environ.get("XMONITOR_LLM_API_KEY", "EMPTY") or "").strip()
LLM_FILTER_MODEL = str(os.environ.get("XMONITOR_LLM_MODEL", "") or "").strip()
try:
    LLM_FILTER_TIMEOUT_SEC = float(os.environ.get("XMONITOR_LLM_TIMEOUT_SEC", "8"))
except Exception:
    LLM_FILTER_TIMEOUT_SEC = 8.0
try:
    LLM_FILTER_CACHE_TTL_SEC = int(os.environ.get("XMONITOR_LLM_CACHE_TTL_SEC", str(6 * 3600)))
except Exception:
    LLM_FILTER_CACHE_TTL_SEC = 6 * 3600
try:
    LLM_FILTER_CACHE_MAX_ENTRIES = int(os.environ.get("XMONITOR_LLM_CACHE_MAX", "5000"))
except Exception:
    LLM_FILTER_CACHE_MAX_ENTRIES = 5000

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
reply_metrics_lock = threading.Lock()
notify_reply_templates = list(DEFAULT_NOTIFY_REPLY_TEMPLATES)
dm_message_templates = list(DEFAULT_DM_TEMPLATES)
last_reply_action_ts = 0.0
last_dm_action_ts = 0.0
last_reply_prepare_refresh_ts = 0.0
reply_outcome_recent = deque(maxlen=50)  # 最近回复成功/失败，用于自适应节流
reply_failure_streak = 0
reply_handle_failures = {}  # {handle: {"count": int, "first_ts": float, "cooldown_until": float, "last_err": str}}
dm_unavailable_cache = {}  # {handle: expire_ts}
dm_unavailable_cache_lock = threading.Lock()
llm_filter_cache = {}  # {signature: {"ts": float, "skip": bool, "reason": str}}
llm_filter_cache_lock = threading.Lock()

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

            # ===== 通知随机间隔刷新扫描 =====
            if notify_enabled and monitor_active and (current_time - last_notification_scan >= notification_interval):
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
                        ensure_notification_tab(blocked_users)
                        scan_persistent_notification_tab(blocked_users, max_recent_minutes=recent_window_minutes)
                        last_notification_scan = now_ts
                        notification_interval = get_random_notification_interval()
                        log_to_ui("debug", f"📬 下次通知扫描间隔: {notification_interval:.1f}s")

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
                    LLM_FILTER_TIMEOUT_SEC = max(2.0, min(30.0, float(data.get("llm_filter_timeout_sec", LLM_FILTER_TIMEOUT_SEC))))
                except Exception:
                    pass

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
    return round(random.uniform(low, high), 2)


def get_random_notification_refresh_interval():
    """生成通知页刷新间隔（秒），避免每轮都刷新页面。"""
    low = max(5.0, float(NOTIFICATION_REFRESH_INTERVAL_MIN_SEC))
    high = max(low, float(NOTIFICATION_REFRESH_INTERVAL_MAX_SEC))
    return round(random.uniform(low, high), 2)


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


def should_skip_content_by_policy(content):
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
    max_tokens=120
):
    endpoint = _llm_filter_endpoint(base_url=base_url)
    model_name = str(model if model is not None else LLM_FILTER_MODEL or "").strip()
    if not endpoint:
        raise ValueError("LLM Base URL 未配置")
    if not model_name:
        raise ValueError("LLM 模型名未配置")

    api_key_val = str(api_key if api_key is not None else LLM_FILTER_API_KEY or "EMPTY").strip() or "EMPTY"
    try:
        timeout_val = float(timeout_sec if timeout_sec is not None else LLM_FILTER_TIMEOUT_SEC)
    except Exception:
        timeout_val = float(LLM_FILTER_TIMEOUT_SEC)
    timeout_val = max(2.0, min(30.0, timeout_val))

    base_payload = {
        "model": model_name,
        "temperature": 0,
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


def _call_openai_compatible_filter_api(content):
    prompt = (
        "你是评论过滤器。只输出JSON对象，不要输出其他文本。\n"
        "返回字段: skip(boolean), reason(string), intent_score(number 0-100)。\n"
        "规则:\n"
        "1) 纯表情或无意义字符 -> skip=true, reason=emoji_or_noise\n"
        "2) 包含 @manateelazycat -> skip=true, reason=blocked_mention\n"
        "3) 其他正常评论 -> skip=false, reason=normal\n"
        f"评论内容: {content}"
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


def _rule_based_intent_analysis(content):
    text = _normalize_content_for_filter(content)
    if not text:
        return {"intent_score": 0, "intent_level": "noise", "signals": ["empty_content"]}
    if _is_emoji_only_content(text):
        return {"intent_score": 0, "intent_level": "noise", "signals": ["emoji_only"]}

    lower = text.lower()
    score = 8
    signals = []

    high_keywords = [
        "询价", "报价", "价格", "多少钱", "怎么卖", "购买", "下单", "采购", "试用",
        "演示", "demo", "部署", "方案", "合作", "联系", "vx", "微信", "whatsapp",
        "quote", "pricing", "price", "buy", "purchase",
    ]
    medium_keywords = [
        "怎么用", "怎么做", "支持吗", "能不能", "可以吗", "介绍下", "了解", "咨询",
        "details", "feature", "功能", "效果",
    ]

    for kw in high_keywords:
        if kw in lower:
            score += 26
            signals.append(f"kw:{kw}")
    for kw in medium_keywords:
        if kw in lower:
            score += 12
            signals.append(f"kw:{kw}")

    if re.fullmatch(r"[1１]+", text):
        score += 42
        signals.append("single_digit_interest")
    if re.search(r"(加|留|联系).{0,4}(微信|vx|v|whatsapp)", text, re.IGNORECASE):
        score += 25
        signals.append("contact_request")
    if re.search(r"(预算|合同|付款|交付|周期|售后)", text):
        score += 18
        signals.append("business_term")
    if len(text) >= 12:
        score += 8

    score = int(max(0, min(100, score)))
    level = _score_to_intent_level(score)
    if not signals and len(text) <= 3:
        level = "noise"
        score = min(score, 15)
        signals.append("very_short_text")
    return {"intent_score": score, "intent_level": level, "signals": signals}


def _llm_intent_analysis(content, *, base_url=None, api_key=None, model=None, timeout_sec=None):
    prompt = (
        "你是销售线索意向识别器。请严格输出JSON对象，不要输出任何解释文本。\n"
        "字段:\n"
        "- intent_score: 0-100\n"
        "- intent_level: high|medium|low|noise\n"
        "- is_intent_user: true/false\n"
        "- buying_signals: string[]\n"
        "- reason: string\n\n"
        "判定要点:\n"
        "1) 明确询价/报价/购买/部署/演示/联系方式 => high或medium\n"
        "2) 功能咨询/了解详情 => medium或low\n"
        "3) 纯闲聊、纯表情、无意义灌水 => noise\n"
        f"评论内容: {content}"
    )
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

    return {
        "intent_score": score,
        "intent_level": level,
        "is_intent_user": bool(is_intent_user),
        "buying_signals": buying_signals,
        "reason": reason,
    }


def analyze_comment_intent(content, *, base_url=None, api_key=None, model=None, timeout_sec=None):
    text = _normalize_content_for_filter(content)
    rule_result = _rule_based_intent_analysis(text)
    rule_score = int(rule_result.get("intent_score", 0))
    rule_level = str(rule_result.get("intent_level", "noise"))
    rule_signals = list(rule_result.get("signals", []))

    result = {
        "content": text,
        "intent_score": rule_score,
        "intent_level": rule_level,
        "is_intent_user": rule_score >= 50,
        "signals": list(rule_signals),
        "reason": "rule_only",
        "rule_score": rule_score,
        "rule_level": rule_level,
        "llm_used": False,
        "llm_score": None,
        "llm_level": "",
        "llm_reason": "",
        "llm_error": "",
    }

    if not _llm_runtime_ready(base_url=base_url, model=model):
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
            return result
    except Exception as e:
        result["llm_error"] = str(e)
        return result

    llm_score = int(llm_result.get("intent_score", 0))
    llm_level = str(llm_result.get("intent_level", "noise"))
    llm_reason = str(llm_result.get("reason", "") or "").strip()
    llm_signals = list(llm_result.get("buying_signals", []))

    blended_score = int(round(max(rule_score, (rule_score * 0.35 + llm_score * 0.65))))
    blended_score = max(0, min(100, blended_score))
    blended_level = _score_to_intent_level(blended_score)

    merged_signals = []
    for sig in (rule_signals + llm_signals):
        sig_text = str(sig).strip()
        if sig_text and sig_text not in merged_signals:
            merged_signals.append(sig_text)

    result.update({
        "intent_score": blended_score,
        "intent_level": blended_level,
        "is_intent_user": bool(blended_score >= 50 or llm_result.get("is_intent_user", False)),
        "signals": merged_signals[:12],
        "reason": llm_reason or "rule_llm_blended",
        "llm_used": True,
        "llm_score": llm_score,
        "llm_level": llm_level,
        "llm_reason": llm_reason,
    })
    return result


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
        text_eles = article.eles('css:[data-testid="tweetText"]', timeout=0)
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


def _extract_notification_status_info(article):
    """提取通知关联的 status 用户和 status_id。"""
    try:
        links = article.eles('tag:a', timeout=0)
        for link in links:
            href = (link.attr('href') or '').strip()
            if not href:
                continue

            # 标准路径：/username/status/123...
            user_matches = list(re.finditer(r'/([A-Za-z0-9_]+)/status/(\d{6,25})', href))
            if user_matches:
                # 同一 href 可能出现拼接链接，优先取更长的 status_id
                best = None
                best_len = -1
                for m in user_matches:
                    sid = _pick_best_status_id(m.group(2), href)
                    if sid and len(sid) > best_len:
                        best = (m.group(1), sid)
                        best_len = len(sid)
                if best:
                    return f"@{best[0]}", best[1]

            # X 新版路径常见形态：/i/status/123... 或 /i/web/status/123...
            m = re.search(r'/(?:i/(?:web/)?|web/)?status/(\d{6,25})', href)
            if m:
                sid = _pick_best_status_id(m.group(1), href)
                if sid:
                    return None, sid

            # 某些跳转链接里会带 conversation_id
            m = re.search(r'conversation_id=(\d{6,25})', href)
            if m:
                sid = _pick_best_status_id(m.group(1), href)
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


def scan_notifications_page(page, blocked_list, max_recent_minutes=None):
    """
    通知页面扫描（回复优先）：
    - 优先抓取“回复了你/提到了你”类通知
    - 支持 tweetText / div[lang] / 文本回退 多策略提取正文
    - 使用 status_id 去重，减少重复和漏抓
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

        # 只处理最新 N 条
        if len(articles) > max_scan_articles:
            articles = articles[:max_scan_articles]
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
        skipped_emoji_only = 0
        skipped_blocked_mention = 0
        article_errors = 0
        trace_logs = []
        trace_limit = NOTIFICATION_TRACE_MAX_ARTICLES if NOTIFICATION_VERBOSE_TRACE else 0

        if NOTIFICATION_VERBOSE_TRACE:
            log_to_ui(
                "debug",
                f"🔎 [NotifyTrace] scan_start url={page.url} articles={len(articles)} recent_window={max_recent_minutes}min"
            )

        for idx, article in enumerate(articles, start=1):
            try:
                # 快速获取文章文本用于初步判断
                article_text = article.text or ""
                if not article_text:
                    skipped_empty_text += 1
                    if idx <= trace_limit:
                        trace_logs.append(f"A{idx:02d} skip=empty_text")
                    continue

                # ===== 0. 快速过滤无效类型 =====
                article_lower = article_text.lower()
                trace_sample = _normalize_one_line(article_text)

                # 快速跳过点赞、转发、关注等
                skip_keywords = [
                    '点赞了', 'liked', 'liked your', '转发了', 'reposted', 'retweeted',
                    '关注了你', 'followed you', '视频来源',
                    '点赞了你的帖子', 'liked your post', 'liked your reply',
                    '转发了你的帖子', 'reposted your', 'retweet了'
                ]
                if any(k in article_lower for k in skip_keywords):
                    skipped_interaction += 1
                    if idx <= trace_limit:
                        trace_logs.append(f"A{idx:02d} skip=interaction text={trace_sample}")
                    continue

                # 回复相关提示（全部通知里通常会出现这些文案）
                reply_hint_keywords = [
                    '回复了你', '回复了你的帖子', '回复了你的贴文', '提到了你', '在帖子中提到了你',
                    'replied to you', 'replied to your post', 'mentioned you', 'mentioned you in a post'
                ]
                is_reply_like = any(k in article_lower for k in reply_hint_keywords)
                is_interaction_only = any(k in article_lower for k in skip_keywords)

                # 必须是 status 类型（评论/提及相关），但对明确“回复/提及”做兜底
                status_handle, status_id = _extract_notification_status_info(article)
                if not status_id and not is_reply_like:
                    skipped_non_reply += 1
                    if idx <= trace_limit:
                        hrefs = _collect_notification_hrefs(article)
                        trace_logs.append(
                            f"A{idx:02d} skip=non_reply status_id=None is_reply_like={is_reply_like} hrefs={hrefs} text={trace_sample}"
                        )
                    continue
                if not status_id and is_reply_like:
                    skipped_no_status += 1
                    if idx <= trace_limit:
                        hrefs = _collect_notification_hrefs(article)
                        trace_logs.append(
                            f"A{idx:02d} keep=fallback_no_status is_reply_like={is_reply_like} hrefs={hrefs} text={trace_sample}"
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
                delegated_now = get_effective_delegated_account()
                delegated_norm = delegated_now.strip().lstrip('@').lower() if delegated_now else ''

                # 如果被提取成了自己的账号，不要直接丢弃（这类误判在通知里比较常见）
                should_skip_block = (handle in blocked_list and (not delegated_norm or handle_norm != delegated_norm))
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
                should_skip_policy, skip_reason = should_skip_content_by_policy(content)
                if should_skip_policy:
                    if skip_reason == "emoji_only":
                        skipped_emoji_only += 1
                    elif skip_reason == "blocked_mention":
                        skipped_blocked_mention += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f"A{idx:02d} skip=content_policy reason={skip_reason} handle={handle} status_id={status_id} text={trace_sample}"
                        )
                    continue

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
                    "status_url": (
                        f"https://x.com/{normalize_handle(status_handle)}/status/{status_id}"
                        if status_id and status_handle else
                        (f"https://x.com/i/status/{status_id}" if status_id else "")
                    )
                })
                log_to_ui("success", f"📬 新通知: {handle} - {content[:20]}...")
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
        if skipped_emoji_only > 0:
            log_to_ui("debug", f"📋 [Notify] 跳过纯表情: {skipped_emoji_only}")
        if skipped_blocked_mention > 0:
            log_to_ui("debug", f"📋 [Notify] 跳过指定@内容: {skipped_blocked_mention}")
        if article_errors > 0:
            log_to_ui("debug", f"📋 [Notify] article异常: {article_errors}")
        if new_captured == 0 and len(articles) > 0:
            log_to_ui("warn", f"📬 本轮扫描未捕获新通知（articles={len(articles)}）")
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
                    skipped_policy += 1
                    continue
                if should_skip_duplicate_content(item.get("handle", ""), item.get("content", "")):
                    skipped_dup_content += 1
                    continue
                history_ids.add(item["key"])
                pending_results.append(item)
                msg_queue.put({"type": "new_data", "data": item})
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
                msg_queue.put({"type": "new_data", "data": item})
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
    global notification_tab, global_browser, notification_last_refresh_at, notification_refresh_interval

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
            notification_refresh_interval = get_random_notification_refresh_interval()
        except Exception as e:
            log_to_ui("error", f"创建通知标签页失败: {str(e)}")
            notification_tab = None


def close_notification_tab():
    """关闭持久通知标签页"""
    global notification_tab, notification_last_refresh_at

    with notification_tab_lock:
        if notification_tab:
            try:
                notification_tab.close()
            except Exception:
                pass
            notification_tab = None
            notification_last_refresh_at = 0.0
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
    global notification_tab, notification_last_refresh_at, notification_refresh_interval, notification_disconnect_streak

    if notification_tab is None:
        return

    try:
        with notification_tab_lock:
            now_ts = time.time()
            need_refresh = (notification_last_refresh_at <= 0) or ((now_ts - notification_last_refresh_at) >= notification_refresh_interval)

            # 仅按随机周期刷新，避免固定高频刷新触发风控
            if need_refresh:
                try:
                    notification_tab.refresh()
                    time.sleep(random.uniform(0.8, 1.8))
                    notification_last_refresh_at = now_ts
                    notification_refresh_interval = get_random_notification_refresh_interval()
                    log_to_ui("debug", f"📬 通知页下次刷新间隔: {notification_refresh_interval:.1f}s")
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

            # 滚动到顶部
            try:
                notification_tab.run_js('window.scrollTo(0, 0);')
                time.sleep(random.uniform(0.25, 0.8))
            except Exception:
                pass

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
        skipped_policy = 0
        if notif_items:
            for item in notif_items:
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
                    msg_queue.put({"type": "new_data", "data": item})
                    new_count += 1
            if new_count > 0:
                save_state()
                log_to_ui("success", f"📬 通知扫描: 新增 {new_count} 条")
            if skipped_dup_content > 0:
                log_to_ui("debug", f"📋 [Notify] 跳过同用户重复内容: {skipped_dup_content}")
            if skipped_policy > 0:
                log_to_ui("debug", f"📋 [Notify] 跳过内容过滤: {skipped_policy}")
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

    try:
        editor.click()
    except Exception:
        pass

    _dm_humanized_idle(tab, 0.06, 0.22, "私信输入前")
    try:
        editor.input(text, clear=True)
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
            const el = arguments[0];
            const text = String(arguments[1] || '');
            if (!el) return false;
            el.focus();
            if (el.value !== undefined) {
                el.value = '';
                el.value = text;
            } else if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
                el.textContent = '';
                try {
                    document.execCommand('insertText', false, text);
                } catch (e) {
                    el.textContent = text;
                }
            } else {
                el.textContent = text;
            }
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
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
            const el = arguments[0];
            const text = String(arguments[1] || '');
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
    """统计探针文本在当前页面正文中的出现次数。"""
    if not tab or not probe_text:
        return 0
    try:
        body_text = str(tab.run_js("return (document.body && document.body.innerText) ? document.body.innerText : ''") or "")
    except Exception:
        try:
            body_text = str(tab.ele('tag:body', timeout=0.3).text or "")
        except Exception:
            body_text = ""
    if not body_text:
        return 0
    haystack = body_text.lower()
    needle = str(probe_text).lower()
    return haystack.count(needle)


def _confirm_dm_message_sent(tab, before_counts, probes, wait_sec=1.15):
    """
    发送后确认消息是否落库：
    - 任一探针出现次数增加，视为已发送成功
    """
    if not probes:
        return False
    deadline = time.time() + max(0.3, float(wait_sec))
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


def _click_with_prompt_guard(tab, element, action_name):
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
            try:
                tab.run_js('arguments[0].click()', element)
                return True, ""
            except Exception as e_js:
                last_err = e_js
                if _is_unhandled_prompt_error(e_js):
                    _prepare_reply_prompt_guard(tab, f"{action_name}JS重试")
                    time.sleep(random.uniform(0.15, 0.35))
                    continue
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


def _open_dm_editor_for_handle(tab, handle):
    """打开某用户私信编辑框，返回编辑框元素。"""
    handle_norm = normalize_handle(handle)
    if not handle_norm:
        return None, "缺少目标用户handle"
    if _is_dm_unavailable_cached(handle_norm):
        return None, "该用户当前不可私信（缓存命中）"

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
    editor_selectors = [
        'css:textarea[data-testid="dm-composer-textarea"]',
        'css:textarea[placeholder="Message"]',
        'css:textarea[placeholder*="消息"]',
        'css:[data-testid="dmComposerTextInput"]',
        'css:[data-testid="dmComposerTextInput"] [contenteditable="true"]',
        'css:div[role="textbox"][contenteditable="true"]',
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

    def _find_editor(timeout_each=2.5):
        for selector in editor_selectors:
            try:
                cand = tab.ele(selector, timeout=timeout_each)
                if cand and cand.states.is_displayed:
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

    open_attempts = DM_EDITOR_OPEN_RETRY_HEADLESS if headless_mode else DM_EDITOR_OPEN_RETRY_NORMAL
    for attempt in range(open_attempts):
        if attempt == 0:
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

        clicked_dm_btn, click_dm_err = _click_with_prompt_guard(tab, dm_btn, "点击私信入口按钮")
        if not clicked_dm_btn:
            log_to_ui("debug", f"📨 私信入口点击失败(尝试{attempt + 1}/{open_attempts}): {click_dm_err}")
            continue
        time.sleep(random.uniform(0.28, 0.62))

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
                _click_with_prompt_guard(tab, dm_btn_retry, "重试点击私信入口按钮")
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
    _capture_runtime_diagnostic(
        tab,
        "open_dm_editor_failed",
        err=f"handle={handle_norm}",
        selectors=dm_btn_selectors + editor_selectors,
        extra={
            "handle": handle_norm,
            "open_attempts": open_attempts,
            "headless_mode": bool(headless_mode),
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
        'css:[data-testid="dmComposerTextInput"]',
        'css:[data-testid="dmComposerTextInput"] [contenteditable="true"]',
        'css:div[role="textbox"][contenteditable="true"]',
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

    def _find_editor(rounds=2, timeout_each=1.5):
        for _ in range(max(1, rounds)):
            for selector in editor_selectors:
                try:
                    cand = tab.ele(selector, timeout=timeout_each)
                    if cand and cand.states.is_displayed:
                        return cand
                except Exception:
                    continue
            time.sleep(random.uniform(0.08, 0.22))
        return None

    def _find_send_btn(rounds=2, timeout_each=1.2):
        for _ in range(max(1, rounds)):
            cand = _wait_first_actionable(tab, send_btn_selectors, timeout=timeout_each, poll=0.08)
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
            # 长文仅允许很小偏差（如末尾标点/空格）
            if current.endswith(exp) and (len(current) - len(exp)) <= 6:
                return True
            return False
        except Exception:
            return False

    def _wait_send_button_after_input(editor_el, expected_text, link_mode=False):
        """输入后等待发送按钮可点击；链接模式下进行额外状态唤醒。"""
        def _wait_link_preview_ready(timeout_sec=3.6):
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
                _dm_humanized_idle(tab, 0.12, 0.24, "等待链接预览加载")
            return False

        if link_mode:
            _wait_link_preview_ready(timeout_sec=3.8)
        btn = _find_send_btn(rounds=2, timeout_each=1.0)
        if btn:
            return btn
        if not link_mode:
            return None

        for _ in range(3):
            _dm_humanized_idle(tab, 0.12, 0.24, "链接消息等待发送按钮")
            if _refresh_dm_editor_state(tab, editor_el, expected_text):
                _dm_humanized_idle(tab, 0.06, 0.14, "链接消息状态刷新后等待")
            btn = _find_send_btn(rounds=2, timeout_each=1.0)
            if btn:
                return btn
        return None

    max_attempts = DM_SEND_RETRY_HEADLESS if headless_mode else DM_SEND_RETRY_NORMAL
    last_err = "发送私信失败"
    dm_text = _sanitize_dm_message_text(text)
    link_only_mode = _is_link_only_message(dm_text)
    probes = _build_dm_message_probes(dm_text)

    for attempt in range(1, max_attempts + 1):
        _throttle_dm_action_if_needed(f"私信发送尝试{attempt}")
        _prepare_reply_prompt_guard(tab, f"私信发送尝试{attempt}")
        _dm_humanized_idle(tab, 0.08, 0.32, f"私信发送尝试{attempt}")
        before_counts = {p: _count_dm_probe_occurrence(tab, p) for p in probes}

        editor = _find_editor(rounds=2, timeout_each=1.4)
        if not editor:
            _handle_dm_passcode_prompt(tab)
            editor = _find_editor(rounds=2, timeout_each=1.6)
        if not editor:
            last_err = "未找到私信输入框"
            time.sleep(random.uniform(0.15, 0.35))
            continue

        try:
            editor.click()
        except Exception:
            pass

        typed_ok = _paste_dm_text_exact(tab, editor, dm_text)
        if not typed_ok:
            typed_ok = _humanized_type_dm_text(tab, editor, dm_text)
        if not typed_ok:
            last_err = "输入私信内容失败"
            time.sleep(random.uniform(0.15, 0.35))
            continue
        if not _editor_has_text(editor, dm_text):
            if link_only_mode:
                _refresh_dm_editor_state(tab, editor, dm_text)
                if not _editor_has_text(editor, dm_text):
                    last_err = "输入后链接状态未稳定写入编辑器"
                    _dm_humanized_idle(tab, 0.08, 0.2, "链接输入校验失败后等待")
                    continue
            else:
                last_err = "输入后文本未稳定写入编辑器"
                _dm_humanized_idle(tab, 0.08, 0.2, "私信输入校验失败后等待")
                continue

        _dm_humanized_idle(tab, 0.08, 0.24, "私信发送前")
        send_btn = _wait_send_button_after_input(editor, dm_text, link_mode=link_only_mode)
        if send_btn:
            clicked_send, click_err = _click_with_prompt_guard(tab, send_btn, "点击私信发送按钮")
            if clicked_send:
                _dm_humanized_idle(tab, 0.18, 0.42, "私信发送后确认")
                if _composer_cleared(editor):
                    return True, ""
                if _confirm_dm_message_sent(tab, before_counts, probes, wait_sec=1.15):
                    log_headless_debug("私信发送后输入框未清空，但已确认消息落库，按成功处理")
                    return True, ""
                if DM_ASSUME_SUCCESS_AFTER_CLICK:
                    log_to_ui("warn", "⚠️ 私信点击发送后状态不确定，按成功处理以避免重复发送")
                    return True, ""
                last_err = "点击私信发送后输入框未清空"
                continue
            last_err = click_err

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
                _dm_humanized_idle(tab, 0.18, 0.42, "私信发送DOM兜底后")
                if _composer_cleared(editor):
                    return True, ""
                if _confirm_dm_message_sent(tab, before_counts, probes, wait_sec=1.1):
                    log_headless_debug("DOM发送后已确认消息落库，按成功处理")
                    return True, ""
                if DM_ASSUME_SUCCESS_AFTER_CLICK:
                    log_to_ui("warn", "⚠️ 私信DOM发送后状态不确定，按成功处理以避免重复发送")
                    return True, ""
                last_err = "DOM点击发送后输入框未清空"
                continue
        except Exception:
            pass

        if not last_err:
            last_err = "未找到可点击的私信发送按钮"

        time.sleep(random.uniform(0.2, 0.45))

    _capture_runtime_diagnostic(
        tab,
        "send_dm_message_failed",
        err=last_err,
        selectors=editor_selectors + send_btn_selectors,
        extra={
            "max_attempts": max_attempts,
            "message_len": len(dm_text),
            "headless_mode": bool(headless_mode),
        }
    )
    return False, last_err


def _send_dm_message_with_retry(tab, text, handle=""):
    """私信发送增强重试（无头模式更激进），必要时重开私信编辑器。"""
    max_attempts = DM_SEND_RETRY_HEADLESS if headless_mode else DM_SEND_RETRY_NORMAL
    last_err = "发送私信失败"
    handle_norm = normalize_handle(handle)

    for attempt in range(1, max_attempts + 1):
        ok, err = _send_dm_message(tab, text)
        if ok:
            return True, ""
        last_err = str(err or last_err)
        log_headless_debug(f"私信发送重试触发 attempt={attempt}/{max_attempts}, err={last_err}")
        if attempt >= max_attempts:
            break

        _prepare_reply_prompt_guard(tab, f"私信重试准备{attempt}")
        need_reopen = any(k in last_err for k in ["输入框", "发送按钮", "点击私信发送"])
        if need_reopen and handle_norm:
            _dm_humanized_idle(tab, 0.12, 0.28, f"私信重试{attempt}重开编辑器前")
            _open_dm_editor_for_handle(tab, handle_norm)
        _dm_humanized_idle(tab, 0.22, 0.68, f"私信重试{attempt}间隔")

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
        "cannot send direct messages",
        "can't be messaged",
        "unable to message",
    ])


def _run_dm_send_sequence_once(tab, dm_handle, share_link, dm_text, mark_func=None, progress=None):
    """执行一次完整私信发送（开私信 -> 发链接 -> 发文案）。"""
    if progress is None:
        progress = {"link_sent": False, "text_sent": False}
    dm_editor, dm_err = _open_dm_editor_for_handle(tab, dm_handle)
    if not dm_editor:
        dm_err_text = str(dm_err or "")
        if _is_dm_closed_error_text(dm_err_text):
            return False, dm_err_text, True
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
        _prepare_reply_prompt_guard(tab, "第二条私信前")
        _humanized_gap_between_dm_messages(tab)
        ok_dm_2, err_dm_2 = _send_dm_message_with_retry(tab, dm_text, handle=dm_handle)
        if not ok_dm_2:
            return False, f"发送私信文案失败: {err_dm_2}", False
        progress["text_sent"] = True
        if callable(mark_func):
            mark_func("send_dm_text")
        log_to_ui("debug", "📨 已发送私信文案")
    else:
        log_to_ui("debug", "📨 跳过重复发送私信文案（本流程已成功发送）")
    return True, "", False


def _run_dm_send_with_recovery(tab, dm_handle, share_link, dm_text, mark_func=None, best_effort=False):
    """私信发送恢复策略：原标签页 -> 重建标签页 -> 重启浏览器 -> 有头兜底。"""
    global headless_mode
    handle_norm = normalize_handle(dm_handle)
    last_err = "发送私信失败"
    work_tab = tab
    progress = {"link_sent": False, "text_sent": False}

    strategies = [("当前标签页", lambda: work_tab)]
    if (not best_effort) and DM_RECOVERY_ENABLE_RECREATE_TAB:
        strategies.append(("重建回复标签页", lambda: ensure_reply_work_tab(force_recreate=True)))
    if (not best_effort) and DM_RECOVERY_ENABLE_RESTART_BROWSER:
        strategies.append(("重启浏览器并重建标签页", lambda: (restart_global_browser(), ensure_reply_work_tab(force_recreate=True))[1]))

    for idx, (label, tab_provider) in enumerate(strategies, start=1):
        try:
            work_tab = tab_provider()
        except Exception as e:
            last_err = f"{label}失败: {e}"
            log_to_ui("warn", f"⚠️ 私信恢复步骤失败({idx}/{len(strategies)}): {last_err}")
            continue

        ok, err, dm_closed = _run_dm_send_sequence_once(
            work_tab, handle_norm, share_link, dm_text, mark_func=mark_func, progress=progress
        )
        if ok:
            if idx > 1:
                log_to_ui("success", f"✅ 私信发送已通过恢复策略成功: {label}")
            return True, "", False, work_tab
        if dm_closed:
            return False, err, True, work_tab

        last_err = str(err or last_err)
        log_to_ui("warn", f"⚠️ 私信发送失败({label}): {last_err}")
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
            }
        )

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
                    work_tab, handle_norm, share_link, dm_text, mark_func=mark_func, progress=progress
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


def send_notification_reply(item, message, dm_message=""):
    """针对通知记录发送回复。"""
    global last_reply_prepare_refresh_ts
    if not global_token.strip():
        return False, "请先配置并验证 auth_token 后再回复"

    status_id = extract_status_id_from_notification_item(item)
    if not status_id:
        return False, "该通知缺少可回复的状态ID（可能是兜底通知记录）"

    handle_hint = item.get("handle", "")

    with reply_action_lock:
        _throttle_reply_action_if_needed()
        _set_reply_flow_active(True)
        flow_started_at = time.perf_counter()
        stage_marks = {}

        def _mark(stage_name):
            stage_marks[stage_name] = time.perf_counter() - flow_started_at

        try:
            tab = ensure_reply_work_tab()
        except Exception as e:
            _set_reply_flow_active(False)
            return False, f"回复工作标签页初始化失败: {e}"

        try:
            _prepare_reply_prompt_guard(tab, "回复流程启动")
            log_to_ui("info", f"💬 开始执行通知回复(复用全局浏览器): {handle_hint} -> status {status_id}")
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
                target_article = None
                target_reply_btn = None
                target_score = 0
                required_score = 260 if status_id else 120
                for attempt in range(4):
                    _prepare_reply_prompt_guard(tab, f"匹配通知卡片尝试{attempt + 1}")
                    if attempt == 3 and not target_article:
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
                    return None, None, 0, None, None, "未在通知页定位到目标评论卡片"

                if target_score < required_score:
                    return None, None, target_score, None, None, f"通知卡片匹配置信度不足(score={target_score})，已阻止误回复"

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
                _reply_humanized_idle(tab, 0.28, 0.62, "回复输入后等待按钮激活")

                send_btn = None
                send_selectors = [
                    'css:[data-testid="tweetButton"]',
                    'css:button[data-testid="tweetButton"]',
                    'css:[data-testid="tweetButtonInline"]',
                ]
                send_btn = _wait_first_actionable(tab, send_selectors, timeout=2.6, poll=0.1)
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
                    _reply_humanized_idle(tab, 0.2, 0.5, "回复发送按钮二次等待")
                    send_btn = _wait_first_actionable(tab, send_selectors, timeout=2.0, poll=0.1)

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
                        _reply_humanized_idle(tab, 0.48, 1.02, "回复发送后稳定等待")
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

                _reply_humanized_idle(tab, 0.26, 0.58, "点击右下角回复按钮前")
                clicked_send, click_send_err = _click_with_prompt_guard(tab, send_btn, "点击右下角回复发送按钮")
                if not clicked_send:
                    return False, click_send_err
                log_to_ui("debug", "💬 已点击右下角回复按钮")
                _reply_humanized_idle(tab, 0.48, 1.02, "回复发送后稳定等待")
                return True, ""

            _prepare_notifications_view(force_refresh=False)
            log_to_ui("debug", "💬 已准备通知视图，开始定位目标通知卡片")
            _reply_humanized_idle(tab, 0.2, 0.48, "定位通知卡片前")

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
            log_to_ui(
                "debug",
                f"💬 已定位通知卡片 score={target_score}, status_id={matched_status_id}, handle={matched_handle or ''}"
            )
            _reply_humanized_idle(tab, 0.18, 0.44, "定位卡片后稳定等待")

            share_link_fallback = _get_status_link_from_item(item, matched_handle, matched_status_id)
            use_quick_share_link = bool(
                share_link_fallback and "/status/" in share_link_fallback and _should_use_share_link_quick_path()
            )
            if use_quick_share_link:
                share_link, share_err = share_link_fallback, ""
                log_to_ui("debug", "🔗 已启用快速链接路径（长队列稳定模式）")
            else:
                _prepare_reply_prompt_guard(tab, "复制分享链接前")
                _reply_humanized_idle(tab, 0.14, 0.36, "复制分享链接前")
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
            log_to_ui("debug", f"🔗 已准备分享链接: {share_link}")
            _reply_humanized_idle(tab, 0.16, 0.4, "发送回复前")

            ok_reply, err_reply = _send_reply_from_button(target_reply_btn, target_score, message)
            if not ok_reply:
                return False, err_reply
            _mark("send_reply")

            dm_handle = item.get("handle", "")
            dm_text = _sanitize_dm_message_text(dm_message)
            if not dm_text:
                dm_text = (dm_message_templates[0] if dm_message_templates else DM_FOLLOWUP_TEXT)
            dm_text = _sanitize_dm_message_text(dm_text)
            ok_dm, dm_err, dm_closed, dm_tab = _run_dm_send_with_recovery(
                tab,
                dm_handle,
                share_link,
                dm_text,
                mark_func=_mark
            )
            if dm_tab:
                tab = dm_tab
            if not ok_dm:
                if dm_closed:
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
        target_idx = -1
        for idx, item in enumerate(pending_results):
            if item.get('key') == key and item.get('source') == '通知页面':
                target = dict(item)
                target_idx = idx
                break

    if not target:
        return jsonify({"status": "err", "msg": "通知记录不存在"}), 404

    target_handle = target.get('handle', '')
    allowed, budget_msg = _check_reply_failure_budget(target_handle)
    if not allowed:
        log_to_ui("warn", f"⏸️ 触发失败预算熔断: {target_handle} - {budget_msg}")
        return jsonify({"status": "err", "msg": budget_msg}), 429

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
        log_to_ui("warn", f"⚠️ 通知回复失败: {err}")
        return jsonify({"status": "err", "msg": err}), 500

    reply_time_text = datetime.datetime.now().strftime("%H:%M:%S")
    with data_lock:
        if target_idx >= 0 and target_idx < len(pending_results):
            row = pending_results[target_idx]
            # 双保险：避免并发期间顺序变化导致 idx 指向错误记录
            if row.get('key') == key and row.get('source') == '通知页面':
                row['notify_replied'] = True
                row['notify_reply_text'] = message
                row['notify_dm_text'] = dm_message
                row['notify_reply_time'] = reply_time_text
            else:
                for row2 in pending_results:
                    if row2.get('key') == key and row2.get('source') == '通知页面':
                        row2['notify_replied'] = True
                        row2['notify_reply_text'] = message
                        row2['notify_dm_text'] = dm_message
                        row2['notify_reply_time'] = reply_time_text
                        break
        else:
            for row2 in pending_results:
                if row2.get('key') == key and row2.get('source') == '通知页面':
                    row2['notify_replied'] = True
                    row2['notify_reply_text'] = message
                    row2['notify_dm_text'] = dm_message
                    row2['notify_reply_time'] = reply_time_text
                    break
    save_state()

    log_to_ui("success", f"✅ 已发送通知回复: {target_handle} -> {message[:30]}")
    return jsonify({
        "status": "ok",
        "reply_time": reply_time_text,
    })


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


def _extract_llm_runtime_from_payload(payload):
    payload = payload or {}
    base_url = str(payload.get("base_url", LLM_FILTER_BASE_URL) or "").strip()
    api_key = str(payload.get("api_key", LLM_FILTER_API_KEY) or "").strip() or "EMPTY"
    model = str(payload.get("model", LLM_FILTER_MODEL) or "").strip()
    try:
        timeout_sec = float(payload.get("timeout_sec", LLM_FILTER_TIMEOUT_SEC))
    except Exception:
        timeout_sec = float(LLM_FILTER_TIMEOUT_SEC)
    timeout_sec = max(2.0, min(30.0, timeout_sec))
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
    if not content:
        return jsonify({"status": "err", "msg": "评论内容不能为空"}), 400

    runtime = _extract_llm_runtime_from_payload(payload)
    analysis = analyze_comment_intent(
        content,
        base_url=runtime["base_url"],
        api_key=runtime["api_key"],
        model=runtime["model"],
        timeout_sec=runtime["timeout_sec"],
    )
    return jsonify({
        "status": "ok",
        "analysis": analysis,
    })


@app.route('/api/set_llm_filter_config', methods=['POST'])
def set_llm_filter_config():
    """设置LLM内容过滤配置（OpenAI兼容接口）。"""
    global LLM_FILTER_ENABLED, LLM_FILTER_BASE_URL, LLM_FILTER_API_KEY, LLM_FILTER_MODEL, LLM_FILTER_TIMEOUT_SEC
    payload = request.get_json(silent=True) or {}

    enabled = bool(payload.get('enabled', False))
    base_url = str(payload.get('base_url', '') or '').strip()
    api_key = str(payload.get('api_key', '') or '').strip()
    model = str(payload.get('model', '') or '').strip()
    try:
        timeout_sec = float(payload.get('timeout_sec', LLM_FILTER_TIMEOUT_SEC))
    except Exception:
        timeout_sec = LLM_FILTER_TIMEOUT_SEC
    timeout_sec = max(2.0, min(30.0, timeout_sec))

    if enabled and (not base_url or not model):
        return jsonify({"status": "err", "msg": "启用LLM过滤时必须填写 Base URL 和模型名"}), 400

    with data_lock:
        LLM_FILTER_ENABLED = enabled
        LLM_FILTER_BASE_URL = base_url
        LLM_FILTER_API_KEY = api_key or "EMPTY"
        LLM_FILTER_MODEL = model
        LLM_FILTER_TIMEOUT_SEC = timeout_sec
    with llm_filter_cache_lock:
        llm_filter_cache.clear()

    save_state()

    if LLM_FILTER_ENABLED and _llm_filter_is_ready():
        log_to_ui("info", f"🤖 [LLMFilter] 配置已更新并启用: model={LLM_FILTER_MODEL}")
    elif LLM_FILTER_ENABLED:
        log_to_ui("warn", "⚠️ [LLMFilter] 已启用但配置不完整")
    else:
        log_to_ui("info", "🤖 [LLMFilter] 已禁用")

    return jsonify({
        "status": "ok",
        "llm_filter_enabled": bool(LLM_FILTER_ENABLED),
        "llm_filter_base_url": str(LLM_FILTER_BASE_URL or ""),
        "llm_filter_api_key": str(LLM_FILTER_API_KEY or ""),
        "llm_filter_model": str(LLM_FILTER_MODEL or ""),
        "llm_filter_timeout_sec": float(LLM_FILTER_TIMEOUT_SEC),
    })

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
    n = []
    try:
        while True:
            m = msg_queue.get_nowait()
            if m['type'] == 'new_data':
                n.append(m['data'])
            # 前端已移除运行日志面板，这里继续消费日志消息但不返回
    except queue.Empty:
        pass
    with data_lock:
        tasks_copy = list(monitor_tasks)
    return jsonify({"new_items": n, "tasks": tasks_copy})

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
