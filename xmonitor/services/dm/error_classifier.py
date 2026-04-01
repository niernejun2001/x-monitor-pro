def is_dm_closed_error_text(dm_err_text):
    text = str(dm_err_text or '')
    return any(k in text for k in [
        '不可私信',
        '未开放私信',
        '无法接收私信',
        '无法向该用户发送私信',
        '不能给该用户发私信',
        '当前不可私信',
        '资料页无私信入口',
        'cannot send direct messages',
        "can't be messaged",
        'unable to message',
    ])


def is_dm_soft_send_error_text(err_text):
    text = str(err_text or '')
    if not text:
        return False
    keywords = [
        '发送按钮未出现',
        '未找到可点击的私信发送按钮',
        '输入后文本未稳定写入编辑器',
        '输入后链接状态未稳定写入编辑器',
        '点击私信发送后输入框未清空',
        'DOM点击发送后输入框未清空',
        'Enter兜底未确认发送',
        '输入私信内容失败',
    ]
    return any(k in text for k in keywords)


def is_dm_send_fallback_continuable_error(err_text):
    text = str(err_text or '')
    if not text:
        return False
    continuable_keywords = [
        'E_DM_SEND_BUTTON_CLICK',
        'click failed',
        'cross world',
        'same JavaScript world',
        '点击私信发送按钮失败',
    ]
    return any(k in text for k in continuable_keywords)


def is_dm_context_or_editor_error_text(err_text):
    text = str(err_text or '')
    if not text:
        return False
    keywords = [
        '未找到私信输入框',
        'E_DM_CONTEXT_LOST',
        '当前页面不在私信上下文',
        '当前页面不在可发送私信会话上下文',
        '打开私信失败',
        '未打开私信输入框',
        'E_DM_EDITOR_NOT_FOUND',
        'E_DM_WRONG_COMPOSER_TARGET',
        '映射异常',
    ]
    return any(k in text for k in keywords)


def is_dm_context_url(url_text):
    low = str(url_text or '').lower()
    return ('/messages' in low) or ('/i/chat/' in low)


def classify_dm_error_text(err_text):
    text = str(err_text or '')
    if not text:
        return 'unknown'
    if is_dm_closed_error_text(text):
        return 'closed'
    if is_dm_soft_send_error_text(text):
        return 'soft_send'
    if is_dm_context_or_editor_error_text(text):
        return 'context'
    return 'unknown'


def is_dm_llm_fallback_allowed(err_code, err_detail):
    code = str(err_code or '').strip().upper()
    detail = str(err_detail or '').strip().lower()
    if not code.startswith('E_DM_LLM_'):
        return False
    if code in {'E_DM_LLM_TEMPLATE_EMPTY', 'E_DM_TEXT_EMPTY'}:
        return False
    safe_validation_codes = {
        'E_DM_LLM_GENERATE_FAILED',
        'E_DM_LLM_TIMEOUT',
        'E_DM_LLM_NOT_READY',
        'E_DM_LLM_COPY_PHRASE',
        'E_DM_LLM_TOO_SIMILAR',
        'E_DM_LLM_DUPLICATE_TEXT',
        'E_DM_LLM_SUBJECT_INVERTED',
        'E_DM_LLM_PROTECTED_LITERAL_CHANGED',
        'E_DM_LLM_EMPTY_OUTPUT',
    }
    if code in safe_validation_codes:
        return True
    network_hints = [
        'no route to host',
        'dial tcp',
        'timed out',
        'timeout',
        'connection refused',
        'temporarily unavailable',
        'http 400',
        'http 401',
        'http 403',
        'http 404',
        'http 429',
        'http 500',
        'http 502',
        'http 503',
        'http 504',
    ]
    return any(k in detail for k in network_hints)
