import random
import time


def humanized_type_dm_text(tab, editor, dm_text, idle_func, log_debug):
    text = str(dm_text or '')
    if not text:
        return False
    target = editor
    for selector in (
        'css:div[role="textbox"][contenteditable="true"]',
        'css:[contenteditable="true"]',
        'css:textarea',
    ):
        if target is not editor:
            break
        try:
            inner = editor.ele(selector, timeout=0)
            if inner and inner.states.is_displayed:
                target = inner
        except Exception:
            pass
    try:
        target.click()
    except Exception:
        pass
    idle_func(tab, 0.06, 0.22, '私信输入前')
    try:
        target.input(text, clear=True)
        log_debug(f'私信输入完成(整段模式, len={len(text)})')
        return True
    except Exception:
        return False


def paste_dm_text_exact(tab, editor, dm_text, idle_func, log_debug):
    text = str(dm_text or '')
    if not text:
        return False
    try:
        editor.click()
    except Exception:
        pass
    idle_func(tab, 0.04, 0.12, '私信粘贴前')
    try:
        ok = tab.run_js(
            """
            const root = arguments[0];
            const text = String(arguments[1] || '');
            if (!root) return false;
            const resolveTarget = (el) => {
              if (!el) return null;
              if (el.value !== undefined || el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
                return el;
              }
              const inner = el.querySelector(
                'div[role="textbox"][contenteditable="true"],[data-testid="dmComposerTextInput"] [contenteditable="true"],textarea[data-testid="dm-composer-textarea"],textarea'
              );
              if (inner) return inner;
              return null;
            };
            let el = resolveTarget(root);
            if (!el) return false;
            const dispatchInput = () => {
              try {
                el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText' }));
              } catch (e) {
                el.dispatchEvent(new Event('input', { bubbles: true }));
              }
              try { el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Enter', code: 'Enter' })); } catch (e) {}
              el.dispatchEvent(new Event('change', { bubbles: true }));
            };
            const setValue = (val) => {
              if (el.value !== undefined) {
                const proto = Object.getPrototypeOf(el);
                const desc = proto ? Object.getOwnPropertyDescriptor(proto, 'value') : null;
                if (desc && typeof desc.set === 'function') {
                  desc.set.call(el, val);
                } else {
                  el.value = val;
                }
              } else if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
                el.textContent = val;
              } else {
                el.textContent = val;
              }
              dispatchInput();
            };
            el.focus();
            setValue('');
            try {
              if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
                document.execCommand('insertText', false, text);
                dispatchInput();
              } else {
                setValue(text);
              }
            } catch (e) {
              setValue(text);
            }
            return true;
            """,
            editor,
            text,
        )
        if ok:
            log_debug(f'私信输入完成(粘贴模式, len={len(text)})')
            return True
    except Exception:
        pass
    try:
        editor.input(text, clear=True)
        log_debug(f'私信输入完成(input整段兜底, len={len(text)})')
        return True
    except Exception:
        return False


def refresh_dm_editor_state(tab, editor, dm_text):
    text = str(dm_text or '')
    if not text:
        return False
    try:
        return bool(tab.run_js(
            """
            const root = arguments[0];
            const text = String(arguments[1] || '');
            if (!root) return false;
            const resolveTarget = (el) => {
                if (!el) return null;
                if (el.value !== undefined || el.isContentEditable || el.getAttribute('contenteditable') === 'true') return el;
                return el.querySelector(
                    'div[role="textbox"][contenteditable="true"],[data-testid="dmComposerTextInput"] [contenteditable="true"],textarea[data-testid="dm-composer-textarea"],textarea'
                );
            };
            let el = resolveTarget(root);
            if (!el) return false;
            const dispatchInput = () => {
                try {
                    el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText'}));
                } catch (e) {
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                }
                el.dispatchEvent(new Event('change', {bubbles: true}));
            };
            const setValue = (val) => {
                if (el.value !== undefined) {
                    const proto = Object.getPrototypeOf(el);
                    const desc = proto ? Object.getOwnPropertyDescriptor(proto, 'value') : null;
                    if (desc && typeof desc.set === 'function') {
                        desc.set.call(el, val);
                    } else {
                        el.value = val;
                    }
                } else {
                    el.textContent = val;
                }
                dispatchInput();
            };
            el.focus();
            setValue(text + ' ');
            setValue(text);
            return true;
            """,
            editor,
            text,
        ))
    except Exception:
        return False


def poke_dm_editor_events(tab, editor):
    if not tab or not editor:
        return False
    try:
        return bool(tab.run_js(
            """
            const el = arguments[0];
            if (!el) return false;
            try { el.focus(); } catch (e) {}
            try {
              el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText' }));
            } catch (e) {
              el.dispatchEvent(new Event('input', { bubbles: true }));
            }
            try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
            return true;
            """,
            editor,
        ))
    except Exception:
        return False


def humanized_gap_between_dm_messages(tab, *, idle_func, humanize_multiplier_fn, min_sec, max_sec, log_ui, log_debug):
    idle_func(tab, 0.08, 0.26, '两条私信间')
    gap = random.uniform(min_sec, max_sec) * humanize_multiplier_fn()
    time.sleep(gap)
    log_ui('debug', f'📨 两条私信间隔 {gap:.2f}s')
    log_debug(f'两条私信间隔完成 {gap:.2f}s')


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
    return any(k in detail for k in network_hints) or code in {
        'E_DM_LLM_GENERATE_FAILED',
        'E_DM_LLM_TIMEOUT',
        'E_DM_LLM_NOT_READY',
    }
