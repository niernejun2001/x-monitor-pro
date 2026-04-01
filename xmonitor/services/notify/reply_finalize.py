import time


def log_notify_reply_timing(log_to_ui, stage_marks, flow_started_at, *, dm_closed=False):
    total_cost = time.perf_counter() - flow_started_at
    if dm_closed:
        log_to_ui(
            "debug",
            f"⏱️ 回复流程耗时(私信关闭): 匹配{stage_marks.get('match_card', 0):.2f}s, "
            f"链接{stage_marks.get('prepare_share_link', 0):.2f}s, "
            f"首评{stage_marks.get('send_reply', 0):.2f}s, 补评{stage_marks.get('fallback_reply', 0):.2f}s, "
            f"总计{total_cost:.2f}s"
        )
        return
    log_to_ui(
        "debug",
        f"⏱️ 回复流程耗时: 匹配{stage_marks.get('match_card', 0):.2f}s, "
        f"链接{stage_marks.get('prepare_share_link', 0):.2f}s, 首评{stage_marks.get('send_reply', 0):.2f}s, "
        f"开私信{stage_marks.get('open_dm', 0):.2f}s, 发链接{stage_marks.get('send_dm_link', 0):.2f}s, "
        f"发文案{stage_marks.get('send_dm_text', 0):.2f}s, 总计{total_cost:.2f}s"
    )


def _send_dm_closed_fallback_reply(
    *,
    tab,
    status_id,
    handle_hint,
    deps,
    prepare_notifications_view,
    match_target_card,
    send_reply_from_button,
    fallback_text,
):
    _wait_document_ready = deps._wait_document_ready

    try:
        now_url = str(tab.url or "")
    except Exception:
        now_url = ""
    if "x.com/notifications" not in now_url:
        tab.get("https://x.com/notifications")
        _wait_document_ready(tab, timeout=5.5)
    prepare_notifications_view(force_refresh=True)
    fb_article, fb_reply_btn, fb_score, _, _, fb_match_err = match_target_card()
    if fb_match_err:
        return False, f"用户不可私信，且补充评论失败: {fb_match_err}"
    ok_fb, err_fb = send_reply_from_button(fb_reply_btn, fb_score, fallback_text)
    if not ok_fb:
        return False, f"用户不可私信，且补充评论失败: {err_fb}"
    return True, ""


def finalize_notify_dm_followup(
    *,
    tab,
    ok_dm,
    dm_err,
    dm_closed,
    share_link,
    status_id,
    handle_hint,
    flow_started_at,
    stage_marks,
    deps,
    mark_func,
    mark_stage_func,
    prepare_notifications_view,
    match_target_card,
    send_reply_from_button,
):
    log_to_ui = deps.log_to_ui
    DM_CLOSED_FALLBACK_REPLY_TEXT = deps.DM_CLOSED_FALLBACK_REPLY_TEXT

    if not ok_dm:
        if not dm_closed:
            return False, dm_err

        mark_stage_func("dm_closed_confirmed", extra={"notify_share_link": share_link}, save=True)
        mark_func("dm_open_failed")
        log_to_ui("warn", "⚠️ 目标用户未开启私信，准备发送补充评论后结束私信流程")
        ok_fb, err_fb = _send_dm_closed_fallback_reply(
            tab=tab,
            status_id=status_id,
            handle_hint=handle_hint,
            deps=deps,
            prepare_notifications_view=prepare_notifications_view,
            match_target_card=match_target_card,
            send_reply_from_button=send_reply_from_button,
            fallback_text=DM_CLOSED_FALLBACK_REPLY_TEXT,
        )
        if not ok_fb:
            return False, err_fb

        mark_func("fallback_reply")
        log_notify_reply_timing(log_to_ui, stage_marks, flow_started_at, dm_closed=True)
        log_to_ui("info", "💬 用户私信关闭，已发送补充评论并结束私信发送流程")
        mark_stage_func("done", save=True)
        return True, ""

    log_notify_reply_timing(log_to_ui, stage_marks, flow_started_at, dm_closed=False)
    mark_stage_func("done", save=True)
    return True, ""
