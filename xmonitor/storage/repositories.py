class MonitorTasksRepository:
    def __init__(self, deps):
        self.deps = deps

    def _set_monitor_tasks(self, rows):
        setter = getattr(self.deps, '_set_runtime_attr', None)
        if callable(setter):
            setter('monitor_tasks', rows)
        else:
            self.deps.monitor_tasks = rows

    def snapshot(self):
        with self.deps.data_lock:
            return list(self.deps.monitor_tasks)

    def add(self, url):
        url_text = str(url or '').strip()
        if not url_text:
            return False
        with self.deps.data_lock:
            if any(task.get('url') == url_text for task in self.deps.monitor_tasks):
                return False
            rows = list(self.deps.monitor_tasks)
            rows.append({'url': url_text, 'last_check': '等待'})
            self._set_monitor_tasks(rows)
        return True

    def remove(self, url):
        url_text = str(url or '').strip()
        with self.deps.data_lock:
            before = len(self.deps.monitor_tasks)
            rows = [task for task in self.deps.monitor_tasks if task.get('url') != url_text]
            self._set_monitor_tasks(rows)
        return before - len(rows)


class PendingResultsRepository:
    def __init__(self, deps):
        self.deps = deps

    def _set_pending_results(self, rows):
        setter = getattr(self.deps, '_set_runtime_attr', None)
        if callable(setter):
            setter('pending_results', rows)
        else:
            self.deps.pending_results = rows

    def snapshot(self):
        with self.deps.data_lock:
            return list(self.deps.pending_results)

    def count_by_source(self, source=None):
        with self.deps.data_lock:
            if not source:
                return len(self.deps.pending_results)
            return sum(1 for row in self.deps.pending_results if row.get('source') == source)

    def find_notify_by_key(self, key, *, copy_row=False):
        key_text = str(key or '').strip()
        if not key_text:
            return -1, None
        with self.deps.data_lock:
            for idx, row in enumerate(self.deps.pending_results):
                if row.get('key') == key_text and row.get('source') == '通知页面':
                    return idx, (dict(row) if copy_row else row)
        return -1, None

    def remove_matching(self, *, key=None, handle=None):
        with self.deps.data_lock:
            before_count = len(self.deps.pending_results)
            if key:
                rows = [r for r in self.deps.pending_results if r.get('key') != key]
            elif handle:
                rows = [r for r in self.deps.pending_results if r.get('handle') != handle]
            else:
                rows = list(self.deps.pending_results)
            removed = before_count - len(rows)
            if removed:
                self._set_pending_results(rows)
        return removed

    def clear_results(self, result_type='all'):
        with self.deps.data_lock:
            before_count = len(self.deps.pending_results)
            if result_type == 'notify':
                rows = [r for r in self.deps.pending_results if r.get('source') != '通知页面']
            elif result_type == 'tweet':
                rows = [r for r in self.deps.pending_results if r.get('source') == '通知页面']
            else:
                rows = []
            removed = before_count - len(rows)
            self._set_pending_results(rows)
        return removed

    def list_reply_items(self, is_reply_fn, *, limit=200):
        limit = max(1, min(int(limit), 2000))
        with self.deps.data_lock:
            reply_items = [dict(item) for item in self.deps.pending_results if is_reply_fn(item)]
        reply_items.reverse()
        return reply_items[:limit]

    def update_notify_manual_reply(self, key, message, dm_message, *, dm_llm_enabled=False):
        key_text = str(key or '').strip()
        if not key_text:
            return False
        updated = False
        with self.deps.data_lock:
            for row in self.deps.pending_results:
                if row.get('key') == key_text and row.get('source') == '通知页面':
                    row['notify_reply_text'] = message
                    row['notify_dm_text'] = dm_message
                    row['notify_dm_text_generated'] = ''
                    row['notify_dm_llm_used'] = bool(dm_llm_enabled)
                    row['notify_dm_llm_latency_ms'] = 0
                    row['notify_dm_llm_regen_attempt'] = 0
                    row['notify_dm_llm_error_code'] = ''
                    row['notify_dm_llm_error_detail'] = ''
                    if not str(row.get('notify_flow_stage', '')).strip():
                        row['notify_flow_stage'] = 'reply_pending'
                    updated = True
                    break
        return updated


class ProcessedUsersRepository:
    def __init__(self, deps):
        self.deps = deps

    def clear(self):
        with self.deps.data_lock:
            self.deps.processed_users.clear()

    def snapshot(self):
        with self.deps.data_lock:
            return set(self.deps.processed_users)
