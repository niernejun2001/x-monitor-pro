import random
import time


DM_PLATFORM_CLOSED_MSG = "该用户当前不可私信（平台限制或对方未开放私信）"
DM_PROFILE_NO_BUTTON_MSG = "该用户当前不可私信（资料页无私信入口）"
DM_COMPOSE_NO_RESULT_MSG = "该用户当前不可私信（新建私信搜索无结果）"


def mark_dm_unavailable_and_return(deps, handle_norm, reason):
    deps._mark_dm_unavailable(handle_norm)
    return None, reason


def load_dm_profile_page(tab, handle_norm, attempt, deps):
    if attempt == 0:
        tab.get(f"https://x.com/{handle_norm}")
        deps._wait_document_ready(tab, timeout=5.5)
        try:
            tab.wait.ele_displayed('tag:main', timeout=8)
        except Exception:
            pass
        time.sleep(random.uniform(0.45, 0.85))
        return True
    if attempt == 1:
        handled = deps._handle_dm_passcode_prompt(tab)
        if handled:
            time.sleep(random.uniform(0.35, 0.7))
        tab.get(f"https://x.com/{handle_norm}")
        deps._wait_document_ready(tab, timeout=5.2)
        try:
            tab.wait.ele_displayed('tag:main', timeout=6)
        except Exception:
            pass
        time.sleep(random.uniform(0.4, 0.8))
        return True
    try:
        tab.refresh()
        deps._wait_document_ready(tab, timeout=4.6)
        time.sleep(random.uniform(0.5, 1.0))
        return True
    except Exception:
        return False


def capture_dm_open_failure(
    tab,
    handle_norm,
    dm_btn_selectors,
    editor_selectors,
    *,
    open_attempts,
    headless_mode,
    dm_entry_mode,
    entry_path,
    entry_stage,
    deps,
):
    deps._capture_runtime_diagnostic(
        tab,
        "open_dm_editor_failed",
        err=f"handle={handle_norm}",
        selectors=dm_btn_selectors + editor_selectors,
        extra={
            "handle": handle_norm,
            "open_attempts": open_attempts,
            "headless_mode": bool(headless_mode),
            "dm_entry_mode": dm_entry_mode,
            "entry_path": entry_path,
            "entry_stage": entry_stage,
        }
    )
    return None, "未打开私信输入框（可能被页面状态打断）"


def try_open_dm_via_direct_compose(
    tab,
    handle_norm,
    *,
    wait_document_ready,
    dm_humanized_idle,
    handle_dm_passcode_prompt,
    wait_editor_or_closed,
    page_mentions_handle,
    wait_first_actionable,
    wait_first_visible,
    click_with_prompt_guard,
    try_rescue_dm_popup_func,
    inspect_direct_compose_picker_state_func,
    direct_compose_state_indicates_closed_func,
    log_headless_debug,
    log_to_ui,
):
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

    def compose_search_indicates_closed():
        state = inspect_direct_compose_picker_state_func(tab, handle_norm)
        return direct_compose_state_indicates_closed_func(state, handle_norm), state

    for idx, url in enumerate(compose_urls, start=1):
        entry_stage = f"open_{idx}"
        try:
            tab.get(url)
            wait_document_ready(tab, timeout=5.2)
            dm_humanized_idle(tab, 0.2, 0.45, f"直达私信入口加载{idx}")
        except Exception as e_open:
            log_headless_debug(f"直达私信入口打开失败({idx}): {e_open}")
            continue

        handled = handle_dm_passcode_prompt(tab)
        if handled:
            dm_humanized_idle(tab, 0.2, 0.45, "直达私信入口口令处理后等待")

        editor_now, editor_state = wait_editor_or_closed(timeout_sec=1.2)
        if editor_now and page_mentions_handle():
            return editor_now, "", f"compose_ready_{idx}"
        if editor_state == "closed":
            return None, "closed", entry_stage

        new_btn = wait_first_actionable(tab, new_msg_btn_selectors, timeout=1.6, poll=0.1)
        if new_btn:
            click_with_prompt_guard(tab, new_btn, "直达入口点击新消息")
            dm_humanized_idle(tab, 0.12, 0.28, "点击新消息后等待")

        recipient_input = wait_first_visible(tab, recipient_input_selectors, timeout=2.8, poll=0.1)
        if not recipient_input:
            if try_rescue_dm_popup_func(tab, handle_norm, log_headless_debug, log_to_ui):
                recipient_input = wait_first_visible(tab, recipient_input_selectors, timeout=1.8, poll=0.1)
            if not recipient_input:
                search_closed, search_state = compose_search_indicates_closed()
                if search_closed:
                    log_to_ui("debug", f"📨 未找到收件人输入框且命中禁发提示，判定不可私信: @{handle_norm} state={search_state}")
                    return None, DM_COMPOSE_NO_RESULT_MSG, f"recipient_input_closed_{idx}"
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
            continue

        dm_humanized_idle(tab, 0.2, 0.42, "输入收件人后等待候选")
        search_closed, search_state = compose_search_indicates_closed()
        if search_closed:
            log_to_ui("debug", f"📨 新建私信搜索无结果，判定不可私信: @{handle_norm} state={search_state}")
            return None, DM_COMPOSE_NO_RESULT_MSG, f"recipient_search_closed_{idx}"

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
            dm_humanized_idle(tab, 0.12, 0.28, "提交收件人后等待")
            search_closed, search_state = compose_search_indicates_closed()
            if search_closed:
                log_to_ui("debug", f"📨 提交收件人后仍无结果，判定不可私信: @{handle_norm} state={search_state}")
                return None, DM_COMPOSE_NO_RESULT_MSG, f"recipient_submit_closed_{idx}"

        next_btn = wait_first_actionable(tab, next_btn_selectors, timeout=1.3, poll=0.1)
        if next_btn:
            click_with_prompt_guard(tab, next_btn, "直达入口点击下一步")
            dm_humanized_idle(tab, 0.12, 0.3, "点击下一步后等待")
        else:
            search_closed, search_state = compose_search_indicates_closed()
            if search_closed:
                log_to_ui("debug", f"📨 未出现可用下一步且搜索无结果，判定不可私信: @{handle_norm} state={search_state}")
                return None, DM_COMPOSE_NO_RESULT_MSG, f"recipient_next_closed_{idx}"
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

        editor_now, editor_state = wait_editor_or_closed(timeout_sec=3.8)
        if editor_now and page_mentions_handle():
            return editor_now, "", f"compose_editor_ready_{idx}"
        if editor_state == "closed":
            return None, "closed", f"recipient_wait_closed_{idx}"
        search_closed, search_state = compose_search_indicates_closed()
        if search_closed:
            log_to_ui("debug", f"📨 等待编辑框期间搜索无结果，判定不可私信: @{handle_norm} state={search_state}")
            return None, DM_COMPOSE_NO_RESULT_MSG, f"recipient_wait_closed_{idx}"
        if editor_now:
            log_to_ui("debug", f"📨 新建私信命中了非目标会话，放弃当前编辑器: @{handle_norm}")
            return None, "", f"recipient_target_mismatch_{idx}"

    return None, "", "direct_compose_exhausted"


