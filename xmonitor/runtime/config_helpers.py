import os
import re


def get_default_user_data_dir():
    xdg_data_home = str(os.environ.get('XDG_DATA_HOME', '')).strip()
    if xdg_data_home:
        root = os.path.abspath(os.path.expanduser(xdg_data_home))
    else:
        root = os.path.join(os.path.expanduser('~'), '.local', 'share')
    return os.path.join(root, 'x-monitor-pro')


def get_data_dir(base_dir):
    custom_data_dir = str(os.environ.get('XMONITOR_DATA_DIR', '')).strip()
    if custom_data_dir:
        return os.path.abspath(os.path.expanduser(custom_data_dir))
    if os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV'):
        return '/app/data'
    use_project_data = str(os.environ.get('XMONITOR_USE_PROJECT_DATA', '0')).strip().lower() in {'1', 'true', 'yes', 'on'}
    if use_project_data:
        return os.path.join(base_dir, 'data')
    return get_default_user_data_dir()


def parse_backoff_seconds(raw, default_values=(2, 5, 9, 15)):
    values = []
    text = str(raw or '').strip()
    if text:
        for part in re.split(r'[\s,，;；]+', text):
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


def resolve_server_port(env_port, *, is_port_available_fn, get_free_port_fn, logging_module):
    env_port_text = str(env_port or '').strip()
    if env_port_text:
        try:
            preferred = int(env_port_text)
            if not (1 <= preferred <= 65535):
                raise ValueError('out_of_range')
            if is_port_available_fn(preferred):
                return preferred, 'env'
            logging_module.warning(f'配置端口不可用，自动回退随机端口: {preferred}')
        except Exception:
            logging_module.warning(f'无效的 XMONITOR_PORT={env_port_text}，自动回退随机端口')
    return get_free_port_fn(), 'random'
