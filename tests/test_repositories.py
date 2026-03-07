import threading
import types
import unittest

from xmonitor.storage.repositories import MonitorTasksRepository, PendingResultsRepository, ProcessedUsersRepository


class RepositoryTests(unittest.TestCase):
    def _make_deps(self):
        deps = types.SimpleNamespace()
        deps.pending_results = [
            {'key': 'n1', 'source': '通知页面', 'handle': '@a', 'content': 'one'},
            {'key': 't1', 'source': 'tweet', 'handle': '@b', 'content': 'two'},
        ]
        deps.processed_users = {'@u1', '@u2'}
        deps.data_lock = threading.Lock()
        deps._set_runtime_attr = lambda name, value: setattr(deps, name, value)
        return deps

    def test_pending_results_repository_remove_and_clear(self):
        deps = self._make_deps()
        repo = PendingResultsRepository(deps)
        removed = repo.remove_matching(key='n1')
        self.assertEqual(removed, 1)
        self.assertEqual(len(deps.pending_results), 1)
        removed2 = repo.clear_results('tweet')
        self.assertEqual(removed2, 1)
        self.assertEqual(deps.pending_results, [])

    def test_pending_results_repository_find_and_update_notify(self):
        deps = self._make_deps()
        repo = PendingResultsRepository(deps)
        idx, row = repo.find_notify_by_key('n1', copy_row=True)
        self.assertEqual(idx, 0)
        self.assertEqual(row['handle'], '@a')
        updated = repo.update_notify_manual_reply('n1', 'reply', 'dm', dm_llm_enabled=True)
        self.assertTrue(updated)
        self.assertEqual(deps.pending_results[0]['notify_reply_text'], 'reply')
        self.assertEqual(deps.pending_results[0]['notify_dm_text'], 'dm')
        self.assertTrue(deps.pending_results[0]['notify_dm_llm_used'])

    def test_processed_users_repository_clear(self):
        deps = self._make_deps()
        repo = ProcessedUsersRepository(deps)
        repo.clear()
        self.assertEqual(deps.processed_users, set())


    def test_monitor_tasks_repository_add_remove_snapshot(self):
        deps = self._make_deps()
        deps.monitor_tasks = []
        repo = MonitorTasksRepository(deps)
        self.assertTrue(repo.add('https://x.com/a'))
        self.assertFalse(repo.add('https://x.com/a'))
        self.assertEqual(repo.snapshot(), [{'url': 'https://x.com/a', 'last_check': '等待'}])
        self.assertEqual(repo.remove('https://x.com/a'), 1)
        self.assertEqual(repo.snapshot(), [])


if __name__ == '__main__':
    unittest.main()
