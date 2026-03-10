import re
import time

from xmonitor.services.notify_reply_context import build_notify_dm_text_supplier


def prepare_notify_share_link(
    *,
    tab,
    item,
    share_link,
    need_share,
    matched_handle,
    matched_status_id,
    status_id,
    deps,
    mark_func=None,
    mark_stage_func=None,
):
    if not need_share:
        share_link = deps._normalize_dm_share_link(
            share_link,
            status_id=matched_status_id or status_id,
            status_handle=matched_handle or item.get("handle", ""),
            fallback_url=deps._get_status_link_from_item(item, matched_handle, matched_status_id),
        )
        if not share_link:
            return False, "", "断点续跑缺少可用分享链接，请重新执行本条通知"
        deps.log_to_ui("info", f"🔁 断点续跑：复用已生成链接（stage={item.get('notify_flow_stage', '') or '-'})")
        return True, share_link, ""

    share_link_fallback = deps._get_status_link_from_item(item, matched_handle, matched_status_id)
    use_quick_share_link = bool(
        share_link_fallback and "/status/" in share_link_fallback and deps._should_use_share_link_quick_path()
    )
    if use_quick_share_link:
        share_link, share_err = share_link_fallback, ""
        deps.log_to_ui("debug", "🔗 已启用快速链接路径（长队列稳定模式）")
    else:
        deps._prepare_reply_prompt_guard(tab, "复制分享链接前")
        deps._reply_humanized_idle(tab, 0.06, 0.18, "复制分享链接前")
        share_link, share_err = deps._click_share_copy_link(tab, item.get("_target_article"), share_link_fallback)
    if share_err:
        deps.log_to_ui("warn", f"⚠️ 分享复制链接失败，使用回退链接: {share_err}")
    if not share_link:
        deps._capture_runtime_diagnostic(
            tab,
            "share_link_missing",
            err="无法确定要发送的链接",
            selectors=[
                'css:button[aria-label*="分享"]',
                'css:button[aria-label*="Share"]',
                'css:[data-testid="share"]',
            ],
            extra={"status_id": matched_status_id, "handle": matched_handle},
        )
        return False, "", "无法确定要发送的链接"

    share_link_raw = str(share_link or "").strip()
    m_url = re.search(r"https?://[^\s<>\"']+", share_link_raw, flags=re.IGNORECASE)
    if m_url:
        share_link = m_url.group(0).strip()
    elif share_link_raw.startswith("x.com/"):
        share_link = f"https://{share_link_raw}"
    elif share_link_raw.startswith("/"):
        share_link = f"https://x.com{share_link_raw}"
    else:
        share_link = (share_link_raw.split() or [""])[0].strip()
    if not re.match(r'^https?://', share_link, flags=re.IGNORECASE):
        return False, "", f"复制链接格式异常: {share_link[:80]}"

    if callable(mark_func):
        mark_func("prepare_share_link")
    if callable(mark_stage_func):
        mark_stage_func("share_link_ready", extra={"notify_share_link": share_link}, save=True)
    deps.log_to_ui("debug", f"🔗 已准备分享链接: {share_link}")
    deps._reply_humanized_idle(tab, 0.08, 0.2, "发送回复前")
    return True, share_link, ""


def run_notify_dm_followup(
    *,
    tab,
    item,
    share_link,
    dm_message,
    dm_progress,
    task_key,
    row_snapshot,
    deps,
    mark_func=None,
    mark_stage_func=None,
):
    dm_handle = item.get("handle", "")
    dm_template_text = deps._sanitize_dm_message_text(dm_message)
    if not dm_template_text:
        dm_template_text = (deps.dm_message_templates[0] if deps.dm_message_templates else deps.DM_FOLLOWUP_TEXT)
    dm_template_text = deps._sanitize_dm_message_text(dm_template_text)

    dm_text_supplier = build_notify_dm_text_supplier(
        task_key=task_key,
        share_link=share_link,
        dm_template_text=dm_template_text,
        deps=deps,
        notify_state_facade=deps.notify_state_facade,
        mark_stage=mark_stage_func,
        generated_dm_text_cache=str(row_snapshot.get("notify_dm_text_generated", "") or "").strip(),
        generated_dm_meta_cache={
            "llm_used": bool(row_snapshot.get("notify_dm_llm_used", False)),
            "latency_ms": int(row_snapshot.get("notify_dm_llm_latency_ms", 0) or 0),
            "regen_attempt": int(row_snapshot.get("notify_dm_llm_regen_attempt", 0) or 0),
        },
    )

    slot_ok, slot_wait = deps._reserve_notify_dm_user_slot(dm_handle, task_key=task_key)
    if not slot_ok:
        return False, f"E_DM_USER_COOLDOWN: @{deps.normalize_handle(dm_handle)} 私信冷却中，请 {slot_wait:.1f}s 后重试", False

    if callable(mark_stage_func):
        mark_stage_func("dm_opening", extra={"notify_share_link": share_link}, save=True)
    return deps._run_dm_send_with_recovery(
        tab,
        dm_handle,
        share_link,
        dm_template_text,
        mark_func=mark_func,
        progress=dm_progress,
        dm_text_supplier=dm_text_supplier,
    )
