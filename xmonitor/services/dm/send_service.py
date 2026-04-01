import random
import time

from xmonitor.services.dm.send_dom import DMSendDomHelper
from xmonitor.services.dm.send_support import (
    attempt_send_via_button,
    attempt_send_via_dom,
    attempt_send_via_enter,
    ensure_editor_text_stable,
)


def send_dm_message(tab, text, deps):
    if not text:
        return False, '空消息'

    editor_selectors = list(deps.DM_EDITOR_SELECTORS)
    send_btn_selectors = list(deps.DM_SEND_BUTTON_SELECTORS)
    dom = DMSendDomHelper(tab, deps, editor_selectors, send_btn_selectors)

    max_attempts = deps.DM_SEND_RETRY_HEADLESS if deps.headless_mode else deps.DM_SEND_RETRY_NORMAL
    last_err = ''
    dm_text = deps._sanitize_dm_message_text(text)
    link_only_mode = deps._is_link_only_message(dm_text)
    probes = deps._build_dm_message_probes(dm_text)

    session_state = deps._read_dm_session_state(tab, '')
    for attempt in range(1, max_attempts + 1):
        deps._throttle_dm_action_if_needed(f'私信发送尝试{attempt}')
        deps._prepare_reply_prompt_guard(tab, f'私信发送尝试{attempt}')
        deps._dm_humanized_idle(tab, 0.04, 0.16, f'私信发送尝试{attempt}')
        before_counts = {p: deps._count_dm_probe_occurrence(tab, p) for p in probes}
        before_counts['__snapshot'] = deps._get_dm_conversation_text(tab)
        before_counts['__sent_markers'] = deps._count_dm_sent_markers(tab)

        editor = dom.find_editor(rounds=2, timeout_each=1.4)
        if not editor:
            deps._handle_dm_passcode_prompt(tab)
            editor = dom.find_editor(rounds=2, timeout_each=1.6)
        if not editor:
            last_err = '未找到私信输入框'
            time.sleep(random.uniform(0.05, 0.12))
            continue
        if deps.DM_FORCE_COMPOSER_BINDING and not dom.editor_matches_bound_send(editor):
            last_err = 'E_DM_WRONG_COMPOSER_TARGET: 编辑器与当前会话发送按钮不在同一容器'
            deps._dm_humanized_idle(tab, 0.06, 0.16, '检测到输入框映射异常后等待')
            continue

        try:
            editor.click()
        except Exception:
            pass

        typed_ok = deps._humanized_type_dm_text(tab, editor, dm_text)
        if not typed_ok:
            typed_ok = deps._paste_dm_text_exact(tab, editor, dm_text)
        if not typed_ok:
            last_err = '输入私信内容失败'
            time.sleep(random.uniform(0.05, 0.12))
            continue
        if deps.DM_FORCE_COMPOSER_BINDING and not dom.editor_matches_bound_send(editor):
            last_err = 'E_DM_WRONG_COMPOSER_TARGET: 文本写入疑似落在上层浮层输入框'
            deps._dm_humanized_idle(tab, 0.06, 0.16, '检测到文本映射异常后等待')
            continue

        text_ok, text_err = ensure_editor_text_stable(tab, editor, dm_text, link_only_mode, deps, dom)
        if not text_ok:
            last_err = text_err
            continue

        deps._dm_humanized_idle(tab, 0.04, 0.12, '私信发送前')
        for send_attempt in (
            lambda: attempt_send_via_button(tab, editor, dm_text, link_only_mode, deps, dom, before_counts, probes),
            lambda: attempt_send_via_enter(tab, editor, dm_text, link_only_mode, deps, dom, before_counts, probes),
            lambda: attempt_send_via_dom(tab, editor, dm_text, link_only_mode, deps, dom, before_counts, probes),
        ):
            result = send_attempt()
            ok_finish, finish_err = result
            if ok_finish is None:
                continue
            if ok_finish:
                return True, ''
            last_err = finish_err
            if deps._is_dm_send_fallback_continuable_error(last_err):
                deps.log_headless_debug(f'私信发送尝试当前方法失败，继续下一个兜底路径: {last_err}')
                continue
            if deps.DM_ASSUME_SUCCESS_AFTER_CLICK and last_err in {
                '点击私信发送后输入框未清空',
                'DOM点击发送后输入框未清空',
            }:
                deps.log_to_ui('warn', '⚠️ 私信点击发送后状态不确定，但当前配置禁止按成功处理')
            break

        if not last_err:
            last_err = '未找到可点击的私信发送按钮（可能输入框内容被清空）'

        time.sleep(random.uniform(0.06, 0.16))
        deps._capture_runtime_diagnostic(
            tab,
            'send_dm_message_failed',
            err=last_err,
            selectors=editor_selectors + send_btn_selectors,
            extra={
                'max_attempts': max_attempts,
                'message_len': len(dm_text),
                'headless_mode': bool(deps.headless_mode),
                'dm_error_class': deps._classify_dm_error_text(last_err),
                'dm_url_ok': bool(session_state.get('url_ok')),
                'dm_conversation_ok': bool(session_state.get('conversation_ok')),
                'dm_editor_ok': bool(session_state.get('editor_ok')),
                'dm_send_btn_enabled': bool(session_state.get('send_button_enabled')),
            }
        )
    return False, last_err


