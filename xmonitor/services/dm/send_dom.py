import random
import time


class DMSendDomHelper:
    def __init__(self, tab, deps, editor_selectors, send_btn_selectors):
        self.tab = tab
        self.deps = deps
        self.editor_selectors = list(editor_selectors or [])
        self.send_btn_selectors = list(send_btn_selectors or [])
        self.editor_css_selectors = [
            s[4:] if str(s).startswith('css:') else str(s)
            for s in self.editor_selectors
        ]
        self.send_btn_css_selectors = [
            s[4:] if str(s).startswith('css:') else str(s)
            for s in self.send_btn_selectors
        ]

    def clear_binding_marks(self):
        try:
            self.tab.run_js(
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

    def bind_dm_composer_target(self):
        try:
            ok = self.tab.run_js(
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
                self.editor_css_selectors,
                self.send_btn_css_selectors,
                self.deps.DM_REJECT_NEW_MESSAGE_OVERLAY,
            )
            return bool(ok)
        except Exception:
            return False

    def get_bound_editor(self):
        try:
            cand = self.tab.ele('css:[data-xm-dm-target="1"]', timeout=0.25)
            if cand and cand.states.is_displayed:
                return cand
        except Exception:
            pass
        return None

    def get_bound_send_btn(self, require_enabled=True):
        try:
            cand = self.tab.ele('css:[data-xm-dm-send-target="1"]', timeout=0.25)
            if not cand:
                return None
            if not cand.states.is_displayed:
                return None
            if require_enabled and (not self.deps._is_element_actionable(cand)):
                return None
            return cand
        except Exception:
            return None

    def editor_matches_bound_send(self, editor_el):
        if not editor_el:
            return False
        try:
            ok = self.tab.run_js(
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

    def has_any_visible_send_btn(self):
        try:
            has_btn = self.tab.run_js(
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
                self.send_btn_css_selectors,
            )
            return bool(has_btn)
        except Exception:
            return False

    def is_valid_dm_editor(self, editor_el):
        try:
            ok = self.tab.run_js(
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
                self.deps.DM_REJECT_NEW_MESSAGE_OVERLAY,
            )
            return bool(ok)
        except Exception:
            return False

    def promote_dm_editor_candidate(self, cand):
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

    def find_editor(self, rounds=2, timeout_each=1.5):
        for _ in range(max(1, rounds)):
            if self.deps.DM_FORCE_COMPOSER_BINDING:
                bound_ok = self.bind_dm_composer_target()
                bound = self.get_bound_editor()
                if bound and self.is_valid_dm_editor(bound):
                    return bound
                if (not bound_ok) and self.has_any_visible_send_btn():
                    return None
            for selector in self.editor_selectors:
                try:
                    cand = self.tab.ele(selector, timeout=timeout_each)
                    cand = self.promote_dm_editor_candidate(cand)
                    if cand and cand.states.is_displayed and self.is_valid_dm_editor(cand):
                        return cand
                except Exception:
                    continue
            time.sleep(random.uniform(0.08, 0.22))
        return None

    def find_send_btn(self, rounds=2, timeout_each=1.2, require_enabled=True):
        for _ in range(max(1, rounds)):
            if self.deps.DM_FORCE_COMPOSER_BINDING:
                self.bind_dm_composer_target()
                bound_btn = self.get_bound_send_btn(require_enabled=require_enabled)
                if bound_btn:
                    return bound_btn
            if require_enabled:
                cand = self.deps._wait_first_actionable(self.tab, self.send_btn_selectors, timeout=timeout_each, poll=0.08)
            else:
                cand = self.deps._wait_first_visible(self.tab, self.send_btn_selectors, timeout=timeout_each, poll=0.08)
            if cand:
                return cand
            time.sleep(random.uniform(0.05, 0.18))
        return None

    def composer_cleared(self, editor_el):
        try:
            remain = self.tab.run_js(
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

    def clear_composer_after_success(self, editor_el):
        cleared = False
        try:
            cleared = bool(self.tab.run_js(
                """
                const root = arguments[0];
                if (!root) return true;
                const resolveTarget = (el) => {
                  if (!el) return null;
                  if (el.value !== undefined || el.isContentEditable || el.getAttribute('contenteditable') === 'true') {
                    return el;
                  }
                  return el.querySelector(
                    'div[role="textbox"][contenteditable="true"],[data-testid="dmComposerTextInput"] [contenteditable="true"],textarea[data-testid="dm-composer-textarea"],textarea'
                  );
                };
                const dispatchAll = (el) => {
                  try {
                    el.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, inputType: 'deleteContentBackward', data: null }));
                  } catch (e) {}
                  try {
                    el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'deleteContentBackward', data: null }));
                  } catch (e) {
                    try { el.dispatchEvent(new Event('input', { bubbles: true })); } catch (_) {}
                  }
                  try { el.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
                  try { el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Backspace', code: 'Backspace' })); } catch (e) {}
                };
                const setValue = (el, val) => {
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
                  dispatchAll(el);
                };
                const el = resolveTarget(root);
                if (!el) return true;
                try { el.focus(); } catch (e) {}
                setValue(el, '');
                let remain = String((el.value !== undefined) ? (el.value || '') : (el.textContent || '')).trim();
                if (remain) {
                  try {
                    const sel = window.getSelection && window.getSelection();
                    if (sel) {
                      sel.removeAllRanges();
                      const range = document.createRange();
                      range.selectNodeContents(el);
                      sel.addRange(range);
                    }
                  } catch (e) {}
                  try { document.execCommand('delete', false, null); } catch (e) {}
                  dispatchAll(el);
                  remain = String((el.value !== undefined) ? (el.value || '') : (el.textContent || '')).trim();
                }
                try { el.blur(); } catch (e) {}
                return remain.length === 0;
                """,
                editor_el,
            ))
        except Exception:
            cleared = False
        self.clear_binding_marks()
        if not cleared:
            try:
                editor_el.input('', clear=True)
                cleared = self.composer_cleared(editor_el)
            except Exception:
                cleared = False
        return bool(cleared)

    def editor_has_text(self, editor_el, expected_text):
        try:
            remain = self.tab.run_js(
                """
                const el = arguments[0];
                if (!el) return '';
                const val = (el.value !== undefined) ? el.value : (el.textContent || '');
                return String(val || '');
                """,
                editor_el,
            )
            current = self.deps._normalize_text_for_compare(remain)
            exp = self.deps._normalize_text_for_compare(expected_text)
            if not exp:
                return True
            if self.deps._is_link_only_message(exp):
                if not current:
                    btn = self.find_send_btn(rounds=1, timeout_each=0.8)
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

    def force_fill_dm_editor_text(self, editor_el, expected_text):
        text = str(expected_text or '')
        if not text:
            return False
        try:
            ok = self.tab.run_js(
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
            if ok and self.editor_has_text(editor_el, text):
                return True
        except Exception:
            pass
        try:
            editor_el.input(text, clear=True)
        except Exception:
            return False
        return self.editor_has_text(editor_el, text)

    def wait_send_button_after_input(self, editor_el, expected_text, link_mode=False):
        def _has_disabled_send_button():
            bound_disabled = self.get_bound_send_btn(require_enabled=False)
            if bound_disabled:
                try:
                    if not self.deps._is_element_actionable(bound_disabled):
                        return True
                except Exception:
                    pass
            try:
                state = self.tab.run_js(
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
                self.deps._refresh_dm_editor_state(self.tab, editor_el, expected_text)
                self.deps._poke_dm_editor_events(self.tab, editor_el)
            except Exception:
                pass
            try:
                self.tab.run_js(
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
            status_id = self.deps._pick_best_status_id(expected_text)
            while time.time() < deadline:
                btn = self.find_send_btn(rounds=1, timeout_each=0.45, require_enabled=True)
                try:
                    state = self.tab.run_js(
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
                self.deps._dm_humanized_idle(self.tab, 0.05, 0.12, '等待链接预览加载')
            return False

        if link_mode:
            _wait_link_preview_ready(timeout_sec=3.0)
        btn = self.find_send_btn(rounds=2, timeout_each=1.0, require_enabled=True)
        if btn:
            return btn
        if not link_mode:
            deadline = time.time() + max(0.6, float(self.deps.DM_TEXT_VERIFY_TIMEOUT_SEC))
            while time.time() < deadline:
                if self.editor_has_text(editor_el, expected_text):
                    self.deps._poke_dm_editor_events(self.tab, editor_el)
                btn = self.find_send_btn(rounds=1, timeout_each=0.6, require_enabled=True)
                if btn:
                    return btn
                self.deps._dm_humanized_idle(self.tab, 0.03, 0.1, '文本消息等待发送按钮')
            if self.editor_has_text(editor_el, expected_text) and _has_disabled_send_button():
                _nudge_editor_for_send_enable()
                self.deps._dm_humanized_idle(self.tab, 0.04, 0.12, '文本消息发送按钮唤醒后等待')
                btn = self.find_send_btn(rounds=2, timeout_each=0.8, require_enabled=True)
                if btn:
                    return btn
            return None
        if self.editor_has_text(editor_el, expected_text):
            if self.deps._poke_dm_editor_events(self.tab, editor_el):
                self.deps._dm_humanized_idle(self.tab, 0.04, 0.12, '链接输入确认后等待按钮')
            btn = self.find_send_btn(rounds=2, timeout_each=1.0, require_enabled=True)
            if btn:
                return btn
        if link_mode:
            try:
                current_text = str(self.tab.run_js(
                    """
                    const el = arguments[0];
                    if (!el) return '';
                    return String((el.value !== undefined) ? (el.value || '') : (el.textContent || ''));
                    """,
                    editor_el,
                ) or '')
            except Exception:
                current_text = ''
            if not self.deps._normalize_text_for_compare(current_text):
                self.deps._paste_dm_text_exact(self.tab, editor_el, expected_text)
                self.deps._dm_humanized_idle(self.tab, 0.05, 0.12, '链接回填后等待按钮')
            btn = self.find_send_btn(rounds=2, timeout_each=1.0, require_enabled=True)
            if btn:
                return btn
        return None
