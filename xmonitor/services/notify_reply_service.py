import datetime
import time


def send_notification_reply(item, message, deps, dm_message=""):
    global_token = deps.global_token
    extract_status_id_from_notification_item = deps.extract_status_id_from_notification_item
    reply_action_lock = deps.reply_action_lock
    _throttle_reply_action_if_needed = deps._throttle_reply_action_if_needed
    _set_reply_flow_active = deps._set_reply_flow_active
    notify_state_facade = deps.notify_state_facade
    ensure_reply_work_tab = deps.ensure_reply_work_tab
    _prepare_reply_prompt_guard = deps._prepare_reply_prompt_guard
    log_to_ui = deps.log_to_ui
    _resolve_notify_resume_stage = deps._resolve_notify_resume_stage
    _normalize_dm_share_link = deps._normalize_dm_share_link
    _get_status_link_from_item = deps._get_status_link_from_item
    _notify_stage_at_least = deps._notify_stage_at_least
    _reply_humanized_idle = deps._reply_humanized_idle
    _prepare_notifications_view_impl = deps._prepare_notifications_view_impl
    _match_target_card_impl = deps._match_target_card_impl
    _send_reply_from_button_impl = deps._send_reply_from_button_impl
    _sanitize_dm_message_text = deps._sanitize_dm_message_text
    dm_message_templates = deps.dm_message_templates
    DM_FOLLOWUP_TEXT = deps.DM_FOLLOWUP_TEXT
    DM_LLM_REWRITE_ENABLED = deps.DM_LLM_REWRITE_ENABLED
    _generate_dm_text_with_llm = deps._generate_dm_text_with_llm
    _reserve_notify_dm_user_slot = deps._reserve_notify_dm_user_slot
    normalize_handle = deps.normalize_handle
    _run_dm_send_with_recovery = deps._run_dm_send_with_recovery
    DM_CLOSED_FALLBACK_REPLY_TEXT = deps.DM_CLOSED_FALLBACK_REPLY_TEXT
    _wait_document_ready = deps._wait_document_ready
    _is_unhandled_prompt_error = deps._is_unhandled_prompt_error
    _capture_runtime_diagnostic = deps._capture_runtime_diagnostic
    sys = __import__('sys')
    time = __import__('time')
    random = __import__('random')
    """针对通知记录发送回复。"""
    global last_reply_prepare_refresh_ts
    if not global_token.strip():
        return False, "请先配置并验证 auth_token 后再回复"

    status_id = extract_status_id_from_notification_item(item)
    if not status_id:
        return False, "该通知缺少可回复的状态ID（可能是兜底通知记录）"

    handle_hint = item.get("handle", "")
    task_key = str(item.get("key", "") or "").strip()

    with reply_action_lock:
        _throttle_reply_action_if_needed()
        _set_reply_flow_active(True)
        flow_started_at = time.perf_counter()
        stage_marks = {}

        def _mark(stage_name):
            stage_marks[stage_name] = time.perf_counter() - flow_started_at
            stage_map = {
                "match_card": "match_card",
                "prepare_share_link": "share_link_ready",
                "send_reply": "reply_sent",
                "open_dm": "dm_opening",
                "send_dm_link": "dm_link_sent",
                "send_dm_text": "dm_text_sent",
                "fallback_reply": "dm_closed_confirmed",
            }
            mapped = stage_map.get(str(stage_name or "").strip())
            if mapped:
                _mark_stage(mapped)

        def _mark_stage(stage_name, error="", retry_at=0.0, extra=None, save=False):
            if not task_key:
                return
            notify_state_facade.update_flow_state(
                task_key,
                stage=stage_name,
                error=error,
                retry_at=retry_at,
                extra=extra,
                save=save,
            )

        try:
            tab = ensure_reply_work_tab()
        except Exception as e:
            _set_reply_flow_active(False)
            return False, f"回复工作标签页初始化失败: {e}"

        try:
            _prepare_reply_prompt_guard(tab, "回复流程启动")
            log_to_ui("info", f"💬 开始执行通知回复(复用全局浏览器): {handle_hint} -> status {status_id}")
            _, row_live = notify_state_facade.find_pending_item_by_key(task_key)
            row_snapshot = dict(row_live or {})
            resume_stage = _resolve_notify_resume_stage(row_snapshot)
            if resume_stage == "reply_pending":
                _mark_stage("reply_pending", error="", extra={"notify_resume_stage": resume_stage})
            else:
                # 断点续跑场景保持原阶段，不回退到 reply_pending，避免重复发消息。
                _mark_stage(resume_stage, error="", retry_at=0.0, extra={"notify_resume_stage": resume_stage})

            saved_share_link = _normalize_dm_share_link(
                str(row_snapshot.get("notify_share_link", "") or "").strip(),
                status_id=status_id,
                status_handle=item.get("status_handle", "") or item.get("handle", ""),
                fallback_url=_get_status_link_from_item(item),
            )
            need_reply = not _notify_stage_at_least(resume_stage, "reply_sent")
            need_share = not _notify_stage_at_least(resume_stage, "share_link_ready")
            dm_progress = {
                "link_sent": _notify_stage_at_least(resume_stage, "dm_link_sent"),
                "text_sent": _notify_stage_at_least(resume_stage, "dm_text_sent"),
            }
            if dm_progress["text_sent"] and (not need_reply) and (not need_share):
                _mark_stage("done", error="", retry_at=0.0, save=True)
                return True, ""

            _reply_humanized_idle(tab, 0.18, 0.42, "回复流程启动")

            try:
                current_url = str(tab.url or "")
            except Exception:
                current_url = ""
            if "x.com/notifications" not in current_url:
                tab.get("https://x.com/notifications")
                _wait_document_ready(tab, timeout=5.0)
                _reply_humanized_idle(tab, 0.22, 0.52, "进入通知页后稳定等待")
            log_to_ui("debug", "💬 已进入通知页，准备定位目标通知卡片")
            try:
                tab.wait.ele_displayed('tag:article', timeout=5)
            except Exception:
                pass

            def _prepare_notifications_view(force_refresh=False):
                return _prepare_notifications_view_impl(tab, sys.modules[__name__], force_refresh=force_refresh)

            def _match_target_card():
                return _match_target_card_impl(tab, item, status_id, sys.modules[__name__])

            def _send_reply_from_button(target_reply_btn, target_score, reply_text):
                return _send_reply_from_button_impl(tab, target_reply_btn, target_score, reply_text, status_id, handle_hint, sys.modules[__name__])

            dm_handle = item.get("handle", "")
            dm_template_text = _sanitize_dm_message_text(dm_message)
            if not dm_template_text:
                dm_template_text = (dm_message_templates[0] if dm_message_templates else DM_FOLLOWUP_TEXT)
            dm_template_text = _sanitize_dm_message_text(dm_template_text)

            def _build_dm_text_supplier():
                def _supplier():
                    if not DM_LLM_REWRITE_ENABLED:
                        return True, dm_template_text, {
                            "error_code": "",
                            "error_detail": "",
                            "llm_used": False,
                            "latency_ms": 0,
                        }
                    _mark_stage(
                        "dm_text_generating",
                        error="",
                        extra={
                            "notify_share_link": share_link,
                            "notify_dm_template_text": dm_template_text,
                            "notify_dm_llm_used": True,
                        },
                        save=True,
                    )
                    ok_gen, dm_text_generated, meta = _generate_dm_text_with_llm(dm_template_text)
                    meta = meta or {}
                    if ok_gen:
                        notify_state_facade.update_flow_state(
                            task_key,
                            stage="dm_text_generating",
                            error="",
                            retry_at=0.0,
                            extra={
                                "notify_share_link": share_link,
                                "notify_dm_template_text": dm_template_text,
                                "notify_dm_text_generated": dm_text_generated,
                                "notify_dm_llm_used": bool(meta.get("llm_used", True)),
                                "notify_dm_llm_latency_ms": int(meta.get("latency_ms", 0) or 0),
                                "notify_dm_llm_regen_attempt": int(meta.get("regen_attempt", 1) or 1),
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
                    return ok_gen, dm_text_generated, meta

                return _supplier

            slot_ok, slot_wait = _reserve_notify_dm_user_slot(dm_handle, task_key=task_key)
            if not slot_ok:
                return False, f"E_DM_USER_COOLDOWN: @{normalize_handle(dm_handle)} 私信冷却中，请 {slot_wait:.1f}s 后重试"
            _mark_stage("dm_opening", extra={"notify_share_link": share_link}, save=True)
            ok_dm, dm_err, dm_closed, dm_tab = _run_dm_send_with_recovery(
                tab,
                dm_handle,
                share_link,
                dm_template_text,
                mark_func=_mark,
                progress=dm_progress,
                dm_text_supplier=_build_dm_text_supplier(),
            )
            if not ok_dm:
                if dm_closed:
                    _mark_stage("dm_closed_confirmed", extra={"notify_share_link": share_link}, save=True)
                    _mark("dm_open_failed")
                    log_to_ui("warn", "⚠️ 目标用户未开启私信，准备发送补充评论后结束私信流程")
                    try:
                        now_url = str(tab.url or "")
                    except Exception:
                        now_url = ""
                    if "x.com/notifications" not in now_url:
                        tab.get("https://x.com/notifications")
                        _wait_document_ready(tab, timeout=5.5)
                    _prepare_notifications_view(force_refresh=True)
                    fb_article, fb_reply_btn, fb_score, _, _, fb_match_err = _match_target_card()
                    if fb_match_err:
                        return False, f"用户不可私信，且补充评论失败: {fb_match_err}"
                    ok_fb, err_fb = _send_reply_from_button(fb_reply_btn, fb_score, DM_CLOSED_FALLBACK_REPLY_TEXT)
                    if not ok_fb:
                        return False, f"用户不可私信，且补充评论失败: {err_fb}"
                    _mark("fallback_reply")
                    total_cost = time.perf_counter() - flow_started_at
                    log_to_ui(
                        "debug",
                        f"⏱️ 回复流程耗时(私信关闭): 匹配{stage_marks.get('match_card', 0):.2f}s, "
                        f"链接{stage_marks.get('prepare_share_link', 0):.2f}s, "
                        f"首评{stage_marks.get('send_reply', 0):.2f}s, 补评{stage_marks.get('fallback_reply', 0):.2f}s, "
                        f"总计{total_cost:.2f}s"
                    )
                    log_to_ui("info", "💬 用户私信关闭，已发送补充评论并结束私信发送流程")
                    _mark_stage("done", save=True)
                    return True, ""
                return False, dm_err

            total_cost = time.perf_counter() - flow_started_at
            log_to_ui(
                "debug",
                f"⏱️ 回复流程耗时: 匹配{stage_marks.get('match_card', 0):.2f}s, "
                f"链接{stage_marks.get('prepare_share_link', 0):.2f}s, 首评{stage_marks.get('send_reply', 0):.2f}s, "
                f"开私信{stage_marks.get('open_dm', 0):.2f}s, 发链接{stage_marks.get('send_dm_link', 0):.2f}s, "
                f"发文案{stage_marks.get('send_dm_text', 0):.2f}s, 总计{total_cost:.2f}s"
            )
            _mark_stage("done", save=True)
            return True, ""
        except Exception as e:
            if _is_unhandled_prompt_error(e):
                diag_before = _capture_runtime_diagnostic(
                    tab,
                    "unhandled_prompt_before_clear",
                    err=e,
                    selectors=[
                        'css:[role="alertdialog"]',
                        'css:[role="dialog"]',
                        'css:[data-testid="confirmationSheetDialog"]',
                        'css:[data-testid="modal"]',
                        'css:[data-testid="reply"]',
                        'css:[data-testid="tweetButton"]',
                        'css:[data-testid="dm-composer-send-button"]',
                    ],
                    extra={"status_id": status_id, "handle_hint": handle_hint, "phase": "before_clear"}
                )
                _prepare_reply_prompt_guard(tab, "异常恢复")
                diag_after = _capture_runtime_diagnostic(
                    tab,
                    "unhandled_prompt_after_clear",
                    err=e,
                    selectors=[
                        'css:[role="alertdialog"]',
                        'css:[role="dialog"]',
                        'css:[data-testid="reply"]',
                        'css:[data-testid="tweetButton"]',
                        'css:[data-testid="dm-composer-send-button"]',
                    ],
                    extra={"status_id": status_id, "handle_hint": handle_hint, "phase": "after_clear"}
                )
                diag_ref = diag_before or diag_after
                if diag_ref:
                    return False, f"检测到未处理提示框，已自动清理，请重试一次（已截图留档: {diag_ref}）"
                return False, "检测到未处理提示框，已自动清理，请重试一次"
            _capture_runtime_diagnostic(
                tab,
                "send_notification_reply_exception",
                err=e,
                selectors=['tag:article', 'css:[data-testid="reply"]', 'css:[data-testid="dm-composer-send-button"]'],
                extra={"status_id": status_id, "handle_hint": handle_hint}
            )
            return False, f"回复发送失败: {e}"
        finally:
            # 无论成功/失败都回到通知页，且保持当前工作标签页不关闭，减少页面抖动
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
            _set_reply_flow_active(False)
