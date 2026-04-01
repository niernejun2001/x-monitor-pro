import random
import time


def load_notify_resume_state(task_key, item, status_id, deps, mark_stage_func):
    _, row_live = deps.notify_state_facade.find_pending_item_by_key(task_key)
    row_snapshot = dict(row_live or {})
    resume_stage = deps._resolve_notify_resume_stage(row_snapshot)
    if resume_stage == "reply_pending":
        mark_stage_func("reply_pending", error="", extra={"notify_resume_stage": resume_stage})
    else:
        mark_stage_func(resume_stage, error="", retry_at=0.0, extra={"notify_resume_stage": resume_stage})

    saved_share_link = deps._normalize_dm_share_link(
        str(row_snapshot.get("notify_share_link", "") or "").strip(),
        status_id=status_id,
        status_handle=item.get("status_handle", "") or item.get("handle", ""),
        fallback_url=deps._get_status_link_from_item(item),
    )
    need_reply = not deps._notify_stage_at_least(resume_stage, "reply_sent")
    need_share = not deps._notify_stage_at_least(resume_stage, "share_link_ready")
    dm_progress = {
        "link_sent": deps._notify_stage_at_least(resume_stage, "dm_link_sent"),
        "text_sent": deps._notify_stage_at_least(resume_stage, "dm_text_sent"),
    }
    return row_snapshot, resume_stage, saved_share_link, need_reply, need_share, dm_progress


def ensure_notifications_page(tab, deps, log_to_ui):
    try:
        current_url = str(tab.url or "")
    except Exception:
        current_url = ""
    if "x.com/notifications" not in current_url:
        tab.get("https://x.com/notifications")
        deps._wait_document_ready(tab, timeout=5.0)
        deps._reply_humanized_idle(tab, 0.22, 0.52, "进入通知页后稳定等待")
    log_to_ui("debug", "💬 已进入通知页，准备定位目标通知卡片")
    try:
        tab.wait.ele_displayed('tag:article', timeout=5)
    except Exception:
        pass


def build_notify_tab_ops(tab, item, status_id, handle_hint, deps):
    def _prepare_notifications_view(force_refresh=False):
        return deps._prepare_notifications_view_impl(tab, deps, force_refresh=force_refresh)

    def _match_target_card():
        return deps._match_target_card_impl(tab, item, status_id, deps)

    def _send_reply_from_button(target_reply_btn, target_score, reply_text):
        return deps._send_reply_from_button_impl(tab, target_reply_btn, target_score, reply_text, status_id, handle_hint, deps)

    return _prepare_notifications_view, _match_target_card, _send_reply_from_button


def match_notify_target_card(
    *,
    tab,
    item,
    need_reply,
    need_share,
    resume_stage,
    status_id,
    handle_hint,
    deps,
    mark_func,
    mark_stage_func,
    log_to_ui,
    prepare_notifications_view,
    match_target_card,
):
    target_article = None
    target_reply_btn = None
    target_score = 0
    matched_handle = deps.normalize_handle(item.get("status_handle", "") or item.get("handle", ""))
    matched_status_id = str(status_id or "")

    if not (need_reply or need_share):
        log_to_ui("info", f"🔁 断点续跑：跳过通知卡片匹配（stage={resume_stage}）")
        return target_article, target_reply_btn, target_score, matched_handle, matched_status_id, ""

    prepare_notifications_view(force_refresh=False)
    log_to_ui("debug", "💬 已准备通知视图，开始定位目标通知卡片")
    deps._reply_humanized_idle(tab, 0.1, 0.26, "定位通知卡片前")

    target_article, target_reply_btn, target_score, matched_handle, matched_status_id, match_err = match_target_card()
    if match_err:
        deps._capture_runtime_diagnostic(
            tab,
            "match_target_card_failed",
            err=match_err,
            selectors=['tag:article', 'css:[data-testid="reply"]'],
            extra={"status_id": status_id, "handle_hint": handle_hint},
        )
        return None, None, 0, matched_handle, matched_status_id, match_err

    mark_func("match_card")
    mark_stage_func("match_card")
    log_to_ui(
        "debug",
        f"💬 已定位通知卡片 score={target_score}, status_id={matched_status_id}, handle={matched_handle or ''}"
    )
    deps._reply_humanized_idle(tab, 0.08, 0.22, "定位卡片后稳定等待")
    return target_article, target_reply_btn, target_score, matched_handle, matched_status_id, ""


def handle_notify_unhandled_prompt(tab, status_id, handle_hint, deps, err):
    diag_before = deps._capture_runtime_diagnostic(
        tab,
        "unhandled_prompt_before_clear",
        err=err,
        selectors=[
            'css:[role="alertdialog"]',
            'css:[role="dialog"]',
            'css:[data-testid="confirmationSheetDialog"]',
            'css:[data-testid="modal"]',
            'css:[data-testid="reply"]',
            'css:[data-testid="tweetButton"]',
            'css:[data-testid="dm-composer-send-button"]',
        ],
        extra={"status_id": status_id, "handle_hint": handle_hint, "phase": "before_clear"},
    )
    deps._prepare_reply_prompt_guard(tab, "异常恢复")
    diag_after = deps._capture_runtime_diagnostic(
        tab,
        "unhandled_prompt_after_clear",
        err=err,
        selectors=[
            'css:[role="alertdialog"]',
            'css:[role="dialog"]',
            'css:[data-testid="reply"]',
            'css:[data-testid="tweetButton"]',
            'css:[data-testid="dm-composer-send-button"]',
        ],
        extra={"status_id": status_id, "handle_hint": handle_hint, "phase": "after_clear"},
    )
    diag_ref = diag_before or diag_after
    if diag_ref:
        return False, f"检测到未处理提示框，已自动清理，请重试一次（已截图留档: {diag_ref}）"
    return False, "检测到未处理提示框，已自动清理，请重试一次"


def restore_notifications_tab(tab):
    try:
        final_url = str(tab.url or "")
    except Exception:
        final_url = ""
    try:
        if "x.com/notifications" not in final_url:
            tab.get("https://x.com/notifications")
            time.sleep(random.uniform(0.3, 0.7))
    except Exception:
        pass
