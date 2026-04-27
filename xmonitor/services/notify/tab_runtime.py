import datetime
import random
import time

from xmonitor.services.notify.scan_logging import format_notify_error
from xmonitor.services.notify.schedule_state import update_notification_refresh_schedule


def _get_notification_article_count(tab):
    try:
        return len(tab.eles('tag:article', timeout=0.4) or [])
    except Exception:
        return 0


def _safe_int(value, default=0):
    try:
        return int(float(value if value is not None else default))
    except Exception:
        return int(default)


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


def _is_notification_tab_disconnected(err_text):
    low = str(err_text or '').lower()
    keywords = (
        'cannot connect',
        'disconnected',
        'pagedisconnectederror',
        'page disconnected',
        '与页面的连接已断开',
        '连接已断开',
    )
    return any(keyword in low for keyword in keywords)


def _handle_notification_tab_disconnect(blocked_users, deps):
    deps.notification_disconnect_streak += 1
    deps.log_to_ui('warn', f'⚠️ 通知标签页连接断开（连续{deps.notification_disconnect_streak}次）')
    deps.close_notification_tab()
    deps.ensure_notification_tab(blocked_users)
    return 0


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
        update_notification_refresh_schedule(deps, last_refresh_at=0.0)
        return 0

    if streak >= soft_threshold:
        deps.log_to_ui('warn', f'⚠️ 通知页连续空列表达到 {streak} 次，执行软恢复刷新')
        try:
            with deps.notification_tab_lock:
                current_tab = deps.notification_tab
                if current_tab:
                    current_tab.get('https://x.com/notifications')
                    _stabilize_notification_tab(current_tab, deps)
                    update_notification_refresh_schedule(
                        deps,
                        last_refresh_at=time.time(),
                        interval=deps._schedule_next_notification_refresh_interval(deps.notification_refresh_interval),
                    )
        except Exception as recover_err:
            deps.log_to_ui('warn', f'⚠️ 通知页空列表软恢复失败: {recover_err}')
    return 0


def _retry_scan_after_empty_refresh(tab, blocked_users, deps, max_recent_minutes):
    deps.log_to_ui('debug', '📬 通知页刷新后首轮为空，执行同轮快速复查')
    time.sleep(random.uniform(0.35, 0.75))
    _stabilize_notification_tab(tab, deps)
    return deps.scan_notifications_page(
        tab,
        blocked_users,
        max_recent_minutes,
        allow_navigation=False,
    )


def _wait_for_articles_after_refresh(tab, deps, timeout_sec=2.2, poll_sec=0.2):
    deadline = time.time() + max(0.4, float(timeout_sec))
    while time.time() < deadline:
        article_count = _get_notification_article_count(tab)
        if article_count > 0:
            return article_count
        deps._wait_document_ready(tab, timeout=min(1.0, max(0.2, float(poll_sec))))
        time.sleep(max(0.05, float(poll_sec)))
    return _get_notification_article_count(tab)


def _mark_notification_idle_cycle(deps):
    idle_scan_streak = int(getattr(deps, 'notification_idle_scan_streak', 0) or 0) + 1
    deps._set_runtime_attr('notification_idle_scan_streak', idle_scan_streak)
    return idle_scan_streak


def _mark_notification_hit_cycle(deps, hit_ts=None):
    deps._set_runtime_attr('notification_idle_scan_streak', 0)
    deps._set_runtime_attr('notification_last_new_item_at', float(hit_ts if hit_ts is not None else time.time()))


def scan_persistent_notification_tab(blocked_users, deps, max_recent_minutes=None, allow_refresh=True):
    """扫描持久通知标签页。"""
    if deps.notification_tab is None:
        return 0

    try:
        if max_recent_minutes is None:
            max_recent_minutes = deps.NOTIFICATION_RECENT_WINDOW_MINUTES

        warmed_article_count = None

        with deps.notification_tab_lock:
            if not deps.notification_tab:
                return 0
            tab = deps.notification_tab
            now_ts = time.time()
            ready_at = float(getattr(deps, 'notification_tab_ready_at', 0.0) or 0.0)
            if ready_at > now_ts:
                return 0
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
                deps._set_runtime_attr('notification_tab_ready_at', time.time() + random.uniform(0.6, 1.4))
                next_refresh_interval = deps._schedule_next_notification_refresh_interval(deps.notification_refresh_interval)
                update_notification_refresh_schedule(deps, last_refresh_at=now_ts, interval=next_refresh_interval)
                deps.log_to_ui('debug', f'📬 通知刷新策略={refresh_strategy}，下次刷新间隔: {next_refresh_interval:.1f}s')
                warmed_article_count = _wait_for_articles_after_refresh(tab, deps, timeout_sec=3.6, poll_sec=0.22)
                if allow_refresh:
                    deps._set_runtime_attr('notification_scan_preflight_deadline_at', time.time() + 1.8)
                deps._set_runtime_attr('notification_tab_ready_at', 0.0)

        if did_refresh and allow_refresh and int(warmed_article_count or 0) <= 0:
            deps.log_to_ui('debug', '📬 通知页刷新后未稳定，先执行预扫描复查')
            notif_items, notif_err = _retry_scan_after_empty_refresh(tab, blocked_users, deps, max_recent_minutes)
        else:
            notif_items, notif_err = deps.scan_notifications_page(
                tab,
                blocked_users,
                max_recent_minutes,
                allow_navigation=allow_refresh,
            )
        article_count = _get_notification_article_count(tab)
        if did_refresh and (not notif_items) and article_count <= 0 and allow_refresh:
            notif_items, notif_err = _retry_scan_after_empty_refresh(tab, blocked_users, deps, max_recent_minutes)
        if did_refresh:
            deps._set_runtime_attr('notification_scan_preflight_deadline_at', 0.0)
        if notif_err:
            if _is_notification_tab_disconnected(notif_err):
                return _handle_notification_tab_disconnect(blocked_users, deps)
            return 0

        deps.notification_disconnect_streak = 0
        article_count = _get_notification_article_count(tab)
        if (not notif_items) and article_count <= 0:
            _mark_notification_idle_cycle(deps)
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
                    analysis_map = analysis if isinstance(analysis, dict) else {}
                    item['intent_score'] = _safe_int(analysis_map.get('intent_score', 0), 0)
                    item['intent_level'] = str(analysis_map.get('intent_level', 'noise'))
                    item['is_intent_user'] = bool(analysis_map.get('is_intent_user', False))
                    item['force_notify'] = bool(analysis_map.get('force_notify', False))
                    item['llm_used'] = bool(analysis_map.get('llm_used', False))
                    item['intent_reason'] = str(analysis_map.get('reason', '') or '')
                    item['intent_signals'] = list(analysis_map.get('signals', []))[:8]
                    item['voice_should_notify'] = bool(deps._should_notify_voice_by_intent(analysis_map))
                except Exception as analyze_err:
                    deps.log_to_ui('warn', f'🤖 AI意向分析[notify_auto] 失败: {format_notify_error(analyze_err)}')

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
                _mark_notification_hit_cycle(deps)
                deps.save_state()
                deps.log_to_ui('success', f'📬 通知扫描: 新增 {new_count} 条')
            else:
                _mark_notification_idle_cycle(deps)
            if skipped_dup_content > 0:
                deps.log_to_ui('debug', f'📋 [Notify] 跳过同用户重复内容: {skipped_dup_content}')
        else:
            _mark_notification_idle_cycle(deps)
        return new_count
    except Exception as e:
        deps.log_to_ui('error', f'通知扫描错误: {format_notify_error(e)}')
        return 0
