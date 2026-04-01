import random
import re
import time


def _get_passcode_digits(deps):
    digits = re.sub(r"\D+", "", str(getattr(deps, 'DM_PASSCODE', '') or ''))
    if len(digits) < 4:
        return ''
    return digits[:8]


def _mark_passcode_warmed(deps, warmed=True):
    with deps.dm_passcode_lock:
        deps.dm_passcode_warmed = bool(warmed)


def handle_dm_passcode_prompt(tab, deps):
    """处理 X 私信 Enter Passcode 页面。成功通过后返回 True。"""
    if not tab:
        return False

    passcode_digits = _get_passcode_digits(deps)
    if len(passcode_digits) < 4:
        return False

    def _is_passcode_page():
        def _is_visible_passcode_ui():
            try:
                state = tab.run_js(
                    """
                    const isVisible = (el) => {
                      if (!el) return false;
                      const st = window.getComputedStyle(el);
                      if (!st) return false;
                      if (st.display === 'none' || st.visibility === 'hidden') return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width > 0 && rect.height > 0;
                    };
                    const norm = (s) => String(s || '').replace(/\\s+/g, ' ').trim().toLowerCase();

                    const nodes = Array.from(document.querySelectorAll('h1,h2,h3,p,span,div,button,a'));
                    let hasEnter = false;
                    let hasForgot = false;
                    for (const el of nodes) {
                      if (!isVisible(el)) continue;
                      const txt = norm(el.innerText || el.textContent || '');
                      if (!txt) continue;
                      if (txt.includes('enter passcode') || txt.includes('输入口令') || txt.includes('输入密码')) {
                        hasEnter = true;
                      }
                      if (txt.includes('forgot passcode') || txt.includes('忘记口令') || txt.includes('忘记密码')) {
                        hasForgot = true;
                      }
                      if (hasEnter && hasForgot) break;
                    }

                    const inputCandidates = Array.from(document.querySelectorAll(
                      'input[type="password"],input[type="tel"],input[inputmode="numeric"],input[autocomplete="one-time-code"],input[maxlength="1"],[data-testid*="passcode"] input,[data-testid*="pin"] input'
                    ));
                    const visibleInputs = inputCandidates.filter((el) => isVisible(el) && !el.disabled).length;
                    const allInputs = inputCandidates.filter((el) => !el.disabled).length;

                    return {
                      visible: Boolean(hasEnter && (hasForgot || visibleInputs >= 1 || allInputs >= 4)),
                      hasEnter: Boolean(hasEnter),
                      hasForgot: Boolean(hasForgot),
                      visibleInputs: Number(visibleInputs),
                      allInputs: Number(allInputs),
                    };
                    """
                ) or {}
                return bool(state.get('visible', False))
            except Exception:
                return False

        try:
            now_url = str(tab.url or '').lower()
        except Exception:
            now_url = ''
        if '/i/chat/pin/recovery' in now_url or '/i/chat/pin' in now_url:
            return True
        return _is_visible_passcode_ui()

    def _wait_passcode_cleared(timeout_sec=8.6):
        deadline = time.time() + max(1.0, float(timeout_sec))
        while time.time() < deadline:
            deps._wait_document_ready(tab, timeout=1.2)
            if not _is_passcode_page():
                return True
            time.sleep(random.uniform(0.18, 0.36))
        return False

    def _fallback_type_passcode_via_body():
        """兜底：向当前焦点逐位输入数字，兼容圆圈口令 UI。"""
        try:
            body = tab.ele('tag:body', timeout=0.8)
        except Exception:
            body = None
        if not body:
            return False
        typed = 0
        for ch in passcode_digits:
            if not ch.isdigit():
                continue
            try:
                body.input(ch, clear=False)
                typed += 1
            except Exception:
                try:
                    tab.run_js(
                        """
                        const d = String(arguments[0] || '');
                        const t = document.activeElement || document.body;
                        if (!t) return false;
                        const ev = { key: d, code: 'Digit' + d, which: Number(d), keyCode: Number(d), bubbles: true };
                        try { t.dispatchEvent(new KeyboardEvent('keydown', ev)); } catch (e) {}
                        try { t.dispatchEvent(new KeyboardEvent('keypress', ev)); } catch (e) {}
                        try {
                          if (t.isContentEditable || t.getAttribute('contenteditable') === 'true') {
                            document.execCommand('insertText', false, d);
                          } else if (t.value !== undefined) {
                            t.value = String(t.value || '') + d;
                            t.dispatchEvent(new Event('input', { bubbles: true }));
                            t.dispatchEvent(new Event('change', { bubbles: true }));
                          }
                        } catch (e) {}
                        try { t.dispatchEvent(new KeyboardEvent('keyup', ev)); } catch (e) {}
                        return true;
                        """,
                        ch,
                    )
                    typed += 1
                except Exception:
                    continue
            time.sleep(random.uniform(0.08, 0.22))
        return typed >= 4

    def _fill_passcode_once():
        try:
            result = tab.run_js(
                """
                const code = String(arguments[0] || '');
                const isVisible = (el) => {
                    if (!el) return false;
                    const st = window.getComputedStyle(el);
                    if (!st) return false;
                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };
                const dispatchInput = (el) => {
                    if (!el) return;
                    try {
                        el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText' }));
                    } catch (e) {
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                };
                const setValue = (el, val) => {
                    if (!el) return;
                    el.focus();
                    if (el.value !== undefined) {
                        const proto = Object.getPrototypeOf(el);
                        const desc = proto ? Object.getOwnPropertyDescriptor(proto, 'value') : null;
                        if (desc && typeof desc.set === 'function') {
                            desc.set.call(el, val);
                        } else {
                            el.value = val;
                        }
                    } else if (el.textContent !== undefined) {
                        el.textContent = val;
                    }
                    dispatchInput(el);
                };

                const inputSelectors = [
                    'input[type="password"]',
                    'input[type="tel"]',
                    'input[inputmode="numeric"]',
                    'input[autocomplete="one-time-code"]',
                    'input[name*="passcode"]',
                    'input[name*="pin"]',
                    '[data-testid*="passcode"] input',
                    '[data-testid*="Passcode"] input',
                    '[data-testid*="pin"] input',
                    '[data-testid*="Pin"] input',
                ];
                const nodes = [];
                const allInputs = [];
                const seen = new Set();
                for (const s of inputSelectors) {
                    for (const el of Array.from(document.querySelectorAll(s))) {
                        if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                        if (!seen.has(el)) allInputs.push(el);
                        if (!isVisible(el)) continue;
                        if (seen.has(el)) continue;
                        seen.add(el);
                        nodes.push(el);
                    }
                }

                let filled = 0;
                const singleInputs = (nodes.length ? nodes : allInputs).filter((el) => {
                    const ml = Number(el.maxLength || el.getAttribute('maxlength') || 0);
                    return ml === 1;
                });
                if (singleInputs.length >= 4) {
                    for (let i = 0; i < Math.min(code.length, singleInputs.length); i += 1) {
                        setValue(singleInputs[i], code[i]);
                    }
                    filled = Math.min(code.length, singleInputs.length);
                } else if (nodes.length > 0) {
                    setValue(nodes[0], code);
                    filled = code.length;
                } else if (allInputs.length > 0) {
                    setValue(allInputs[0], code);
                    filled = code.length;
                }

                if (filled < 4) {
                    const clickDigitBtn = (digit) => {
                        const directSelectors = [
                            `button[aria-label="${digit}"]`,
                            `[role="button"][aria-label="${digit}"]`,
                            `button[data-value="${digit}"]`,
                            `[role="button"][data-value="${digit}"]`,
                        ];
                        for (const s of directSelectors) {
                            const cands = Array.from(document.querySelectorAll(s));
                            for (const el of cands) {
                                if (!isVisible(el)) continue;
                                if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                                try { el.click(); } catch (e) {}
                                return true;
                            }
                        }

                        const allBtn = Array.from(document.querySelectorAll('button, [role="button"]'));
                        for (const el of allBtn) {
                            if (!isVisible(el)) continue;
                            if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                            const txt = String(el.innerText || el.textContent || '').trim();
                            const aria = String(el.getAttribute('aria-label') || '').trim();
                            const title = String(el.getAttribute('title') || '').trim();
                            if (txt === digit || aria === digit || title === digit) {
                                try { el.click(); } catch (e) {}
                                return true;
                            }
                        }
                        return false;
                    };

                    let keypadClicked = 0;
                    for (const ch of code.split('')) {
                        if (!/\\d/.test(ch)) continue;
                        if (clickDigitBtn(ch)) keypadClicked += 1;
                    }
                    if (keypadClicked >= 4) filled = Math.max(filled, keypadClicked);
                }

                if (filled < 4) {
                    const focusSelectors = [
                        '[data-testid*="passcode"] input',
                        '[data-testid*="Passcode"] input',
                        '[data-testid*="passcode"]',
                        '[data-testid*="Passcode"]',
                        '[data-testid*="pin"] input',
                        '[data-testid*="Pin"] input',
                        '[data-testid*="pin"]',
                        '[data-testid*="Pin"]',
                        'input[inputmode="numeric"]',
                        'input[type="tel"]',
                        'main',
                        'body'
                    ];
                    let focusEl = null;
                    for (const s of focusSelectors) {
                        const cands = Array.from(document.querySelectorAll(s));
                        for (const el of cands) {
                            if (!el) continue;
                            if (!isVisible(el) && s !== 'body') continue;
                            focusEl = el;
                            break;
                        }
                        if (focusEl) break;
                    }
                    try { if (focusEl) focusEl.click(); } catch (e) {}
                    try { if (focusEl) focusEl.focus(); } catch (e) {}

                    const sendDigit = (digit) => {
                        const target = document.activeElement || focusEl || document.body;
                        if (!target) return;
                        const evInit = { key: digit, code: 'Digit' + digit, which: Number(digit), keyCode: Number(digit), bubbles: true };
                        try { target.dispatchEvent(new KeyboardEvent('keydown', evInit)); } catch (e) {}
                        try { target.dispatchEvent(new KeyboardEvent('keypress', evInit)); } catch (e) {}
                        if (target.value !== undefined) {
                            const cur = String(target.value || '');
                            setValue(target, cur + digit);
                        } else if (target.isContentEditable || target.getAttribute('contenteditable') === 'true') {
                            try {
                                document.execCommand('insertText', false, digit);
                            } catch (e) {
                                target.textContent = String(target.textContent || '') + digit;
                            }
                            dispatchInput(target);
                        } else {
                            try {
                                document.dispatchEvent(new KeyboardEvent('keydown', evInit));
                                document.dispatchEvent(new KeyboardEvent('keypress', evInit));
                                document.dispatchEvent(new KeyboardEvent('keyup', evInit));
                            } catch (e) {}
                        }
                        try { target.dispatchEvent(new KeyboardEvent('keyup', evInit)); } catch (e) {}
                    };

                    for (const ch of code.split('')) {
                        if (!/\\d/.test(ch)) continue;
                        sendDigit(ch);
                    }

                    let filledCount = 0;
                    for (const el of (singleInputs.length ? singleInputs : allInputs)) {
                        try {
                            const v = String((el.value !== undefined) ? (el.value || '') : (el.textContent || '')).trim();
                            if (v) filledCount += Math.min(v.length, 1);
                        } catch (e) {}
                    }
                    if (filledCount >= 4) filled = Math.max(filled, 4);
                }

                let clicked = false;
                const btnSelectors = [
                    'button[type="submit"]',
                    '[data-testid*="confirm"]',
                    '[data-testid*="Confirm"]',
                    '[data-testid*="continue"]',
                    '[data-testid*="Continue"]',
                    'button',
                    '[role="button"]',
                ];
                const btnKeywords = ['continue', 'confirm', 'submit', 'verify', 'unlock', 'next', '继续', '确认', '提交', '验证', '下一步', '解锁'];
                for (const s of btnSelectors) {
                    for (const el of Array.from(document.querySelectorAll(s))) {
                        if (!isVisible(el)) continue;
                        if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                        const txt = String((el.innerText || el.textContent || '')).trim().toLowerCase();
                        if (!txt) continue;
                        if (!btnKeywords.some((k) => txt.includes(k))) continue;
                        el.click();
                        clicked = true;
                        break;
                    }
                    if (clicked) break;
                }

                try {
                    const ae = document.activeElement;
                    if (ae) {
                        ae.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
                        ae.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
                    }
                } catch (e) {}

                return { filled, clicked, inputCount: allInputs.length };
                """,
                passcode_digits,
            ) or {}
            return {
                'ok': int(result.get('filled', 0)) >= 4,
                'filled': int(result.get('filled', 0)),
                'clicked': bool(result.get('clicked', False)),
                'inputCount': int(result.get('inputCount', 0)),
            }
        except Exception:
            return {'ok': False, 'filled': 0, 'clicked': False, 'inputCount': 0}

    if not _is_passcode_page():
        return False

    deps.log_to_ui('warn', '🔐 检测到 Enter Passcode，尝试自动输入口令...')
    for attempt in range(1, 4):
        deps._prepare_reply_prompt_guard(tab, f'口令页处理{attempt}')
        fill_result = _fill_passcode_once()
        filled_ok = bool(fill_result.get('ok', False))
        try:
            now_url = str(tab.url or '')
        except Exception:
            now_url = ''
        deps.log_headless_debug(
            f"Enter Passcode尝试{attempt}: filled={fill_result.get('filled', 0)}, "
            f"clicked={fill_result.get('clicked', False)}, inputCount={fill_result.get('inputCount', 0)}, "
            f"ok={filled_ok}, url={now_url}"
        )
        if filled_ok and _wait_passcode_cleared(timeout_sec=8.8):
            _mark_passcode_warmed(deps)
            deps.log_to_ui('info', '🔓 Enter Passcode 自动通过，私信通道已恢复')
            return True

        if not filled_ok:
            typed_ok = _fallback_type_passcode_via_body()
            deps.log_headless_debug(f'Enter Passcode尝试{attempt}: body_input_fallback={typed_ok}')
            if typed_ok and _wait_passcode_cleared(timeout_sec=8.8):
                _mark_passcode_warmed(deps)
                deps.log_to_ui('info', '🔓 Enter Passcode 自动通过，私信通道已恢复')
                return True

        time.sleep(random.uniform(0.25, 0.55))

    deps._capture_runtime_diagnostic(
        tab,
        'dm_passcode_prompt_blocking',
        err='Enter Passcode 自动处理失败',
        selectors=[
            'css:input[type="password"]',
            'css:input[type="tel"]',
            'css:input[inputmode="numeric"]',
            'css:input[autocomplete="one-time-code"]',
            'css:[role="dialog"]',
            'css:[role="alertdialog"]',
            'css:button[type="submit"]',
        ],
        extra={'url': str(getattr(tab, 'url', '') or ''), 'passcode_len': len(passcode_digits)},
    )
    deps.log_to_ui('warn', '⚠️ Enter Passcode 自动输入未通过，请检查口令或手工输入一次')
    return False


