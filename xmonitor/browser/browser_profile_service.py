import os
import re
import subprocess
import time


def pid_exists(pid):
    """判断进程是否存在。"""
    try:
        if not pid or int(pid) <= 0:
            return False
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def extract_singleton_lock_pid(profile_dir):
    """从 Chromium SingletonLock 中提取 PID（若可解析）。"""
    lock_path = os.path.join(profile_dir, 'SingletonLock')
    if not os.path.lexists(lock_path):
        return None

    target = ''
    try:
        if os.path.islink(lock_path):
            target = os.readlink(lock_path)
        else:
            with open(lock_path, 'r', encoding='utf-8', errors='ignore') as f:
                target = f.read().strip()
    except Exception:
        return None

    match = re.search(r'(\d+)\s*$', str(target))
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def cleanup_stale_profile_singletons(profile_dir):
    """清理陈旧的 Chromium profile 锁文件。"""
    names = ('SingletonLock', 'SingletonCookie', 'SingletonSocket')
    for name in names:
        path = os.path.join(profile_dir, name)
        try:
            if os.path.lexists(path):
                os.remove(path)
        except Exception:
            pass


def list_profile_bound_browser_pids(profile_dir):
    """列出绑定到指定 user-data-dir 的 chrome/chromium 进程 PID。"""
    if not profile_dir:
        return []
    profile_dir = os.path.abspath(profile_dir)
    needle = f'--user-data-dir={profile_dir}'
    try:
        proc = subprocess.run(
            ['ps', '-eo', 'pid=,args='],
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
    for raw in (proc.stdout or '').splitlines():
        line = raw.strip()
        if not line or needle not in line:
            continue
        low = line.lower()
        if ('chrome' not in low) and ('chromium' not in low):
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


def terminate_pids(pids, term_wait=1.6, kill_wait=0.8):
    """尝试先 TERM 后 KILL 终止进程，返回已终止的 PID 列表。"""
    if not pids:
        return []
    pending = [pid for pid in pids if pid_exists(pid)]
    if not pending:
        return []

    def _wait_until_done(target_pids, timeout_sec):
        deadline = time.time() + max(0.1, float(timeout_sec))
        remain = list(target_pids)
        while time.time() < deadline and remain:
            remain = [pid for pid in remain if pid_exists(pid)]
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

    return [pid for pid in pids if not pid_exists(pid)]


def auto_cleanup_profile_runtime(profile_dir):
    """
    自动清理 profile 运行时冲突：
    1) 结束绑定该 profile 的残留浏览器进程
    2) 清理 Singleton 锁文件
    """
    bound_pids = list_profile_bound_browser_pids(profile_dir)
    killed_pids = terminate_pids(bound_pids) if bound_pids else []
    cleanup_stale_profile_singletons(profile_dir)
    return {
        'bound_total': len(bound_pids),
        'killed_total': len(killed_pids),
        'bound_pids': bound_pids,
        'killed_pids': killed_pids,
    }


def is_profile_locked_by_alive_process(profile_dir):
    """
    判断固定 profile 是否被存活进程占用。
    返回 (locked: bool, pid: int|None)
    """
    pid = extract_singleton_lock_pid(profile_dir)
    if pid and pid_exists(pid):
        return True, pid
    return False, pid