def try_open_dm_via_profile_click(
    tab,
    handle_norm,
    *,
    open_attempts,
    has_cannot_dm_hint,
    find_dm_btn,
    click_with_prompt_guard,
    wait_editor_or_closed,
    page_mentions_handle,
    try_rescue_dm_popup_func,
    log_headless_debug,
    log_to_ui,
    handle_dm_passcode_prompt,
    wait_document_ready,
    load_profile_page,
):
    profile_opened_rounds = 0
    dm_btn_seen = False

    for attempt in range(open_attempts):
        if attempt < 2:
            profile_opened_rounds += 1
        load_profile_page(tab, handle_norm, attempt)

        if has_cannot_dm_hint():
            return None, DM_PLATFORM_CLOSED_MSG, profile_opened_rounds, dm_btn_seen

        dm_btn = find_dm_btn()
        if not dm_btn:
            continue
        dm_btn_seen = True

        clicked_dm_btn, click_dm_err = click_with_prompt_guard(
            tab,
            dm_btn,
            "点击私信入口按钮",
        )
        if not clicked_dm_btn:
            log_to_ui("debug", f"📨 私信入口点击失败(尝试{attempt + 1}/{open_attempts}): {click_dm_err}")
            continue
        time.sleep(random.uniform(0.28, 0.62))

        editor, editor_state = wait_editor_or_closed(timeout_sec=1.4)
        if editor and page_mentions_handle():
            return editor, "", profile_opened_rounds, dm_btn_seen
        if editor_state == "closed":
            return None, DM_PLATFORM_CLOSED_MSG, profile_opened_rounds, dm_btn_seen

        if try_rescue_dm_popup_func(tab, handle_norm, log_headless_debug, log_to_ui):
            editor, editor_state = wait_editor_or_closed(timeout_sec=2.2)
            if editor and page_mentions_handle():
                return editor, "", profile_opened_rounds, dm_btn_seen
            if editor_state == "closed":
                return None, DM_PLATFORM_CLOSED_MSG, profile_opened_rounds, dm_btn_seen

        handled_after_click = handle_dm_passcode_prompt(tab)
        if handled_after_click:
            try:
                tab.get(f"https://x.com/{handle_norm}")
                wait_document_ready(tab, timeout=4.8)
                time.sleep(random.uniform(0.4, 0.8))
            except Exception:
                pass
            dm_btn_retry = find_dm_btn()
            if dm_btn_retry:
                click_with_prompt_guard(
                    tab,
                    dm_btn_retry,
                    "重试点击私信入口按钮",
                )
                time.sleep(random.uniform(0.4, 0.8))

        editor, editor_state = wait_editor_or_closed(timeout_sec=3.6)
        if editor and page_mentions_handle():
            return editor, "", profile_opened_rounds, dm_btn_seen
        if editor_state == "closed":
            return None, DM_PLATFORM_CLOSED_MSG, profile_opened_rounds, dm_btn_seen
        if has_cannot_dm_hint():
            return None, DM_PLATFORM_CLOSED_MSG, profile_opened_rounds, dm_btn_seen

    return None, "", profile_opened_rounds, dm_btn_seen
