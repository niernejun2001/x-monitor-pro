import time


def inspect_direct_compose_picker_state(tab, handle_norm):
    try:
        state = tab.run_js(
            """
            const handle = String(arguments[0] || '').replace(/^@+/, '').trim().toLowerCase();
            const low = (v) => String(v || '').toLowerCase();
            const isVisible = (el) => {
              if (!el) return false;
              const st = window.getComputedStyle(el);
              if (!st) return false;
              if (st.display === 'none' || st.visibility === 'hidden') return false;
              const r = el.getBoundingClientRect();
              return r.width > 0 && r.height > 0;
            };
            const roots = Array.from(document.querySelectorAll('[role="dialog"],[data-testid*="typeahead"],[data-testid*="Typeahead"],main'))
              .filter(isVisible);
            const noResultHints = [
              'no results',
              'no people found',
              'no user found',
              'try searching for people',
              '未找到',
              '没有结果',
              '无结果',
              '找不到',
              '搜索无结果',
            ];
            const nextHints = ['next', '下一步', '继续', '开始'];
            let searchScene = false;
            let noResults = false;
            let candidateCount = 0;
            let exactMatch = false;
            let nextVisible = false;
            let nextDisabled = false;
            let typedValue = '';

            for (const root of roots) {
              const rootText = low(root.innerText || root.textContent || '');
              if (
                rootText.includes('new message') ||
                rootText.includes('创建一条私信') ||
                rootText.includes('创建私信') ||
                rootText.includes('搜索私信') ||
                rootText.includes('search direct messages') ||
                rootText.includes('recipient')
              ) {
                searchScene = true;
              }
              if (noResultHints.some((k) => rootText.includes(k))) {
                noResults = true;
              }

              const inputs = Array.from(root.querySelectorAll('input,textarea')).filter(isVisible);
              for (const input of inputs) {
                const val = low(input.value || input.getAttribute('value') || '');
                if (val && !typedValue) {
                  typedValue = val;
                }
              }

              const nodes = Array.from(root.querySelectorAll('[role="option"],[data-testid*="TypeaheadUser"],[data-testid*="conversation"],a,button,[role="button"]'))
                .filter(isVisible);
              for (const n of nodes) {
                const txt = low((n.innerText || n.textContent || '').trim());
                if (!txt) continue;
                if (noResultHints.some((k) => txt.includes(k))) {
                  noResults = true;
                  continue;
                }
                if (nextHints.some((k) => txt.includes(k))) {
                  nextVisible = true;
                  if (n.disabled || n.getAttribute('aria-disabled') === 'true') {
                    nextDisabled = true;
                  }
                  continue;
                }
                candidateCount += 1;
                if (handle && (txt.includes('@' + handle) || txt.includes(handle))) {
                  exactMatch = true;
                }
              }
            }

            return {
              searchScene: !!searchScene,
              noResults: !!noResults,
              candidateCount: Number(candidateCount || 0),
              exactMatch: !!exactMatch,
              nextVisible: !!nextVisible,
              nextDisabled: !!nextDisabled,
              typedValue: String(typedValue || ''),
            };
            """,
            handle_norm,
        ) or {}
    except Exception:
        state = {}
    return {
        'search_scene': bool(state.get('searchScene')),
        'no_results': bool(state.get('noResults')),
        'candidate_count': int(state.get('candidateCount', 0) or 0),
        'exact_match': bool(state.get('exactMatch')),
        'next_visible': bool(state.get('nextVisible')),
        'next_disabled': bool(state.get('nextDisabled')),
        'typed_value': str(state.get('typedValue', '') or '').strip().lower(),
    }


def direct_compose_state_indicates_closed(state, handle_norm):
    handle_norm = str(handle_norm or '').strip().lstrip('@').lower()
    typed_value = str((state or {}).get('typed_value', '') or '').strip().lower()
    no_results = bool((state or {}).get('no_results'))
    exact_match = bool((state or {}).get('exact_match'))
    candidate_count = int((state or {}).get('candidate_count', 0) or 0)
    next_visible = bool((state or {}).get('next_visible'))
    next_disabled = bool((state or {}).get('next_disabled'))
    search_scene = bool((state or {}).get('search_scene'))
    typed_handle = bool(handle_norm) and (handle_norm in typed_value)
    if no_results and typed_handle:
        return True
    if search_scene and typed_handle and (not exact_match) and candidate_count <= 0 and next_visible and next_disabled:
        return True
    return False


def get_body_text(tab):
    try:
        return (tab.ele('tag:body', timeout=0.6).text or "").lower()
    except Exception:
        return ""


def has_cannot_dm_hint(tab, cannot_dm_keywords):
    body = get_body_text(tab)
    return any(k in body for k in (cannot_dm_keywords or []))


def page_mentions_handle(tab, handle_norm):
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
            const roots = Array.from(document.querySelectorAll('[role="dialog"],main,[data-testid*="DM"],[data-testid*="dm"],header'));
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


def is_valid_dm_editor(tab, cand, reject_overlay):
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
              if (hasSearchScene && !hasSend) return false;
              if (!hasSend && rect && Number(rect.top || 0) < (window.innerHeight * 0.45)) return false;
            }
            if (hasComposer) return true;
            if (hasSend) return true;
            return false;
            """,
            cand,
            reject_overlay,
        )
        return bool(ok)
    except Exception:
        return False


def find_dm_editor(tab, editor_selectors, reject_overlay, timeout_each=2.5):
    for selector in list(editor_selectors or []):
        try:
            cand = tab.ele(selector, timeout=timeout_each)
            if cand and cand.states.is_displayed and is_valid_dm_editor(tab, cand, reject_overlay):
                return cand
        except Exception:
            continue
    return None


def wait_dm_editor_or_closed(tab, editor_selectors, reject_overlay, cannot_dm_keywords, timeout_sec=3.2):
    deadline = time.time() + max(0.6, float(timeout_sec))
    while time.time() < deadline:
        if has_cannot_dm_hint(tab, cannot_dm_keywords):
            return None, "closed"
        editor_now = find_dm_editor(tab, editor_selectors, reject_overlay, timeout_each=0.5)
        if editor_now:
            return editor_now, ""
        time.sleep(0.08)
    return None, ""


def try_rescue_dm_popup(tab, handle_norm, log_headless_debug, log_to_ui):
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
