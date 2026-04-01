import datetime
import hashlib
import re


def _empty_stats():
    return {
        'new_captured': 0,
        'skipped_old': 0,
        'skipped_non_reply': 0,
        'skipped_no_status': 0,
        'skipped_no_content': 0,
        'skipped_blacklist': 0,
        'skipped_duplicate': 0,
        'skipped_no_handle': 0,
        'skipped_interaction': 0,
        'skipped_empty_text': 0,
        'policy_flagged_emoji_only': 0,
        'policy_flagged_blocked_mention': 0,
        'article_errors': 0,
    }


def _normalize_trace_sample(deps, article_text):
    return deps._normalize_one_line(article_text)


def _normalize_share_status_url(status_id, status_handle, twitter_cli_enriched, deps):
    if isinstance(twitter_cli_enriched, dict):
        status_url = str((twitter_cli_enriched or {}).get('status_url', '') or '').strip()
        if status_url:
            return status_url
    if status_id and status_handle:
        return f"https://x.com/{deps.normalize_handle(status_handle)}/status/{status_id}"
    if status_id:
        return f'https://x.com/i/status/{status_id}'
    return ''


def _build_unique_key(article, status_id, handle_norm, content, deps):
    if status_id:
        return f'notif_status_{deps._pick_best_status_id(status_id)}', status_id
    try:
        time_ele = article.ele('tag:time', timeout=0)
    except Exception:
        time_ele = None
    time_token = ''
    if time_ele:
        time_token = ((time_ele.attr('datetime') or time_ele.text or '')).strip()
    raw_key = f'{handle_norm}|{content}|{time_token}'
    digest = hashlib.md5(raw_key.encode('utf-8')).hexdigest()[:20]
    return f'notif_fallback_{digest}', status_id


