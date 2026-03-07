from xmonitor.storage.notify_state_store import (
    collect_due_notify_retry_items,
    find_pending_notify_item_by_key,
    mark_notify_reply_success,
    process_notify_retry_queue,
    resolve_notify_retry_backoff_sec,
    schedule_notify_retry,
    update_notify_flow_state,
)


class NotifyStateFacade:
    def __init__(self, deps):
        self.deps = deps

    def find_pending_item_by_key(self, item_key):
        return find_pending_notify_item_by_key(item_key, self.deps.pending_results, self.deps.data_lock)

    def update_flow_state(
        self,
        item_key,
        stage=None,
        error='',
        retry_at=0.0,
        attempt=None,
        extra=None,
        save=False,
        error_code=None,
        error_detail=None,
    ):
        return update_notify_flow_state(
            item_key,
            pending_results=self.deps.pending_results,
            data_lock=self.deps.data_lock,
            save_state_cb=self.deps.save_state,
            normalize_stage_fn=self.deps._normalize_notify_flow_stage,
            split_error_fn=self.deps._split_flow_error,
            stage=stage,
            error=error,
            retry_at=retry_at,
            attempt=attempt,
            extra=extra,
            save=save,
            error_code=error_code,
            error_detail=error_detail,
        )

    def clear_flow_error(self, item_key, save=False):
        return self.update_flow_state(
            item_key,
            error='',
            retry_at=0.0,
            save=save,
            error_code='',
            error_detail='',
        )

    def resolve_retry_backoff_sec(self, attempt):
        return resolve_notify_retry_backoff_sec(attempt, self.deps.DM_RETRY_BACKOFF_SEC)

    def is_unknown_failure_retryable(self, err_text):
        msg = str(err_text or '').strip()
        if not msg:
            return True
        if self.deps._is_dm_closed_error_text(msg):
            return False
        hard_stop_keywords = [
            '缺少可回复的状态id',
            'missing key',
            '通知记录不存在',
            '请先配置并验证 auth_token',
        ]
        lower_msg = msg.lower()
        return not any(keyword in lower_msg for keyword in hard_stop_keywords)

    def mark_reply_success(self, key, message, dm_message, reply_time_text=None, save=True):
        return mark_notify_reply_success(
            key,
            message,
            dm_message,
            pending_results=self.deps.pending_results,
            data_lock=self.deps.data_lock,
            save_state_cb=self.deps.save_state,
            reply_time_text=reply_time_text,
        )

    def schedule_retry(self, item_key, err_text, attempt, reason='retry_queue', save=True):
        return schedule_notify_retry(
            item_key,
            err_text,
            attempt,
            pending_results=self.deps.pending_results,
            data_lock=self.deps.data_lock,
            update_state_fn=self.update_flow_state,
            resolve_resume_stage_fn=self.deps._resolve_notify_resume_stage,
            split_flow_error_fn=self.deps._split_flow_error,
            find_item_fn=self.find_pending_item_by_key,
            is_retryable_fn=self.is_unknown_failure_retryable,
            max_retry=self.deps.DM_TASK_MAX_RETRY,
            backoff_seconds=self.deps.DM_RETRY_BACKOFF_SEC,
            policy=self.deps.DM_UNKNOWN_FAILURE_POLICY,
            reason=reason,
            save=save,
        )

    def collect_due_retry_items(self, limit=2):
        return collect_due_notify_retry_items(limit, self.deps.pending_results, self.deps.data_lock)

    def process_retry_queue(self, max_items=1):
        return process_notify_retry_queue(
            max_items,
            pending_results=self.deps.pending_results,
            data_lock=self.deps.data_lock,
            collect_due_items_fn=self.collect_due_retry_items,
            update_state_fn=self.update_flow_state,
            find_item_fn=self.find_pending_item_by_key,
            resolve_resume_stage_fn=self.deps._resolve_notify_resume_stage,
            send_notification_reply_fn=self.deps.send_notification_reply,
            record_reply_outcome_fn=self.deps._record_reply_outcome,
            mark_success_fn=self.mark_reply_success,
            schedule_retry_fn=self.schedule_retry,
            log_fn=self.deps.log_to_ui,
        )

    def get_pending_notify_count(self):
        return self.deps.pending_results_repo.count_by_source('通知页面')
