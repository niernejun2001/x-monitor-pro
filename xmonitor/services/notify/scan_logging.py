import traceback

from xmonitor.services.support.error_format import format_runtime_error


def format_notify_error(err):
    return format_runtime_error(err)


def merge_scan_stats(target, delta):
    for key, value in (delta or {}).items():
        target[key] = int(target.get(key, 0) or 0) + int(value or 0)
    return target


def log_notification_scan_summary(
    deps,
    *,
    stats,
    trace_logs,
    article_count,
):
    if stats.get('skipped_old', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] 跳过旧通知: {stats['skipped_old']}")
    if stats.get('skipped_non_reply', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] 跳过非回复: {stats['skipped_non_reply']}")
    if stats.get('skipped_interaction', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] 跳过互动通知: {stats['skipped_interaction']}")
    if stats.get('skipped_no_status', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] 回复/提及但无status_id(已兜底): {stats['skipped_no_status']}")
    if stats.get('skipped_no_content', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] 跳过无正文: {stats['skipped_no_content']}")
    if stats.get('skipped_no_handle', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] 跳过无用户: {stats['skipped_no_handle']}")
    if stats.get('skipped_blacklist', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] 跳过保护名单: {stats['skipped_blacklist']}")
    if stats.get('skipped_duplicate', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] 跳过重复: {stats['skipped_duplicate']}")
    if stats.get('skipped_empty_text', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] 跳过空文本: {stats['skipped_empty_text']}")
    if stats.get('policy_flagged_emoji_only', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] 内容标记(纯表情): {stats['policy_flagged_emoji_only']}")
    if stats.get('policy_flagged_blocked_mention', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] 内容标记(指定@): {stats['policy_flagged_blocked_mention']}")
    if stats.get('article_errors', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] article异常: {stats['article_errors']}")
    if stats.get('recovered_status_id', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] 已从HTML恢复status_id: {stats['recovered_status_id']}")
    if stats.get('recovered_handle', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] 已恢复handle: {stats['recovered_handle']}")
    if stats.get('twitter_cli_enrich_ok', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] twitter-cli enrich命中: {stats['twitter_cli_enrich_ok']}")
    if stats.get('twitter_cli_enrich_errors', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] twitter-cli enrich失败: {stats['twitter_cli_enrich_errors']}")
    if stats.get('twitter_cli_enrich_content_filled', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] twitter-cli补全正文: {stats['twitter_cli_enrich_content_filled']}")
    if stats.get('twitter_cli_enrich_handle_filled', 0) > 0:
        deps.log_to_ui('debug', f"📋 [Notify] twitter-cli补全handle: {stats['twitter_cli_enrich_handle_filled']}")
    if stats.get('new_captured', 0) == 0 and article_count > 0 and deps.NOTIFICATION_VERBOSE_TRACE:
        deps.log_to_ui('debug', f'📬 本轮扫描未捕获新通知（articles={article_count}）')
    if trace_logs and (deps.NOTIFICATION_VERBOSE_TRACE and (stats.get('new_captured', 0) == 0 or stats.get('article_errors', 0) > 0)):
        for trace in trace_logs:
            deps.log_to_ui('debug', f'🔎 [NotifyTrace] {trace}')


def log_notification_scan_exception(deps, err):
    deps.log_to_ui('error', f'❌ scan_notifications_page异常: {format_notify_error(err)}')
    deps.log_to_ui('debug', f'🔎 [NotifyTrace] traceback={traceback.format_exc()}')
