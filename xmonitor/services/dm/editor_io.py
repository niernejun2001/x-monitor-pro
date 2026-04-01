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
