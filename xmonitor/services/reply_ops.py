import random
import re
import time


def prepare_notifications_view(tab, deps, *, force_refresh=False):
    did_refresh = False
    deps._prepare_reply_prompt_guard(tab, '准备通知视图')
    if force_refresh:
        now_ts = time.time()
        should_refresh = (now_ts - deps.last_reply_prepare_refresh_ts) >= deps.REPLY_PREPARE_REFRESH_MIN_GAP_SEC
        if should_refresh:
            try:
                tab.refresh()
                did_refresh = True
                deps.last_reply_prepare_refresh_ts = now_ts
                deps._reply_humanized_idle(tab, 0.35, 0.9, '通知页刷新后等待')
            except Exception:
                pass
    try:
        tabs = tab.eles('css:[role="tab"]', timeout=0.9)
        for notify_tab in tabs:
            tab_text = (notify_tab.text or '').strip().lower()
            if tab_text not in {'全部', 'all'}:
                continue
            is_selected = (notify_tab.attr('aria-selected') or '').lower() == 'true'
            if not is_selected:
                try:
                    notify_tab.click()
                except Exception:
                    tab.run_js('arguments[0].click()', notify_tab)
                deps._reply_humanized_idle(tab, 0.24, 0.52, '通知Tab切换后等待')
            break
    except Exception:
        pass
    if force_refresh or did_refresh:
        try:
            tab.run_js('window.scrollTo(0, 0);')
        except Exception:
            pass


