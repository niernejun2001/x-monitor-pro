import time
import datetime


def find_pending_notify_item_by_key(item_key, pending_results, data_lock):
    key = str(item_key or '').strip()
    if not key:
        return -1, None
    with data_lock:
        for idx, row in enumerate(pending_results):
            if row.get('key') == key and row.get('source') == '通知页面':
                return idx, row
    return -1, None


def update_notify_flow_state(
    item_key,
    *,
    pending_results,
    data_lock,
    save_state_cb,
    normalize_stage_fn,
    split_error_fn,
    stage=None,
    error='',
    retry_at=0.0,
    attempt=None,
    extra=None,
    save=False,
    error_code=None,
    error_detail=None,
):
    key = str(item_key or '').strip()
    if not key:
        return False
    stage_text = normalize_stage_fn(stage) or str(stage or '').strip()
    err_text = str(error or '').strip()
    code_text = str(error_code or '').strip()
    detail_text = str(error_detail or '').strip()
    if err_text and (not code_text or not detail_text):
        parsed_code, parsed_detail = split_error_fn(err_text)
        if not code_text:
            code_text = parsed_code
        if not detail_text:
            detail_text = parsed_detail
    now = time.time()
    updated = False
    with data_lock:
        for row in pending_results:
            if row.get('key') != key or row.get('source') != '通知页面':
                continue
            if stage_text:
                row['notify_flow_stage'] = stage_text
            row['notify_flow_error'] = detail_text or err_text
            row['notify_flow_error_code'] = code_text
            row['notify_flow_error_detail'] = detail_text or err_text
            row['notify_flow_updated_at'] = now
            row['notify_flow_updated_time'] = datetime.datetime.fromtimestamp(now).strftime('%H:%M:%S')
            if attempt is not None:
                try:
                    row['notify_flow_attempt'] = int(attempt)
                except Exception:
                    row['notify_flow_attempt'] = attempt
            if retry_at:
                try:
                    retry_ts = float(retry_at)
                except Exception:
                    retry_ts = 0.0
                if retry_ts > 0:
                    row['notify_retry_at'] = retry_ts
                    row['notify_retry_time'] = datetime.datetime.fromtimestamp(retry_ts).strftime('%H:%M:%S')
            else:
                row['notify_retry_at'] = 0
                row['notify_retry_time'] = ''
            if not (detail_text or err_text):
                row['notify_flow_error'] = ''
                row['notify_flow_error_code'] = ''
                row['notify_flow_error_detail'] = ''
            if isinstance(extra, dict):
                for key2, value in extra.items():
                    row[key2] = value
            updated = True
            break
    if updated and save:
        save_state_cb()
    return updated


def collect_due_notify_retry_items(limit, pending_results, data_lock):
    now = time.time()
    max_items = max(1, int(limit))
    items = []
    with data_lock:
        for row in pending_results:
            if row.get('source') != '通知页面':
                continue
            if bool(row.get('notify_replied', False)):
                continue
            if str(row.get('notify_flow_stage', '') or '').strip().lower() != 'retry_waiting':
                continue
            retry_at = float(row.get('notify_retry_at', 0) or 0)
            if retry_at <= 0 or retry_at > now:
                continue
            items.append(dict(row))
            if len(items) >= max_items:
                break
    return items

def resolve_notify_retry_backoff_sec(attempt, backoff_seconds):
    try:
        idx = max(0, int(attempt) - 1)
    except Exception:
        idx = 0
    if idx < len(backoff_seconds):
        return int(backoff_seconds[idx])
    return int(backoff_seconds[-1]) if backoff_seconds else 15


def schedule_notify_retry(
    item_key,
    err_text,
    attempt,
    *,
    pending_results,
    data_lock,
    update_state_fn,
    resolve_resume_stage_fn,
    split_flow_error_fn,
    find_item_fn,
    is_retryable_fn,
    max_retry,
    backoff_seconds,
    policy,
    reason='retry_queue',
    save=True,
):
    key = str(item_key or '').strip()
    err_msg = str(err_text or '').strip() or 'E_REPLY_FAILED: 未知错误'
    _, cur_row = find_item_fn(key)
    resume_stage = resolve_resume_stage_fn(cur_row or {})
    try:
        attempt_num = max(1, int(attempt))
    except Exception:
        attempt_num = 1

    code, detail = split_flow_error_fn(err_msg)
    if policy != 'retry_queue':
        update_state_fn(
            key,
            stage='retry_waiting',
            attempt=attempt_num,
            error=detail,
            error_code=code or 'E_REPLY_FAILED',
            error_detail=detail or err_msg,
            retry_at=0,
            extra={
                'notify_retry_reason': f'{reason}:policy_disabled',
                'notify_resume_stage': resume_stage,
            },
            save=save,
        )
        return False, 0.0, '重试队列已禁用，请人工重试'

    if (not is_retryable_fn(err_msg)) or code == 'E_DM_CLOSED_CONFIRMED':
        update_state_fn(
            key,
            stage='retry_waiting',
            attempt=attempt_num,
            error=detail,
            error_code=code or 'E_REPLY_FAILED',
            error_detail=detail or err_msg,
            retry_at=0,
            extra={
                'notify_retry_reason': f'{reason}:not_retryable',
                'notify_resume_stage': resume_stage,
            },
            save=save,
        )
        return False, 0.0, '错误不可自动重试，请人工处理'

    if attempt_num >= max_retry:
        update_state_fn(
            key,
            stage='retry_waiting',
            attempt=attempt_num,
            error=detail,
            error_code=code or 'E_REPLY_FAILED',
            error_detail=detail or err_msg,
            retry_at=0,
            extra={
                'notify_retry_reason': f'{reason}:max_retry_reached',
                'notify_resume_stage': resume_stage,
            },
            save=save,
        )
        return False, 0.0, f'已达到最大重试次数({max_retry})，请人工重试'

    backoff_sec = resolve_notify_retry_backoff_sec(attempt_num, backoff_seconds)
    import time as _time
    retry_at = _time.time() + max(1, int(backoff_sec))
    update_state_fn(
        key,
        stage='retry_waiting',
        attempt=attempt_num,
        error=detail,
        error_code=code or 'E_REPLY_FAILED',
        error_detail=detail or err_msg,
        retry_at=retry_at,
        extra={'notify_retry_reason': reason, 'notify_resume_stage': resume_stage},
        save=save,
    )
    return True, retry_at, f'已加入重试队列，{int(backoff_sec)}s 后重试'


