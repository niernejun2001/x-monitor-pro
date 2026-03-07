import re
import time


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
            # 无头模式下该按钮有时在视口外，先滚到底部
            try:
                page.run_js('window.scrollTo(0, document.body.scrollHeight);')
                time.sleep(0.4)
            except Exception:
                pass

            menu_btn = None
            menu_selectors = [
                'css:[data-testid="SideNav_AccountSwitcher_Button"]',
                'css:button[data-testid="SideNav_AccountSwitcher_Button"]',
                'css:div[data-testid="SideNav_AccountSwitcher_Button"]',
            ]

            # 多轮重试，适配无头渲染延迟
            for _ in range(3):
                for selector in menu_selectors:
                    try:
                        candidate = page.ele(selector, timeout=1.5)
                        if candidate and candidate.states.is_displayed:
                            menu_btn = candidate
                            break
                    except Exception:
                        pass
                if menu_btn:
                    break
                time.sleep(0.8)

            if not menu_btn:
                log_to_ui("error", "❌ 未找到账户菜单按钮")
                return False

            log_to_ui("success", "✅ 找到菜单按钮，点击中...")
            page.run_js('arguments[0].click()', menu_btn)
            log_to_ui("info", "⏳ 等待菜单内容加载...")
            time.sleep(4)  # 保持较长等待，确保菜单完全渲染
            log_to_ui("success", "✅ 菜单已打开，继续扫描...")
        except Exception as e:
            log_to_ui("error", f"❌ 点击菜单失败: {str(e)}")
            return False

        # 步骤2: 在菜单中查找匹配的账户
        log_to_ui("info", f"🔍 步骤2: 查找账户匹配 '{target_account}'...")

        found_delegated = None

        # 直接方法：查找所有 UserCell 按钮
        try:
            user_cells = []
            for _ in range(3):
                try:
                    user_cells = page.eles('css:[data-testid="UserCell"]', timeout=1.5)
                except Exception:
                    user_cells = []
                if user_cells:
                    break
                time.sleep(0.8)
            log_to_ui("info", f"   找到 {len(user_cells)} 个账户选项...")

            for cell in user_cells:
                try:
                    cell_text = (cell.text or '').strip()
                    cell_html = (cell.html or '').strip()
                    # 简单的调试日志
                    # log_to_ui("debug", f"   🔹 检查账户: {cell_text.replace(chr(10), ' ')}")

                    combined_text = f"{cell_text} {cell_html}".lower()
                    handle_match = re.search(r'@([a-zA-Z0-9_]{1,30})', combined_text)
                    cell_handle = handle_match.group(1).lower() if handle_match else ""

                    # 检查是否包含目标handle（优先精确匹配）
                    direct_hit = cell_handle == target_clean
                    fallback_hit = re.search(rf'@?{re.escape(target_clean)}\b', combined_text) is not None
                    if direct_hit or fallback_hit:
                        if cell.states.is_displayed:
                            found_delegated = cell
                            log_to_ui("success", f"   ✅ 找到目标账户: {cell_text.splitlines()[0]}")
                            break
                except:
                    pass

            if not found_delegated:
                log_to_ui("error", f"❌ 未找到匹配 '{target_account}' 的账户")
                # 打印所有找到的选项供调试
                for cell in user_cells:
                    cell_text = (cell.text or '').replace(chr(10), ' ')
                    handle_match = re.search(r'@([a-zA-Z0-9_]{1,30})', cell_text.lower())
                    handle_hint = f"@{handle_match.group(1)}" if handle_match else "无@handle"
                    log_to_ui("info", f"   - 可选: {handle_hint} | {cell_text[:60]}")
                return False

        except Exception as e:
            log_to_ui("error", f"❌ 查找 UserCell 失败: {str(e)}")
            return False

        # 步骤3: 点击委派账户div
        log_to_ui("info", "👆 步骤3: 点击委派账户...")
        try:
            time.sleep(0.5)
            page.run_js('arguments[0].click()', found_delegated)
            log_to_ui("success", "✅ 已点击委派账户")
            log_to_ui("info", "⏳ 等待弹窗出现...")
            time.sleep(3.5)  # 增加到3.5秒，等待弹窗加载
        except Exception as e:
            log_to_ui("error", f"❌ 点击委派账户失败: {str(e)}")
            return False

        # 步骤4: 处理弹窗
        log_to_ui("info", "🔍 步骤4: 处理弹窗...")
        time.sleep(2)  # 再等待2秒，确保弹窗完全加载

        try:
            # 查找弹窗中的确认按钮
            buttons = page.eles('tag:button', timeout=2)
            log_to_ui("info", f"   发现 {len(buttons)} 个按钮，查找确认按钮...")

            for btn in buttons:
                btn_text = (btn.text or '').strip()

                # 查找包含确认关键字的按钮
                confirm_keywords = ['切换', 'switch', '确认', 'confirm', '是', 'yes', '好的']
                if any(kw.lower() in btn_text.lower() for kw in confirm_keywords):
                    if btn.states.is_displayed:
                        log_to_ui("success", f"   ✅ 找到确认按钮: {btn_text}")
                        time.sleep(0.5)
                        page.run_js('arguments[0].click()', btn)
                        time.sleep(2)
                        log_to_ui("success", "✅ 确认按钮已点击")

                        log_to_ui("success", "=" * 60)
                        log_to_ui("success", "✅ 账户切换成功！")
                        log_to_ui("success", "=" * 60)
                        return True
        except Exception as e:
            log_to_ui("warn", f"⚠️ 处理弹窗出错: {str(e)}")
            return False

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
    selectors = [
        'css:[data-testid="SideNav_AccountSwitcher_Button"]',
        'css:button[data-testid="SideNav_AccountSwitcher_Button"]',
        'css:div[data-testid="SideNav_AccountSwitcher_Button"]',
    ]

    for selector in selectors:
        try:
            btn = page.ele(selector, timeout=0.8)
            if not btn:
                continue
            text = (btn.text or '').strip()
            match = re.search(r'@([A-Za-z0-9_]{1,30})', text)
            if match:
                return match.group(1).lower()
        except Exception:
            pass

    try:
        profile_link = page.ele('css:a[data-testid="AppTabBar_Profile_Link"]', timeout=0.8)
        href = (profile_link.attr('href') or '').strip() if profile_link else ''
        match = re.search(r'/([A-Za-z0-9_]{1,30})/?$', href)
        if match:
            handle = match.group(1).lower()
            if handle not in {'home', 'notifications', 'explore', 'messages', 'compose', 'i'}:
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
