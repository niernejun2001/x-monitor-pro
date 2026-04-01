import random
import time


def dismiss_pending_browser_prompt(tab, deps, max_rounds=2):
    """
    尝试清理浏览器原生提示框（alert/confirm/prompt）。
    兼容不同 DrissionPage 版本的 handle_alert 参数签名。
    """
    handler = getattr(tab, 'handle_alert', None)
    if not callable(handler):
        return 0

    handled_count = 0
    last_prompt_text = ''
    for _ in range(max_rounds):
        result = None
        called = False
        for kwargs in (
            {'accept': True, 'timeout': 0.6},
            {'accept': True},
            {'ok': True, 'timeout': 0.6},
            {'ok': True},
            {'timeout': 0.6},
            {},
        ):
            try:
                result = handler(**kwargs)
                called = True
                break
            except TypeError:
                continue
            except Exception as e:
                if not deps._is_unhandled_prompt_error(e):
                    called = True
                    result = False
                    break
                result = False
                called = True
                break
        if not called:
            for args in ((True, 0.6), (True,), tuple()):
                try:
                    result = handler(*args)
                    called = True
                    break
                except TypeError:
                    continue
                except Exception as e:
                    if not deps._is_unhandled_prompt_error(e):
                        called = True
                        result = False
                        break
                    result = False
                    called = True
                    break
        if not called:
            break

        if isinstance(result, str):
            last_prompt_text = result.strip()

        if result not in (None, False, '', 0):
            handled_count += 1
            time.sleep(0.08)
            continue
        break
    if handled_count > 0 and last_prompt_text:
        deps.log_headless_debug(f'提示框内容: {last_prompt_text[:160]}')
    return handled_count


def install_headless_dialog_guard(tab, deps):
    """无头模式下注入 JS，对页面 alert/confirm/prompt 做无阻塞兜底。"""
    if not deps.headless_mode:
        return False
    try:
        return bool(tab.run_js(
            """
            (() => {
              if (window.__xmonDialogGuardInstalled) return true;
              window.__xmonDialogGuardInstalled = true;
              window.__xmonDialogGuardLogs = [];
              const pushLog = (type, msg) => {
                try {
                  window.__xmonDialogGuardLogs.push({
                    t: Date.now(),
                    type,
                    msg: String(msg || '')
                  });
                  if (window.__xmonDialogGuardLogs.length > 20) {
                    window.__xmonDialogGuardLogs.shift();
                  }
                } catch (e) {}
              };
              window.alert = (msg) => { pushLog('alert', msg); return true; };
              window.confirm = (msg) => { pushLog('confirm', msg); return true; };
              window.prompt = (msg, defVal) => {
                pushLog('prompt', msg);
                return (defVal === undefined || defVal === null) ? '' : String(defVal);
              };
              try { window.onbeforeunload = null; } catch (e) {}
              try { document.onbeforeunload = null; } catch (e) {}
              const _rawWinAdd = window.addEventListener.bind(window);
              window.addEventListener = function(type, listener, options) {
                if (String(type || '').toLowerCase() === 'beforeunload') {
                  pushLog('beforeunload_blocked', 'window.addEventListener');
                  return;
                }
                return _rawWinAdd(type, listener, options);
              };
              const _rawDocAdd = document.addEventListener.bind(document);
              document.addEventListener = function(type, listener, options) {
                if (String(type || '').toLowerCase() === 'beforeunload') {
                  pushLog('beforeunload_blocked', 'document.addEventListener');
                  return;
                }
                return _rawDocAdd(type, listener, options);
              };
              return true;
            })();
            """
        ))
    except Exception:
        return False