def mark_notify_reply_success(key, message, dm_message, *, pending_results, data_lock, save_state_cb, reply_time_text=''):
    key = str(key or '').strip()
    if not key:
        return False
    reply_time = str(reply_time_text or '').strip() or datetime.datetime.now().strftime('%H:%M:%S')
    updated = False
    with data_lock:
        for row in pending_results:
            if row.get('key') != key or row.get('source') != '通知页面':
                continue
            row['notify_replied'] = True
            row['notify_reply_text'] = str(message or '')
            row['notify_dm_text'] = str(dm_message or '')
            row['notify_reply_time'] = reply_time
            row['notify_flow_stage'] = 'done'
            row['notify_flow_error'] = ''
            row['notify_flow_error_code'] = ''
            row['notify_flow_error_detail'] = ''
            row['notify_retry_at'] = 0
            row['notify_retry_time'] = ''
            row['notify_flow_updated_at'] = time.time()
            row['notify_flow_updated_time'] = datetime.datetime.now().strftime('%H:%M:%S')
            updated = True
            break
    if updated:
        save_state_cb()
    return updated


def process_notify_retry_queue(
    max_items,
    *,
    pending_results,
    data_lock,
    collect_due_items_fn,
    update_state_fn,
    find_item_fn,
    resolve_resume_stage_fn,
    send_notification_reply_fn,
    record_reply_outcome_fn,
    mark_success_fn,
    schedule_retry_fn,
    log_fn,
):
    due_items = collect_due_items_fn(limit=max_items)
    if not due_items:
        return 0

    done_count = 0
    for item in due_items:
        key = str(item.get('key', '') or '').strip()
        if not key:
            continue
        reply_text = str(item.get('notify_reply_text', '') or '').strip()
        dm_text = str(item.get('notify_dm_text', '') or '').strip()
        if not reply_text or not dm_text:
            update_state_fn(
                key,
                stage='retry_waiting',
                error='缺少重试模板：请手动在通知行重新选择回复与私信模板',
                error_code='E_MISSING_TEMPLATE',
                error_detail='missing notify_reply_text or notify_dm_text',
                retry_at=0,
                save=True,
            )
            continue

        try:
            current_attempt = int(item.get('notify_flow_attempt', 0) or 0) + 1
        except Exception:
            current_attempt = 1
        _, live_row = find_item_fn(key)
        resume_stage = resolve_resume_stage_fn(live_row or item)
        update_state_fn(
            key,
            stage='reply_pending',
            attempt=current_attempt,
            error='',
            retry_at=0,
            extra={
                'notify_retry_reason': 'auto_retry_execute',
                'notify_resume_stage': resume_stage,
            },
            save=True,
        )

        ok, err = send_notification_reply_fn(item, reply_text, dm_message=dm_text)
        if ok:
            record_reply_outcome_fn(item.get('handle', ''), True, '')
            mark_success_fn(key, reply_text, dm_text, save=True)
            done_count += 1
            log_fn('success', f"✅ 自动重试成功: {item.get('handle', '')}")
            continue

        record_reply_outcome_fn(item.get('handle', ''), False, err or '')
        scheduled, _, schedule_msg = schedule_retry_fn(
            key,
            err or 'E_REPLY_FAILED: 自动重试失败',
            attempt=current_attempt,
            reason='auto_retry_queue',
            save=True,
        )
        if scheduled:
            log_fn('warn', f"⚠️ 自动重试失败，已重新排队: {item.get('handle', '')} - {schedule_msg}")
        else:
            log_fn('warn', f"⚠️ 自动重试失败，转人工处理: {item.get('handle', '')} - {schedule_msg}")

    return done_count
