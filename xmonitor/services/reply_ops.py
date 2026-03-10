import random
import re
import time

from xmonitor.services.reply_submit_service import send_reply_from_button


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
