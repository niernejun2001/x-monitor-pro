import tempfile
import unittest
from unittest import mock

from xmonitor.runtime.startup_support import save_local_json_config


class StartupSupportTests(unittest.TestCase):
    def test_save_local_json_config_formats_blank_error(self):
        class _BlankError(Exception):
            def __str__(self):
                return ''

        with tempfile.TemporaryDirectory() as tmpdir:
            target = f'{tmpdir}/config.json'
            with mock.patch('builtins.open', side_effect=_BlankError()):
                ok, err = save_local_json_config(target, {'a': 1})

        self.assertFalse(ok)
        self.assertEqual(err, '_BlankError')


if __name__ == '__main__':
    unittest.main()
