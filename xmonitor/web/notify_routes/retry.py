import datetime

from flask import jsonify, request

from .helpers import build_retry_payload


def _first_text(*values):
    for value in values:
        text = str(value or '').strip()
        if text:
            return text
    return ''


def _first_template(templates):
    for template in list(templates or []):
        text = str(template or '').strip()
        if text:
            return text
    return ''


def register_notify_retry_routes(app, deps):
    @app.route('/api/notify_retry', methods=['POST'])
    def notify_retry():
        payload = request.get_json(silent=True) or {}
        key = str(payload.get('key', '') or '').strip()
        if not key:
            return jsonify({'status': 'err', 'msg': 'missing key'}), 400
        _, row = deps.notify_state_facade.find_pending_item_by_key(key)
        if not row:
            return jsonify({'status': 'err', 'msg': '通知记录不存在'}), 404

        item = dict(row)
        if bool(item.get('notify_replied', False)):
            return jsonify({'status': 'ok', 'msg': '该任务已完成', 'flow_stage': 'done'})

        reply_text = _first_text(
            payload.get('message', ''),
            item.get('notify_reply_text', ''),
            _first_template(getattr(deps, 'notify_reply_templates', [])),
        )
        dm_text = _first_text(
            payload.get('dm_message', ''),
            item.get('notify_dm_text', ''),
            _first_template(getattr(deps, 'dm_message_templates', [])),
        )
        if not reply_text or not dm_text:
            return jsonify({'status': 'err', 'msg': '缺少回复或私信模板，请先在该行重新选择后点击回复'}), 400
        item['notify_reply_text'] = reply_text
        item['notify_dm_text'] = dm_text

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
                'notify_reply_text': reply_text,
                'notify_dm_text': dm_text,
                'notify_dm_text_generated': '',
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
            return jsonify(build_retry_payload(flow_err_code, flow_err_detail, retry_at, attempt, schedule_msg)), 202
        payload = build_retry_payload(flow_err_code, flow_err_detail, 0, attempt, f'{err}（{schedule_msg}）', status='err')
        return jsonify(payload), 500