def send_dm_message_with_retry(tab, text, handle='', deps=None):
    deps = deps or __import__('app')
    max_attempts = deps.DM_SEND_RETRY_HEADLESS if deps.headless_mode else deps.DM_SEND_RETRY_NORMAL
    last_err = '发送私信失败'
    handle_norm = deps.normalize_handle(handle)
    last_session_state = {}

    for attempt in range(1, max_attempts + 1):
        if handle_norm:
            session_state = deps._ensure_dm_session_ready_for_handle(tab, handle_norm, allow_reopen=True)
            last_session_state = dict(session_state or {})
            if not session_state.get('ready'):
                last_err = (
                    'E_DM_CONTEXT_LOST: 当前页面不在可发送私信会话上下文，'
                    f"url_ok={int(bool(session_state.get('url_ok')))}, "
                    f"conversation_ok={int(bool(session_state.get('conversation_ok')))}, "
                    f"editor_ok={int(bool(session_state.get('editor_ok')))}"
                )
                if attempt < max_attempts:
                    deps._dm_humanized_idle(tab, 0.22, 0.56, f'私信上下文恢复失败等待{attempt}')
                    continue
                break

        ok, err = send_dm_message(tab, text, deps)
        if ok:
            return True, ''
        last_err = str(err or last_err)
        deps.log_headless_debug(f'私信发送重试触发 attempt={attempt}/{max_attempts}, err={last_err}')
        if attempt >= max_attempts:
            break

        deps._prepare_reply_prompt_guard(tab, f'私信重试准备{attempt}')
        need_reopen = deps._is_dm_context_or_editor_error_text(last_err)
        if need_reopen and handle_norm:
            deps._dm_humanized_idle(tab, 0.08, 0.18, f'私信重试{attempt}重开编辑器前')
            deps._open_dm_editor_for_handle(tab, handle_norm)
        if deps._is_dm_soft_send_error_text(last_err):
            deps._dm_humanized_idle(tab, deps.DM_SOFT_RETRY_MIN_SEC, deps.DM_SOFT_RETRY_MAX_SEC, f'私信重试{attempt}快速间隔')
        else:
            deps._dm_humanized_idle(tab, 0.16, 0.42, f'私信重试{attempt}间隔')

    deps._capture_runtime_diagnostic(
        tab,
        'send_dm_with_retry_failed',
        err=last_err,
        selectors=[
            'css:textarea[data-testid="dm-composer-textarea"]',
            'css:[data-testid="dmComposerTextInput"]',
            'css:[data-testid="dm-composer-send-button"]',
            'css:[data-testid="dmComposerSendButton"]',
        ],
        extra={
            'handle': handle_norm,
            'max_attempts': max_attempts,
            'message_len': len(str(text or '')),
            'headless_mode': bool(deps.headless_mode),
            'dm_error_class': deps._classify_dm_error_text(last_err),
            'dm_url_ok': bool(last_session_state.get('url_ok')),
            'dm_conversation_ok': bool(last_session_state.get('conversation_ok')),
            'dm_editor_ok': bool(last_session_state.get('editor_ok')),
            'dm_send_btn_enabled': bool(last_session_state.get('send_button_enabled')),
        }
    )
    return False, last_err
