import re


NOTIFY_FLOW_STAGE_ORDER = {
    "reply_pending": 10,
    "match_card": 20,
    "share_link_ready": 30,
    "reply_sent": 40,
    "dm_opening": 50,
    "dm_link_sent": 60,
    "dm_text_generating": 65,
    "dm_text_sent": 70,
    "dm_closed_confirmed": 80,
    "done": 90,
    "retry_waiting": 95,
}

NOTIFY_FLOW_DEFAULTS = {
    "notify_flow_stage": "",
    "notify_resume_stage": "",
    "notify_flow_error": "",
    "notify_flow_error_code": "",
    "notify_flow_error_detail": "",
    "notify_flow_attempt": 0,
    "notify_retry_at": 0.0,
    "notify_retry_time": "",
    "notify_flow_updated_at": 0.0,
    "notify_flow_updated_time": "",
    "notify_share_link": "",
    "notify_dm_text_generated": "",
    "notify_dm_llm_used": False,
    "notify_dm_llm_latency_ms": 0,
    "notify_dm_llm_regen_attempt": 0,
    "notify_dm_llm_error_code": "",
    "notify_dm_llm_error_detail": "",
}


def normalize_notify_flow_stage(stage):
    text = str(stage or "").strip().lower()
    return text if text in NOTIFY_FLOW_STAGE_ORDER else ""


def notify_stage_rank(stage):
    return int(NOTIFY_FLOW_STAGE_ORDER.get(normalize_notify_flow_stage(stage), 0))


def notify_stage_at_least(stage, baseline):
    return notify_stage_rank(stage) >= notify_stage_rank(baseline)


def resolve_notify_resume_stage(row_like):
    row = row_like if isinstance(row_like, dict) else {}
    stage = normalize_notify_flow_stage(row.get("notify_flow_stage", ""))
    resume_hint = normalize_notify_flow_stage(row.get("notify_resume_stage", ""))
    if stage == "retry_waiting":
        return resume_hint or "reply_pending"
    if resume_hint and notify_stage_rank(resume_hint) > notify_stage_rank(stage):
        return resume_hint
    return stage or "reply_pending"


def split_flow_error(error_text, default_code="E_REPLY_FAILED"):
    msg = str(error_text or "").strip()
    if not msg:
        return "", ""
    match = re.search(r"\b(E_[A-Z0-9_]+)\b", msg)
    if match:
        code = match.group(1).strip()
        detail = msg.replace(code, "", 1).strip(" :,-")
        return code, (detail or msg)
    return str(default_code or "E_REPLY_FAILED"), msg


def ensure_notify_flow_fields(row_like):
    row = row_like if isinstance(row_like, dict) else {}
    for key, value in NOTIFY_FLOW_DEFAULTS.items():
        row.setdefault(key, value)
    return row
