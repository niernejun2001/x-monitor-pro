import os
import tempfile
import types
import unittest

from xmonitor.storage.storage_sqlite import (
    has_blob,
    has_processed_users_table,
    has_structured_state,
    load_blob,
    load_processed_users_set,
    load_structured_state,
    save_blob,
    save_processed_users_set,
    save_structured_state,
)


class StorageSQLiteTests(unittest.TestCase):
    def test_save_and_load_blob(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = types.SimpleNamespace(
                DATA_DIR=tmpdir,
                SQLITE_STATE_FILE=os.path.join(tmpdir, 'state.sqlite3'),
            )
            payload = {'token': 'abc', 'pending': [1, 2, 3]}
            save_blob(deps, 'sample', payload)
            self.assertTrue(os.path.exists(deps.SQLITE_STATE_FILE))
            self.assertTrue(has_blob(deps, 'sample'))
            self.assertEqual(load_blob(deps, 'sample'), payload)
            self.assertIsNone(load_blob(deps, 'missing'))

    def test_save_and_load_structured_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = types.SimpleNamespace(
                DATA_DIR=tmpdir,
                SQLITE_STATE_FILE=os.path.join(tmpdir, 'state.sqlite3'),
            )
            pending = [
                {'key': 'a', 'handle': '@a', 'content': 'one'},
                {'key': 'b', 'handle': '@b', 'content': 'two'},
            ]
            history_ids = {'h2', 'h1'}
            content_dedupe = {'sig1': 1.5, 'sig2': 2.5}
            save_structured_state(deps, pending, history_ids, content_dedupe)
            self.assertTrue(has_structured_state(deps))
            loaded = load_structured_state(deps)
            self.assertEqual(loaded['pending_results'], pending)
            self.assertEqual(set(loaded['history_ids']), history_ids)
            self.assertEqual(loaded['content_dedupe'], content_dedupe)




    def test_save_and_load_processed_users_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            deps = types.SimpleNamespace(
                DATA_DIR=tmpdir,
                SQLITE_STATE_FILE=os.path.join(tmpdir, 'state.sqlite3'),
            )
            users = {'@b', '@a'}
            save_processed_users_set(deps, users)
            self.assertTrue(has_processed_users_table(deps))
            self.assertEqual(load_processed_users_set(deps), ['@a', '@b'])


if __name__ == '__main__':
    unittest.main()
