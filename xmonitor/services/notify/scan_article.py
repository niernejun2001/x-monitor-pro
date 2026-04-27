import datetime
import hashlib

from xmonitor.services.notify.scan_logging import format_notify_error
from xmonitor.services.support.status_links import canonical_status_url


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
        'recovered_status_id': 0,
        'recovered_handle': 0,
        'twitter_cli_enrich_ok': 0,
        'twitter_cli_enrich_errors': 0,
        'twitter_cli_enrich_content_filled': 0,
        'twitter_cli_enrich_handle_filled': 0,
    }


def _normalize_trace_sample(deps, article_text):
    return deps._normalize_one_line(article_text)


def _normalize_share_status_url_from_raw(raw_url, status_id, status_handle, deps):
    raw = str(raw_url or '').strip()
    sid = str(status_id or '').strip()
    normalizer = getattr(deps, '_normalize_dm_share_link', None)
    if callable(normalizer):
        try:
            normalized = str(
                normalizer(
                    raw,
                    status_id=sid,
                    status_handle=status_handle,
                    fallback_url=raw,
                ) or ''
            ).strip()
            if normalized:
                return normalized
        except Exception:
            pass
    return canonical_status_url(
        raw,
        status_id=sid,
        status_handle=status_handle,
        normalize_handle_fn=deps.normalize_handle,
        pick_best_status_id_fn=deps._pick_best_status_id,
    )


def _normalize_share_status_url(status_id, status_handle, twitter_cli_enriched, deps):
    if isinstance(twitter_cli_enriched, dict):
        status_url = str((twitter_cli_enriched or {}).get('status_url', '') or '').strip()
        if status_url:
            return _normalize_share_status_url_from_raw(status_url, status_id, status_handle, deps)
    return _normalize_share_status_url_from_raw('', status_id, status_handle, deps)


def _resolve_status_handle(status_handle, handle):
    primary = str(status_handle or '').strip()
    if primary:
        return primary if primary.startswith('@') else f'@{primary}'
    fallback = str(handle or '').strip()
    if fallback.startswith('@') and len(fallback) > 1:
        return fallback
    return f'@{fallback}' if fallback else ''


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


