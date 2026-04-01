import time

from xmonitor.services.notify.reply_context import NotifyReplyProgressTracker


def prepare_notify_reply_context(item, deps):
    global_token = deps.global_token
    extract_status_id_from_notification_item = deps.extract_status_id_from_notification_item
    _throttle_reply_action_if_needed = deps._throttle_reply_action_if_needed
    _set_reply_flow_active = deps._set_reply_flow_active
    notify_state_facade = deps.notify_state_facade
    ensure_reply_work_tab = deps.ensure_reply_work_tab

    if not global_token.strip():
        return None, "请先配置并验证 auth_token 后再回复"

    status_id = extract_status_id_from_notification_item(item)
    if not status_id:
        return None, "该通知缺少可回复的状态ID（可能是兜底通知记录）"

    handle_hint = item.get("handle", "")
    task_key = str(item.get("key", "") or "").strip()

    _throttle_reply_action_if_needed()
    _set_reply_flow_active(True)
    flow_started_at = time.perf_counter()
    progress = NotifyReplyProgressTracker(task_key, flow_started_at, notify_state_facade)

    try:
        tab = ensure_reply_work_tab()
    except Exception as e:
        _set_reply_flow_active(False)
        return None, f"回复工作标签页初始化失败: {e}"

    return {
        "status_id": status_id,
        "handle_hint": handle_hint,
        "task_key": task_key,
        "flow_started_at": flow_started_at,
        "progress": progress,
        "mark": progress.mark,
        "mark_stage": progress.mark_stage,
        "stage_marks": progress.stage_marks,
        "tab": tab,
    }, ""