def warmup_dm_passcode_if_needed(tab, deps, force=False):
    """在会话内预热一次 Enter Passcode，避免首条私信被拦截。"""
    passcode_digits = _get_passcode_digits(deps)
    if len(passcode_digits) < 4:
        return
    if not tab:
        return

    with deps.dm_passcode_lock:
        if deps.dm_passcode_warmed and not force:
            return

    try:
        now_url = str(tab.url or '')
    except Exception:
        now_url = ''

    def _is_passcode_blocking_now():
        try:
            u = str(tab.url or '').lower()
        except Exception:
            u = ''
        if '/i/chat/pin/recovery' in u or '/i/chat/pin' in u:
            return True
        try:
            state = tab.run_js(
                """
                const isVisible = (el) => {
                  if (!el) return false;
                  const st = window.getComputedStyle(el);
                  if (!st) return false;
                  if (st.display === 'none' || st.visibility === 'hidden') return false;
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                };
                const norm = (s) => String(s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                let hasEnter = false;
                let hasForgot = false;
                for (const el of Array.from(document.querySelectorAll('h1,h2,h3,p,span,div,a,button'))) {
                  if (!isVisible(el)) continue;
                  const txt = norm(el.innerText || el.textContent || '');
                  if (!txt) continue;
                  if (txt.includes('enter passcode') || txt.includes('输入口令') || txt.includes('输入密码')) hasEnter = true;
                  if (txt.includes('forgot passcode') || txt.includes('忘记口令') || txt.includes('忘记密码')) hasForgot = true;
                  if (hasEnter && hasForgot) break;
                }
                return Boolean(hasEnter && hasForgot);
                """
            )
        except Exception:
            state = False
        return bool(state)

    try:
        if '/i/chat/' not in now_url and '/messages' not in now_url:
            tab.get('https://x.com/messages')
            deps._wait_document_ready(tab, timeout=6.0)
            time.sleep(random.uniform(0.3, 0.7))

        handled = handle_dm_passcode_prompt(tab, deps)
        if handled:
            _mark_passcode_warmed(deps)
            return

        if not _is_passcode_blocking_now():
            _mark_passcode_warmed(deps)
        else:
            deps.log_to_ui('warn', '⚠️ 口令预热未通过，后续私信流程将继续尝试自动输入')
    except Exception as e:
        deps.log_headless_debug(f'口令预热异常: {e}')
