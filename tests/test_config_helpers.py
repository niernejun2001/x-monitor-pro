import logging
import os
import tempfile
import unittest
from unittest import mock

from xmonitor.runtime.config_helpers import (
    get_data_dir,
    get_default_user_data_dir,
    parse_backoff_seconds,
    resolve_server_port,
)


class ConfigHelpersTests(unittest.TestCase):
    def test_parse_backoff_seconds(self):
        self.assertEqual(parse_backoff_seconds('2, 5, 5, 9'), (2, 5, 9))
        self.assertEqual(parse_backoff_seconds(''), (2, 5, 9, 15))

    def test_resolve_server_port(self):
        port, source = resolve_server_port('8080', is_port_available_fn=lambda p: p == 8080, get_free_port_fn=lambda: 9999, logging_module=logging)
        self.assertEqual((port, source), (8080, 'env'))
        port2, source2 = resolve_server_port('bad', is_port_available_fn=lambda p: False, get_free_port_fn=lambda: 9999, logging_module=logging)
        self.assertEqual((port2, source2), (9999, 'random'))

    def test_get_default_user_data_dir(self):
        path = get_default_user_data_dir()
        self.assertTrue(path.endswith('x-monitor-pro'))

    def test_get_data_dir_project_override(self):
        with mock.patch.dict(os.environ, {'XMONITOR_USE_PROJECT_DATA': '1'}, clear=False):
            self.assertTrue(get_data_dir('/tmp/demo').endswith('/tmp/demo/data'))


if __name__ == '__main__':
    unittest.main()
