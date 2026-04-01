from xmonitor.services.support.state_payload import build_template_payload

_TEMPLATE_LIMITS = {
    'reply': 180,
    'dm': 4000,
}

_TEMPLATE_LABELS = {
    'reply': '评论回复',
    'dm': '私信',
}


class TemplateAdminError(ValueError):
    pass


def get_template_list_and_limit(deps, template_type):
    template_type = str(template_type or '').strip().lower()
    if template_type == 'reply':
        return deps.notify_reply_templates, _TEMPLATE_LIMITS['reply']
    if template_type == 'dm':
        return deps.dm_message_templates, _TEMPLATE_LIMITS['dm']
    return None, 0


def _template_label(template_type):
    return _TEMPLATE_LABELS.get(template_type, '模板')


def _validate_template_content(content, max_len):
    content = str(content or '').strip()
    if not content:
        raise TemplateAdminError('模板内容不能为空')
    if len(content) > int(max_len or 0):
        raise TemplateAdminError(f'模板内容过长，最多 {int(max_len)} 字')
    return content


def add_template(deps, template_type, content):
    templates, max_len = get_template_list_and_limit(deps, template_type)
    if templates is None:
        raise TemplateAdminError('模板类型不支持')
    content = _validate_template_content(content, max_len)
    with deps.data_lock:
        templates.append(content)
    deps.save_state()
    deps.log_to_ui('info', f'📝 已添加{_template_label(template_type)}模板')
    payload = {'status': 'ok'}
    payload.update(build_template_payload(deps))
    return payload


def update_template(deps, template_type, index, content):
    templates, max_len = get_template_list_and_limit(deps, template_type)
    if templates is None:
        raise TemplateAdminError('模板类型不支持')
    try:
        index = int(index)
    except Exception as exc:
        raise TemplateAdminError('模板索引无效') from exc
    if index < 0 or index >= len(templates):
        raise TemplateAdminError('模板索引无效')
    content = _validate_template_content(content, max_len)
    with deps.data_lock:
        templates[index] = content
    deps.save_state()
    deps.log_to_ui('info', f'📝 已更新{_template_label(template_type)}模板')
    payload = {'status': 'ok'}
    payload.update(build_template_payload(deps))
    return payload


def delete_template(deps, template_type, index):
    templates, _ = get_template_list_and_limit(deps, template_type)
    if templates is None:
        raise TemplateAdminError('模板类型不支持')
    try:
        index = int(index)
    except Exception as exc:
        raise TemplateAdminError('模板索引无效') from exc
    if index < 0 or index >= len(templates):
        raise TemplateAdminError('模板索引无效')
    with deps.data_lock:
        templates.pop(index)
    deps.save_state()
    deps.log_to_ui('info', f'📝 已删除{_template_label(template_type)}模板')
    payload = {'status': 'ok'}
    payload.update(build_template_payload(deps))
    return payload
