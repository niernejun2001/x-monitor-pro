import datetime
import random
import time
from flask import jsonify, request


def register_notify_routes(app, deps):
    @app.route('/api/notify_reply', methods=['POST'])
    def notify_reply():
        key = request.json.get('key', '').strip()
        message = request.json.get('message', '').strip()
        dm_message = request.json.get('dm_message', '').strip()
        if not key:
            return jsonify({'status': 'err', 'msg': 'missing key'}), 400
        if not message:
            return jsonify({'status': 'err', 'msg': 'missing message'}), 400

        _, target = deps.pending_results_repo.find_notify_by_key(key, copy_row=True)
        if not target:
            return jsonify({'status': 'err', 'msg': '通知记录不存在'}), 404

        updated = deps.pending_results_repo.update_notify_manual_reply(
            key,
            message,
            dm_message,
            dm_llm_enabled=deps.DM_LLM_REWRITE_ENABLED,
        )
        if not updated:
            return jsonify({'status': 'err', 'msg': '通知记录不存在'}), 404
        deps.save_state()

        target_handle = target.get('handle', '')
        allowed, budget_msg = deps._check_reply_failure_budget(target_handle)
        if not allowed:
            deps.log_to_ui('warn', f'⏸️ 触发失败预算熔断: {target_handle} - {budget_msg}')
            return jsonify({'status': 'err', 'msg': budget_msg}), 429

        try:
            base_attempt = int(target.get('notify_flow_attempt', 0) or 0)
        except Exception:
            base_attempt = 0
        cur_attempt = max(1, base_attempt + 1)
        deps.notify_state_facade.update_flow_state(
            key,
            stage='reply_pending',
            attempt=cur_attempt,
            error='',
            retry_at=0,
            extra={
                'notify_resume_stage': 'reply_pending',
                'notify_retry_reason': 'manual_notify_reply_execute',
                'notify_share_link': '',
            },
            save=True,
        )

        max_attempts = 1 + (max(0, int(deps.UNHANDLED_PROMPT_AUTO_RETRY)) if deps.headless_mode else 0)
        ok, err = False, '通知回复失败'
        for attempt in range(1, max_attempts + 1):
            ok, err = deps.send_notification_reply(target, message, dm_message=dm_message)
            if ok:
                break
            if deps._is_unhandled_prompt_error(err) and attempt < max_attempts:
                remaining = max_attempts - attempt
                deps.log_to_ui('warn', f'⚠️ 检测到未处理提示框，自动恢复后重试（剩余{remaining}次）')
                try:
                    recover_tab = deps.ensure_reply_work_tab(force_recreate=(attempt >= 2))
                    deps._prepare_reply_prompt_guard(recover_tab, f'自动恢复重试{attempt}')
                    try:
                        now_url = str(recover_tab.url or '')
                    except Exception:
                        now_url = ''
                    if 'x.com/notifications' not in now_url:
                        recover_tab.get('https://x.com/notifications')
                        deps._wait_document_ready(recover_tab, timeout=5.0)
                except Exception as recover_err:
                    deps.log_to_ui('warn', f'⚠️ 提示框自动恢复失败: {recover_err}')
                time.sleep(random.uniform(0.45, 1.1))
                continue
            break

        deps._record_reply_outcome(target_handle, ok, err if not ok else '')
        if not ok:
            flow_err_code, flow_err_detail = deps._split_flow_error(err)
            scheduled, retry_at, schedule_msg = deps.notify_state_facade.schedule_retry(
                key,
                err,
                attempt=cur_attempt,
                reason='manual_notify_reply',
                save=True,
            )
            deps.log_to_ui('warn', f'⚠️ 通知回复失败: {err}')
            if scheduled:
                return jsonify({
                    'status': 'retry_waiting',
                    'msg': schedule_msg,
                    'flow_stage': 'retry_waiting',
                    'flow_error_code': flow_err_code,
                    'flow_error_detail': flow_err_detail,
                    'retry_at': retry_at,
                    'retry_time': datetime.datetime.fromtimestamp(retry_at).strftime('%H:%M:%S'),
                    'attempt': cur_attempt,
                }), 202
            return jsonify({
                'status': 'err',
                'msg': f'{err}（{schedule_msg}）',
                'flow_stage': 'retry_waiting',
                'flow_error_code': flow_err_code,
                'flow_error_detail': flow_err_detail,
                'retry_at': 0,
                'retry_time': '',
                'attempt': cur_attempt,
            }), 500

        reply_time_text = datetime.datetime.now().strftime('%H:%M:%S')
        deps.notify_state_facade.mark_reply_success(key, message, dm_message, reply_time_text=reply_time_text, save=True)
        deps.log_to_ui('success', f'✅ 已发送通知回复: {target_handle} -> {message[:30]}')
        return jsonify({
            'status': 'ok',
            'reply_time': reply_time_text,
            'flow_stage': 'done',
            'retry_at': 0,
            'retry_time': '',
            'attempt': cur_attempt,
        })

    @app.route('/api/notify_retry', methods=['POST'])
    def notify_retry():
        key = str(request.json.get('key', '') or '').strip()
        if not key:
            return jsonify({'status': 'err', 'msg': 'missing key'}), 400
        _, row = deps.notify_state_facade.find_pending_item_by_key(key)
        if not row:
            return jsonify({'status': 'err', 'msg': '通知记录不存在'}), 404

        item = dict(row)
        if bool(item.get('notify_replied', False)):
            return jsonify({'status': 'ok', 'msg': '该任务已完成', 'flow_stage': 'done'})

        reply_text = str(item.get('notify_reply_text', '') or '').strip()
        dm_text = str(item.get('notify_dm_text', '') or '').strip()
        if not reply_text or not dm_text:
            return jsonify({'status': 'err', 'msg': '缺少回复或私信模板，请先在该行重新选择后点击回复'}), 400

        try:
            attempt = int(item.get('notify_flow_attempt', 0) or 0) + 1
        except Exception:
            attempt = 1
        resume_stage = deps._resolve_notify_resume_stage(item)
        deps.notify_state_facade.update_flow_state(
            key,
            stage='reply_pending',
            attempt=attempt,
            error='',
            retry_at=0,
            extra={
                'notify_resume_stage': resume_stage,
                'notify_retry_reason': 'manual_retry_execute',
            },
            save=True,
        )

        ok, err = deps.send_notification_reply(item, reply_text, dm_message=dm_text)
        deps._record_reply_outcome(item.get('handle', ''), ok, err if not ok else '')
        if ok:
            reply_time_text = datetime.datetime.now().strftime('%H:%M:%S')
            deps.notify_state_facade.mark_reply_success(key, reply_text, dm_text, reply_time_text=reply_time_text, save=True)
            return jsonify({
                'status': 'ok',
                'msg': '重试成功',
                'flow_stage': 'done',
                'reply_time': reply_time_text,
                'retry_at': 0,
                'retry_time': '',
                'attempt': attempt,
            })

        scheduled, retry_at, schedule_msg = deps.notify_state_facade.schedule_retry(
            key,
            err,
            attempt=attempt,
            reason='manual_retry_api',
            save=True,
        )
        flow_err_code, flow_err_detail = deps._split_flow_error(err)
        if scheduled:
            return jsonify({
                'status': 'retry_waiting',
                'msg': schedule_msg,
                'flow_stage': 'retry_waiting',
                'flow_error_code': flow_err_code,
                'flow_error_detail': flow_err_detail,
                'retry_at': retry_at,
                'retry_time': datetime.datetime.fromtimestamp(retry_at).strftime('%H:%M:%S'),
                'attempt': attempt,
            }), 202
        return jsonify({
            'status': 'err',
            'msg': f'{err}（{schedule_msg}）',
            'flow_stage': 'retry_waiting',
            'flow_error_code': flow_err_code,
            'flow_error_detail': flow_err_detail,
            'retry_at': 0,
            'retry_time': '',
            'attempt': attempt,
        }), 500
