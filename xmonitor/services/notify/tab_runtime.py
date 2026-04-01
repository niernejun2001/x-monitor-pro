import datetime
import random
import time


def _get_notification_article_count(tab):
    try:
        return len(tab.eles('tag:article', timeout=0.4) or [])
    except Exception:
        return 0


def _stabilize_notification_tab(tab, deps):
    deps._wait_document_ready(tab, timeout=5.0)
    time.sleep(random.uniform(0.4, 1.0))
    try:
        tabs = tab.eles('css:[role="tab"]', timeout=0.8)
        for tab_btn in tabs:
            tab_text = (tab_btn.text or '').strip().lower()
            if tab_text in ['全部', 'all']:
                if tab_btn.attr('aria-selected') != 'true':
                    tab_btn.click()
                    time.sleep(random.uniform(0.2, 0.6))
                break
    except Exception:
        pass
    try:
        tab.run_js('window.scrollTo(0, 0);')
    except Exception:
        pass


def _handle_empty_notification_articles(tab, blocked_users, deps, *, allow_refresh):
    streak = int(getattr(deps, 'notification_empty_article_streak', 0) or 0) + 1
    deps._set_runtime_attr('notification_empty_article_streak', streak)

    if not allow_refresh:
        return 0

    soft_threshold = max(1, int(getattr(deps, 'NOTIFICATION_EMPTY_RECOVER_SOFT_THRESHOLD', 3) or 3))
    hard_threshold = max(soft_threshold + 1, int(getattr(deps, 'NOTIFICATION_EMPTY_RECOVER_HARD_THRESHOLD', 6) or 6))

    if streak >= hard_threshold:
        deps.log_to_ui('warn', f'⚠️ 通知页连续空列表达到 {streak} 次，重建通知标签页恢复')
        deps.close_notification_tab()
        deps.ensure_notification_tab(blocked_users)
        deps._set_runtime_attr('notification_last_refresh_at', 0.0)
        return 0

    if streak >= soft_threshold:
        deps.log_to_ui('warn', f'⚠️ 通知页连续空列表达到 {streak} 次，执行软恢复刷新')
        try:
            with deps.notification_tab_lock:
                current_tab = deps.notification_tab
                if current_tab:
                    current_tab.get('https://x.com/notifications')
                    _stabilize_notification_tab(current_tab, deps)
                    deps._set_runtime_attr('notification_last_refresh_at', time.time())
                    deps._set_runtime_attr(
                        'notification_refresh_interval',
                        deps._schedule_next_notification_refresh_interval(deps.notification_refresh_interval),
                    )
        except Exception as recover_err:
            deps.log_to_ui('warn', f'⚠️ 通知页空列表软恢复失败: {recover_err}')
    return 0


