import datetime
import time

from xmonitor.services.notify.scan_article import process_notification_article
from xmonitor.services.notify.scan_logging import (
    format_notify_error,
    log_notification_scan_exception,
    log_notification_scan_summary,
    merge_scan_stats,
)


def _await_notification_articles_if_needed(page, articles, deps):
    current = list(articles or [])
    meta = {'waited': False, 'wait_ms': 0, 'polls': 0}
    try:
        current_url = str(page.url or '')
    except Exception:
        current_url = ''
    if current or 'notifications' not in current_url:
        return current, meta

    deadline = float(getattr(deps, 'notification_scan_preflight_deadline_at', 0.0) or 0.0)
    if deadline <= time.time():
        return current, meta

    if getattr(deps, 'NOTIFICATION_VERBOSE_TRACE', False):
        deps.log_to_ui('debug', '📬 通知页预扫描等待首批 article 稳定')

    started_at = time.time()
    while time.time() < deadline:
        meta['polls'] += 1
        try:
            current = list(page.eles('tag:article', timeout=0.35) or [])
        except Exception:
            current = []
        if current:
            break
        time.sleep(min(0.18, max(0.05, deadline - time.time())))
    meta['waited'] = meta['polls'] > 0
    meta['wait_ms'] = max(0, int(round((time.time() - started_at) * 1000)))
    return current, meta


def scan_notifications_page(page, blocked_list, max_recent_minutes, deps, allow_navigation=True):
    results = []
    seen_in_page = set()
    try:
        if max_recent_minutes is None:
            max_recent_minutes = deps.NOTIFICATION_RECENT_WINDOW_MINUTES
        max_scan_articles = deps.NOTIFICATION_MAX_SCAN_ARTICLES

        if 'notifications' not in page.url:
            if not allow_navigation:
                return results, None
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
        articles, preflight_meta = _await_notification_articles_if_needed(page, articles, deps)
        total_articles = len(articles)
        if len(articles) > max_scan_articles:
            articles = articles[:max_scan_articles]
            deps.log_to_ui(
                'warn',
                f'⚠️ 通知列表过长(total={total_articles})，当前仅扫描前{max_scan_articles}条；可调大 XMONITOR_NOTIFY_MAX_ARTICLES'
            )
        articles = deps.reorder_articles_for_scan(articles)

        stats = {}
        trace_logs = []
        trace_limit = deps.NOTIFICATION_TRACE_MAX_ARTICLES if deps.NOTIFICATION_VERBOSE_TRACE else 0

        if deps.NOTIFICATION_VERBOSE_TRACE:
            preflight_hint = ''
            if preflight_meta.get('waited'):
                preflight_hint = (
                    f" preflight_wait_ms={int(preflight_meta.get('wait_ms', 0) or 0)}"
                    f" preflight_polls={int(preflight_meta.get('polls', 0) or 0)}"
                )
            deps.log_to_ui(
                'debug',
                f'🔎 [NotifyTrace] scan_start url={page.url} articles={len(articles)} recent_window={max_recent_minutes}min{preflight_hint}'
            )

        blocked_norm_set = set()
        for raw_handle in (blocked_list or []):
            norm = deps.normalize_handle(raw_handle)
            if norm:
                blocked_norm_set.add(norm)
        delegated_now = deps.get_effective_delegated_account()
        delegated_norm = deps.normalize_handle(delegated_now)

        for idx, article in enumerate(articles, start=1):
            outcome = process_notification_article(
                article,
                idx,
                max_recent_minutes=max_recent_minutes,
                trace_limit=trace_limit,
                blocked_norm_set=blocked_norm_set,
                delegated_norm=delegated_norm,
                seen_in_page=seen_in_page,
                deps=deps,
            )
            merge_scan_stats(stats, outcome.get('stats'))
            trace_logs.extend(outcome.get('traces') or [])
            result = outcome.get('result')
            if result:
                results.append(result)
                if deps.NOTIFICATION_VERBOSE_TRACE:
                    deps.log_to_ui(
                        'debug',
                        f"📬 [NotifyCandidate][{result.get('notification_type', '')}] {result.get('handle', '')} - {str(result.get('content', ''))[:20]}..."
                    )

        log_notification_scan_summary(
            deps,
            stats=stats,
            trace_logs=trace_logs,
            article_count=len(articles),
        )

        return results, None
    except Exception as e:
        log_notification_scan_exception(deps, e)
        return [], format_notify_error(e)
