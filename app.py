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
import concurrent.futures
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
delegated_account_active = ""  # 当前浏览器会话已切换到的委派账户（标准化handle）
delegated_switch_ok = False
headless_mode = True    # 无头模式开关：True=无头，False=有头（调试用）
data_lock = threading.Lock()
browser_lock = threading.Lock() # 浏览器操作锁（用于多标签页同步）
tab_lock = threading.Lock()     # 标签页创建/销毁锁
notification_monitoring = False  # 新增：通知监控开关
NOTIFICATION_SCAN_INTERVAL_MIN_SEC = 6
NOTIFICATION_SCAN_INTERVAL_MAX_SEC = 12
NOTIFICATION_RECENT_WINDOW_MINUTES = 30
NOTIFICATION_MAX_SCAN_ARTICLES = 60
NOTIFICATION_VERBOSE_TRACE = True
NOTIFICATION_TRACE_MAX_ARTICLES = 12
NOTIFICATION_TRACE_TEXT_LEN = 120
NOTIFICATION_REFRESH_INTERVAL_MIN_SEC = 25
NOTIFICATION_REFRESH_INTERVAL_MAX_SEC = 55
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
DM_PASSCODE = os.environ.get("XMONITOR_DM_PASSCODE", "1234")
PROXY_ENV_KEYS = (
    "XMONITOR_PROXY",
    "ALL_PROXY",
    "all_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
)

# --- 全局浏览器实例 (单浏览器多标签页模式) ---
global_browser = None
global_browser_dir = None
browser_initialized = False

reply_action_lock = threading.Lock()
reply_work_tab = None
reply_work_tab_lock = threading.Lock()
dm_passcode_warmed = False
dm_passcode_lock = threading.Lock()
notify_reply_templates = list(DEFAULT_NOTIFY_REPLY_TEMPLATES)
dm_message_templates = list(DEFAULT_DM_TEMPLATES)

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


def init_global_browser():
    """初始化全局浏览器实例"""
    global global_browser, global_browser_dir, browser_initialized

    if browser_initialized and global_browser:
        return global_browser

    max_attempts = 3
    last_error = None
    use_temp_profile_fallback = False

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
                global_browser_dir = create_browser_user_data_dir(
                    prefer_persistent=not use_temp_profile_fallback
                )
                port = get_free_port()
                co = init_browser_options(port, global_browser_dir)
                mode_text = "无头模式" if headless_mode else "有头模式(调试)"
                profile_mode = "固定持久目录" if is_persistent_browser_profile_dir(global_browser_dir) else "临时目录"
                log_to_ui("info", f"🖥️ 正在初始化浏览器: {mode_text} | Profile: {profile_mode}")
                log_to_ui("debug", f"🗂️ 浏览器用户目录: {global_browser_dir}")
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
                    log_to_ui("warn", "⚠️ 固定Profile疑似被占用，本轮后将自动回退临时Profile启动")

                if global_browser_dir:
                    cleanup_browser_user_data_dir(global_browser_dir)
                    global_browser_dir = None

                log_to_ui("warn", f"⚠️ 浏览器初始化失败({attempt}/{max_attempts}): {str(e)}")

        if attempt < max_attempts:
            time.sleep(1.5 * attempt)

    raise RuntimeError(f"浏览器初始化失败，已重试 {max_attempts} 次: {last_error}")


def cleanup_global_browser():
    """清理全局浏览器"""
    global global_browser, global_browser_dir, browser_initialized, delegated_account_active, delegated_switch_ok, reply_work_tab, dm_passcode_warmed

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


def restart_global_browser():
    """重启全局浏览器"""
    log_to_ui("info", "🔄 正在重启浏览器...")
    cleanup_global_browser()
    time.sleep(1)
    browser = init_global_browser()

    # 切换委派账户
    if delegated_account.strip():
        browser.get("https://x.com/home")
        time.sleep(2)
        ensure_delegated_account_session(browser, delegated_account)
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

    log_to_ui("info", ">>> 🚀 引擎启动 (v11.1 全并行标签页版)...")
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
        delegated = delegated_account.strip()
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
                delegated = delegated_account.strip()
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
        "headless_mode": headless_mode,  # 保存有头/无头模式
        "history_ids": list(history_ids),  # 保存状态ID去重缓存
        "content_dedupe": content_dedupe,  # 保存同用户同内容去重缓存
        "notify_reply_templates": notify_reply_templates,  # 保存通知回复模板
        "dm_message_templates": dm_message_templates,  # 保存私信模板
    }
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4, ensure_ascii=False)
        logging.info(f"💾 状态已保存: {len(pending_results)} 条待处理，{len(history_ids)} 条历史ID，{len(content_dedupe)} 条内容签名")
    except Exception as e:
        logging.error(f"保存状态失败: {e}")