def match_target_card(tab, item, status_id, deps):
    def should_allow_status_fallback():
        policy = str(deps.REPLY_STATUS_FALLBACK_POLICY or 'high_priority_only').strip().lower()
        if policy == 'always':
            return True, 'policy=always'
        if policy == 'off':
            return False, 'policy=off'
        intent_level = str(item.get('intent_level', '') or '').strip().lower()
        try:
            intent_score = int(float(item.get('intent_score', 0) or 0))
        except Exception:
            intent_score = 0
        force_notify_raw = item.get('force_notify', False)
        if isinstance(force_notify_raw, str):
            force_notify = force_notify_raw.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
        else:
            force_notify = bool(force_notify_raw)
        if force_notify:
            return True, 'force_notify=true'
        if intent_level == 'high':
            return True, 'intent_level=high'
        if intent_score >= int(deps.REPLY_STATUS_FALLBACK_MIN_SCORE):
            return True, f'intent_score={intent_score}'
        strong_signal_keys = {
            'short_reply_intent_signal',
            'performance_consult_signal',
            'business_consult_signal',
            'force_intent_keyword',
            'product_consult_signal',
            'product_contact_combo',
        }
        raw_signals = item.get('intent_signals', [])
        if not isinstance(raw_signals, (list, tuple)):
            raw_signals = [raw_signals]
        signal_hits = []
        for sig in raw_signals:
            sig_norm = str(sig or '').strip().lower()
            if sig_norm in strong_signal_keys and sig_norm not in signal_hits:
                signal_hits.append(sig_norm)
        if signal_hits:
            return True, f"signal={'|'.join(signal_hits[:3])}"
        content_low = deps._normalize_content_for_filter(item.get('content', '')).lower()
        keyword_hits = deps._find_keyword_hits(content_low, deps.INTENT_FORCE_NOTIFY_KEYWORDS)
        if keyword_hits:
            return True, f"keyword={'|'.join(keyword_hits[:3])}"
        return False, f"policy=high_priority_only, unmet (force={force_notify}, level={intent_level or '-'}, score={intent_score})"

    def fallback_match_on_status_page():
        fallback_urls = []
        for cand in [
            str(item.get('status_url', '') or '').strip(),
            deps._get_status_link_from_item(item),
            (
                f"https://x.com/{deps.normalize_handle(item.get('status_handle', ''))}/status/{status_id}"
                if status_id and deps.normalize_handle(item.get('status_handle', '')) else ''
            ),
            (f'https://x.com/i/status/{status_id}' if status_id else ''),
        ]:
            url = str(cand or '').strip()
            if not url:
                continue
            if url.startswith('/'):
                url = f'https://x.com{url}'
            elif url.startswith('x.com/'):
                url = f'https://{url}'
            if url not in fallback_urls:
                fallback_urls.append(url)
        if not fallback_urls:
            return None, None, 0, None, None, '通知页未命中，且缺少可用 status 链接兜底'
        for idx, url in enumerate(fallback_urls, start=1):
            deps._prepare_reply_prompt_guard(tab, f'会话页兜底匹配{idx}')
            try:
                tab.get(url)
                deps._wait_document_ready(tab, timeout=5.2)
                deps._reply_humanized_idle(tab, 0.24, 0.56, f'会话页兜底加载{idx}')
            except Exception:
                continue
            try:
                tab.wait.ele_displayed('tag:article', timeout=4)
            except Exception:
                pass
            for sweep in range(3):
                target_article_fb, target_score_fb = deps._match_reply_target_article(
                    tab,
                    status_id,
                    item.get('handle', ''),
                    item.get('content', ''),
                )
                if target_article_fb and target_score_fb >= 120:
                    try:
                        target_reply_btn_fb = target_article_fb.ele('css:[data-testid="reply"]', timeout=0.6)
                    except Exception:
                        target_reply_btn_fb = None
                    if target_reply_btn_fb and target_reply_btn_fb.states.is_displayed:
                        matched_handle_fb = deps.normalize_handle(item.get('status_handle', '') or item.get('handle', ''))
                        matched_status_id_fb = str(status_id or '')
                        deps.log_to_ui('info', f'💬 通知页未命中，已回退会话页定位成功(score={target_score_fb}, url={url})')
                        return target_article_fb, target_reply_btn_fb, target_score_fb, matched_handle_fb, matched_status_id_fb, ''
                try:
                    tab.run_js('window.scrollBy(0, 760);')
                    deps._reply_humanized_idle(tab, 0.16, 0.4, f'会话页兜底滚动{sweep + 1}')
                except Exception:
                    pass
        return None, None, 0, None, None, '未在通知页定位到目标评论卡片，且会话页兜底未命中'

    target_article = None
    target_reply_btn = None
    target_score = 0
    required_score = 260 if status_id else 120
    for attempt in range(3):
        deps._prepare_reply_prompt_guard(tab, f'匹配通知卡片尝试{attempt + 1}')
        if attempt == 2 and not target_article:
            prepare_notifications_view(tab, deps, force_refresh=True)
            deps.log_to_ui('debug', '💬 匹配未命中，执行一次刷新后重试')
        target_article, target_reply_btn, target_score = deps._match_notification_card_for_reply(
            tab,
            status_id,
            item.get('handle', ''),
            item.get('content', ''),
        )
        if target_article and target_reply_btn and target_score >= required_score:
            break
        try:
            if attempt < 2:
                tab.run_js('window.scrollBy(0, 640);')
            else:
                tab.run_js('window.scrollTo(0, 0);')
            deps._reply_humanized_idle(tab, 0.18, 0.46, f'匹配卡片滚动等待{attempt + 1}')
        except Exception:
            pass

    if not target_article:
        allow_fallback, fallback_reason = should_allow_status_fallback()
        if not allow_fallback:
            deps.log_to_ui('debug', f'💬 状态页兜底已跳过: {fallback_reason}')
            return None, None, 0, None, None, f'未在通知页定位到目标评论卡片（已跳过状态页兜底: {fallback_reason}）'
        deps.log_to_ui('debug', f'💬 通知页未命中，执行状态页兜底: {fallback_reason}')
        return fallback_match_on_status_page()

    if target_score < required_score:
        allow_fallback, fallback_reason = should_allow_status_fallback()
        if not allow_fallback:
            deps.log_to_ui('debug', f'💬 状态页兜底已跳过: {fallback_reason}, score={target_score}, required={required_score}')
            return None, None, target_score, None, None, '通知页命中低置信目标且状态页兜底被策略跳过: ' + f'{fallback_reason} (score={target_score}, required={required_score})'
        deps.log_to_ui('debug', f'💬 通知页低置信命中，执行状态页兜底: {fallback_reason}, score={target_score}, required={required_score}')
        return fallback_match_on_status_page()

    try:
        matched_handle, matched_status_id = deps._extract_notification_status_info(target_article)
    except Exception:
        matched_handle, matched_status_id = None, None
    return target_article, target_reply_btn, target_score, matched_handle, matched_status_id, ''