def click_first_actionable_by_selectors(tab, selectors):
    """通过 CSS 选择器在当前文档重新定位并点击元素，避免跨 JS world 的句柄失效。"""
    if not tab or not selectors:
        return False
    css_list = []
    for sel in (selectors or []):
        s = str(sel or '').strip()
        if not s:
            continue
        if s.startswith('css:'):
            s = s[4:]
        if not s:
            continue
        css_list.append(s)
    if not css_list:
        return False
    try:
        clicked = tab.run_js(
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
              for (const el of nodes) {
                if (!isVisible(el)) continue;
                if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
                try { el.click(); return true; } catch (e) {}
              }
            }
            return false;
            """,
            css_list,
        )
        return bool(clicked)
    except Exception:
        return False


def click_with_prompt_guard(tab, element, action_name, deps, refetch_selectors=None):
    """点击元素时自动处理未处理提示框并重试。"""
    last_err = None
    max_retry = deps.REPLY_PROMPT_GUARD_MAX_RETRY + (1 if deps.headless_mode else 0)
    for attempt in range(max_retry):
        deps._prepare_reply_prompt_guard(tab, f'{action_name}前')
        try:
            element.click()
            return True, ''
        except Exception as e_click:
            last_err = e_click
            if deps._is_unhandled_prompt_error(e_click):
                deps._prepare_reply_prompt_guard(tab, f'{action_name}重试')
                time.sleep(random.uniform(0.15, 0.35))
                continue
            if refetch_selectors and deps._is_cross_world_click_error(e_click):
                if click_first_actionable_by_selectors(tab, refetch_selectors):
                    return True, ''
            try:
                if refetch_selectors and click_first_actionable_by_selectors(tab, refetch_selectors):
                    return True, ''
                focused_clicked = bool(tab.run_js(
                    """
                    const el = document.activeElement;
                    if (!el) return false;
                    if (el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
                    try { el.click(); return true; } catch (e) { return false; }
                    """
                ))
                if focused_clicked:
                    return True, ''
            except Exception as e_js:
                last_err = e_js
                if deps._is_unhandled_prompt_error(e_js):
                    deps._prepare_reply_prompt_guard(tab, f'{action_name}JS重试')
                    time.sleep(random.uniform(0.15, 0.35))
                    continue
                if refetch_selectors and deps._is_cross_world_click_error(e_js):
                    if click_first_actionable_by_selectors(tab, refetch_selectors):
                        return True, ''
                break
    return False, f'{action_name}失败: {last_err}'


def click_share_copy_link(tab, target_article, fallback_link, deps):
    """在目标卡片点击分享->复制链接，返回可用链接（优先真实复制，失败回退）。"""
    try:
        anchors = target_article.eles('tag:a', timeout=0.4)
    except Exception:
        anchors = []
    article_link = ''
    for anchor in anchors:
        try:
            href = (anchor.attr('href') or '').strip()
        except Exception:
            href = ''
        if not href or '/status/' not in href:
            continue
        article_link = deps._normalize_dm_share_link(href, fallback_url=fallback_link)
        if article_link:
            break
    if article_link:
        fallback_link = article_link

    share_btn = None
    share_selectors = [
        'css:button[aria-label*="分享"]',
        'css:button[aria-label*="Share"]',
        'css:[data-testid="share"]',
    ]
    for selector in share_selectors:
        try:
            share_btn = target_article.ele(selector, timeout=0.8)
            if share_btn and share_btn.states.is_displayed:
                break
        except Exception:
            continue
    if not share_btn:
        return fallback_link, '未找到分享按钮'

    clicked_share, share_click_err = click_with_prompt_guard(tab, share_btn, '点击分享按钮', deps)
    if not clicked_share:
        return fallback_link, share_click_err
    deps._wait_first_visible(tab, ['css:[role="menuitem"]', 'css:div[role="menu"]'], timeout=1.4, poll=0.1)

    copy_btn = None
    copy_keyword_list = ['复制链接', 'copy link', 'link to post', 'link to tweet']
    copy_selectors = ['css:[role="menuitem"]', 'tag:button', 'css:div[role="button"]', 'tag:span']
    for selector in copy_selectors:
        try:
            candidates = tab.eles(selector, timeout=0.8)
        except Exception:
            candidates = []
        for cand in candidates:
            try:
                txt = (cand.text or '').strip().lower()
                if txt and any(keyword in txt for keyword in copy_keyword_list):
                    copy_btn = cand
                    break
            except Exception:
                continue
        if copy_btn:
            break

    if not copy_btn:
        return fallback_link, '未找到复制链接按钮'

    clicked_copy, copy_click_err = click_with_prompt_guard(tab, copy_btn, '点击复制链接按钮', deps)
    if not clicked_copy:
        return fallback_link, copy_click_err

    return fallback_link, ''


def confirm_dm_closed_dual_stage(tab, handle, deps):
    """
    双阶段确认“不可私信”：
    - strict_hint_only: 看到明确禁发文案即判定关闭
    - dual_stage_confirm: 在忽略缓存后再探测一次，仍命中关闭才确认
    """
    handle_norm = deps.normalize_handle(handle)
    if not handle_norm:
        return False, 'missing_handle'

    if deps.DM_CLOSED_DETECT_MODE == 'strict_hint_only':
        return True, 'strict_hint_only'

    deps._clear_dm_unavailable_cache(handle_norm)
    try:
        retry_editor, retry_err = deps._open_dm_editor_for_handle(
            tab,
            handle_norm,
            ignore_cached_unavailable=True,
        )
    except Exception as e:
        retry_editor, retry_err = None, f'confirm_exception:{e}'

    if retry_editor:
        return False, 'editor_opened_on_confirm'

    retry_err_text = str(retry_err or '')
    if deps._is_dm_closed_error_text(retry_err_text):
        return True, 'closed_hint_confirmed_twice'

    return False, f'confirm_not_closed:{retry_err_text[:80]}'
