def send_reply_from_button(tab, target_reply_btn, target_score, reply_text, status_id, handle_hint, deps):
    deps._prepare_reply_prompt_guard(tab, '点击回复入口前')
    deps._reply_humanized_idle(tab, 0.16, 0.4, '点击回复入口前')
    try:
        tab.run_js('arguments[0].scrollIntoView({block:"center"});', target_reply_btn)
    except Exception:
        pass
    clicked_reply, click_reply_err = deps._click_with_prompt_guard(tab, target_reply_btn, '点击左下角回复按钮')
    if not clicked_reply:
        return False, click_reply_err
    deps.log_to_ui('debug', f'💬 已点击通知卡片左下角回复按钮(score={target_score})，等待回复输入框')
    deps._reply_humanized_idle(tab, 0.22, 0.56, '等待回复输入框弹出')
    editor_selectors = [
        'css:[data-testid="tweetTextarea_0"] [role="textbox"]',
        'css:[data-testid="tweetTextarea_0"] [contenteditable="true"]',
        'css:[data-testid="tweetTextarea_0"] div[contenteditable="true"]',
        'css:[data-testid="tweetTextarea_0"]',
        'css:div[role="dialog"] div[role="textbox"][contenteditable="true"]',
        'css:div[role="textbox"][contenteditable="true"]',
    ]
    editor = deps._wait_first_visible(tab, editor_selectors, timeout=3.0, poll=0.1)
    if not editor:
        deps._reply_humanized_idle(tab, 0.12, 0.28, '回复输入框二次唤醒')
        try:
            deps._click_with_prompt_guard(tab, target_reply_btn, '点击左下角回复按钮(二次唤醒)')
        except Exception:
            pass
        editor = deps._wait_first_visible(tab, editor_selectors, timeout=3.8, poll=0.1)
    if not editor:
        deps._capture_runtime_diagnostic(
            tab,
            'reply_editor_not_found',
            err='未弹出回复输入框',
            selectors=editor_selectors + [
                'css:[data-testid="reply"]',
                'css:[role="dialog"]',
                'css:[data-testid="sheetDialog"]',
            ],
            extra={
                'status_id': status_id,
                'handle_hint': handle_hint,
                'target_score': target_score,
            }
        )
        return False, '未弹出回复输入框'

    def _read_reply_editor_text():
        try:
            val = tab.run_js(
                """
                const el = arguments[0];
                if (!el) return '';
                if (el.value !== undefined) return String(el.value || '');
                return String(el.innerText || el.textContent || '');
                """,
                editor,
            )
            return str(val or '')
        except Exception:
            return ''

    def _reply_input_stable(expected_text):
        expected_norm = deps._normalize_text_for_compare(expected_text)
        current_norm = deps._normalize_text_for_compare(_read_reply_editor_text())
        if not expected_norm:
            return bool(current_norm)
        if not current_norm:
            return False
        if current_norm == expected_norm:
            return True
        if expected_norm in current_norm or current_norm in expected_norm:
            return True
        return False

    typed_ok = False
    deps._prepare_reply_prompt_guard(tab, '填充回复内容前')
    deps._reply_humanized_idle(tab, 0.14, 0.36, '填充回复内容前')
    try:
        editor.click()
    except Exception:
        pass
    try:
        editor.input(reply_text, clear=True)
        typed_ok = True
    except Exception:
        try:
            tab.run_js(
                """
                const el = arguments[0];
                const text = arguments[1];
                el.focus();
                if (el.textContent !== undefined) el.textContent = '';
                document.execCommand('insertText', false, text);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                """,
                editor,
                reply_text,
            )
            typed_ok = True
        except Exception:
            typed_ok = False
    if not typed_ok:
        return False, '输入回复内容失败'
    if not _reply_input_stable(reply_text):
        try:
            tab.run_js(
                """
                const el = arguments[0];
                const text = String(arguments[1] || '');
                if (!el) return false;
                el.focus();
                try {
                  if (el.value !== undefined) {
                    el.value = text;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                  }
                } catch (e) {}
                try {
                  const sel = window.getSelection();
                  const range = document.createRange();
                  range.selectNodeContents(el);
                  sel.removeAllRanges();
                  sel.addRange(range);
                } catch (e) {}
                try {
                  document.execCommand('insertText', false, text);
                } catch (e) {
                  el.textContent = text;
                }
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
                """,
                editor,
                reply_text,
            )
        except Exception:
            pass
    editor_now_text = _read_reply_editor_text()
    if not _reply_input_stable(reply_text):
        deps._capture_runtime_diagnostic(
            tab,
            'reply_input_not_stable',
            err='回复框填充后文本未稳定',
            selectors=editor_selectors + [
                'css:[data-testid="tweetButton"]',
                'css:button[data-testid="tweetButton"]',
                'css:[data-testid="tweetButtonInline"]',
                'css:button[data-testid="tweetButtonInline"]',
            ],
            extra={
                'status_id': status_id,
                'handle_hint': handle_hint,
                'target_score': target_score,
                'expected_len': len(deps._normalize_text_for_compare(reply_text)),
                'current_len': len(deps._normalize_text_for_compare(editor_now_text)),
                'current_preview': deps._normalize_text_for_compare(editor_now_text)[:180],
            }
        )
        return False, f'回复输入后文本未生效(当前长度={len(deps._normalize_text_for_compare(editor_now_text))})'
    deps.log_to_ui('debug', f'💬 已填充回复内容(len={len(deps._normalize_text_for_compare(editor_now_text))})')
    deps._reply_humanized_idle(tab, 0.1, 0.26, '回复输入后等待按钮激活')
    send_selectors = [
        'css:[data-testid="tweetButton"]',
        'css:button[data-testid="tweetButton"]',
        'css:[data-testid="tweetButtonInline"]',
    ]
    send_btn = deps._wait_first_actionable(tab, send_selectors, timeout=1.4, poll=0.08)
    if not send_btn:
        try:
            tab.run_js(
                """
                const el = arguments[0];
                const text = String(arguments[1] || '');
                if (!el) return;
                el.focus();
                if (el.textContent !== undefined) el.textContent = text + ' ';
                el.dispatchEvent(new Event('input', {bubbles: true}));
                if (el.textContent !== undefined) el.textContent = text;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                """,
                editor,
                reply_text,
            )
        except Exception:
            pass
        deps._reply_humanized_idle(tab, 0.08, 0.22, '回复发送按钮二次等待')
        send_btn = deps._wait_first_actionable(tab, send_selectors, timeout=1.2, poll=0.08)
    if not send_btn:
        try:
            clicked_inline = tab.run_js(
                """
                const editor = arguments[0];
                if (!editor) return false;
                const isVisible = (el) => {
                  if (!el) return false;
                  const st = window.getComputedStyle(el);
                  if (!st) return false;
                  if (st.display === 'none' || st.visibility === 'hidden') return false;
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                };
                const root = editor.closest('[role="dialog"],section,main') || document;
                const selectors = [
                  '[data-testid="tweetButton"]',
                  'button[data-testid="tweetButton"]',
                  '[data-testid="tweetButtonInline"]',
                  'button[data-testid="tweetButtonInline"]',
                  'button[aria-label*="回复"]',
                  'button[aria-label*="Reply"]'
                ];
                for (const s of selectors) {
                  const nodes = Array.from(root.querySelectorAll(s));
                  for (const n of nodes) {
                    if (!isVisible(n)) continue;
                    if (n.disabled || n.getAttribute('aria-disabled') === 'true') continue;
                    try { n.click(); return true; } catch (e) {}
                  }
                }
                return false;
                """,
                editor,
            )
            if clicked_inline:
                send_btn = True
        except Exception:
            pass
    if not send_btn:
        return False, '回复发送按钮未激活'
    if send_btn is True:
        clicked_send, click_send_err = True, ''
    else:
        clicked_send, click_send_err = deps._click_with_prompt_guard(tab, send_btn, '点击右下角回复按钮')
    if not clicked_send:
        return False, click_send_err or '点击回复发送按钮失败'
    deps.log_to_ui('debug', '💬 已点击右下角回复按钮')
    deps._reply_humanized_idle(tab, 0.16, 0.38, '回复发送后等待')
    return True, ''
