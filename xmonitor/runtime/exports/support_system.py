import os
from urllib.parse import urlsplit

from xmonitor.runtime.browser_guard import get_browser_path as _get_browser_path_impl
from xmonitor.runtime.config_helpers import resolve_server_port as _resolve_server_port_impl
from xmonitor.runtime.startup_support import (
    get_free_port as _get_free_port_impl,
    is_port_available as _is_port_available_impl,
)


def build_support_system_exports(
    *,
    safe_float_fn,
    safe_int_fn,
    env_port_getter,
    proxy_env_keys,
    logging_module,
):
    def _safe_float(val, default_val):
        return safe_float_fn(val, default_val)

    def _safe_int(val, default_val):
        return safe_int_fn(val, default_val)

    def get_browser_path():
        return _get_browser_path_impl()

    def get_browser_proxy():
        for env_key in tuple(proxy_env_keys or ()):
            value = str(os.environ.get(env_key, '') or '').strip()
            if value:
                return value
        return ''

    def get_browser_proxy_source():
        for env_key in tuple(proxy_env_keys or ()):
            value = str(os.environ.get(env_key, '') or '').strip()
            if value:
                return env_key
        return ''

    def _format_browser_proxy_display(proxy_value):
        raw = str(proxy_value or '').strip()
        if not raw:
            return ''
        has_scheme = '://' in raw
        try:
            parsed = urlsplit(raw if has_scheme else f'http://{raw}')
        except Exception:
            return raw
        host = parsed.hostname or ''
        if not host:
            return raw
        scheme = f'{parsed.scheme}://' if has_scheme and parsed.scheme else ''
        auth = '***@' if (parsed.username or parsed.password) else ''
        port = f':{parsed.port}' if parsed.port else ''
        return f'{scheme}{auth}{host}{port}'

    def build_browser_proxy_runtime_payload():
        proxy_value = get_browser_proxy()
        return {
            'browser_proxy_configured': bool(proxy_value),
            'browser_proxy_source': get_browser_proxy_source(),
            'browser_proxy_display': _format_browser_proxy_display(proxy_value),
        }

    def get_free_port():
        return _get_free_port_impl()

    def is_port_available(port, host='127.0.0.1'):
        return _is_port_available_impl(port, host=host)

    def resolve_server_port():
        return _resolve_server_port_impl(
            env_port_getter(),
            is_port_available_fn=is_port_available,
            get_free_port_fn=get_free_port,
            logging_module=logging_module,
        )

    return {
        '_safe_float': _safe_float,
        '_safe_int': _safe_int,
        'get_browser_path': get_browser_path,
        'get_browser_proxy': get_browser_proxy,
        'get_browser_proxy_source': get_browser_proxy_source,
        'build_browser_proxy_runtime_payload': build_browser_proxy_runtime_payload,
        'get_free_port': get_free_port,
        'is_port_available': is_port_available,
        'resolve_server_port': resolve_server_port,
    }
