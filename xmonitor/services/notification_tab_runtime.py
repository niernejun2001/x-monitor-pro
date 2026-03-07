import datetime
import random
import time


def scan_persistent_notification_tab(blocked_users, deps, max_recent_minutes=None):
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
            need_refresh = (
                float(deps.notification_last_refresh_at or 0.0) <= 0
                or (now_ts - float(deps.notification_last_refresh_at or 0.0)) >= float(deps.notification_refresh_interval or 0.0)
            )
            try:
                cur_url = str(tab.url or '')
            except Exception:
                cur_url = ''
            if 'notifications' not in cur_url:
                tab.get('https://x.com/notifications')
                deps._wait_document_ready(tab, timeout=5.0)
                time.sleep(random.uniform(0.5, 1.2))
            elif need_refresh:
                try:
                    tab.refresh()
                    deps._wait_document_ready(tab, timeout=5.0)
                    time.sleep(random.uniform(0.5, 1.2))
                except Exception:
                    pass
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
            deps._set_runtime_attr('notification_last_refresh_at', now_ts)
            deps._set_runtime_attr(
                'notification_refresh_interval',
                deps._schedule_next_notification_refresh_interval(deps.notification_refresh_interval),
            )

        notif_items, notif_err = deps.scan_notifications_page(tab, blocked_users, max_recent_minutes)
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
                    deps.pending_results.append(item)
                deps.enqueue_new_data(item)
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
