import random
import re
import time


def open_dm_editor_for_handle(tab, handle, deps, ignore_cached_unavailable=False):
    normalize_handle = deps.normalize_handle
    _is_dm_unavailable_cached = deps._is_dm_unavailable_cached
    DM_PROFILE_BUTTON_SELECTORS = deps.DM_PROFILE_BUTTON_SELECTORS
    DM_EDITOR_SELECTORS = deps.DM_EDITOR_SELECTORS
    DM_ENTRY_MODE = deps.DM_ENTRY_MODE
    DM_PROFILE_NO_BUTTON_AS_CLOSED = deps.DM_PROFILE_NO_BUTTON_AS_CLOSED
    DM_REJECT_NEW_MESSAGE_OVERLAY = deps.DM_REJECT_NEW_MESSAGE_OVERLAY
    DM_EDITOR_OPEN_RETRY_HEADLESS = deps.DM_EDITOR_OPEN_RETRY_HEADLESS
    DM_EDITOR_OPEN_RETRY_NORMAL = deps.DM_EDITOR_OPEN_RETRY_NORMAL
    _capture_runtime_diagnostic = deps._capture_runtime_diagnostic
    _click_with_prompt_guard = deps._click_with_prompt_guard
    _dm_humanized_idle = deps._dm_humanized_idle
    _handle_dm_passcode_prompt = deps._handle_dm_passcode_prompt
    _mark_dm_unavailable = deps._mark_dm_unavailable
    _wait_document_ready = deps._wait_document_ready
    _wait_first_actionable = deps._wait_first_actionable
    _wait_first_visible = deps._wait_first_visible
    headless_mode = deps.headless_mode
    log_headless_debug = deps.log_headless_debug
    log_to_ui = deps.log_to_ui
    """打开某用户私信编辑框，返回编辑框元素。"""
    handle_norm = normalize_handle(handle)
    if not handle_norm:
        return None, "缺少目标用户handle"
    if (not ignore_cached_unavailable) and _is_dm_unavailable_cached(handle_norm):
        return None, "该用户当前不可私信（缓存命中）"
    entry_path = "init"
    entry_stage = "init"

    dm_btn_selectors = list(DM_PROFILE_BUTTON_SELECTORS)
    editor = None
    dm_btn_seen = False
    profile_opened_rounds = 0
    editor_selectors = list(DM_EDITOR_SELECTORS)
    cannot_dm_keywords = [
        "cannot send direct messages",
        "can't be messaged",
        "unable to message",
        "you can’t message this account",
        "该用户无法接收私信",
        "无法向该用户发送私信",
        "不能给该用户发私信",
        "无法发送私信",
    ]

    def _get_body_text():
        try:
            return (tab.ele('tag:body', timeout=0.6).text or "").lower()
        except Exception:
            return ""

    def _has_cannot_dm_hint():
        body = _get_body_text()
        return any(k in body for k in cannot_dm_keywords)

    def _find_dm_btn():
        return _wait_first_actionable(tab, dm_btn_selectors, timeout=1.8, poll=0.1)

    def _is_valid_dm_editor(cand):
        try:
            ok = tab.run_js(
                """
                const el = arguments[0];
                const rejectOverlay = !!arguments[1];
                if (!el) return false;
                const low = (s) => String(s || '').toLowerCase();
                const attrText = [
                  el.getAttribute('aria-label'),
                  el.getAttribute('placeholder'),
                  el.getAttribute('data-testid'),
                  el.getAttribute('name')
                ].map(low).join(' ');
                const rejectKeys = [
                  'search', '搜索', 'people', 'person', 'group', 'groups',
                  'recipient', '收件人', 'to', 'new message', '新消息'
                ];
                if (rejectKeys.some((k) => attrText.includes(k))) return false;
                const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : { top: 0, width: 0, height: 0 };
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
                const hasComposer = !!root.querySelector(
                  '[data-testid="dmComposerTextInput"],textarea[data-testid="dm-composer-textarea"]'
                );
                const hasSend = !!root.querySelector(
                  '[data-testid="dm-composer-send-button"],[data-testid="dmComposerSendButton"],button[data-testid*="dm-composer-send"]'
                );
                if (rejectOverlay) {
                  // 新私信搜索浮层：只允许进入带发送区的真实会话编辑器
                  if (hasSearchScene && !hasSend) return false;
                  // 顶部搜索输入框通常位于页面上半区且没有发送区，过滤掉
                  if (!hasSend && rect && Number(rect.top || 0) < (window.innerHeight * 0.45)) return false;
                }
                if (hasComposer) return true;
                if (hasSend) return true;
                return false;
                """,
                cand,
                DM_REJECT_NEW_MESSAGE_OVERLAY,
            )
            return bool(ok)
        except Exception:
            return False

    def _find_editor(timeout_each=2.5):
        for selector in editor_selectors:
            try:
                cand = tab.ele(selector, timeout=timeout_each)
                if cand and cand.states.is_displayed and _is_valid_dm_editor(cand):
                    return cand
            except Exception:
                continue
        return None

    def _wait_editor_or_closed(timeout_sec=3.2):
        deadline = time.time() + max(0.6, float(timeout_sec))
        while time.time() < deadline:
            if _has_cannot_dm_hint():
                return None, "closed"
            editor_now = _find_editor(timeout_each=0.5)
            if editor_now:
                return editor_now, ""
            time.sleep(0.08)
        return None, ""

    def _try_open_dm_via_direct_compose():
        """优先走 messages/compose 直达会话，避免资料页按钮点击后落到消息列表小窗。"""
        nonlocal entry_path, entry_stage
        compose_urls = ["https://x.com/messages/compose", "https://x.com/messages"]
        recipient_input_selectors = [
            'css:[role="dialog"] input[placeholder*="Search"]',
            'css:[role="dialog"] input[placeholder*="搜索"]',
            'css:[role="dialog"] input[aria-label*="Search"]',
            'css:[role="dialog"] input[aria-label*="搜索"]',
            'css:[data-testid*="typeahead"] input',
            'css:[data-testid*="Typeahead"] input',
            'css:main input[placeholder*="Search"]',
            'css:main input[placeholder*="搜索"]',
        ]
        next_btn_selectors = [
            'css:button[data-testid="nextButton"]',
            'css:[role="dialog"] [data-testid*="next"]',
            'css:[data-testid*="DM"] [data-testid*="next"]',
            'css:[role="dialog"] button[aria-label*="Next"]',
            'css:[role="dialog"] button[aria-label*="下一步"]',
            'css:[role="dialog"] button[aria-label*="继续"]',
        ]
        new_msg_btn_selectors = [
            'css:a[href*="/messages/compose"]',
            'css:[data-testid*="NewDM"]',
            'css:[data-testid*="newDM"]',
            'css:button[aria-label*="新消息"]',
            'css:button[aria-label*="New message"]',
        ]

        def _page_mentions_handle():
            try:
                hit = tab.run_js(
                    """
                    const handle = String(arguments[0] || '').replace(/^@+/, '').toLowerCase();
                    if (!handle) return false;
                    const isVisible = (el) => {
                      if (!el) return false;
                      const st = window.getComputedStyle(el);
                      if (!st) return false;
                      if (st.display === 'none' || st.visibility === 'hidden') return false;
                      const r = el.getBoundingClientRect();
                      return r.width > 0 && r.height > 0;
                    };
                    const roots = Array.from(document.querySelectorAll('[role="dialog"],main,[data-testid*="DM"],[data-testid*="dm"]'));
                    for (const root of roots) {
                      if (!isVisible(root)) continue;
                      const txt = String(root.innerText || root.textContent || '').toLowerCase();
                      if (!txt) continue;
                      if (txt.includes('@' + handle) || txt.includes(handle)) return true;
                    }
                    return false;
                    """,
                    handle_norm,
                )
                return bool(hit)
            except Exception:
                return False

        for idx, url in enumerate(compose_urls, start=1):
            entry_path = "direct_compose"
            entry_stage = f"open_{idx}"
            try:
                tab.get(url)
                _wait_document_ready(tab, timeout=5.2)
                _dm_humanized_idle(tab, 0.2, 0.45, f"直达私信入口加载{idx}")
            except Exception as e_open:
                log_headless_debug(f"直达私信入口打开失败({idx}): {e_open}")
                continue

            handled = _handle_dm_passcode_prompt(tab)
            if handled:
                _dm_humanized_idle(tab, 0.2, 0.45, "直达私信入口口令处理后等待")

            editor_now, editor_state = _wait_editor_or_closed(timeout_sec=1.2)
            if editor_now and _page_mentions_handle():
                entry_stage = f"compose_ready_{idx}"
                return editor_now, ""
            if editor_state == "closed":
                return None, "closed"

            # messages 首页场景：主动点“新消息”
            new_btn = _wait_first_actionable(tab, new_msg_btn_selectors, timeout=1.6, poll=0.1)
            if new_btn:
                _click_with_prompt_guard(tab, new_btn, "直达入口点击新消息")
                _dm_humanized_idle(tab, 0.12, 0.28, "点击新消息后等待")

            recipient_input = _wait_first_visible(tab, recipient_input_selectors, timeout=2.8, poll=0.1)
            if not recipient_input:
                entry_stage = f"recipient_input_missing_{idx}"
                continue

            try:
                recipient_input.click()
            except Exception:
                pass
            typed_ok = False
            try:
                recipient_input.input(f"@{handle_norm}", clear=True)
                typed_ok = True
            except Exception:
                try:
                    tab.run_js(
                        """
                        const el = arguments[0];
                        const text = String(arguments[1] || '');
                        if (!el) return false;
                        el.focus();
                        if (el.value !== undefined) {
                          el.value = text;
                          el.dispatchEvent(new Event('input', { bubbles: true }));
                          el.dispatchEvent(new Event('change', { bubbles: true }));
                          return true;
                        }
                        return false;
                        """,
                        recipient_input,
                        f"@{handle_norm}",
                    )
                    typed_ok = True
                except Exception:
                    typed_ok = False
            if not typed_ok:
                entry_stage = f"recipient_input_failed_{idx}"
                continue

            _dm_humanized_idle(tab, 0.2, 0.42, "输入收件人后等待候选")

            selected = False
            try:
                pick_state = tab.run_js(
                    """
                    const handle = String(arguments[0] || '').replace(/^@+/, '').toLowerCase();
                    const isVisible = (el) => {
                      if (!el) return false;
                      const st = window.getComputedStyle(el);
                      if (!st) return false;
                      if (st.display === 'none' || st.visibility === 'hidden') return false;
                      const r = el.getBoundingClientRect();
                      return r.width > 0 && r.height > 0;
                    };
                    const clickNode = (el) => {
                      if (!el) return false;
                      const node = el.closest('a,button,[role="button"],[role="option"],[role="link"]') || el;
                      if (!isVisible(node)) return false;
                      try { node.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                      try { node.click(); } catch (e) { return false; }
                      return true;
                    };
                    const roots = Array.from(document.querySelectorAll('[role="dialog"],[data-testid*="typeahead"],[data-testid*="Typeahead"],main'));
                    for (const root of roots) {
                      if (!isVisible(root)) continue;
                      const nodes = Array.from(root.querySelectorAll('[role="option"],[data-testid*="TypeaheadUser"],[data-testid*="conversation"],a,button,[role="button"]'));
                      for (const n of nodes) {
                        if (!isVisible(n)) continue;
                        const txt = String(n.innerText || n.textContent || '').trim().toLowerCase();
                        if (!txt) continue;
                        if (!txt.includes('@' + handle) && !txt.includes(handle)) continue;
                        if (clickNode(n)) return { selected: true };
                      }
                    }
                    return { selected: false };
                    """,
                    handle_norm,
                ) or {}
                selected = bool(pick_state.get("selected", False))
            except Exception:
                selected = False

            if not selected:
                try:
                    recipient_input.input('\n', clear=False)
                except Exception:
                    pass

            next_btn = _wait_first_actionable(tab, next_btn_selectors, timeout=1.3, poll=0.1)
            if next_btn:
                _click_with_prompt_guard(tab, next_btn, "直达入口点击下一步")
                _dm_humanized_idle(tab, 0.12, 0.3, "点击下一步后等待")
            else:
                try:
                    tab.run_js(
                        """
                        const isVisible = (el) => {
                          if (!el) return false;
                          const st = window.getComputedStyle(el);
                          if (!st) return false;
                          if (st.display === 'none' || st.visibility === 'hidden') return false;
                          const r = el.getBoundingClientRect();
                          return r.width > 0 && r.height > 0;
                        };
                        const keys = ['next', '下一步', '继续', '开始'];
                        for (const btn of Array.from(document.querySelectorAll('[role="dialog"] button,[role="dialog"] [role="button"]'))) {
                          if (!isVisible(btn)) continue;
                          if (btn.disabled || btn.getAttribute('aria-disabled') === 'true') continue;
                          const txt = String(btn.innerText || btn.textContent || '').trim().toLowerCase();
                          if (!txt) continue;
                          if (!keys.some((k) => txt.includes(k))) continue;
                          btn.click();
                          return true;
                        }
                        return false;
                        """
                    )
                except Exception:
                    pass

            editor_now, editor_state = _wait_editor_or_closed(timeout_sec=3.8)
            if editor_now:
                entry_stage = f"compose_editor_ready_{idx}"
                return editor_now, ""
            if editor_state == "closed":
                return None, "closed"

        return None, ""

    def _try_rescue_dm_popup():
        """
        私信入口点击后若未直接出现输入框，尝试点击消息小窗中的“新消息/目标会话”入口。
        兼容 X 新版点击私信后先弹出会话列表而非直接进入 composer 的场景。
        """
        try:
            result = tab.run_js(
                """
                const handle = String(arguments[0] || '').replace(/^@+/, '').trim().toLowerCase();
                const isVisible = (el) => {
                  if (!el) return false;
                  const st = window.getComputedStyle(el);
                  if (!st) return false;
                  if (st.display === 'none' || st.visibility === 'hidden') return false;
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                };
                const isClickable = (el) => {
                  if (!el) return false;
                  if (el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
                  const role = String(el.getAttribute('role') || '').toLowerCase();
                  const tag = String(el.tagName || '').toLowerCase();
                  if (tag === 'button' || tag === 'a') return true;
                  if (role === 'button' || role === 'link') return true;
                  return !!el.closest('a,button,[role="button"],[role="link"]');
                };
                const clickEl = (el) => {
                  if (!el) return false;
                  const node = (isClickable(el) ? el : (el.closest('a,button,[role="button"],[role="link"]') || el));
                  if (!node || !isVisible(node)) return false;
                  try { node.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                  const evOpts = { bubbles: true, cancelable: true, composed: true, view: window };
                  try { node.dispatchEvent(new MouseEvent('pointerdown', evOpts)); } catch (e) {}
                  try { node.dispatchEvent(new MouseEvent('mousedown', evOpts)); } catch (e) {}
                  try { node.dispatchEvent(new MouseEvent('mouseup', evOpts)); } catch (e) {}
                  try { node.click(); } catch (e) { return false; }
                  return true;
                };

                const dmSelectors = [
                  '[data-testid="sendDMFromProfile"]',
                  'button[data-testid="sendDMFromProfile"]',
                  '[data-testid="sendDM"]',
                  'button[data-testid="sendDM"]',
                  'a[href*="/messages/compose"]',
                  '[data-testid*="NewDM"]',
                  '[data-testid*="newDM"]',
                  'button[aria-label*="新消息"]',
                  'button[aria-label*="Message"]',
                  '[role="button"][aria-label*="Message"]'
                ];
                for (const s of dmSelectors) {
                  const nodes = Array.from(document.querySelectorAll(s));
                  for (const n of nodes) {
                    if (!isVisible(n)) continue;
                    if (!clickEl(n)) continue;
                    return { clicked: true, path: 'selector', selector: s };
                  }
                }

                const convoRoots = Array.from(document.querySelectorAll(
                  '[role="dialog"],[data-testid*="DM"],[data-testid*="dm"],[data-testid*="sheet"],[aria-label*="Messages"],[aria-label*="消息"]'
                )).filter(isVisible);
                for (const root of convoRoots) {
                  const convoNodes = Array.from(root.querySelectorAll(
                    '[data-testid*="conversation"],a[href*="/messages/"],div[role="link"],button,[role="button"]'
                  ));
                  for (const n of convoNodes) {
                    if (!isVisible(n)) continue;
                    const txt = String(n.innerText || n.textContent || '').toLowerCase();
                    if (!txt) continue;
                    if (handle && !txt.includes(handle)) continue;
                    if (!clickEl(n)) continue;
                    return { clicked: true, path: 'conversation', selector: 'conversation_node' };
                  }
                }

                const dialogButtons = Array.from(document.querySelectorAll(
                  '[role="dialog"] button,[role="dialog"] [role="button"],[data-testid*="sheet"] button,[data-testid*="DM"] button'
                ));
                const btnKeywords = ['message', '发消息', '私信', 'new message', '新消息', 'next', '继续', 'chat'];
                for (const n of dialogButtons) {
                  if (!isVisible(n)) continue;
                  const txt = String(n.innerText || n.textContent || '').trim().toLowerCase();
                  if (!txt) continue;
                  if (!btnKeywords.some((k) => txt.includes(k))) continue;
                  if (!clickEl(n)) continue;
                  return { clicked: true, path: 'dialog_button', selector: 'dialog_btn' };
                }
                return { clicked: false, path: 'none' };
                """,
                handle_norm,
            ) or {}
        except Exception as e:
            log_headless_debug(f"私信弹窗兜底点击异常: {e}")
            return False

        if bool(result.get("clicked")):
            log_to_ui(
                "debug",
                f"📨 私信弹窗兜底点击成功: path={result.get('path', '')} selector={result.get('selector', '')}"
            )
            time.sleep(random.uniform(0.2, 0.45))
            return True
        return False

    if DM_ENTRY_MODE in {"direct_compose_first", "dual_probe"}:
        editor_direct, direct_state = _try_open_dm_via_direct_compose()
        if editor_direct:
            return editor_direct, ""
        if direct_state == "closed":
            _mark_dm_unavailable(handle_norm)
            return None, "该用户当前不可私信（平台限制或对方未开放私信）"

    entry_path = "profile_click"
    open_attempts = DM_EDITOR_OPEN_RETRY_HEADLESS if headless_mode else DM_EDITOR_OPEN_RETRY_NORMAL
    for attempt in range(open_attempts):
        if attempt == 0:
            profile_opened_rounds += 1
            tab.get(f"https://x.com/{handle_norm}")
            _wait_document_ready(tab, timeout=5.5)
            try:
                tab.wait.ele_displayed('tag:main', timeout=8)
            except Exception:
                pass
            time.sleep(random.uniform(0.45, 0.85))
        elif attempt == 1:
            # 第一次失败后重进资料页，规避临时页面状态拦截
            handled = _handle_dm_passcode_prompt(tab)
            if handled:
                time.sleep(random.uniform(0.35, 0.7))
            profile_opened_rounds += 1
            tab.get(f"https://x.com/{handle_norm}")
            _wait_document_ready(tab, timeout=5.2)
            try:
                tab.wait.ele_displayed('tag:main', timeout=6)
            except Exception:
                pass
            time.sleep(random.uniform(0.4, 0.8))
        else:
            try:
                tab.refresh()
                _wait_document_ready(tab, timeout=4.6)
                time.sleep(random.uniform(0.5, 1.0))
            except Exception:
                pass

        if _has_cannot_dm_hint():
            _mark_dm_unavailable(handle_norm)
            return None, "该用户当前不可私信（平台限制或对方未开放私信）"

        dm_btn = _find_dm_btn()
        if not dm_btn:
            continue
        dm_btn_seen = True

        clicked_dm_btn, click_dm_err = _click_with_prompt_guard(
            tab,
            dm_btn,
            "点击私信入口按钮",
            refetch_selectors=dm_btn_selectors,
        )
        if not clicked_dm_btn:
            log_to_ui("debug", f"📨 私信入口点击失败(尝试{attempt + 1}/{open_attempts}): {click_dm_err}")
            continue
        time.sleep(random.uniform(0.28, 0.62))

        # 第一轮快速检查：若未进入编辑框，尝试识别并点击消息小窗会话入口。
        editor, editor_state = _wait_editor_or_closed(timeout_sec=1.4)
        if editor:
            return editor, ""
        if editor_state == "closed":
            _mark_dm_unavailable(handle_norm)
            return None, "该用户当前不可私信（平台限制或对方未开放私信）"
        if _try_rescue_dm_popup():
            editor, editor_state = _wait_editor_or_closed(timeout_sec=2.2)
            if editor:
                return editor, ""
            if editor_state == "closed":
                _mark_dm_unavailable(handle_norm)
                return None, "该用户当前不可私信（平台限制或对方未开放私信）"

        handled_after_click = _handle_dm_passcode_prompt(tab)
        if handled_after_click:
            # 保留二次点击兜底，兼容被打断后回到资料页的场景
            try:
                tab.get(f"https://x.com/{handle_norm}")
                _wait_document_ready(tab, timeout=4.8)
                time.sleep(random.uniform(0.4, 0.8))
            except Exception:
                pass
            dm_btn_retry = _find_dm_btn()
            if dm_btn_retry:
                _click_with_prompt_guard(
                    tab,
                    dm_btn_retry,
                    "重试点击私信入口按钮",
                    refetch_selectors=dm_btn_selectors,
                )
                time.sleep(random.uniform(0.4, 0.8))

        editor, editor_state = _wait_editor_or_closed(timeout_sec=3.6)
        if editor:
            return editor, ""
        if editor_state == "closed":
            _mark_dm_unavailable(handle_norm)
            return None, "该用户当前不可私信（平台限制或对方未开放私信）"
        if _has_cannot_dm_hint():
            _mark_dm_unavailable(handle_norm)
            return None, "该用户当前不可私信（平台限制或对方未开放私信）"

    if _has_cannot_dm_hint():
        _mark_dm_unavailable(handle_norm)
        return None, "该用户当前不可私信（平台限制或对方未开放私信）"

    if (
        DM_PROFILE_NO_BUTTON_AS_CLOSED
        and profile_opened_rounds > 0
        and (not dm_btn_seen)
    ):
        _mark_dm_unavailable(handle_norm)
        return None, "该用户当前不可私信（资料页无私信入口）"

    # profile_first 模式下，只有在资料页入口失败时才回退到直达私信搜索路径。
    if DM_ENTRY_MODE == "profile_first":
        editor_direct_fallback, direct_state = _try_open_dm_via_direct_compose()
        if editor_direct_fallback:
            log_to_ui("debug", f"📨 资料页私信入口失败，已回退直达私信入口: @{handle_norm}")
            return editor_direct_fallback, ""
        if direct_state == "closed":
            _mark_dm_unavailable(handle_norm)
            return None, "该用户当前不可私信（平台限制或对方未开放私信）"

    _capture_runtime_diagnostic(
        tab,
        "open_dm_editor_failed",
        err=f"handle={handle_norm}",
        selectors=dm_btn_selectors + editor_selectors,
        extra={
            "handle": handle_norm,
            "open_attempts": open_attempts,
            "headless_mode": bool(headless_mode),
            "dm_entry_mode": DM_ENTRY_MODE,
            "entry_path": entry_path,
            "entry_stage": entry_stage,
        }
    )
    return None, "未打开私信输入框（可能被页面状态打断）"
