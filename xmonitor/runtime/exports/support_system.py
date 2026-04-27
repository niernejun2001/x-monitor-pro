import os
import socket
import subprocess
from urllib.parse import urlsplit

from xmonitor.runtime.browser_guard import get_browser_path as _get_browser_path_impl
from xmonitor.runtime.config_helpers import resolve_server_port as _resolve_server_port_impl
from xmonitor.runtime.startup_support import (
    get_free_port as _get_free_port_impl,
    is_port_available as _is_port_available_impl,
)

LOCAL_PROXY_CANDIDATES = (
    ('http', '127.0.0.1', 7890, 'auto_local_http_7890'),
    ('http', '127.0.0.1', 7897, 'auto_local_http_7897'),
    ('socks5', '127.0.0.1', 7891, 'auto_local_socks5_7891'),
    ('socks5', '127.0.0.1', 7898, 'auto_local_socks5_7898'),
    ('socks5', '127.0.0.1', 1080, 'auto_local_socks5_1080'),
    ('http', '127.0.0.1', 8080, 'auto_local_http_8080'),
)


def _parse_gsettings_value(raw):
    text = str(raw or '').strip()
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        return text[1:-1]
    return text


def _read_proxy_from_env(proxy_env_keys, environ=None):
    environ = environ or os.environ
    for env_key in tuple(proxy_env_keys or ()):
        value = str(environ.get(env_key, '') or '').strip()
        if value:
            return value, env_key
    return '', ''


def _gsettings_get(schema, key):
    try:
        proc = subprocess.run(
            ['gsettings', 'get', schema, key],
            capture_output=True,
            text=True,
            timeout=1.2,
            check=False,
        )
    except Exception:
        return ''
    if proc.returncode != 0:
        return ''
    return _parse_gsettings_value(proc.stdout)


def _read_proxy_from_gsettings(reader=None):
    reader = reader or _gsettings_get
    mode = _parse_gsettings_value(reader('org.gnome.system.proxy', 'mode')).strip().lower()
    if mode != 'manual':
        return '', ''
    for scheme, schema in (
        ('http', 'org.gnome.system.proxy.http'),
        ('http', 'org.gnome.system.proxy.https'),
        ('socks5', 'org.gnome.system.proxy.socks'),
    ):
        host = _parse_gsettings_value(reader(schema, 'host')).strip()
        port_raw = _parse_gsettings_value(reader(schema, 'port')).strip()
        try:
            port = int(port_raw)
        except Exception:
            port = 0
        if host and port > 0:
            return f'{scheme}://{host}:{port}', f'gsettings_{schema.rsplit(".", 1)[-1]}'
    return '', ''


def _is_local_proxy_port_open(host, port, timeout=0.15):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def _read_proxy_from_local_candidates(port_probe=None):
    port_probe = port_probe or _is_local_proxy_port_open
    for scheme, host, port, source in LOCAL_PROXY_CANDIDATES:
        if port_probe(host, port):
            return f'{scheme}://{host}:{port}', source
    return '', ''


def _resolve_browser_proxy(proxy_env_keys, environ=None, gsettings_reader=None, local_port_probe=None):
    value, source = _read_proxy_from_env(proxy_env_keys, environ=environ)
    if value:
        return value, source
    value, source = _read_proxy_from_gsettings(reader=gsettings_reader)
    if value:
        return value, source
    return _read_proxy_from_local_candidates(port_probe=local_port_probe)


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
        value, _ = _resolve_browser_proxy(proxy_env_keys)
        return value

    def get_browser_proxy_source():
        _, source = _resolve_browser_proxy(proxy_env_keys)
        return source

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
