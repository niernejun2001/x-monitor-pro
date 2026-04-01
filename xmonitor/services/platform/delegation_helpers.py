import re
import time

ACCOUNT_SWITCHER_SELECTORS = [
    'css:[data-testid="SideNav_AccountSwitcher_Button"]',
    'css:button[data-testid="SideNav_AccountSwitcher_Button"]',
    'css:div[data-testid="SideNav_AccountSwitcher_Button"]',
]

CONFIRM_KEYWORDS = ['切换', 'switch', '确认', 'confirm', '是', 'yes', '好的']
RESERVED_PROFILE_ROUTES = {'home', 'notifications', 'explore', 'messages', 'compose', 'i'}


def extract_handle_from_text(text):
    match = re.search(r'@([A-Za-z0-9_]{1,30})', str(text or ''))
    return match.group(1).lower() if match else ''


def extract_profile_handle_from_href(href):
    match = re.search(r'/([A-Za-z0-9_]{1,30})/?$', str(href or '').strip())
    if not match:
        return ''
    handle = match.group(1).lower()
    return '' if handle in RESERVED_PROFILE_ROUTES else handle


def find_account_menu_button(page, *, sleep_fn=time.sleep, selectors=None, attempts=3, timeout=1.5):
    selectors = list(selectors or ACCOUNT_SWITCHER_SELECTORS)
    try:
        page.run_js('window.scrollTo(0, document.body.scrollHeight);')
        sleep_fn(0.4)
    except Exception:
        pass

    menu_btn = None
    for _ in range(max(1, int(attempts))):
        for selector in selectors:
            try:
                candidate = page.ele(selector, timeout=timeout)
                if candidate and candidate.states.is_displayed:
                    menu_btn = candidate
                    break
            except Exception:
                pass
        if menu_btn:
            break
        sleep_fn(0.8)
    return menu_btn


def find_matching_delegated_user_cell(page, target_clean, *, log_to_ui, sleep_fn=time.sleep, attempts=3, timeout=1.5):
    user_cells = []
    for _ in range(max(1, int(attempts))):
        try:
            user_cells = page.eles('css:[data-testid="UserCell"]', timeout=timeout)
        except Exception:
            user_cells = []
        if user_cells:
            break
        sleep_fn(0.8)
    log_to_ui("info", f"   找到 {len(user_cells)} 个账户选项...")

    found = None
    for cell in user_cells:
        try:
            cell_text = (cell.text or '').strip()
            cell_html = (cell.html or '').strip()
            combined_text = f"{cell_text} {cell_html}".lower()
            cell_handle = extract_handle_from_text(combined_text)
            direct_hit = cell_handle == target_clean
            fallback_hit = re.search(rf'@?{re.escape(target_clean)}\b', combined_text) is not None
            if (direct_hit or fallback_hit) and cell.states.is_displayed:
                found = cell
                log_to_ui("success", f"   ✅ 找到目标账户: {cell_text.splitlines()[0]}")
                break
        except Exception:
            pass
    return found, user_cells


def log_available_user_cells(user_cells, *, log_to_ui):
    for cell in user_cells or []:
        cell_text = (getattr(cell, 'text', '') or '').replace(chr(10), ' ')
        handle = extract_handle_from_text(cell_text.lower())
        handle_hint = f"@{handle}" if handle else "无@handle"
        log_to_ui("info", f"   - 可选: {handle_hint} | {cell_text[:60]}")


def safe_click_target(page, target, *, log_to_ui, label):
    errors = []
    click_fn = getattr(target, 'click', None)
    if callable(click_fn):
        try:
            click_fn()
            return True
        except Exception as exc:
            errors.append(f'element.click(): {exc}')
    try:
        page.run_js('arguments[0].click()', target)
        return True
    except Exception as exc:
        errors.append(f'page.run_js(): {exc}')
    log_to_ui('error', f'❌ {label}失败: {" | ".join(errors)}')
    return False


def click_visible_confirm_button(page, *, log_to_ui, sleep_fn=time.sleep, timeout=2):
    try:
        buttons = page.eles('tag:button', timeout=timeout)
        log_to_ui("info", f"   发现 {len(buttons)} 个按钮，查找确认按钮...")
        for btn in buttons:
            btn_text = (btn.text or '').strip()
            if any(kw.lower() in btn_text.lower() for kw in CONFIRM_KEYWORDS):
                if btn.states.is_displayed:
                    log_to_ui("success", f"   ✅ 找到确认按钮: {btn_text}")
                    sleep_fn(0.5)
                    if not safe_click_target(page, btn, log_to_ui=log_to_ui, label='点击确认按钮'):
                        return False
                    sleep_fn(2)
                    log_to_ui("success", "✅ 确认按钮已点击")
                    return True
    except Exception as e:
        log_to_ui("warn", f"⚠️ 处理弹窗出错: {str(e)}")
        return False
    return None
