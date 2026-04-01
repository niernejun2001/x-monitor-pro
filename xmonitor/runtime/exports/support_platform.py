from xmonitor.services.platform.twitter_cli import (
    build_twitter_cli_runtime_payload as _build_twitter_cli_runtime_payload_impl,
    enrich_notification_from_twitter_cli as _enrich_notification_from_twitter_cli_impl,
    fetch_twitter_cli_tweet_detail as _fetch_twitter_cli_tweet_detail_impl,
    fetch_twitter_cli_user as _fetch_twitter_cli_user_impl,
    get_twitter_cli_status as _get_twitter_cli_status_impl,
)


def build_support_platform_exports(deps):
    def _build_twitter_cli_runtime_payload():
        return _build_twitter_cli_runtime_payload_impl(deps)

    def _get_twitter_cli_status(verify=False):
        return _get_twitter_cli_status_impl(deps, verify=verify)

    def _fetch_twitter_cli_tweet_detail(tweet_id, max_count=8, force_refresh=False):
        return _fetch_twitter_cli_tweet_detail_impl(
            deps,
            tweet_id,
            max_count=max_count,
            force_refresh=force_refresh,
        )

    def _fetch_twitter_cli_user(screen_name, force_refresh=False):
        return _fetch_twitter_cli_user_impl(
            deps,
            screen_name,
            force_refresh=force_refresh,
        )

    def _enrich_notification_from_twitter_cli(status_id, handle_hint='', content_hint=''):
        return _enrich_notification_from_twitter_cli_impl(
            deps,
            status_id,
            handle_hint=handle_hint,
            content_hint=content_hint,
        )

    return {
        '_build_twitter_cli_runtime_payload': _build_twitter_cli_runtime_payload,
        '_get_twitter_cli_status': _get_twitter_cli_status,
        '_fetch_twitter_cli_tweet_detail': _fetch_twitter_cli_tweet_detail,
        '_fetch_twitter_cli_user': _fetch_twitter_cli_user,
        '_enrich_notification_from_twitter_cli': _enrich_notification_from_twitter_cli,
    }
