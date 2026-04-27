import types
import unittest

from xmonitor.services.support.diagnostics import probe_selectors_snapshot


class DiagnosticsTests(unittest.TestCase):
    def test_probe_selectors_snapshot_formats_blank_error(self):
        class _BlankError(Exception):
            def __str__(self):
                return ''

        tab = types.SimpleNamespace(
            ele=lambda selector, timeout=0.25: (_ for _ in ()).throw(_BlankError()),
        )

        rows = probe_selectors_snapshot(tab, ['css:button'])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['error'], '_BlankError')


if __name__ == '__main__':
    unittest.main()