def _recover_status_id_from_article(article, deps):
    try:
        html = str(article.html or '')
    except Exception:
        html = ''
    if not html:
        return '', []
    hints = list(deps._extract_status_id_candidates_from_text(html) or [])
    recovered = deps._pick_best_status_id(*hints) if hints else ''
    return recovered, hints


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
        recovered_status_id, html_status_hints = ('', [])
        if not status_id:
            recovered_status_id, html_status_hints = _recover_status_id_from_article(article, deps)
            if recovered_status_id:
                status_id = recovered_status_id
                stats['recovered_status_id'] += 1
                if idx <= trace_limit:
                    traces.append(
                        f'A{idx:02d} recover=status_hint status_id={status_id} hints={html_status_hints[:3]}'
                    )
        if not status_id and not is_reply_like:
            stats['skipped_non_reply'] += 1
            if idx <= trace_limit:
                hrefs = deps._collect_notification_hrefs(article)
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

        twitter_cli_enriched = None
        twitter_cli_enrich_error = ''
        twitter_cli_enrich_attempted = False

        def _try_twitter_cli_enrich(handle_hint, content_hint):
            nonlocal twitter_cli_enriched, twitter_cli_enrich_error, twitter_cli_enrich_attempted
            if twitter_cli_enrich_attempted:
                return twitter_cli_enriched
            if not (
                status_id
                and getattr(deps, 'TWITTER_CLI_ENABLED', False)
                and getattr(deps, 'TWITTER_CLI_NOTIFY_ENRICH', False)
            ):
                return twitter_cli_enriched
            twitter_cli_enrich_attempted = True
            try:
                twitter_cli_enriched = deps._enrich_notification_from_twitter_cli(
                    status_id,
                    handle_hint=handle_hint,
                    content_hint=content_hint,
                )
            except Exception as enrich_err:
                twitter_cli_enriched = {
                    'status': 'err',
                    'msg': format_notify_error(enrich_err),
                }
                stats['twitter_cli_enrich_errors'] += 1
                twitter_cli_enrich_error = str(twitter_cli_enriched.get('msg', '') or '').strip()
                if idx <= trace_limit:
                    traces.append(
                        f'A{idx:02d} enrich=twitter_cli_err status_id={status_id} '
                        f'err={deps._normalize_one_line(twitter_cli_enrich_error, 80)}'
                    )
            return twitter_cli_enriched

        handle = status_handle or deps._extract_notification_handle(article, article_text)
        if (not handle or not status_handle) and status_id:
            enrich_result = _try_twitter_cli_enrich(handle or '', '')
            if isinstance(enrich_result, dict) and enrich_result.get('status') == 'ok':
                stats['twitter_cli_enrich_ok'] += 1
                enriched_status_handle = str(enrich_result.get('status_handle', '') or '').strip()
                if (not status_handle) and enriched_status_handle:
                    status_handle = enriched_status_handle
                    stats['twitter_cli_enrich_handle_filled'] += 1
                if (not handle) and enriched_status_handle:
                    handle = enriched_status_handle
                    stats['recovered_handle'] += 1
        if not handle:
            stats['skipped_no_handle'] += 1
            if idx <= trace_limit:
                enrich_hint = f' enrich_err={deps._normalize_one_line(twitter_cli_enrich_error, 80)}' if twitter_cli_enrich_error else ''
                hrefs = deps._collect_notification_hrefs(article)
                tweet_texts = deps._collect_notification_tweet_texts(article)
                status_hint = html_status_hints[-1] if html_status_hints else ''
                traces.append(
                    f'A{idx:02d} skip=no_handle status_id={status_id} age={age_minutes}'
                    f" status_hint={status_hint or '-'} tweetText={tweet_texts or '-'} hrefs={hrefs}{enrich_hint} text={trace_sample}"
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
        if (
            status_id
            and getattr(deps, 'TWITTER_CLI_ENABLED', False)
            and getattr(deps, 'TWITTER_CLI_NOTIFY_ENRICH', False)
            and ((not content) or (not status_handle))
        ):
            _try_twitter_cli_enrich(handle, content)
            if isinstance(twitter_cli_enriched, dict) and twitter_cli_enriched.get('status') == 'ok':
                if not stats['twitter_cli_enrich_ok']:
                    stats['twitter_cli_enrich_ok'] += 1
                enriched_content = str(twitter_cli_enriched.get('content', '') or '').strip()
                enriched_status_handle = str(twitter_cli_enriched.get('status_handle', '') or '').strip()
                if (not content) and enriched_content:
                    content = enriched_content
                    stats['twitter_cli_enrich_content_filled'] += 1
                if (not status_handle) and enriched_status_handle:
                    status_handle = enriched_status_handle
                    stats['twitter_cli_enrich_handle_filled'] += 1
                if idx <= trace_limit:
                    traces.append(
                        f'A{idx:02d} enrich=twitter_cli status_id={status_id} '
                        f'handle={status_handle or handle} content={deps._normalize_one_line(content, 80)}'
                    )
        if not content:
            stats['skipped_no_content'] += 1
            if idx <= trace_limit:
                enrich_hint = f' enrich_err={deps._normalize_one_line(twitter_cli_enrich_error, 80)}' if twitter_cli_enrich_error else ''
                hrefs = deps._collect_notification_hrefs(article)
                tweet_texts = deps._collect_notification_tweet_texts(article)
                traces.append(
                    f'A{idx:02d} skip=no_content handle={handle} status_id={status_id}'
                    f" tweetText={tweet_texts or '-'} hrefs={hrefs}{enrich_hint} text={trace_sample}"
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
        resolved_status_handle = _resolve_status_handle(status_handle, handle)
        status_url = _normalize_share_status_url(status_id, resolved_status_handle, twitter_cli_enriched, deps)
        result = {
            'handle': handle,
            'content': content,
            'key': unique_key,
            'source': '通知页面',
            'time': datetime.datetime.now().strftime('%H:%M:%S'),
            'status_id': status_id or '',
            'status_handle': resolved_status_handle,
            'notification_type': notification_type,
            'is_reply_to_me': bool(is_reply_to_me),
            'is_mention_to_me': bool(is_mention_to_me),
            'notification_text': relation['normalized_text'][:600],
            'notification_age_minutes': (round(float(age_minutes), 2) if age_minutes is not None else None),
            'status_url': status_url,
            'twitter_cli_enriched': bool(
                isinstance(twitter_cli_enriched, dict) and twitter_cli_enriched.get('status') == 'ok'
            ),
            'twitter_cli_enrich_source': (
                str((twitter_cli_enriched or {}).get('source', '') or '').strip()
                if isinstance(twitter_cli_enriched, dict) else ''
            ),
            'twitter_cli_enrich_error': twitter_cli_enrich_error,
        }
        if idx <= trace_limit:
            traces.append(
                f'A{idx:02d} pass handle={handle} status_id={status_id} age={age_minutes} content={deps._normalize_one_line(content)}'
            )
        return {'result': result, 'stats': stats, 'traces': traces, 'notification_type': notification_type}
    except Exception as article_err:
        stats['article_errors'] += 1
        if idx <= trace_limit:
            traces.append(f'A{idx:02d} skip=exception err={deps._normalize_one_line(format_notify_error(article_err), 160)}')
        return {'result': None, 'stats': stats, 'traces': traces}
