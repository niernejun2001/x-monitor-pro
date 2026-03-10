import time


class NotifyReplyProgressTracker:
    STAGE_MAP = {
        "match_card": "match_card",
        "prepare_share_link": "share_link_ready",
        "send_reply": "reply_sent",
        "open_dm": "dm_opening",
        "send_dm_link": "dm_link_sent",
        "send_dm_text": "dm_text_sent",
        "fallback_reply": "dm_closed_confirmed",
    }

    def __init__(self, task_key, flow_started_at, notify_state_facade):
        self.task_key = str(task_key or "").strip()
        self.flow_started_at = float(flow_started_at)
        self.notify_state_facade = notify_state_facade
        self.stage_marks = {}

    def mark(self, stage_name):
        self.stage_marks[stage_name] = time.perf_counter() - self.flow_started_at
        mapped = self.STAGE_MAP.get(str(stage_name or "").strip())
        if mapped:
            self.mark_stage(mapped)

    def mark_stage(self, stage_name, error="", retry_at=0.0, extra=None, save=False):
        if not self.task_key:
            return
        self.notify_state_facade.update_flow_state(
            self.task_key,
            stage=stage_name,
            error=error,
            retry_at=retry_at,
            extra=extra,
            save=save,
        )


def build_notify_dm_text_supplier(
    *,
    task_key,
    share_link,
    dm_template_text,
    deps,
    notify_state_facade,
    mark_stage,
    generated_dm_text_cache="",
    generated_dm_meta_cache=None,
):
    cache = {
        "text": str(generated_dm_text_cache or "").strip(),
        "meta": dict(generated_dm_meta_cache or {}),
    }

    def _supplier():
        if cache["text"]:
            return True, cache["text"], {
                "error_code": "",
                "error_detail": "",
                "llm_used": bool(cache["meta"].get("llm_used", True)),
                "latency_ms": int(cache["meta"].get("latency_ms", 0) or 0),
                "regen_attempt": int(cache["meta"].get("regen_attempt", 0) or 0),
                "cached": True,
            }
        if not deps.DM_LLM_REWRITE_ENABLED:
            return True, dm_template_text, {
                "error_code": "",
                "error_detail": "",
                "llm_used": False,
                "latency_ms": 0,
            }
        mark_stage(
            "dm_text_generating",
            error="",
            extra={
                "notify_share_link": share_link,
                "notify_dm_template_text": dm_template_text,
                "notify_dm_llm_used": True,
            },
            save=True,
        )
        ok_gen, dm_text_generated, meta = deps._generate_dm_text_with_llm(dm_template_text)
        meta = meta or {}
        if ok_gen:
            cache["text"] = deps._sanitize_dm_message_text(dm_text_generated)
            cache["meta"] = {
                "llm_used": bool(meta.get("llm_used", True)),
                "latency_ms": int(meta.get("latency_ms", 0) or 0),
                "regen_attempt": int(meta.get("regen_attempt", 1) or 1),
            }
            notify_state_facade.update_flow_state(
                task_key,
                stage="dm_text_generating",
                error="",
                retry_at=0.0,
                extra={
                    "notify_share_link": share_link,
                    "notify_dm_template_text": dm_template_text,
                    "notify_dm_text_generated": cache["text"],
                    "notify_dm_llm_used": bool(cache["meta"].get("llm_used", True)),
                    "notify_dm_llm_latency_ms": int(cache["meta"].get("latency_ms", 0) or 0),
                    "notify_dm_llm_regen_attempt": int(cache["meta"].get("regen_attempt", 1) or 1),
                    "notify_dm_llm_error_code": "",
                    "notify_dm_llm_error_detail": "",
                },
                save=True,
            )
        else:
            err_code = str(meta.get("error_code", "E_DM_LLM_GENERATE_FAILED") or "E_DM_LLM_GENERATE_FAILED")
            err_detail = str(meta.get("error_detail", "") or "第二条私信文案生成失败")
            notify_state_facade.update_flow_state(
                task_key,
                stage="dm_text_generating",
                error=f"{err_code}: {err_detail}",
                retry_at=0.0,
                extra={
                    "notify_share_link": share_link,
                    "notify_dm_template_text": dm_template_text,
                    "notify_dm_llm_used": bool(meta.get("llm_used", True)),
                    "notify_dm_llm_latency_ms": int(meta.get("latency_ms", 0) or 0),
                    "notify_dm_llm_error_code": err_code,
                    "notify_dm_llm_error_detail": err_detail,
                },
                save=True,
            )
        return ok_gen, (cache["text"] if ok_gen else dm_text_generated), meta

    return _supplier
