import datetime
import hashlib
import re
import time
import traceback


def scan_notifications_page(page, blocked_list, max_recent_minutes, deps):
    results = []
    seen_in_page = set()
    try:
        if max_recent_minutes is None:
            max_recent_minutes = deps.NOTIFICATION_RECENT_WINDOW_MINUTES
        max_scan_articles = deps.NOTIFICATION_MAX_SCAN_ARTICLES

        if 'notifications' not in page.url:
            deps.log_to_ui('info', '📬 正在访问通知页面...')
            page.get('https://x.com/notifications')
            try:
                page.wait.ele_displayed('tag:article', timeout=5)
            except Exception:
                pass
            time.sleep(1)
            try:
                tabs = page.eles('css:[role="tab"]', timeout=0.5)
                for tab in tabs:
                    tab_text = (tab.text or '').strip().lower()
                    if tab_text in ['全部', 'all']:
                        tab.click()
                        time.sleep(0.5)
                        break
            except Exception:
                pass

        articles = page.eles('tag:article', timeout=0.8)
        total_articles = len(articles)
        if len(articles) > max_scan_articles:
            articles = articles[:max_scan_articles]
            deps.log_to_ui(
                'warn',
                f'⚠️ 通知列表过长(total={total_articles})，当前仅扫描前{max_scan_articles}条；可调大 XMONITOR_NOTIFY_MAX_ARTICLES'
            )
        articles = deps.reorder_articles_for_scan(articles)

        new_captured = 0
        skipped_old = 0
        skipped_non_reply = 0
        skipped_no_status = 0
        skipped_no_content = 0
        skipped_blacklist = 0
        skipped_duplicate = 0
        skipped_no_handle = 0
        skipped_interaction = 0
        skipped_empty_text = 0
        policy_flagged_emoji_only = 0
        policy_flagged_blocked_mention = 0
        article_errors = 0
        trace_logs = []
        trace_limit = deps.NOTIFICATION_TRACE_MAX_ARTICLES if deps.NOTIFICATION_VERBOSE_TRACE else 0

        if deps.NOTIFICATION_VERBOSE_TRACE:
            deps.log_to_ui(
                'debug',
                f'🔎 [NotifyTrace] scan_start url={page.url} articles={len(articles)} recent_window={max_recent_minutes}min'
            )

        blocked_norm_set = set()
        for raw_handle in (blocked_list or []):
            norm = deps.normalize_handle(raw_handle)
            if norm:
                blocked_norm_set.add(norm)
        delegated_now = deps.get_effective_delegated_account()
        delegated_norm = deps.normalize_handle(delegated_now)

        for idx, article in enumerate(articles, start=1):
            try:
                article_text = article.text or ''
                if not article_text:
                    skipped_empty_text += 1
                    if idx <= trace_limit:
                        trace_logs.append(f'A{idx:02d} skip=empty_text')
                    continue

                trace_sample = deps._normalize_one_line(article_text)
                relation = deps._classify_notification_type(article_text)
                notification_type = relation['notification_type']
                is_reply_like = relation['is_reply_like']
                is_reply_to_me = relation['is_reply_to_me']
                is_mention_to_me = relation['is_mention_to_me']
                is_interaction_only = relation['is_interaction_only']

                if is_interaction_only:
                    skipped_interaction += 1
                    if idx <= trace_limit:
                        trace_logs.append(f'A{idx:02d} skip=interaction type={notification_type} text={trace_sample}')
                    continue

                if deps.NOTIFICATION_REPLY_ONLY_MODE and (not is_reply_to_me):
                    skipped_non_reply += 1
                    if idx <= trace_limit:
                        trace_logs.append(f'A{idx:02d} skip=reply_only_filter type={notification_type} text={trace_sample}')
                    continue

                status_handle, status_id = deps._extract_notification_status_info(article)
                if not status_id and not is_reply_like:
                    skipped_non_reply += 1
                    if idx <= trace_limit:
                        hrefs = deps._collect_notification_hrefs(article)
                        html_status_hints = deps._extract_status_id_candidates_from_text(article.html or '')
                        status_hint = html_status_hints[-1] if html_status_hints else ''
                        tweet_texts = deps._collect_notification_tweet_texts(article)
                        trace_logs.append(
                            f'A{idx:02d} skip=non_reply status_id=None is_reply_like={is_reply_like} '
                            f'status_hint={status_hint or '-'} tweetText={tweet_texts or '-'} hrefs={hrefs} text={trace_sample}'
                        )
                    continue
                if not status_id and is_reply_like:
                    skipped_no_status += 1
                    if idx <= trace_limit:
                        hrefs = deps._collect_notification_hrefs(article)
                        trace_logs.append(
                            f'A{idx:02d} keep=fallback_no_status type={notification_type} '
                            f'is_reply_like={is_reply_like} hrefs={hrefs} text={trace_sample}'
                        )

                age_minutes = deps._parse_notification_age_minutes(article)
                if age_minutes is not None and age_minutes > max_recent_minutes:
                    skipped_old += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f'A{idx:02d} skip=old age={age_minutes:.1f}m status_id={status_id} text={trace_sample}'
                        )
                    continue

                handle = status_handle or deps._extract_notification_handle(article, article_text)
                if not handle:
                    skipped_no_handle += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f'A{idx:02d} skip=no_handle status_id={status_id} age={age_minutes} text={trace_sample}'
                        )
                    continue

                handle_norm = handle.strip().lstrip('@').lower()
                should_skip_block = (handle_norm in blocked_norm_set and (not delegated_norm or handle_norm != delegated_norm))
                if should_skip_block:
                    skipped_blacklist += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f'A{idx:02d} skip=blacklist handle={handle} status_id={status_id} text={trace_sample}'
                        )
                    continue

                content = deps._extract_notification_content(article, article_text, handle)
                if not content:
                    skipped_no_content += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f'A{idx:02d} skip=no_content handle={handle} status_id={status_id} text={trace_sample}'
                        )
                    continue

                should_skip_policy, policy_reason = deps.should_skip_content_by_policy(content)
                if should_skip_policy:
                    if policy_reason == 'emoji_only':
                        policy_flagged_emoji_only += 1
                    elif policy_reason == 'blocked_mention':
                        policy_flagged_blocked_mention += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f'A{idx:02d} skip=policy reason={policy_reason} handle={handle} status_id={status_id} content={deps._normalize_one_line(content)}'
                        )
                    continue

                unique_key = ''
                if status_id:
                    status_id = deps._pick_best_status_id(status_id)
                    unique_key = f'notif_status_{status_id}'
                else:
                    try:
                        time_ele = article.ele('tag:time', timeout=0)
                    except Exception:
                        time_ele = None
                    time_token = ''
                    if time_ele:
                        time_token = ((time_ele.attr('datetime') or time_ele.text or '')).strip()
                    raw_key = f'{handle_norm}|{content}|{time_token}'
                    digest = hashlib.md5(raw_key.encode('utf-8')).hexdigest()[:20]
                    unique_key = f'notif_fallback_{digest}'

                if unique_key in seen_in_page or unique_key in deps.history_ids:
                    skipped_duplicate += 1
                    if idx <= trace_limit:
                        trace_logs.append(
                            f'A{idx:02d} skip=duplicate handle={handle} status_id={status_id} key={unique_key}'
                        )
                    continue
                seen_in_page.add(unique_key)

                new_captured += 1
                results.append({
                    'handle': handle,
                    'content': content,
                    'key': unique_key,
                    'source': '通知页面',
                    'time': datetime.datetime.now().strftime('%H:%M:%S'),
                    'status_id': status_id or '',
                    'status_handle': (status_handle or '').strip(),
                    'notification_type': notification_type,
                    'is_reply_to_me': bool(is_reply_to_me),
                    'is_mention_to_me': bool(is_mention_to_me),
                    'notification_text': relation['normalized_text'][:600],
                    'notification_age_minutes': (round(float(age_minutes), 2) if age_minutes is not None else None),
                    'status_url': (
                        f"https://x.com/{deps.normalize_handle(status_handle)}/status/{status_id}"
                        if status_id and status_handle else
                        (f'https://x.com/i/status/{status_id}' if status_id else '')
                    )
                })
                if deps.NOTIFICATION_VERBOSE_TRACE:
                    deps.log_to_ui('debug', f'📬 [NotifyCandidate][{notification_type}] {handle} - {content[:20]}...')
                if idx <= trace_limit:
                    trace_logs.append(
                        f'A{idx:02d} pass handle={handle} status_id={status_id} age={age_minutes} content={deps._normalize_one_line(content)}'
                    )

            except Exception as article_err:
                article_errors += 1
                if idx <= trace_limit:
                    trace_logs.append(f'A{idx:02d} skip=exception err={deps._normalize_one_line(article_err, 160)}')
                continue

        if skipped_old > 0:
            deps.log_to_ui('debug', f'📋 [Notify] 跳过旧通知: {skipped_old}')
        if skipped_non_reply > 0:
            deps.log_to_ui('debug', f'📋 [Notify] 跳过非回复: {skipped_non_reply}')
        if skipped_interaction > 0:
            deps.log_to_ui('debug', f'📋 [Notify] 跳过互动通知: {skipped_interaction}')
        if skipped_no_status > 0:
            deps.log_to_ui('debug', f'📋 [Notify] 回复/提及但无status_id(已兜底): {skipped_no_status}')
        if skipped_no_content > 0:
            deps.log_to_ui('debug', f'📋 [Notify] 跳过无正文: {skipped_no_content}')
        if skipped_no_handle > 0:
            deps.log_to_ui('debug', f'📋 [Notify] 跳过无用户: {skipped_no_handle}')
        if skipped_blacklist > 0:
            deps.log_to_ui('debug', f'📋 [Notify] 跳过保护名单: {skipped_blacklist}')
        if skipped_duplicate > 0:
            deps.log_to_ui('debug', f'📋 [Notify] 跳过重复: {skipped_duplicate}')
        if skipped_empty_text > 0:
            deps.log_to_ui('debug', f'📋 [Notify] 跳过空文本: {skipped_empty_text}')
        if policy_flagged_emoji_only > 0:
            deps.log_to_ui('debug', f'📋 [Notify] 内容标记(纯表情): {policy_flagged_emoji_only}')
        if policy_flagged_blocked_mention > 0:
            deps.log_to_ui('debug', f'📋 [Notify] 内容标记(指定@): {policy_flagged_blocked_mention}')
        if article_errors > 0:
            deps.log_to_ui('debug', f'📋 [Notify] article异常: {article_errors}')
        if new_captured == 0 and len(articles) > 0 and deps.NOTIFICATION_VERBOSE_TRACE:
            deps.log_to_ui('debug', f'📬 本轮扫描未捕获新通知（articles={len(articles)}）')
        if trace_logs and (deps.NOTIFICATION_VERBOSE_TRACE and (new_captured == 0 or article_errors > 0)):
            for trace in trace_logs:
                deps.log_to_ui('debug', f'🔎 [NotifyTrace] {trace}')

        return results, None
    except Exception as e:
        deps.log_to_ui('error', f'❌ scan_notifications_page异常: {str(e)}')
        deps.log_to_ui('debug', f'🔎 [NotifyTrace] traceback={traceback.format_exc()}')
        return [], str(e)
