import re
import time

from xmonitor.services.platform.delegation_helpers import (
    ACCOUNT_SWITCHER_SELECTORS,
    click_visible_confirm_button,
    extract_handle_from_text,
    extract_profile_handle_from_href,
    find_account_menu_button,
    find_matching_delegated_user_cell,
    log_available_user_cells,
    safe_click_target,
)


def switch_to_delegated_account(page, target_account, deps):
    log_to_ui = deps.log_to_ui
    normalize_handle = deps.normalize_handle
    get_current_account_handle = deps.get_current_account_handle
    """
    切换到委派账户
    步骤：
    1. 点击左下角账户菜单按钮
    2. 等待菜单出现
    3. 找到匹配 target_account 的账户
    4. 点击该div
    5. 处理弹窗确认
    """
    try:
        log_to_ui("info", "=" * 60)
        log_to_ui("info", f"🔄 开始切换到委派账户: {target_account}")
        log_to_ui("info", "=" * 60)

        if not target_account:
            log_to_ui("error", "❌ 未指定委派账户用户名")
            return False

        target_clean = normalize_handle(target_account)
        current_handle = get_current_account_handle(page)
        if current_handle and current_handle == target_clean:
            log_to_ui("success", f"✅ 当前已是目标委派账户 @{target_clean}，跳过切换")
            return True

        # 步骤1: 点击左下角账户菜单
        log_to_ui("info", "🔍 步骤1: 点击左下角账户菜单...")
        try:
            menu_btn = find_account_menu_button(page, sleep_fn=time.sleep, selectors=ACCOUNT_SWITCHER_SELECTORS)
            if not menu_btn:
                log_to_ui("error", "❌ 未找到账户菜单按钮")
                return False

            log_to_ui("success", "✅ 找到菜单按钮，点击中...")
            if not safe_click_target(page, menu_btn, log_to_ui=log_to_ui, label='点击菜单按钮'):
                return False
            log_to_ui("info", "⏳ 等待菜单内容加载...")
            time.sleep(4)  # 保持较长等待，确保菜单完全渲染
            log_to_ui("success", "✅ 菜单已打开，继续扫描...")
        except Exception as e:
            log_to_ui("error", f"❌ 点击菜单失败: {str(e)}")
            return False

        # 步骤2: 在菜单中查找匹配的账户
        log_to_ui("info", f"🔍 步骤2: 查找账户匹配 '{target_account}'...")
        try:
            found_delegated, user_cells = find_matching_delegated_user_cell(
                page,
                target_clean,
                log_to_ui=log_to_ui,
                sleep_fn=time.sleep,
            )
            if not found_delegated:
                log_to_ui("error", f"❌ 未找到匹配 '{target_account}' 的账户")
                log_available_user_cells(user_cells, log_to_ui=log_to_ui)
                return False

        except Exception as e:
            log_to_ui("error", f"❌ 查找 UserCell 失败: {str(e)}")
            return False

        # 步骤3: 点击委派账户div
        log_to_ui("info", "👆 步骤3: 点击委派账户...")
        try:
            time.sleep(0.5)
            if not safe_click_target(page, found_delegated, log_to_ui=log_to_ui, label='点击委派账户'):
                return False
            log_to_ui("success", "✅ 已点击委派账户")
            log_to_ui("info", "⏳ 等待弹窗出现...")
            time.sleep(3.5)  # 增加到3.5秒，等待弹窗加载
        except Exception as e:
            log_to_ui("error", f"❌ 点击委派账户失败: {str(e)}")
            return False

        # 步骤4: 处理弹窗
        log_to_ui("info", "🔍 步骤4: 处理弹窗...")
        time.sleep(2)  # 再等待2秒，确保弹窗完全加载

        clicked_confirm = click_visible_confirm_button(page, log_to_ui=log_to_ui, sleep_fn=time.sleep)
        if clicked_confirm is False:
            return False
        if clicked_confirm:
            log_to_ui("success", "=" * 60)
            log_to_ui("success", "✅ 账户切换成功！")
            log_to_ui("success", "=" * 60)
            return True

        log_to_ui("info", "=" * 60)
        log_to_ui("info", "ℹ️ 委派账户点击完成，但未找到确认按钮")
        log_to_ui("info", "=" * 60)
        return True

    except Exception as e:
        log_to_ui("error", "=" * 60)
        log_to_ui("error", f"❌ 切换过程异常: {str(e)}")
        log_to_ui("error", "=" * 60)
        return False



def get_current_account_handle(page):
    """尝试从侧边栏读取当前账号 handle，失败返回空字符串。"""
    for selector in ACCOUNT_SWITCHER_SELECTORS:
        try:
            btn = page.ele(selector, timeout=0.8)
            if not btn:
                continue
            handle = extract_handle_from_text((btn.text or '').strip())
            if handle:
                return handle
        except Exception:
            pass

    try:
        profile_link = page.ele('css:a[data-testid="AppTabBar_Profile_Link"]', timeout=0.8)
        href = (profile_link.attr('href') or '').strip() if profile_link else ''
        handle = extract_profile_handle_from_href(href)
        if handle:
            return handle
    except Exception:
        pass

    return ''


def ensure_delegated_account_session(page, target_account, deps):
    """
    确保当前会话已在目标委派账户：
    - 已在目标账户：仅刷新，不重复切换
    - 当前会话已切换过：先刷新校验，仍命中则直接复用
    - 否则执行一次切换
    """
    target_clean = deps.normalize_handle(target_account)
    if not target_clean:
        deps.log_to_ui('error', '❌ 未指定委派账户用户名')
        return False

    current_handle = get_current_account_handle(page)
    if current_handle and current_handle == target_clean:
        deps._set_runtime_attr('delegated_account_active', target_clean)
        deps._set_runtime_attr('delegated_switch_ok', True)
        deps.log_to_ui('success', f'✅ 当前已是委派账户 @{target_clean}，仅刷新页面复用会话')
        try:
            page.refresh()
            time.sleep(1.2)
        except Exception:
            pass
        return True

    if deps.delegated_switch_ok and deps.delegated_account_active == target_clean:
        deps.log_to_ui('info', f'ℹ️ 会话内已切换过 @{target_clean}，先刷新校验，无需重复登录')
        try:
            page.refresh()
            time.sleep(1.2)
        except Exception:
            pass
        current_handle = get_current_account_handle(page)
        if current_handle and current_handle == target_clean:
            deps.log_to_ui('success', '✅ 刷新后确认仍为目标委派账户，跳过重复切换')
            return True
        deps.log_to_ui('warn', '⚠️ 刷新后未检测到目标委派账户，将执行一次重新切换')

    switch_success = deps.switch_to_delegated_account(page, target_account)
    if switch_success:
        deps._set_runtime_attr('delegated_account_active', target_clean)
        deps._set_runtime_attr('delegated_switch_ok', True)
        try:
            page.refresh()
            time.sleep(1.2)
            deps.log_to_ui('info', '🔄 委派账户切换完成，已刷新页面')
        except Exception:
            pass
        return True

    deps._set_runtime_attr('delegated_switch_ok', False)
    return False