def send_reply_from_button(tab, target_reply_btn, target_score, reply_text, status_id, handle_hint, deps):
    deps._prepare_reply_prompt_guard(tab, '点击回复入口前')
    deps._reply_humanized_idle(tab, 0.16, 0.4, '点击回复入口前')
    try:
        tab.run_js('arguments[0].scrollIntoView({block:"center"});', target_reply_btn)
    except Exception:
        pass
    clicked_reply, click_reply_err = deps._click_with_prompt_guard(tab, target_reply_btn, '点击左下角回复按钮')
    if not clicked_reply:
        return False, click_reply_err
    deps.log_to_ui('debug', f'💬 已点击通知卡片左下角回复按钮(score={target_score})，等待回复输入框')
    deps._reply_humanized_idle(tab, 0.22, 0.56, '等待回复输入框弹出')
    editor_selectors = [
        'css:[data-testid="tweetTextarea_0"] [role="textbox"]',
        'css:[data-testid="tweetTextarea_0"] [contenteditable="true"]',
        'css:[data-testid="tweetTextarea_0"] div[contenteditable="true"]',
        'css:[data-testid="tweetTextarea_0"]',
        'css:div[role="dialog"] div[role="textbox"][contenteditable="true"]',
        'css:div[role="textbox"][contenteditable="true"]',
    ]
    editor = deps._wait_first_visible(tab, editor_selectors, timeout=3.0, poll=0.1)
    if not editor:
        deps._reply_humanized_idle(tab, 0.12, 0.28, '回复输入框二次唤醒')
        try:
            deps._click_with_prompt_guard(tab, target_reply_btn, '点击左下角回复按钮(二次唤醒)')
        except Exception:
            pass
        editor = deps._wait_first_visible(tab, editor_selectors, timeout=3.8, poll=0.1)
    if not editor:
        deps._capture_runtime_diagnostic(
            tab,
            'reply_editor_not_found',
            err='未弹出回复输入框',
            selectors=editor_selectors + [
                'css:[data-testid="reply"]',
                'css:[role="dialog"]',
                'css:[data-testid="sheetDialog"]',
            ],
            extra={
                'status_id': status_id,
                'handle_hint': handle_hint,
                'target_score': target_score,
            }
        )
        return False, '未弹出回复输入框'

    def _read_reply_editor_text():
        try:
            val = tab.run_js(
                """
                const el = arguments[0];
                if (!el) return '';
                if (el.value !== undefined) return String(el.value || '');
                return String(el.innerText || el.textContent || '');
                """,
                editor,
            )
            return str(val or '')
        except Exception:
            return ''

    def _reply_input_stable(expected_text):
        expected_norm = deps._normalize_text_for_compare(expected_text)
        current_norm = deps._normalize_text_for_compare(_read_reply_editor_text())
        if not expected_norm:
            return bool(current_norm)
        if not current_norm:
            return False
        if current_norm == expected_norm:
            return True
        if expected_norm in current_norm or current_norm in expected_norm:
            return True
        return False

    typed_ok = False
    deps._prepare_reply_prompt_guard(tab, '填充回复内容前')
    deps._reply_humanized_idle(tab, 0.14, 0.36, '填充回复内容前')
    try:
        editor.click()
    except Exception:
        pass
    try:
        editor.input(reply_text, clear=True)
        typed_ok = True
    except Exception:
        try:
            tab.run_js(
                """
                const el = arguments[0];
                const text = arguments[1];
                el.focus();
                if (el.textContent !== undefined) el.textContent = '';
                document.execCommand('insertText', false, text);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                """,
                editor,
                reply_text,
            )
            typed_ok = True
        except Exception:
            typed_ok = False
    if not typed_ok:
        return False, '输入回复内容失败'
    if not _reply_input_stable(reply_text):
        try:
            tab.run_js(
                """
                const el = arguments[0];
                const text = String(arguments[1] || '');
                if (!el) return false;
                el.focus();
                try {
                  if (el.value !== undefined) {
                    el.value = text;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                  }
                } catch (e) {}
                try {
                  const sel = window.getSelection();
                  const range = document.createRange();
                  range.selectNodeContents(el);
                  sel.removeAllRanges();
                  sel.addRange(range);
                } catch (e) {}
                try {
                  document.execCommand('insertText', false, text);
                } catch (e) {
                  el.textContent = text;
                }
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
                """,
                editor,
                reply_text,
            )
        except Exception:
            pass
    editor_now_text = _read_reply_editor_text()
    if not _reply_input_stable(reply_text):
        deps._capture_runtime_diagnostic(
            tab,
            'reply_input_not_stable',
            err='回复框填充后文本未稳定',
            selectors=editor_selectors + [
                'css:[data-testid="tweetButton"]',
                'css:button[data-testid="tweetButton"]',
                'css:[data-testid="tweetButtonInline"]',
                'css:button[data-testid="tweetButtonInline"]',
            ],
            extra={
                'status_id': status_id,
                'handle_hint': handle_hint,
                'target_score': target_score,
                'expected_len': len(deps._normalize_text_for_compare(reply_text)),
                'current_len': len(deps._normalize_text_for_compare(editor_now_text)),
                'current_preview': deps._normalize_text_for_compare(editor_now_text)[:180],
            }
        )
        return False, f'回复输入后文本未生效(当前长度={len(deps._normalize_text_for_compare(editor_now_text))})'
    deps.log_to_ui('debug', f'💬 已填充回复内容(len={len(deps._normalize_text_for_compare(editor_now_text))})')
    deps._reply_humanized_idle(tab, 0.1, 0.26, '回复输入后等待按钮激活')
    send_selectors = [
        'css:[data-testid="tweetButton"]',
        'css:button[data-testid="tweetButton"]',
        'css:[data-testid="tweetButtonInline"]',
    ]
    send_btn = deps._wait_first_actionable(tab, send_selectors, timeout=1.4, poll=0.08)
    if not send_btn:
        try:
            tab.run_js(
                """
                const el = arguments[0];
                const text = String(arguments[1] || '');
                if (!el) return;
                el.focus();
                if (el.textContent !== undefined) el.textContent = text + ' ';
                el.dispatchEvent(new Event('input', {bubbles: true}));
                if (el.textContent !== undefined) el.textContent = text;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                """,
                editor,
                reply_text,
            )
        except Exception:
            pass
        deps._reply_humanized_idle(tab, 0.08, 0.22, '回复发送按钮二次等待')
        send_btn = deps._wait_first_actionable(tab, send_selectors, timeout=1.2, poll=0.08)
    if not send_btn:
        try:
            clicked_inline = tab.run_js(
                """
                const editor = arguments[0];
                if (!editor) return false;
                const isVisible = (el) => {
                  if (!el) return false;
                  const st = window.getComputedStyle(el);
                  if (!st) return false;
                  if (st.display === 'none' || st.visibility === 'hidden') return false;
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                };
                const root = editor.closest('[role="dialog"],section,main') || document;
                const selectors = [
                  '[data-testid="tweetButton"]',
                  'button[data-testid="tweetButton"]',
                  '[data-testid="tweetButtonInline"]',
                  'button[data-testid="tweetButtonInline"]',
                  'button[aria-label*="回复"]',
                  'button[aria-label*="Reply"]'
                ];
                for (const s of selectors) {
                  const nodes = Array.from(root.querySelectorAll(s));
                  for (const n of nodes) {
                    if (!isVisible(n)) continue;
                    if (n.disabled || n.getAttribute('aria-disabled') === 'true') continue;
                    try { n.click(); return true; } catch (e) {}
                  }
                }
                return false;
                """,
                editor,
            )
            if clicked_inline:
                send_btn = True
        except Exception:
            pass
    if not send_btn:
        return False, '回复发送按钮未激活'
    if send_btn is True:
        clicked_send, click_send_err = True, ''
    else:
        clicked_send, click_send_err = deps._click_with_prompt_guard(tab, send_btn, '点击右下角回复按钮')
    if not clicked_send:
        return False, click_send_err or '点击回复发送按钮失败'
    deps.log_to_ui('debug', '💬 已点击右下角回复按钮')
    deps._reply_humanized_idle(tab, 0.16, 0.38, '回复发送后等待')
    return True, ''