def process_notification_article(
    article,
    idx,
    *,
    max_recent_minutes,
    trace_limit,
    blocked_norm_set,
    delegated_norm,
    seen_in_page,
    deps,
):
    stats = _empty_stats()
    traces = []
    try:
        article_text = article.text or ''
        if not article_text:
            stats['skipped_empty_text'] += 1
            if idx <= trace_limit:
                traces.append(f'A{idx:02d} skip=empty_text')
            return {'result': None, 'stats': stats, 'traces': traces}

        trace_sample = _normalize_trace_sample(deps, article_text)
        relation = deps._classify_notification_type(article_text)
        notification_type = relation['notification_type']
        is_reply_like = relation['is_reply_like']
        is_reply_to_me = relation['is_reply_to_me']
        is_mention_to_me = relation['is_mention_to_me']
        is_interaction_only = relation['is_interaction_only']

        if is_interaction_only:
            stats['skipped_interaction'] += 1
            if idx <= trace_limit:
                traces.append(f'A{idx:02d} skip=interaction type={notification_type} text={trace_sample}')
            return {'result': None, 'stats': stats, 'traces': traces}

        if deps.NOTIFICATION_REPLY_ONLY_MODE and (not is_reply_to_me):
            stats['skipped_non_reply'] += 1
            if idx <= trace_limit:
                traces.append(f'A{idx:02d} skip=reply_only_filter type={notification_type} text={trace_sample}')
            return {'result': None, 'stats': stats, 'traces': traces}

        status_handle, status_id = deps._extract_notification_status_info(article)
        if not status_id and not is_reply_like:
            stats['skipped_non_reply'] += 1
            if idx <= trace_limit:
                hrefs = deps._collect_notification_hrefs(article)
                html_status_hints = deps._extract_status_id_candidates_from_text(article.html or '')
                status_hint = html_status_hints[-1] if html_status_hints else ''
                tweet_texts = deps._collect_notification_tweet_texts(article)
                traces.append(
                    f'A{idx:02d} skip=non_reply status_id=None is_reply_like={is_reply_like} '
                    f"status_hint={status_hint or '-'} tweetText={tweet_texts or '-'} hrefs={hrefs} text={trace_sample}"
                )
            return {'result': None, 'stats': stats, 'traces': traces}
        if not status_id and is_reply_like:
            stats['skipped_no_status'] += 1
            if idx <= trace_limit:
                hrefs = deps._collect_notification_hrefs(article)
                traces.append(
                    f'A{idx:02d} keep=fallback_no_status type={notification_type} '
                    f'is_reply_like={is_reply_like} hrefs={hrefs} text={trace_sample}'
                )

        age_minutes = deps._parse_notification_age_minutes(article)
        if age_minutes is not None and age_minutes > max_recent_minutes:
            stats['skipped_old'] += 1
            if idx <= trace_limit:
                traces.append(
                    f'A{idx:02d} skip=old age={age_minutes:.1f}m status_id={status_id} text={trace_sample}'
                )
            return {'result': None, 'stats': stats, 'traces': traces}

        handle = status_handle or deps._extract_notification_handle(article, article_text)
        if not handle:
            stats['skipped_no_handle'] += 1
            if idx <= trace_limit:
                traces.append(
                    f'A{idx:02d} skip=no_handle status_id={status_id} age={age_minutes} text={trace_sample}'
                )
            return {'result': None, 'stats': stats, 'traces': traces}

        handle_norm = handle.strip().lstrip('@').lower()
        should_skip_block = (handle_norm in blocked_norm_set and (not delegated_norm or handle_norm != delegated_norm))
        if should_skip_block:
            stats['skipped_blacklist'] += 1
            if idx <= trace_limit:
                traces.append(
                    f'A{idx:02d} skip=blacklist handle={handle} status_id={status_id} text={trace_sample}'
                )
            return {'result': None, 'stats': stats, 'traces': traces}

        content = deps._extract_notification_content(article, article_text, handle)
        twitter_cli_enriched = None
        if (
            status_id
            and getattr(deps, 'TWITTER_CLI_ENABLED', False)
            and getattr(deps, 'TWITTER_CLI_NOTIFY_ENRICH', False)
            and ((not content) or (not status_handle))
        ):
            try:
                twitter_cli_enriched = deps._enrich_notification_from_twitter_cli(
                    status_id,
                    handle_hint=handle,
                    content_hint=content,
                )
            except Exception as enrich_err:
                twitter_cli_enriched = {
                    'status': 'err',
                    'msg': str(enrich_err),
                }
            if isinstance(twitter_cli_enriched, dict) and twitter_cli_enriched.get('status') == 'ok':
                enriched_content = str(twitter_cli_enriched.get('content', '') or '').strip()
                enriched_status_handle = str(twitter_cli_enriched.get('status_handle', '') or '').strip()
                if (not content) and enriched_content:
                    content = enriched_content
                if (not status_handle) and enriched_status_handle:
                    status_handle = enriched_status_handle
                if idx <= trace_limit:
                    traces.append(
                        f'A{idx:02d} enrich=twitter_cli status_id={status_id} '
                        f'handle={status_handle or handle} content={deps._normalize_one_line(content, 80)}'
                    )
        if not content:
            stats['skipped_no_content'] += 1
            if idx <= trace_limit:
                traces.append(
                    f'A{idx:02d} skip=no_content handle={handle} status_id={status_id} text={trace_sample}'
                )
            return {'result': None, 'stats': stats, 'traces': traces}

        should_skip_policy, policy_reason = deps.should_skip_content_by_policy(content)
        if should_skip_policy:
            if policy_reason == 'emoji_only':
                stats['policy_flagged_emoji_only'] += 1
            elif policy_reason == 'blocked_mention':
                stats['policy_flagged_blocked_mention'] += 1
            if idx <= trace_limit:
                traces.append(
                    f'A{idx:02d} skip=policy reason={policy_reason} handle={handle} status_id={status_id} content={deps._normalize_one_line(content)}'
                )
            return {'result': None, 'stats': stats, 'traces': traces}

        unique_key, status_id = _build_unique_key(article, status_id, handle_norm, content, deps)
        if unique_key in seen_in_page or unique_key in deps.history_ids:
            stats['skipped_duplicate'] += 1
            if idx <= trace_limit:
                traces.append(
                    f'A{idx:02d} skip=duplicate handle={handle} status_id={status_id} key={unique_key}'
                )
            return {'result': None, 'stats': stats, 'traces': traces}
        seen_in_page.add(unique_key)

        stats['new_captured'] += 1
        status_url = _normalize_share_status_url(status_id, status_handle, twitter_cli_enriched, deps)
        result = {
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
            'status_url': status_url,
            'status_handle': (status_handle or '').strip(),
            'twitter_cli_enriched': bool(
                isinstance(twitter_cli_enriched, dict) and twitter_cli_enriched.get('status') == 'ok'
            ),
            'twitter_cli_enrich_source': (
                str((twitter_cli_enriched or {}).get('source', '') or '').strip()
                if isinstance(twitter_cli_enriched, dict) else ''
            ),
        }
        if idx <= trace_limit:
            traces.append(
                f'A{idx:02d} pass handle={handle} status_id={status_id} age={age_minutes} content={deps._normalize_one_line(content)}'
            )
        return {'result': result, 'stats': stats, 'traces': traces, 'notification_type': notification_type}
    except Exception as article_err:
        stats['article_errors'] += 1
        if idx <= trace_limit:
            traces.append(f'A{idx:02d} skip=exception err={deps._normalize_one_line(article_err, 160)}')
        return {'result': None, 'stats': stats, 'traces': traces}
