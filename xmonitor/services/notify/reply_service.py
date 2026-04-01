import time

from xmonitor.services.notify.reply_bootstrap import prepare_notify_reply_context
from xmonitor.services.notify.reply_context import (
    NotifyReplyProgressTracker,
)
from xmonitor.services.notify.reply_dm_service import (
    prepare_notify_share_link,
    run_notify_dm_followup,
)
from xmonitor.services.notify.reply_finalize import finalize_notify_dm_followup
from xmonitor.services.notify.reply_support import (
    build_notify_tab_ops,
    ensure_notifications_page,
    handle_notify_unhandled_prompt,
    load_notify_resume_state,
    match_notify_target_card,
    restore_notifications_tab,
)


def send_notification_reply(item, message, deps, dm_message=""):
    reply_action_lock = deps.reply_action_lock
    _set_reply_flow_active = deps._set_reply_flow_active
    _prepare_reply_prompt_guard = deps._prepare_reply_prompt_guard
    log_to_ui = deps.log_to_ui
    _reply_humanized_idle = deps._reply_humanized_idle
    _is_unhandled_prompt_error = deps._is_unhandled_prompt_error
    _capture_runtime_diagnostic = deps._capture_runtime_diagnostic
    """针对通知记录发送回复。"""
    with reply_action_lock:
        runtime, init_err = prepare_notify_reply_context(item, deps)
        if init_err:
            return False, init_err

        status_id = runtime["status_id"]
        handle_hint = runtime["handle_hint"]
        task_key = runtime["task_key"]
        flow_started_at = runtime["flow_started_at"]
        _mark = runtime["mark"]
        _mark_stage = runtime["mark_stage"]
        stage_marks = runtime["stage_marks"]
        tab = runtime["tab"]

        try:
            _prepare_reply_prompt_guard(tab, "回复流程启动")
            log_to_ui("info", f"💬 开始执行通知回复(复用全局浏览器): {handle_hint} -> status {status_id}")
            row_snapshot, resume_stage, saved_share_link, need_reply, need_share, dm_progress = load_notify_resume_state(
                task_key,
                item,
                status_id,
                deps,
                _mark_stage,
            )
            if dm_progress["text_sent"] and (not need_reply) and (not need_share):
                _mark_stage("done", error="", retry_at=0.0, save=True)
                return True, ""

            _reply_humanized_idle(tab, 0.18, 0.42, "回复流程启动")
            ensure_notifications_page(tab, deps, log_to_ui)

            _prepare_notifications_view, _match_target_card, _send_reply_from_button = build_notify_tab_ops(
                tab,
                item,
                status_id,
                handle_hint,
                deps,
            )
            target_article, target_reply_btn, target_score, matched_handle, matched_status_id, match_err = match_notify_target_card(
                tab=tab,
                item=item,
                need_reply=need_reply,
                need_share=need_share,
                resume_stage=resume_stage,
                status_id=status_id,
                handle_hint=handle_hint,
                deps=deps,
                mark_func=_mark,
                mark_stage_func=_mark_stage,
                log_to_ui=log_to_ui,
                prepare_notifications_view=_prepare_notifications_view,
                match_target_card=_match_target_card,
            )
            if match_err:
                return False, match_err

            share_link = str(saved_share_link or "").strip()
            item["_target_article"] = target_article
            ok_share, share_link, share_err = prepare_notify_share_link(
                tab=tab,
                item=item,
                share_link=share_link,
                need_share=need_share,
                matched_handle=matched_handle,
                matched_status_id=matched_status_id,
                status_id=status_id,
                deps=deps,
                mark_func=_mark,
                mark_stage_func=_mark_stage,
            )
            item.pop("_target_article", None)
            if not ok_share:
                return False, share_err

            if need_reply:
                ok_reply, err_reply = _send_reply_from_button(target_reply_btn, target_score, message)
                if not ok_reply:
                    return False, err_reply
                _mark("send_reply")
                _mark_stage("reply_sent", extra={"notify_share_link": share_link}, save=True)
            else:
                log_to_ui("info", f"🔁 断点续跑：跳过公开回复发送（stage={resume_stage}）")

            ok_dm, dm_err, dm_closed, dm_tab = run_notify_dm_followup(
                tab=tab,
                item=item,
                share_link=share_link,
                dm_message=dm_message,
                dm_progress=dm_progress,
                task_key=task_key,
                row_snapshot=row_snapshot,
                deps=deps,
                mark_func=_mark,
                mark_stage_func=_mark_stage,
            )
            return finalize_notify_dm_followup(
                tab=tab,
                ok_dm=ok_dm,
                dm_err=dm_err,
                dm_closed=dm_closed,
                share_link=share_link,
                status_id=status_id,
                handle_hint=handle_hint,
                flow_started_at=flow_started_at,
                stage_marks=stage_marks,
                deps=deps,
                mark_func=_mark,
                mark_stage_func=_mark_stage,
                prepare_notifications_view=_prepare_notifications_view,
                match_target_card=_match_target_card,
                send_reply_from_button=_send_reply_from_button,
            )
        except Exception as e:
            if _is_unhandled_prompt_error(e):
                return handle_notify_unhandled_prompt(tab, status_id, handle_hint, deps, e)
            _capture_runtime_diagnostic(
                tab,
                "send_notification_reply_exception",
                err=e,
                selectors=['tag:article', 'css:[data-testid="reply"]', 'css:[data-testid="dm-composer-send-button"]'],
                extra={"status_id": status_id, "handle_hint": handle_hint}
            )
            return False, f"回复发送失败: {e}"
        finally:
            restore_notifications_tab(tab)
            _set_reply_flow_active(False)