def load_state():
    global global_token, monitor_tasks, monitor_active, processed_users, pending_results, notification_monitoring, delegated_account, history_ids, headless_mode, content_dedupe, notify_reply_templates, dm_message_templates
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
                delegated_account = data.get("delegated_account", "")  # 恢复委派账户
                headless_mode = data.get("headless_mode", True)  # 恢复有头/无头模式
                notify_reply_templates = _sanitize_template_list(
                    data.get("notify_reply_templates", []),
                    DEFAULT_NOTIFY_REPLY_TEMPLATES
                )
                dm_message_templates = _sanitize_template_list(
                    data.get("dm_message_templates", []),
                    DEFAULT_DM_TEMPLATES
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

                # 从待处理列表中也恢复去重ID（双重保险）
                for item in pending_results:
                    if item.get('source') == '通知页面':
                        removed = False
                        if 'reply_checked' in item:
                            item.pop('reply_checked', None)
                            removed = True
                        if 'reply_text' in item:
                            item.pop('reply_text', None)
                            removed = True
                        if 'reply_time' in item:
                            item.pop('reply_time', None)
                            removed = True
                        if removed:
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
                logging.info(f"   - 委派账户: {delegated_account if delegated_account else '未设置'}")
                logging.info(f"   - 浏览器模式: {'无头' if headless_mode else '有头(调试)'}")
                logging.info(f"   - 回复模板: {len(notify_reply_templates)} 条")
                logging.info(f"   - 私信模板: {len(dm_message_templates)} 条")

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
def init_browser_options(port, user_data_path):
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
    co.headless(headless_mode)  # 根据配置决定有头/无头模式
    if headless_mode:
        # 新版 Chromium 在容器/无界面环境下更稳定
        co.set_argument('--headless=new')

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
    if headless_mode:
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
        debug_skipped = {"no_user": 0, "no_handle": 0, "no_content": 0, "blacklist": 0, "duplicate": 0, "has_reply": 0}

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
            m = re.search(r'/([A-Za-z0-9_]+)/status/(\d+)', href)
            if m:
                return f"@{m.group(1)}", m.group(2)

            # X 新版路径常见形态：/i/status/123... 或 /i/web/status/123...
            m = re.search(r'/(?:i/(?:web/)?|web/)?status/(\d+)', href)
            if m:
                return None, m.group(1)

            # 某些跳转链接里会带 conversation_id
            m = re.search(r'conversation_id=(\d+)', href)
            if m:
                return None, m.group(1)
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
                delegated_norm = delegated_account.strip().lstrip('@').lower() if delegated_account else ''

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
        for item in new_items:
            with data_lock:
                if item["key"] in history_ids:
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
        for item in new_items:
            with data_lock:
                if item["key"] in history_ids:
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
        debug_stats = {"no_user": 0, "no_handle": 0, "no_content": 0, "blacklist": 0, "duplicate": 0, "has_reply": 0}

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

                    # 去重
                    unique_key = f"{handle}_{content[:50]}"
                    if unique_key in seen_in_page or unique_key in history_ids:
                        debug_stats["duplicate"] += 1
                        continue
                    seen_in_page.add(unique_key)

                    # 检查是否已回复过该评论
                    # 通过检查后续articles是否来自当前登录用户来判断
                    if delegated_account:
                        my_handle = delegated_account.strip().lstrip('@').lower()
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
                        delegated = delegated_account.strip()
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

    status_id = str(item.get("status_id", "")).strip()
    if status_id.isdigit():
        return status_id

    status_url = str(item.get("status_url", "")).strip()
    if status_url:
        m = re.search(r'/status/(\d+)', status_url)
        if m:
            return m.group(1)

    key = str(item.get("key", "")).strip()
    m = re.match(r'^notif_status_(\d+)$', key)
    if m:
        return m.group(1)

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

        m = re.search(r'/(?:i/(?:web/)?|web/)?status/(\d+)', href)
        if m:
            ids.add(m.group(1))
            continue
        m = re.search(r'/[A-Za-z0-9_]+/status/(\d+)', href)
        if m:
            ids.add(m.group(1))
            continue
        m = re.search(r'conversation_id=(\d+)', href)
        if m:
            ids.add(m.group(1))
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
    """确保回复专用工作标签页可用（复用同一标签页，避免重复触发 passcode）。"""
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


def _get_status_link_from_item(item, matched_status_handle=None, matched_status_id=None):
    status_id = str(matched_status_id or item.get("status_id") or "").strip()
    status_handle = normalize_handle(matched_status_handle or item.get("status_handle") or "")
    if status_id and status_handle:
        return f"https://x.com/{status_handle}/status/{status_id}"
    if status_id:
        return f"https://x.com/i/status/{status_id}"
    status_url = str(item.get("status_url", "")).strip()
    return status_url


def _click_share_copy_link(tab, target_article, fallback_link):
    """在目标卡片点击分享->复制链接，返回可用链接（优先真实复制，失败回退）。"""
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

    try:
        share_btn.click()
    except Exception:
        try:
            tab.run_js('arguments[0].click()', share_btn)
        except Exception:
            return fallback_link, "点击分享按钮失败"
    time.sleep(0.6)

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

    try:
        copy_btn.click()
    except Exception:
        try:
            tab.run_js('arguments[0].click()', copy_btn)
        except Exception:
            return fallback_link, "点击复制链接按钮失败"
    time.sleep(0.4)

    # X 菜单复制通常写入系统剪贴板，自动读取常被权限限制；这里稳妥回退为已识别链接
    return fallback_link, ""


def _handle_dm_passcode_prompt(tab):
    """若出现 Enter Passcode 弹窗，自动输入口令并提交。"""
    global dm_passcode_warmed
    if not DM_PASSCODE:
        return False

    prompt_detected = False
    try:
        body_text = (tab.ele('tag:body', timeout=0.5).text or "").lower()
        prompt_detected = ("enter passcode" in body_text) or ("输入密码" in body_text) or ("passcode" in body_text)
    except Exception:
        prompt_detected = False

    pass_input = None
    submit_anchor_input = None
    input_selectors = [
        'css:input[placeholder*="Passcode"]',
        'css:input[aria-label*="Passcode"]',
        'css:input[type="password"]',
        'css:[data-testid*="passcode"] input',
    ]
    for selector in input_selectors:
        try:
            cand = tab.ele(selector, timeout=0.6)
            if cand and cand.states.is_displayed:
                pass_input = cand
                prompt_detected = True
                break
        except Exception:
            continue

    # 兼容 4 位分格输入框（每格1位数字）
    otp_inputs = []
    otp_selectors = [
        'css:input[inputmode="numeric"][maxlength="1"]',
        'css:input[maxlength="1"][pattern*="[0-9]"]',
        'css:[data-testid*="passcode"] input[maxlength="1"]',
    ]
    for selector in otp_selectors:
        try:
            candidates = tab.eles(selector, timeout=0.6)
        except Exception:
            candidates = []
        visible_inputs = []
        for cand in candidates:
            try:
                if cand and cand.states.is_displayed:
                    visible_inputs.append(cand)
            except Exception:
                continue
        if len(visible_inputs) >= 4:
            otp_inputs = visible_inputs
            prompt_detected = True
            break

    if not prompt_detected:
        return False

    typed = False
    # 优先处理 4 位分格输入
    if len(otp_inputs) >= 4:
        digits = [ch for ch in DM_PASSCODE if ch.isdigit()]
        if len(digits) >= 4:
            filled = 0
            for idx, inp in enumerate(otp_inputs[:4]):
                digit = digits[idx]
                try:
                    inp.click()
                except Exception:
                    pass
                try:
                    inp.input(digit, clear=True)
                    filled += 1
                    continue
                except Exception:
                    pass
                try:
                    tab.run_js(
                        """
                        const el = arguments[0];
                        const text = arguments[1];
                        el.focus();
                        el.value = '';
                        el.value = text;
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        """,
                        inp,
                        digit,
                    )
                    filled += 1
                except Exception:
                    continue
            if filled >= 4:
                typed = True
                submit_anchor_input = otp_inputs[0]
        else:
            log_to_ui("warn", "⚠️ Passcode 不是4位数字，无法填充分格输入框")

    # 兜底：单输入框
    if (not typed) and pass_input:
        try:
            pass_input.click()
        except Exception:
            pass

        try:
            pass_input.input(DM_PASSCODE, clear=True)
            typed = True
            submit_anchor_input = pass_input
        except Exception:
            try:
                tab.run_js(
                    """
                    const el = arguments[0];
                    const text = arguments[1];
                    el.focus();
                    el.value = '';
                    el.value = text;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    """,
                    pass_input,
                    DM_PASSCODE,
                )
                typed = True
                submit_anchor_input = pass_input
            except Exception:
                typed = False

    if not typed:
        log_to_ui("warn", "⚠️ 检测到 Passcode 弹窗，但输入失败")
        return False
    with dm_passcode_lock:
        dm_passcode_warmed = True

    submit_btn = None
    submit_selectors = [
        'css:button[type="submit"]',
        'css:[data-testid*="passcode"] button',
        'css:button',
    ]
    submit_keywords = ['continue', 'submit', 'confirm', 'unlock', 'next', '确定', '继续', '提交', '确认']
    for selector in submit_selectors:
        try:
            btns = tab.eles(selector, timeout=0.8)
        except Exception:
            btns = []
        for btn in btns:
            try:
                txt = (btn.text or "").strip().lower()
                if selector == 'css:button[type="submit"]' or any(k in txt for k in submit_keywords):
                    if btn.states.is_displayed:
                        submit_btn = btn
                        break
            except Exception:
                continue
        if submit_btn:
            break

    if submit_btn:
        try:
            submit_btn.click()
        except Exception:
            try:
                tab.run_js('arguments[0].click()', submit_btn)
            except Exception:
                pass
    else:
        if submit_anchor_input:
            try:
                submit_anchor_input.input("\n")
            except Exception:
                pass

    time.sleep(0.8)
    log_to_ui("info", "🔐 已自动输入 Passcode 并尝试提交")
    return True


def _warmup_dm_passcode_if_needed(tab, force=False):
    """首次使用回复工作标签页时，预热私信Passcode后回到通知页。"""
    global dm_passcode_warmed
    if not tab or not DM_PASSCODE:
        return

    with dm_passcode_lock:
        warmed = dm_passcode_warmed
    if warmed and not force:
        return

    try:
        log_to_ui("debug", "🔐 准备预热私信 Passcode（先进入聊天再返回通知）")
        tab.get("https://x.com/messages/compose")
        try:
            tab.wait.ele_displayed('tag:main', timeout=6)
        except Exception:
            pass
        time.sleep(0.9)

        # 弹窗可能延迟出现，做两次检测输入
        _handle_dm_passcode_prompt(tab)
        time.sleep(0.5)
        _handle_dm_passcode_prompt(tab)

        with dm_passcode_lock:
            dm_passcode_warmed = True
        log_to_ui("debug", "🔐 私信 Passcode 预热完成")
    except Exception as e:
        log_to_ui("warn", f"⚠️ 私信 Passcode 预热异常: {e}")
    finally:
        try:
            tab.get("https://x.com/notifications")
            time.sleep(0.5)
        except Exception:
            pass


def _open_dm_editor_for_handle(tab, handle):
    """打开某用户私信编辑框，返回编辑框元素。"""
    handle_norm = normalize_handle(handle)
    if not handle_norm:
        return None, "缺少目标用户handle"

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
        for selector in dm_btn_selectors:
            try:
                btns = tab.eles(selector, timeout=1.2)
            except Exception:
                btns = []
            for btn in btns:
                try:
                    if btn and btn.states.is_displayed:
                        disabled = (btn.attr('aria-disabled') or '').lower()
                        if disabled != 'true':
                            return btn
                except Exception:
                    continue
        return None

    def _find_editor(timeout_each=2.5):
        for selector in editor_selectors:
            try:
                cand = tab.ele(selector, timeout=timeout_each)
                if cand and cand.states.is_displayed:
                    return cand
            except Exception:
                continue
        return None

    for attempt in range(3):
        if attempt == 0:
            tab.get(f"https://x.com/{handle_norm}")
            try:
                tab.wait.ele_displayed('tag:main', timeout=8)
            except Exception:
                pass
            time.sleep(1.0)
        elif attempt == 1:
            # 第一次失败后，优先处理可能拦截流程的 passcode
            handled = _handle_dm_passcode_prompt(tab)
            if handled:
                time.sleep(0.7)
            tab.get(f"https://x.com/{handle_norm}")
            try:
                tab.wait.ele_displayed('tag:main', timeout=6)
            except Exception:
                pass
            time.sleep(0.9)
        else:
            try:
                tab.refresh()
                time.sleep(1.0)
            except Exception:
                pass

        if _has_cannot_dm_hint():
            return None, "该用户当前不可私信（平台限制或对方未开放私信）"

        dm_btn = _find_dm_btn()
        if not dm_btn:
            continue

        try:
            dm_btn.click()
        except Exception:
            try:
                tab.run_js('arguments[0].click()', dm_btn)
            except Exception:
                continue
        time.sleep(1.0)

        handled_after_click = _handle_dm_passcode_prompt(tab)
        if handled_after_click:
            # 输入 passcode 后通常会回到资料页，需要再次点击私信按钮
            try:
                tab.get(f"https://x.com/{handle_norm}")
                time.sleep(0.9)
            except Exception:
                pass
            dm_btn_retry = _find_dm_btn()
            if dm_btn_retry:
                try:
                    dm_btn_retry.click()
                except Exception:
                    try:
                        tab.run_js('arguments[0].click()', dm_btn_retry)
                    except Exception:
                        pass
                time.sleep(0.9)

        editor = _find_editor(timeout_each=2.0)
        if editor:
            return editor, ""
        if _has_cannot_dm_hint():
            return None, "该用户当前不可私信（平台限制或对方未开放私信）"

    if _has_cannot_dm_hint():
        return None, "该用户当前不可私信（平台限制或对方未开放私信）"
    return None, "未打开私信输入框（可能被 Passcode 或页面状态打断）"


def _send_dm_message(tab, text):
    """在当前私信弹窗发送一条消息。"""
    if not text:
        return False, "空消息"

    editor = None
    editor_selectors = [
        'css:textarea[data-testid="dm-composer-textarea"]',
        'css:textarea[placeholder="Message"]',
        'css:textarea[placeholder*="消息"]',
        'css:[data-testid="dmComposerTextInput"]',
        'css:[data-testid="dmComposerTextInput"] [contenteditable="true"]',
        'css:div[role="textbox"][contenteditable="true"]',
    ]
    for selector in editor_selectors:
        try:
            editor = tab.ele(selector, timeout=2)
            if editor and editor.states.is_displayed:
                break
        except Exception:
            continue
    if not editor:
        _handle_dm_passcode_prompt(tab)
        for selector in editor_selectors:
            try:
                editor = tab.ele(selector, timeout=2)
                if editor and editor.states.is_displayed:
                    break
            except Exception:
                continue
    if not editor:
        return False, "未找到私信输入框"

    try:
        editor.click()
    except Exception:
        pass

    typed_ok = False
    try:
        editor.input(text, clear=True)
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
                text,
            )
            typed_ok = True
        except Exception:
            typed_ok = False
    if not typed_ok:
        return False, "输入私信内容失败"

    send_btn = None
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
    for selector in send_btn_selectors:
        try:
            cands = tab.eles(selector, timeout=1.5)
        except Exception:
            cands = []
        for cand in cands:
            try:
                if not (cand and cand.states.is_displayed):
                    continue
                aria_disabled = (cand.attr('aria-disabled') or '').lower()
                html_disabled = cand.attr('disabled')
                if aria_disabled == 'true' or html_disabled is not None:
                    continue
                send_btn = cand
                break
            except Exception:
                continue
        if send_btn:
            break
    if not send_btn:
        # 兜底：直接用浏览器 DOM 点击私信发送按钮
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
                time.sleep(0.7)
                return True, ""
        except Exception:
            pass
        return False, "未找到私信发送按钮"

    try:
        send_btn.click()
    except Exception:
        try:
            tab.run_js('arguments[0].click()', send_btn)
        except Exception:
            return False, "点击私信发送失败"
    time.sleep(0.7)
    return True, ""


