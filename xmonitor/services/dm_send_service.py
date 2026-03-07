import random
import time


def send_dm_message(tab, text, deps):
    if not text:
        return False, '空消息'

    editor_selectors = list(deps.DM_EDITOR_SELECTORS)
    send_btn_selectors = list(deps.DM_SEND_BUTTON_SELECTORS)
    editor_css_selectors = [
        s[4:] if str(s).startswith('css:') else str(s)
        for s in editor_selectors
    ]
    send_btn_css_selectors = [
        s[4:] if str(s).startswith('css:') else str(s)
        for s in send_btn_selectors
    ]

    def _clear_dm_binding_marks():
        try:
            tab.run_js(
                """
                document.querySelectorAll('[data-xm-dm-target],[data-xm-dm-send-target],[data-xm-dm-root]').forEach((el) => {
                  try { el.removeAttribute('data-xm-dm-target'); } catch (e) {}
                  try { el.removeAttribute('data-xm-dm-send-target'); } catch (e) {}
                  try { el.removeAttribute('data-xm-dm-root'); } catch (e) {}
                });
                return true;
                """
            )
        except Exception:
            pass

    def _bind_dm_composer_target():
        try:
            ok = tab.run_js(
                """
                const editorSels = arguments[0] || [];
                const sendSels = arguments[1] || [];
                const rejectOverlay = !!arguments[2];
                const isVisible = (el) => {
                  if (!el) return false;
                  const st = window.getComputedStyle(el);
                  if (!st) return false;
                  if (st.display === 'none' || st.visibility === 'hidden') return false;
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                };
                const isBadScene = (text) => {
                  const t = String(text || '').toLowerCase();
                  return (
                    t.includes('搜索私信') ||
                    t.includes('创建一条私信') ||
                    t.includes('创建私信') ||
                    t.includes('new message') ||
                    t.includes('search direct messages') ||
                    t.includes('recipient')
                  );
                };
                document.querySelectorAll('[data-xm-dm-target],[data-xm-dm-send-target],[data-xm-dm-root]').forEach((el) => {
                  try { el.removeAttribute('data-xm-dm-target'); } catch (e) {}
                  try { el.removeAttribute('data-xm-dm-send-target'); } catch (e) {}
                  try { el.removeAttribute('data-xm-dm-root'); } catch (e) {}
                });
                const sendButtons = [];
                for (const s of sendSels) {
                  let nodes = [];
                  try { nodes = Array.from(document.querySelectorAll(s)); } catch (e) { nodes = []; }
                  for (const n of nodes) {
                    if (!isVisible(n)) continue;
                    if (!sendButtons.includes(n)) sendButtons.push(n);
                  }
                }
                if (!sendButtons.length) return false;
                const editorScore = (editor, btn, root) => {
                  if (!editor || !btn) return -1e9;
                  const er = editor.getBoundingClientRect();
                  const br = btn.getBoundingClientRect();
                  const rr = root && root.getBoundingClientRect ? root.getBoundingClientRect() : { width: 0, height: 0 };
                  const editableSelf = !!(
                    editor.value !== undefined ||
                    editor.isContentEditable ||
                    editor.getAttribute('contenteditable') === 'true' ||
                    editor.getAttribute('contenteditable') === 'plaintext-only'
                  );
                  const width = Number(er.width || 0);
                  const height = Number(er.height || 0);
                  const top = Number(er.top || 0);
                  const bottom = Number(er.bottom || 0);
                  const nearFooterBand = top >= (window.innerHeight * 0.55);
                  const verticalGap = Math.abs(bottom - br.top);
                  const aboveBtn = bottom <= (br.bottom + 24);
                  const closeToBtn = verticalGap <= 220;
                  const leftOfBtn = (Number(er.left || 0) <= Number(br.left || 0) + 48);
                  const rootArea = Math.max(1, Number(rr.width || 0) * Number(rr.height || 0));
                  let score = 0;
                  if (editableSelf) score += 500;
                  if (nearFooterBand) score += 420;
                  if (aboveBtn) score += 220;
                  if (closeToBtn) score += Math.max(0, 260 - verticalGap);
                  if (leftOfBtn) score += 120;
                  if (width >= 180) score += 160;
                  if (height >= 24) score += 80;
                  score += Math.min(240, Math.max(0, bottom));
                  score -= Math.min(180, Math.max(0, top < (window.innerHeight * 0.45) ? 160 : 0));
                  score -= Math.min(120, Math.log10(rootArea + 1) * 16);
                  return score;
                };
                const pickEditorByBtn = (btn) => {
                  const chain = [];
                  let node = btn;
                  for (let i = 0; i < 12 && node; i++) {
                    chain.push(node);
                    node = node.parentElement;
                  }
                  let best = null;
                  for (const root of chain) {
                    if (!root || root.nodeType !== 1) continue;
                    const rootText = String(root.innerText || root.textContent || '').slice(0, 800);
                    if (rejectOverlay && isBadScene(rootText)) continue;
                    let editors = [];
                    for (const s of editorSels) {
                      let found = [];
                      try { found = Array.from(root.querySelectorAll(s)); } catch (e) { found = []; }
                      for (const e of found) {
                        if (!isVisible(e)) continue;
                        if (!editors.includes(e)) editors.push(e);
                      }
                    }
                    if (!editors.length) continue;
                    for (const editor of editors) {
                      const score = editorScore(editor, btn, root);
                      if (!best || score > best.score) {
                        best = { editor, root, score };
                      }
                    }
                  }
                  return best;
                };
                const candidates = [];
                for (const btn of sendButtons) {
                  const picked = pickEditorByBtn(btn);
                  if (!picked || !picked.editor || !picked.root) continue;
                  const r = btn.getBoundingClientRect();
                  const enabled = !(btn.disabled || btn.getAttribute('aria-disabled') === 'true');
                  candidates.push({ btn, editor: picked.editor, root: picked.root, enabled, top: Number(r.top || 0), score: Number(picked.score || 0) });
                }
                if (!candidates.length) return false;
                candidates.sort((a, b) => {
                  if (a.enabled !== b.enabled) return Number(b.enabled) - Number(a.enabled);
                  if (a.score !== b.score) return Number(b.score || 0) - Number(a.score || 0);
                  return Number(b.top || 0) - Number(a.top || 0);
                });
                const target = candidates[0];
                try { target.root.setAttribute('data-xm-dm-root', '1'); } catch (e) {}
                try { target.editor.setAttribute('data-xm-dm-target', '1'); } catch (e) {}
                try { target.btn.setAttribute('data-xm-dm-send-target', '1'); } catch (e) {}
                try { target.editor.focus(); } catch (e) {}
                return true;
                """,
                editor_css_selectors,
                send_btn_css_selectors,
                deps.DM_REJECT_NEW_MESSAGE_OVERLAY,
            )
            return bool(ok)
        except Exception:
            return False

    def _get_bound_editor():
        try:
            cand = tab.ele('css:[data-xm-dm-target="1"]', timeout=0.25)
            if cand and cand.states.is_displayed:
                return cand
        except Exception:
            pass
        return None

    def _get_bound_send_btn(require_enabled=True):
        try:
            cand = tab.ele('css:[data-xm-dm-send-target="1"]', timeout=0.25)
            if not cand:
                return None
            if not cand.states.is_displayed:
                return None
            if require_enabled and (not deps._is_element_actionable(cand)):
                return None
            return cand
        except Exception:
            return None

    def _editor_matches_bound_send(editor_el):
        if not editor_el:
            return False
        try:
            ok = tab.run_js(
                """
                const ed = arguments[0];
                const btn = document.querySelector('[data-xm-dm-send-target="1"]');
                const root = document.querySelector('[data-xm-dm-root="1"]');
                if (!ed) return false;
                if (!btn) return true;
                if (!root) return false;
                return root.contains(ed);
                """,
                editor_el,
            )
            return bool(ok)
        except Exception:
            return False

    def _has_any_visible_send_btn():
        try:
            has_btn = tab.run_js(
                """
                const selectors = arguments[0] || [];
                const isVisible = (el) => {
                  if (!el) return false;
                  const st = window.getComputedStyle(el);
                  if (!st) return false;
                  if (st.display === 'none' || st.visibility === 'hidden') return false;
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                };
                for (const s of selectors) {
                  let nodes = [];
                  try { nodes = Array.from(document.querySelectorAll(s)); } catch (e) { nodes = []; }
                  for (const n of nodes) {
                    if (isVisible(n)) return true;
                  }
                }
                return false;
                """,
                send_btn_css_selectors,
            )
            return bool(has_btn)
        except Exception:
            return False

    def _is_valid_dm_editor(editor_el):
        try:
            ok = tab.run_js(
                """
                const el = arguments[0];
                const rejectOverlay = !!arguments[1];
                if (!el) return false;
                const low = (s) => String(s || '').toLowerCase();
                const attrs = [
                  el.getAttribute('aria-label'),
                  el.getAttribute('placeholder'),
                  el.getAttribute('data-testid'),
                  el.getAttribute('name')
                ].map(low).join(' ');
                const rejectKeys = [
                  'search', '搜索', 'recipient', '收件人', 'people', 'group', 'new message', '新消息'
                ];
                if (rejectKeys.some((k) => attrs.includes(k))) return false;
                const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : { top: 0, width: 0, height: 0 };
                const editable = !!(
                  el.value !== undefined ||
                  el.isContentEditable ||
                  el.getAttribute('contenteditable') === 'true' ||
                  el.querySelector('textarea,[contenteditable="true"]')
                );
                if (!editable) return false;
                const url = low(window.location.href || '');
                if (url.includes('/i/chat/')) return true;
                const root = el.closest('[role="dialog"]') || document;
                const rootText = low((root.innerText || root.textContent || '').slice(0, 800));
                const hasSearchScene = (
                  rootText.includes('搜索私信') ||
                  rootText.includes('创建一条私信') ||
                  rootText.includes('创建私信') ||
                  rootText.includes('new message') ||
                  rootText.includes('search direct messages') ||
                  rootText.includes('recipient')
                );
                const hasSend = !!root.querySelector(
                  '[data-testid="dm-composer-send-button"],[data-testid="dmComposerSendButton"],button[data-testid*="dm-composer-send"]'
                );
                if (rejectOverlay) {
                  if (hasSearchScene && !hasSend) return false;
                  if (!hasSend && rect && Number(rect.top || 0) < (window.innerHeight * 0.45)) return false;
                }
                if (root.querySelector('[data-testid="dmComposerTextInput"],textarea[data-testid="dm-composer-textarea"]')) {
                  return true;
                }
                return hasSend;
                """,
                editor_el,
                deps.DM_REJECT_NEW_MESSAGE_OVERLAY,
            )
            return bool(ok)
        except Exception:
            return False

    def _promote_dm_editor_candidate(cand):
        if not cand:
            return cand
        for selector in (
            'css:div[role="textbox"][contenteditable]:not([contenteditable="false"])',
            'css:[contenteditable]:not([contenteditable="false"])',
            'css:[contenteditable="true"]',
        ):
            try:
                inner = cand.ele(selector, timeout=0)
                if inner and inner.states.is_displayed:
                    return inner
            except Exception:
                pass
        return cand

    def _find_editor(rounds=2, timeout_each=1.5):
        for _ in range(max(1, rounds)):
            if deps.DM_FORCE_COMPOSER_BINDING:
                bound_ok = _bind_dm_composer_target()
                bound = _get_bound_editor()
                if bound and _is_valid_dm_editor(bound):
                    return bound
                if (not bound_ok) and _has_any_visible_send_btn():
                    return None
            for selector in editor_selectors:
                try:
                    cand = tab.ele(selector, timeout=timeout_each)
                    cand = _promote_dm_editor_candidate(cand)
                    if cand and cand.states.is_displayed and _is_valid_dm_editor(cand):
                        return cand
                except Exception:
                    continue
            time.sleep(random.uniform(0.08, 0.22))
        return None

    def _find_send_btn(rounds=2, timeout_each=1.2, require_enabled=True):
        for _ in range(max(1, rounds)):
            if deps.DM_FORCE_COMPOSER_BINDING:
                _bind_dm_composer_target()
                bound_btn = _get_bound_send_btn(require_enabled=require_enabled)
                if bound_btn:
                    return bound_btn
            if require_enabled:
                cand = deps._wait_first_actionable(tab, send_btn_selectors, timeout=timeout_each, poll=0.08)
            else:
                cand = deps._wait_first_visible(tab, send_btn_selectors, timeout=timeout_each, poll=0.08)
            if cand:
                return cand
            time.sleep(random.uniform(0.05, 0.18))
        return None

    def _composer_cleared(editor_el):
        try:
            remain = tab.run_js(
                """
                const el = arguments[0];
                if (!el) return '';
                const val = (el.value !== undefined) ? el.value : (el.textContent || '');
                return String(val || '').trim();
                """,
                editor_el,
            )
            return len(str(remain or '').strip()) == 0
        except Exception:
            return True

    def _editor_has_text(editor_el, expected_text):
        try:
            remain = tab.run_js(
                """
                const el = arguments[0];
                if (!el) return '';
                const val = (el.value !== undefined) ? el.value : (el.textContent || '');
                return String(val || '');
                """,
                editor_el,
            )
            current = deps._normalize_text_for_compare(remain)
            exp = deps._normalize_text_for_compare(expected_text)
            if not exp:
                return True
            if deps._is_link_only_message(exp):
                if not current:
                    btn = _find_send_btn(rounds=1, timeout_each=0.8)
                    return bool(btn)
                if exp in current or current in exp:
                    return True
                if 'x.com/' in current or 'twitter.com/' in current:
                    return True
                return False
            if current == exp:
                return True
            if current.count(exp) >= 2:
                return False
            if exp and (exp in current):
                return True
            if current and (current in exp) and len(current) >= max(12, int(len(exp) * 0.72)):
                return True
            if current.endswith(exp) and (len(current) - len(exp)) <= 6:
                return True
            return False
        except Exception:
            return False

    def _force_fill_dm_editor_text(editor_el, expected_text):
        text = str(expected_text or '')
        if not text:
            return False
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
                  return el.querySelector(
                    'div[role="textbox"][contenteditable="true"],[data-testid="dmComposerTextInput"] [contenteditable="true"],textarea[data-testid="dm-composer-textarea"],textarea'
                  );
                };
                let el = resolveTarget(root);
                if (!el) return false;
                const dispatchAll = () => {
                  try {
                    el.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, inputType: 'insertText', data: text }));
                  } catch (e) {}
                  try {
                    el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
                  } catch (e) {
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                  }
                  try { el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Process', code: 'Process' })); } catch (e) {}
                  try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
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
                  dispatchAll();
                };
                try { el.focus(); } catch (e) {}
                if (el.value !== undefined) {
                  setValue(text);
                  return true;
                }
                try {
                  const sel = window.getSelection && window.getSelection();
                  if (sel) {
                    sel.removeAllRanges();
                    const range = document.createRange();
                    range.selectNodeContents(el);
                    sel.addRange(range);
                  }
                } catch (e) {}
                let done = false;
                try {
                  done = !!document.execCommand('insertText', false, text);
                } catch (e) {}
                if (!done || !String(el.textContent || '').trim()) {
                  setValue(text);
                } else {
                  dispatchAll();
                }
                return true;
                """,
                editor_el,
                text,
            )
            if ok and _editor_has_text(editor_el, text):
                return True
        except Exception:
            pass
        try:
            editor_el.input(text, clear=True)
        except Exception:
            return False
        return _editor_has_text(editor_el, text)

    def _wait_send_button_after_input(editor_el, expected_text, link_mode=False):
        def _has_disabled_send_button():
            bound_disabled = _get_bound_send_btn(require_enabled=False)
            if bound_disabled:
                try:
                    if not deps._is_element_actionable(bound_disabled):
                        return True
                except Exception:
                    pass
            try:
                state = tab.run_js(
                    """
                    const sels = [
                      'button[data-testid="dm-composer-send-button"]',
                      '[data-testid="dm-composer-send-button"]',
                      'button[data-testid*="dm-composer-send"]',
                      '[data-testid*="dm-composer-send"]',
                      '[data-testid="dmComposerSendButton"]',
                      'button[data-testid="dmComposerSendButton"]',
                      'button[aria-label*="Send"]',
                      'button[aria-label*="发送"]'
                    ];
                    const isVisible = (el) => {
                      if (!el) return false;
                      const st = window.getComputedStyle(el);
                      if (!st) return false;
                      if (st.display === 'none' || st.visibility === 'hidden') return false;
                      const r = el.getBoundingClientRect();
                      return r.width > 0 && r.height > 0;
                    };
                    for (const s of sels) {
                      for (const el of Array.from(document.querySelectorAll(s))) {
                        if (!isVisible(el)) continue;
                        if (el.disabled || el.getAttribute('aria-disabled') === 'true') return true;
                      }
                    }
                    return false;
                    """
                )
                return bool(state)
            except Exception:
                return False

        def _nudge_editor_for_send_enable():
            try:
                deps._refresh_dm_editor_state(tab, editor_el, expected_text)
                deps._poke_dm_editor_events(tab, editor_el)
            except Exception:
                pass
            try:
                tab.run_js(
                    """
                    const el = arguments[0];
                    const text = String(arguments[1] || '');
                    if (!el) return false;
                    try { el.focus(); } catch (e) {}
                    const dispatchAll = () => {
                      try { el.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, inputType: 'insertText', data: ' ' })); } catch (e) {}
                      try { el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: ' ' })); } catch (e) {
                        try { el.dispatchEvent(new Event('input', { bubbles: true })); } catch (_) {}
                      }
                      try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                    };
                    if (el.value !== undefined) {
                      const v = String(el.value || '');
                      el.value = v + ' ';
                      dispatchAll();
                      el.value = v;
                      dispatchAll();
                      return true;
                    }
                    if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
                      try {
                        const sel = window.getSelection && window.getSelection();
                        if (sel) {
                          sel.removeAllRanges();
                          const range = document.createRange();
                          range.selectNodeContents(el);
                          range.collapse(false);
                          sel.addRange(range);
                        }
                      } catch (e) {}
                      let changed = false;
                      try { changed = !!document.execCommand('insertText', false, ' '); } catch (e) {}
                      dispatchAll();
                      try { document.execCommand('delete'); } catch (e) {}
                      dispatchAll();
                      if (!changed) {
                        el.textContent = text;
                        dispatchAll();
                      }
                      return true;
                    }
                    return false;
                    """,
                    editor_el,
                    expected_text,
                )
            except Exception:
                pass

        def _wait_link_preview_ready(timeout_sec=2.8):
            deadline = time.time() + max(1.0, float(timeout_sec))
            status_id = deps._pick_best_status_id(expected_text)
            while time.time() < deadline:
                btn = _find_send_btn(rounds=1, timeout_each=0.45, require_enabled=True)
                try:
                    state = tab.run_js(
                        """
                        const el = arguments[0];
                        const raw = String(arguments[1] || '');
                        const sid = String(arguments[2] || '');
                        if (!el) return { hasCard: false, hasPreview: false, hrefOk: false };
                        const root = el.closest('[role="dialog"],section,main') || document;
                        const html = String(root.innerHTML || '');
                        const text = String(root.innerText || root.textContent || '');
                        return {
                          hasCard: /card|preview|expandedurl|unfurl/i.test(html),
                          hasPreview: new RegExp('(x\\.com/[^\\s<>"]+/status/\\d+|twitter\\.com/[^\\s<>"]+/status/\\d+)', 'i').test(html + ' ' + text),
                          hrefOk: !!(sid && new RegExp(`status/${sid}`).test(html + ' ' + text)) || (raw && (html + ' ' + text).includes(raw))
                        };
                        """,
                        editor_el,
                        expected_text,
                        status_id,
                    ) or {}
                except Exception:
                    state = {}
                if btn:
                    return True
                if state.get('hasPreview') or state.get('hrefOk') or state.get('hasCard'):
                    return True
                deps._dm_humanized_idle(tab, 0.05, 0.12, '等待链接预览加载')
            return False

        if link_mode:
            _wait_link_preview_ready(timeout_sec=3.0)
        btn = _find_send_btn(rounds=2, timeout_each=1.0, require_enabled=True)
        if btn:
            return btn
        if not link_mode:
            deadline = time.time() + max(0.6, float(deps.DM_TEXT_VERIFY_TIMEOUT_SEC))
            while time.time() < deadline:
                if _editor_has_text(editor_el, expected_text):
                    deps._poke_dm_editor_events(tab, editor_el)
                btn = _find_send_btn(rounds=1, timeout_each=0.6, require_enabled=True)
                if btn:
                    return btn
                deps._dm_humanized_idle(tab, 0.03, 0.1, '文本消息等待发送按钮')
            if _editor_has_text(editor_el, expected_text) and _has_disabled_send_button():
                _nudge_editor_for_send_enable()
                deps._dm_humanized_idle(tab, 0.04, 0.12, '文本消息发送按钮唤醒后等待')
                btn = _find_send_btn(rounds=2, timeout_each=0.8, require_enabled=True)
                if btn:
                    return btn
            return None
        if _editor_has_text(editor_el, expected_text):
            if deps._poke_dm_editor_events(tab, editor_el):
                deps._dm_humanized_idle(tab, 0.04, 0.12, '链接输入确认后等待按钮')
            btn = _find_send_btn(rounds=2, timeout_each=1.0, require_enabled=True)
            if btn:
                return btn
        if link_mode:
            try:
                current_text = str(tab.run_js(
                    """
                    const el = arguments[0];
                    if (!el) return '';
                    return String((el.value !== undefined) ? (el.value || '') : (el.textContent || ''));
                    """,
                    editor_el,
                ) or '')
            except Exception:
                current_text = ''
            if not deps._normalize_text_for_compare(current_text):
                deps._paste_dm_text_exact(tab, editor_el, expected_text)
                deps._dm_humanized_idle(tab, 0.05, 0.12, '链接回填后等待按钮')
            btn = _find_send_btn(rounds=2, timeout_each=1.0, require_enabled=True)
            if btn:
                return btn
        return None

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

        editor = _find_editor(rounds=2, timeout_each=1.4)
        if not editor:
            deps._handle_dm_passcode_prompt(tab)
            editor = _find_editor(rounds=2, timeout_each=1.6)
        if not editor:
            last_err = '未找到私信输入框'
            time.sleep(random.uniform(0.05, 0.12))
            continue
        if deps.DM_FORCE_COMPOSER_BINDING and not _editor_matches_bound_send(editor):
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
        if deps.DM_FORCE_COMPOSER_BINDING and not _editor_matches_bound_send(editor):
            last_err = 'E_DM_WRONG_COMPOSER_TARGET: 文本写入疑似落在上层浮层输入框'
            deps._dm_humanized_idle(tab, 0.06, 0.16, '检测到文本映射异常后等待')
            continue
        if not _editor_has_text(editor, dm_text):
            if link_only_mode:
                deps._poke_dm_editor_events(tab, editor)
                if not _editor_has_text(editor, dm_text):
                    last_err = '输入后链接状态未稳定写入编辑器'
                    deps._dm_humanized_idle(tab, 0.08, 0.2, '链接输入校验失败后等待')
                    continue
            else:
                deps._dm_humanized_idle(tab, 0.04, 0.12, '私信文本二次回填前')
                recovered = _force_fill_dm_editor_text(editor, dm_text)
                if not recovered and not _editor_has_text(editor, dm_text):
                    recovered = deps._humanized_type_dm_text(tab, editor, dm_text)
                if not recovered and not _editor_has_text(editor, dm_text):
                    last_err = '输入后文本未稳定写入编辑器'
                    deps._dm_humanized_idle(tab, 0.08, 0.2, '私信输入校验失败后等待')
                    continue

        deps._dm_humanized_idle(tab, 0.04, 0.12, '私信发送前')
        send_btn = _wait_send_button_after_input(editor, dm_text, link_mode=link_only_mode)
        if send_btn:
            clicked_send, click_err = deps._click_with_prompt_guard(tab, send_btn, '点击私信发送按钮')
            if clicked_send:
                deps._dm_humanized_idle(tab, 0.06, 0.16, '私信发送后确认')
                if _composer_cleared(editor):
                    return True, ''
                if deps._confirm_dm_message_sent(tab, before_counts, probes, wait_sec=deps.DM_SEND_CONFIRM_WAIT_SEC):
                    deps.log_headless_debug('私信发送后输入框未清空，但已确认消息落库，按成功处理')
                    return True, ''
                if deps.DM_ASSUME_SUCCESS_AFTER_CLICK:
                    deps.log_to_ui('warn', '⚠️ 私信点击发送后状态不确定，但当前配置禁止按成功处理')
                last_err = '点击私信发送后输入框未清空'
                continue
            last_err = click_err
        elif _editor_has_text(editor, dm_text):
            deps._dm_humanized_idle(tab, 0.02, 0.08, '私信发送Enter兜底前')
            try:
                enter_sent = bool(tab.run_js(
                    """
                    const el = arguments[0];
                    if (!el) return false;
                    try { el.focus(); } catch (e) {}
                    const ev = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true };
                    try { el.dispatchEvent(new KeyboardEvent('keydown', ev)); } catch (e) {}
                    try { el.dispatchEvent(new KeyboardEvent('keypress', ev)); } catch (e) {}
                    try { el.dispatchEvent(new KeyboardEvent('keyup', ev)); } catch (e) {}
                    return true;
                    """,
                    editor,
                ))
            except Exception:
                enter_sent = False
            if enter_sent:
                deps._dm_humanized_idle(tab, 0.06, 0.16, '私信发送Enter兜底后')
                if _composer_cleared(editor):
                    return True, ''
                if deps._confirm_dm_message_sent(tab, before_counts, probes, wait_sec=deps.DM_SEND_CONFIRM_WAIT_SEC):
                    return True, ''
            last_err = '发送按钮未出现或未激活，且Enter兜底未确认发送'

        deps._dm_humanized_idle(tab, 0.06, 0.18, '私信发送DOM兜底前')
        try:
            clicked = tab.run_js(
                """
                const selectors = [
                  'button[data-testid="dm-composer-send-button"]',
                  '[data-testid="dm-composer-send-button"]',
                  'button[data-testid*="dm-composer-send"]',
                  '[data-testid*="dm-composer-send"]',
                  '[data-testid="dmComposerSendButton"]',
                  'button[data-testid="dmComposerSendButton"]',
                  'button[aria-label*="Send"]',
                  'button[aria-label*="发送"]',
                  '[role="button"][aria-label*="Send"]',
                  '[role="button"][aria-label*="发送"]',
                ];
                for (const s of selectors) {
                  const nodes = Array.from(document.querySelectorAll(s));
                  for (const el of nodes) {
                    const style = window.getComputedStyle(el);
                    const hidden = style.display === 'none' || style.visibility === 'hidden';
                    const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
                    if (!hidden && !disabled) {
                      el.click();
                      return true;
                    }
                  }
                }
                return false;
                """
            )
            if clicked:
                deps._dm_humanized_idle(tab, 0.06, 0.16, '私信发送DOM兜底后')
                if _composer_cleared(editor):
                    return True, ''
                if deps._confirm_dm_message_sent(tab, before_counts, probes, wait_sec=deps.DM_SEND_CONFIRM_WAIT_SEC):
                    deps.log_headless_debug('DOM发送后已确认消息落库，按成功处理')
                    return True, ''
                if deps.DM_ASSUME_SUCCESS_AFTER_CLICK:
                    deps.log_to_ui('warn', '⚠️ 私信DOM发送后状态不确定，但当前配置禁止按成功处理')
                last_err = 'DOM点击发送后输入框未清空'
                continue
        except Exception:
            pass

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