def scan_persistent_notification_tab(blocked_users, deps, max_recent_minutes=None, allow_refresh=True):
    """扫描持久通知标签页。"""
    if deps.notification_tab is None:
        return 0

    try:
        if max_recent_minutes is None:
            max_recent_minutes = deps.NOTIFICATION_RECENT_WINDOW_MINUTES

        with deps.notification_tab_lock:
            if not deps.notification_tab:
                return 0
            tab = deps.notification_tab
            now_ts = time.time()
            did_refresh = False
            refresh_strategy = 'scan_only'
            need_refresh = allow_refresh and (
                float(deps.notification_last_refresh_at or 0.0) <= 0
                or (now_ts - float(deps.notification_last_refresh_at or 0.0)) >= float(deps.notification_refresh_interval or 0.0)
            )
            try:
                cur_url = str(tab.url or '')
            except Exception:
                cur_url = ''
            if 'notifications' not in cur_url and allow_refresh:
                tab.get('https://x.com/notifications')
                _stabilize_notification_tab(tab, deps)
                did_refresh = True
                refresh_strategy = 'navigate_to_notifications'
            elif need_refresh:
                try:
                    tab.refresh()
                    _stabilize_notification_tab(tab, deps)
                    did_refresh = True
                    refresh_strategy = 'hard_refresh'
                except Exception:
                    pass
            if not did_refresh:
                _stabilize_notification_tab(tab, deps)
            if did_refresh:
                next_refresh_interval = deps._schedule_next_notification_refresh_interval(deps.notification_refresh_interval)
                deps._set_runtime_attr('notification_last_refresh_at', now_ts)
                deps._set_runtime_attr('notification_refresh_interval', next_refresh_interval)
                deps.log_to_ui('debug', f'📬 通知刷新策略={refresh_strategy}，下次刷新间隔: {next_refresh_interval:.1f}s')

        notif_items, notif_err = deps.scan_notifications_page(
            tab,
            blocked_users,
            max_recent_minutes,
            allow_navigation=allow_refresh,
        )
        if notif_err:
            err_text = str(notif_err).lower()
            disconnected = ('cannot connect' in err_text) or ('disconnected' in err_text)
            if disconnected:
                deps.notification_disconnect_streak += 1
                deps.log_to_ui('warn', f'⚠️ 通知标签页连接断开（连续{deps.notification_disconnect_streak}次）')
                deps.close_notification_tab()
                deps.ensure_notification_tab(blocked_users)
            return 0

        deps.notification_disconnect_streak = 0
        article_count = _get_notification_article_count(tab)
        if (not notif_items) and article_count <= 0:
            return _handle_empty_notification_articles(tab, blocked_users, deps, allow_refresh=allow_refresh)
        if article_count > 0 and getattr(deps, 'notification_empty_article_streak', 0):
            deps._set_runtime_attr('notification_empty_article_streak', 0)

        new_count = 0
        skipped_dup_content = 0
        if notif_items:
            for item in notif_items:
                with deps.data_lock:
                    if item['key'] in deps.history_ids:
                        continue
                    if deps.should_skip_duplicate_content(item.get('handle', ''), item.get('content', '')):
                        deps.history_ids.add(item['key'])
                        skipped_dup_content += 1
                        continue
                    deps.history_ids.add(item['key'])

                try:
                    runtime_base_url = deps.LLM_FILTER_BASE_URL if deps.LLM_FILTER_ENABLED else ''
                    runtime_model = deps.LLM_FILTER_MODEL if deps.LLM_FILTER_ENABLED else ''
                    runtime_api_key = deps.LLM_FILTER_API_KEY if deps.LLM_FILTER_ENABLED else ''
                    analysis = deps.analyze_comment_intent(
                        item.get('content', ''),
                        base_url=runtime_base_url,
                        api_key=runtime_api_key,
                        model=runtime_model,
                        timeout_sec=deps.LLM_FILTER_TIMEOUT_SEC,
                    )
                    item['intent_score'] = int(analysis.get('intent_score', 0))
                    item['intent_level'] = str(analysis.get('intent_level', 'noise'))
                    item['is_intent_user'] = bool(analysis.get('is_intent_user', False))
                    item['force_notify'] = bool(analysis.get('force_notify', False))
                    item['llm_used'] = bool(analysis.get('llm_used', False))
                    item['intent_reason'] = str(analysis.get('reason', '') or '')
                    item['intent_signals'] = list(analysis.get('signals', []))[:8]
                    item['voice_should_notify'] = bool(deps._should_notify_voice_by_intent(analysis))
                except Exception as analyze_err:
                    deps.log_to_ui('warn', f'🤖 AI意向分析[notify_auto] 失败: {analyze_err}')

                with deps.data_lock:
                    deps._ensure_notify_flow_fields(item)
                    deps.pending_results.append(item)
                deps.enqueue_new_data(item)
                try:
                    deps._enqueue_notify_server_audio(item)
                except Exception as audio_err:
                    deps.log_to_ui('warn', f'🔊 [ServerAudio] 通知播报入队失败: {audio_err}')
                new_count += 1

            if new_count > 0:
                deps.save_state()
                deps.log_to_ui('success', f'📬 通知扫描: 新增 {new_count} 条')
            if skipped_dup_content > 0:
                deps.log_to_ui('debug', f'📋 [Notify] 跳过同用户重复内容: {skipped_dup_content}')
        return new_count
    except Exception as e:
        deps.log_to_ui('error', f'通知扫描错误: {str(e)}')
        return 0
