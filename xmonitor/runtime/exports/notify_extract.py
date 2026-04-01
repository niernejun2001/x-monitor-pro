import re

from xmonitor.services.notify.extract import (
    collect_notification_hrefs as _collect_notification_hrefs_impl,
    collect_notification_tweet_texts as _collect_notification_tweet_texts_impl,
    extract_notification_content as _extract_notification_content_impl,
    extract_notification_status_info as _extract_notification_status_info_impl,
    extract_status_from_href as _extract_status_from_href_impl,
)
from xmonitor.services.notify.match import (
    extract_status_id_from_notification_item as _extract_status_id_from_notification_item_impl,
    extract_status_ids_from_article as _extract_status_ids_from_article_impl,
    is_reply_to_me_notification_item as _is_reply_to_me_notification_item_impl,
    match_notification_card_for_reply as _match_notification_card_for_reply_impl,
    match_reply_target_article as _match_reply_target_article_impl,
)
from xmonitor.services.notify.scan_helpers import (
    extract_notification_handle as _extract_notification_handle_impl,
    parse_notification_age_minutes as _parse_notification_age_minutes_impl,
)


def build_notify_extract_exports(
    *,
    pick_best_status_id_fn,
    reply_to_you_keywords,
    normalize_handle_fn,
    normalize_content_for_dedupe_fn,
    normalize_one_line_fn,
    is_noise_notification_text_fn,
    score_notification_candidate_fn,
):
    def _parse_notification_age_minutes(article):
        return _parse_notification_age_minutes_impl(article)

    def _extract_notification_handle(article, article_text):
        return _extract_notification_handle_impl(article, article_text)

    def _normalize_notification_text(text):
        return re.sub(r'\s+', ' ', text or '').strip()

    def _extract_notification_content(article, article_text, handle):
        return _extract_notification_content_impl(
            article,
            article_text,
            handle,
            normalize_notification_text_fn=_normalize_notification_text,
            is_noise_notification_text_fn=is_noise_notification_text_fn,
            score_notification_candidate_fn=score_notification_candidate_fn,
        )

    def _extract_status_from_href(href):
        return _extract_status_from_href_impl(href, pick_best_status_id_fn=pick_best_status_id_fn)

    def _extract_notification_status_info(article):
        return _extract_notification_status_info_impl(
            article,
            extract_status_from_href_fn=_extract_status_from_href,
            pick_best_status_id_fn=pick_best_status_id_fn,
        )

    def _collect_notification_hrefs(article, max_links=4):
        return _collect_notification_hrefs_impl(article, max_links=max_links)

    def _collect_notification_tweet_texts(article, max_items=2):
        return _collect_notification_tweet_texts_impl(
            article,
            max_items=max_items,
            normalize_one_line_fn=normalize_one_line_fn,
        )

    def extract_status_id_from_notification_item(item):
        return _extract_status_id_from_notification_item_impl(item, pick_best_status_id_fn=pick_best_status_id_fn)

    def is_reply_to_me_notification_item(item):
        return _is_reply_to_me_notification_item_impl(item, reply_to_you_keywords=reply_to_you_keywords)

    def _extract_status_ids_from_article(article):
        return _extract_status_ids_from_article_impl(article, pick_best_status_id_fn=pick_best_status_id_fn)

    def _match_reply_target_article(page, status_id, handle, content):
        return _match_reply_target_article_impl(
            page,
            status_id,
            handle,
            content,
            extract_status_ids_from_article_fn=_extract_status_ids_from_article,
            normalize_handle_fn=normalize_handle_fn,
            normalize_content_for_dedupe_fn=normalize_content_for_dedupe_fn,
        )

    def _match_notification_card_for_reply(page, status_id, handle, content):
        return _match_notification_card_for_reply_impl(
            page,
            status_id,
            handle,
            content,
            extract_notification_status_info_fn=_extract_notification_status_info,
            extract_notification_handle_fn=_extract_notification_handle,
            extract_notification_content_fn=_extract_notification_content,
            normalize_handle_fn=normalize_handle_fn,
            normalize_content_for_dedupe_fn=normalize_content_for_dedupe_fn,
        )

    return {
        '_parse_notification_age_minutes': _parse_notification_age_minutes,
        '_extract_notification_handle': _extract_notification_handle,
        '_normalize_notification_text': _normalize_notification_text,
        '_extract_notification_content': _extract_notification_content,
        '_extract_status_from_href': _extract_status_from_href,
        '_extract_notification_status_info': _extract_notification_status_info,
        '_collect_notification_hrefs': _collect_notification_hrefs,
        '_collect_notification_tweet_texts': _collect_notification_tweet_texts,
        'extract_status_id_from_notification_item': extract_status_id_from_notification_item,
        'is_reply_to_me_notification_item': is_reply_to_me_notification_item,
        '_extract_status_ids_from_article': _extract_status_ids_from_article,
        '_match_reply_target_article': _match_reply_target_article,
        '_match_notification_card_for_reply': _match_notification_card_for_reply,
    }