def send_notification_reply(item, message, dm_message=""):
    """针对通知记录发送回复。"""
    if not global_token.strip():
        return False, "请先配置并验证 auth_token 后再回复"

    status_id = extract_status_id_from_notification_item(item)
    if not status_id:
        return False, "该通知缺少可回复的状态ID（可能是兜底通知记录）"

    handle_hint = item.get("handle", "")

    with reply_action_lock:
        try:
            tab = ensure_reply_work_tab()
        except Exception as e:
            return False, f"回复工作标签页初始化失败: {e}"

        try:
            log_to_ui("info", f"💬 开始执行通知回复(复用全局浏览器): {handle_hint} -> status {status_id}")

            tab.get("https://x.com/notifications")
            log_to_ui("debug", "💬 已打开通知页，准备定位目标通知卡片")
            try:
                tab.wait.ele_displayed('tag:article', timeout=8)
            except Exception:
                pass
            time.sleep(1.0)

            def _prepare_notifications_view():
                # 新通知有时尚未渲染，先刷新再定位
                try:
                    tab.refresh()
                    time.sleep(random.uniform(0.8, 1.6))
                except Exception:
                    pass
                try:
                    tabs = tab.eles('css:[role="tab"]', timeout=1.2)
                    for notify_tab in tabs:
                        tab_text = (notify_tab.text or "").strip().lower()
                        if tab_text in {'全部', 'all'}:
                            try:
                                notify_tab.click()
                            except Exception:
                                tab.run_js('arguments[0].click()', notify_tab)
                            time.sleep(0.7)
                            break
                except Exception:
                    pass
                try:
                    tab.run_js('window.scrollTo(0, 0);')
                except Exception:
                    pass

            _prepare_notifications_view()
            log_to_ui("debug", "💬 已刷新通知页并切到全部，开始定位目标通知卡片")

            # 在通知页中定位目标通知卡片（只点该卡片左下角回复）
            target_article = None
            target_reply_btn = None
            target_score = 0
            for attempt in range(5):
                if attempt == 2 and not target_article:
                    _prepare_notifications_view()
                    log_to_ui("debug", "💬 首轮未命中，已再次刷新通知页后重试匹配")
                target_article, target_reply_btn, target_score = _match_notification_card_for_reply(
                    tab,
                    status_id,
                    item.get("handle", ""),
                    item.get("content", "")
                )
                required_score = 260 if status_id else 120
                if target_article and target_reply_btn and target_score >= required_score:
                    break
                try:
                    tab.run_js('window.scrollBy(0, 720);')
                    time.sleep(0.7)
                except Exception:
                    pass
            if not target_article:
                return False, "未在通知页定位到目标评论卡片"
            required_score = 260 if status_id else 120
            if target_score < required_score:
                return False, f"通知卡片匹配置信度不足(score={target_score})，已阻止误回复"
            try:
                matched_handle, matched_status_id = _extract_notification_status_info(target_article)
            except Exception:
                matched_handle, matched_status_id = None, None
            log_to_ui(
                "debug",
                f"💬 已定位通知卡片 score={target_score}, status_id={matched_status_id}, handle={matched_handle or ''}"
            )

            share_link_fallback = _get_status_link_from_item(item, matched_handle, matched_status_id)
            share_link, share_err = _click_share_copy_link(tab, target_article, share_link_fallback)
            if share_err:
                log_to_ui("warn", f"⚠️ 分享复制链接失败，使用回退链接: {share_err}")
            if not share_link:
                return False, "无法确定要发送的链接"
            log_to_ui("debug", f"🔗 已准备分享链接: {share_link}")

            try:
                tab.run_js('arguments[0].scrollIntoView({block:\"center\"});', target_reply_btn)
            except Exception:
                pass

            try:
                target_reply_btn.click()
            except Exception:
                tab.run_js('arguments[0].click()', target_reply_btn)
            log_to_ui("debug", f"💬 已点击通知卡片左下角回复按钮(score={target_score})，等待回复输入框")
            time.sleep(0.9)

            editor = None
            editor_selectors = [
                'css:[data-testid="tweetTextarea_0"] [role="textbox"]',
                'css:[data-testid="tweetTextarea_0"]',
                'css:div[role="textbox"][contenteditable="true"]',
            ]
            for selector in editor_selectors:
                try:
                    candidate = tab.ele(selector, timeout=4)
                    if candidate and candidate.states.is_displayed:
                        editor = candidate
                        break
                except Exception:
                    continue
            if not editor:
                return False, "未弹出回复输入框"

            typed_ok = False
            try:
                editor.click()
            except Exception:
                pass

            try:
                editor.input(message, clear=True)
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
                        message,
                    )
                    typed_ok = True
                except Exception:
                    typed_ok = False

            if not typed_ok:
                return False, "输入回复内容失败"
            log_to_ui("debug", "💬 已填充回复内容")

            # 右下角“回复”按钮
            send_btn = None
            send_selectors = [
                'css:[data-testid="tweetButton"]',
                'css:button[data-testid="tweetButton"]',
                'css:[data-testid="tweetButtonInline"]',
            ]
            for selector in send_selectors:
                try:
                    candidates = tab.eles(selector, timeout=2)
                except Exception:
                    candidates = []
                for candidate in candidates:
                    try:
                        if candidate and candidate.states.is_displayed:
                            disabled = (candidate.attr('aria-disabled') or '').lower()
                            if disabled != 'true':
                                send_btn = candidate
                                break
                    except Exception:
                        continue
                if send_btn:
                    break

            if not send_btn:
                return False, "未找到可点击的右下角回复按钮"

            try:
                send_btn.click()
            except Exception:
                tab.run_js('arguments[0].click()', send_btn)
            log_to_ui("debug", "💬 已点击右下角回复按钮")

            time.sleep(1.8)

            dm_editor, dm_err = _open_dm_editor_for_handle(tab, item.get("handle", ""))
            if not dm_editor:
                return False, f"打开私信失败: {dm_err}"

            ok_dm_1, err_dm_1 = _send_dm_message(tab, share_link)
            if not ok_dm_1:
                return False, f"发送私信链接失败: {err_dm_1}"
            log_to_ui("debug", "📨 已发送私信链接")

            dm_text = str(dm_message or "").strip()
            if not dm_text:
                dm_text = (dm_message_templates[0] if dm_message_templates else DM_FOLLOWUP_TEXT)
            ok_dm_2, err_dm_2 = _send_dm_message(tab, dm_text)
            if not ok_dm_2:
                return False, f"发送私信文案失败: {err_dm_2}"
            log_to_ui("debug", "📨 已发送私信文案")

            return True, ""
        except Exception as e:
            return False, f"回复发送失败: {e}"
        finally:
            # 无论成功/失败都回到通知页，且保持当前工作标签页不关闭，避免重复 Passcode 校验
            try:
                tab.get("https://x.com/notifications")
                time.sleep(0.6)
            except Exception:
                pass

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
            "headless_mode": headless_mode,
            "notify_reply_templates": list(notify_reply_templates),
            "dm_message_templates": list(dm_message_templates),
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
        for item in pending_results:
            if item.get('key') == key and item.get('source') == '通知页面':
                target = dict(item)
                break

    if not target:
        return jsonify({"status": "err", "msg": "通知记录不存在"}), 404

    ok, err = send_notification_reply(target, message, dm_message=dm_message)
    if not ok:
        log_to_ui("warn", f"⚠️ 通知回复失败: {err}")
        return jsonify({"status": "err", "msg": err}), 500

    log_to_ui("success", f"✅ 已发送通知回复: {target.get('handle', '')} -> {message[:30]}")
    return jsonify({"status": "ok"})


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
    global delegated_account, delegated_account_active, delegated_switch_ok
    account = request.json.get('account', '').strip()
    old_norm = normalize_handle(delegated_account)
    new_norm = normalize_handle(account)
    with data_lock:
        delegated_account = account
        if old_norm != new_norm:
            delegated_account_active = ""
            delegated_switch_ok = False
    save_state()
    if account:
        log_to_ui("info", f"👤 已设置委派账户: {account}")
    else:
        log_to_ui("info", "👤 已清除委派账户")
    return jsonify({"status":"ok", "delegated_account": delegated_account})

@app.route('/api/toggle_headless', methods=['POST'])
def toggle_headless():
    """切换有头/无头模式"""
    global headless_mode
    enabled = request.json.get('enabled', True)
    with data_lock:
        headless_mode = enabled
    save_state()
    mode_text = "无头模式" if enabled else "有头模式(调试)"
    log_to_ui("info", f"🖥️ 浏览器模式已切换为: {mode_text}")
    log_to_ui("warn", "⚠️ 需要重启监控才能生效")
    return jsonify({"status":"ok", "headless_mode": headless_mode})

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
