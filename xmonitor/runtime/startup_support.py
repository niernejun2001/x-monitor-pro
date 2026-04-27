import json
import os
import shutil
import socket

from xmonitor.services.support.error_format import format_runtime_error


def load_local_json_config(path, *, logging_module):
    try:
        if not os.path.exists(path):
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            obj = json.load(f)
            if isinstance(obj, dict):
                return obj
    except Exception as e:
        logging_module.warning(f'读取本地配置失败: {format_runtime_error(e)}')
    return {}


def save_local_json_config(path, cfg):
    try:
        target = os.path.abspath(os.path.expanduser(path))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True, ''
    except Exception as e:
        return False, format_runtime_error(e)


def ensure_directory(path, *, logging_module):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        logging_module.error(f'创建数据目录失败: {format_runtime_error(e)}')


def migrate_legacy_state_files(base_dir, state_file, processed_file, *, logging_module):
    try:
        def sync_if_newer(legacy_file, target_file, label):
            if legacy_file == target_file or not os.path.exists(legacy_file):
                return
            if (not os.path.exists(target_file)) or (os.path.getmtime(legacy_file) > os.path.getmtime(target_file)):
                shutil.copy2(legacy_file, target_file)
                logging_module.info(f'📦 已同步{label}: {legacy_file} -> {target_file}')

        legacy_state_candidates = [
            os.path.join(base_dir, 'spider_state.json'),
            os.path.join(base_dir, 'data', 'spider_state.json'),
        ]
        legacy_processed_candidates = [
            os.path.join(base_dir, 'processed_users.json'),
            os.path.join(base_dir, 'data', 'processed_users.json'),
        ]

        for legacy_state in legacy_state_candidates:
            sync_if_newer(legacy_state, state_file, '状态文件')
        for legacy_processed in legacy_processed_candidates:
            sync_if_newer(legacy_processed, processed_file, '黑名单文件')
    except Exception as e:
        logging_module.warning(f'迁移历史数据文件失败: {format_runtime_error(e)}')


def get_free_port(host='127.0.0.1'):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def is_port_available(port, host='127.0.0.1'):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, int(port)))
        return True
    except Exception:
        return False
