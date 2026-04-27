import os
import unittest
from unittest import mock

from xmonitor.runtime.exports import support_system


class SupportSystemProxyTests(unittest.TestCase):
    def test_read_proxy_from_env_prefers_first_match(self):
        value, source = support_system._read_proxy_from_env(
            ('XMONITOR_PROXY', 'ALL_PROXY'),
            environ={'ALL_PROXY': 'http://127.0.0.1:7890', 'XMONITOR_PROXY': 'socks5://127.0.0.1:7891'},
        )
        self.assertEqual(value, 'socks5://127.0.0.1:7891')
        self.assertEqual(source, 'XMONITOR_PROXY')

    def test_read_proxy_from_gsettings_requires_manual_mode(self):
        values = {
            ('org.gnome.system.proxy', 'mode'): "'manual'",
            ('org.gnome.system.proxy.http', 'host'): "'127.0.0.1'",
            ('org.gnome.system.proxy.http', 'port'): '7897',
        }
        reader = lambda schema, key: values.get((schema, key), '')
        value, source = support_system._read_proxy_from_gsettings(reader=reader)
        self.assertEqual(value, 'http://127.0.0.1:7897')
        self.assertEqual(source, 'gsettings_http')

    def test_resolve_browser_proxy_falls_back_to_local_candidates(self):
        probe = lambda host, port: port == 7890
        value, source = support_system._resolve_browser_proxy(
            ('XMONITOR_PROXY', 'ALL_PROXY'),
            environ={},
            gsettings_reader=lambda schema, key: "'none'" if key == 'mode' else '',
            local_port_probe=probe,
        )
        self.assertEqual(value, 'http://127.0.0.1:7890')
        self.assertEqual(source, 'auto_local_http_7890')

    def test_format_browser_proxy_display_masks_credentials(self):
        exports = support_system.build_support_system_exports(
            safe_float_fn=float,
            safe_int_fn=int,
            env_port_getter=lambda: '',
            proxy_env_keys=('XMONITOR_PROXY',),
            logging_module=mock.Mock(),
        )
        with mock.patch.dict(os.environ, {'XMONITOR_PROXY': 'http://user:pass@127.0.0.1:7890'}, clear=True):
            payload = exports['build_browser_proxy_runtime_payload']()
        self.assertTrue(payload['browser_proxy_configured'])
        self.assertEqual(payload['browser_proxy_source'], 'XMONITOR_PROXY')
        self.assertEqual(payload['browser_proxy_display'], 'http://***@127.0.0.1:7890')


if __name__ == '__main__':
    unittest.main()
