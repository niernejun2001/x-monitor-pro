import datetime


def build_retry_payload(flow_err_code, flow_err_detail, retry_at, attempt, schedule_msg, status='retry_waiting'):
    return {
        'status': status,
        'msg': schedule_msg,
        'flow_stage': 'retry_waiting',
        'flow_error_code': flow_err_code,
        'flow_error_detail': flow_err_detail,
        'retry_at': retry_at,
        'retry_time': datetime.datetime.fromtimestamp(retry_at).strftime('%H:%M:%S') if retry_at else '',
        'attempt': attempt,
    }
