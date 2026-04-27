import re

from xmonitor.services.support.status_links import (
    canonical_status_url,
    extract_status_link_parts,
    status_identity,
    status_url_priority,
    status_url_quality,
)

NOTIFY_META_ACTION_PATTERN = (
    r'(?:'
    r'回复了你的帖子'
    r'|回复了你的贴文'
    r'|回复了你的推文'
    r'|回复了你'
    r'|回复(?:\s*@[\w_]{1,30})*'
    r'|在帖子中提到了你'
    r'|提到了你'
    r'|replied to your post'
    r'|replied to your tweet'
    r'|replied to you'
    r'|mentioned you in a post'
    r'|mentioned you'
    r')'
)


def strip_notification_meta_prefix(text):
    raw = str(text or '').strip()
    if not raw:
        return ''
    patterns = (
        rf'^\s*.+?\s+@[\w_]{{1,30}}\s*·\s*[^ ]+\s*{NOTIFY_META_ACTION_PATTERN}\s*',
        rf'^\s*@[\w_]{{1,30}}\s*·\s*[^ ]+\s*{NOTIFY_META_ACTION_PATTERN}\s*',
        rf'^\s*.+?\s*·\s*[^ ]+\s*{NOTIFY_META_ACTION_PATTERN}\s*',
    )
    cleaned = raw
    for pattern in patterns:
        newer = re.sub(pattern, '', cleaned, count=1, flags=re.IGNORECASE).strip(' -:|·')
        if newer and newer != cleaned:
            cleaned = newer
            break
    return cleaned if cleaned != raw else ''


def strip_notification_trailing_metrics(text):
    raw = str(text or '').strip()
    if not raw or re.fullmatch(r'\d{1,6}', raw):
        return ''

    match = re.match(r'^(.*?)(?:\s+(\d{1,4})){1,3}\s*$', raw)
    if not match:
        return ''

    prefix = str(match.group(1) or '').strip(' -:|·')
    if not prefix or prefix == raw:
        return ''

    trailing_tokens = re.findall(r'(\d{1,4})', raw[len(prefix):])
    if len(trailing_tokens) >= 2:
        return prefix

    if re.search(r'[。！？!?…]$', prefix):
        return prefix

    compact_prefix = re.sub(r'\s+', '', prefix)
    if len(compact_prefix) >= 8 and re.search(r'[\u4e00-\u9fffA-Za-z]', prefix):
        return prefix

    return ''


def extract_notification_content(
    article,
    article_text,
    handle,
    *,
    normalize_notification_text_fn,
    is_noise_notification_text_fn,
    score_notification_candidate_fn,
):
    user_name_candidates = set()
    candidates = []
    tweet_text_candidates = []
    seen = set()

    def add_candidate(source, text):
        normalized = normalize_notification_text_fn(text)
        if not normalized:
            return
        variants = [(source, normalized)]
        stripped = strip_notification_meta_prefix(normalized)
        if stripped:
            variants.append((f'{source}_stripped', stripped))
        trimmed_variants = []
        for variant_source, variant_text in list(variants):
            can_trim = str(variant_source).endswith('_stripped') or source in {'tweetText', 'lang', 'tail', 'cleaned'}
            if not can_trim:
                continue
            trimmed = strip_notification_trailing_metrics(variant_text)
            if trimmed:
                trimmed_variants.append((f'{variant_source}_trimmed', trimmed))
        variants.extend(trimmed_variants)
        for variant_source, variant_text in variants:
            key = variant_text.lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.append((variant_source, variant_text))
            if str(variant_source).startswith('tweetText'):
                tweet_text_candidates.append((variant_source, variant_text))

    try:
        user_ele = article.ele('css:[data-testid="User-Name"]', timeout=0)
        if user_ele:
            for seg in re.split(r'[\r\n]+', user_ele.text or ''):
                txt = normalize_notification_text_fn(seg)
                if not txt:
                    continue
                low = txt.lower()
                if re.fullmatch(r'@\w+', txt):
                    continue
                if re.fullmatch(r'\d+[smhd]', low):
                    continue
                if txt in {'·', '-', '|'}:
                    continue
                user_name_candidates.add(txt)
    except Exception:
        pass

    try:
        text_eles = article.eles('css:[data-testid="tweetText"]', timeout=0.25)
        for ele in text_eles:
            add_candidate('tweetText', ele.text or '')
    except Exception:
        pass

    try:
        lang_eles = article.eles('css:div[lang]', timeout=0)
        for ele in lang_eles:
            add_candidate('lang', ele.text or '')
    except Exception:
        pass

    try:
        for line in re.split(r'[\r\n]+', article_text or ''):
            add_candidate('line', line)
    except Exception:
        pass

    one_line = normalize_notification_text_fn(article_text or '')
    if one_line:
        tail_patterns = [
            r'(?:回复了你的帖子|回复了你的贴文|回复了你的推文|replied to your post|replied to your tweet)[:：]\s*(.+)$',
            r'(?:回复了你|replied to you)[:：]\s*(.+)$',
            r'(?:提到了你|mentioned you)[:：]\s*(.+)$',
            r'(?:在帖子中提到了你|mentioned you in a post)[:：]\s*(.+)$',
        ]
        for pattern in tail_patterns:
            match = re.search(pattern, one_line, flags=re.IGNORECASE)
            if match:
                add_candidate('tail', match.group(1))

        cleaned = one_line
        cleaned = re.sub(r'@\w+', ' ', cleaned)
        cleaned = re.sub(
            r'(回复了你的帖子|回复了你的贴文|回复了你的推文|在帖子中提到了你|回复了你|提到了你|点赞了|转发了|关注了你)',
            ' ',
            cleaned,
        )
        cleaned = re.sub(
            r'\b(replied to your post|replied to your tweet|mentioned you in a post|replied to you|mentioned you|liked your|liked|retweeted|reposted|followed you)\b',
            ' ',
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r'\b\d+[smhd]\b', ' ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip(' -:|')
        add_candidate('cleaned', cleaned)

    if tweet_text_candidates:
        best_tweet = ''
        best_tweet_score = -10**9
        for source, txt in tweet_text_candidates:
            if is_noise_notification_text_fn(txt, handle, user_name_candidates):
                continue
            score = score_notification_candidate_fn(txt, source, user_name_candidates)
            txt_low = txt.lower()
            txt_len = len(txt)
            if txt_len <= 4:
                score += 26
            elif txt_len <= 20:
                score += 14
            elif txt_len <= 80:
                score += 8
            elif txt_len > 180:
                score -= 16
            if re.search(r'https?://|www\.', txt_low):
                score -= 8
            if score > best_tweet_score:
                best_tweet_score = score
                best_tweet = txt
        if best_tweet:
            return best_tweet[:280]

    best_text = ''
    best_score = -10**9
    for source, txt in candidates:
        if is_noise_notification_text_fn(txt, handle, user_name_candidates):
            continue
        score = score_notification_candidate_fn(txt, source, user_name_candidates)
        if score > best_score:
            best_score = score
            best_text = txt
    if best_text:
        return best_text[:280]
    return ''


def extract_status_from_href(href, *, pick_best_status_id_fn):
    return extract_status_link_parts(href, pick_best_status_id_fn=pick_best_status_id_fn)


def _fill_status_handle_from_hrefs(status_handle, status_id, hrefs, *, extract_status_from_href_fn):
    current_handle = str(status_handle or '').strip()
    target_status_id = str(status_id or '').strip()
    if current_handle or not target_status_id:
        return current_handle, target_status_id
    for href in hrefs or []:
        try:
            candidate_handle, candidate_status_id = extract_status_from_href_fn(href)
        except Exception:
            continue
        if candidate_handle and str(candidate_status_id or '').strip() == target_status_id:
            return str(candidate_handle or '').strip(), target_status_id
    return current_handle, target_status_id


def extract_notification_status_info(article, *, extract_status_from_href_fn, pick_best_status_id_fn):
    raw_html = ''
    all_hrefs = []
    dom_hrefs = []
    try:
        raw_html = str(article.html or '')
    except Exception:
        raw_html = ''

    try:
        links = article.eles('tag:a', timeout=0)
        for link in links:
            href = (link.attr('href') or '').strip()
            if href:
                dom_hrefs.append(href)
    except Exception:
        dom_hrefs = []

    if raw_html:
        try:
            time_href_matches = re.findall(
                r'<a[^>]+href=[\'"]([^\'"]+)[\'"][^>]*>\s*<time\b',
                raw_html,
                flags=re.IGNORECASE | re.DOTALL,
            )
            all_hrefs.extend(time_href_matches)
            all_hrefs.extend(dom_hrefs)
            for href in reversed(time_href_matches):
                status_handle, status_id = extract_status_from_href_fn(href)
                if status_id:
                    return _fill_status_handle_from_hrefs(
                        status_handle,
                        status_id,
                        all_hrefs,
                        extract_status_from_href_fn=extract_status_from_href_fn,
                    )
        except Exception:
            pass

    try:
        all_hrefs.extend(dom_hrefs)
        for href in reversed(dom_hrefs):
            status_handle, status_id = extract_status_from_href_fn(href)
            if status_id:
                return _fill_status_handle_from_hrefs(
                    status_handle,
                    status_id,
                    all_hrefs,
                    extract_status_from_href_fn=extract_status_from_href_fn,
                )
    except Exception:
        pass

    try:
        if raw_html:
            href_matches = re.findall(r'href=[\'"]([^\'"]+)[\'"]', raw_html, flags=re.IGNORECASE)
            all_hrefs.extend(href_matches)
            for href in reversed(href_matches):
                status_handle, status_id = extract_status_from_href_fn(href)
                if status_id:
                    return _fill_status_handle_from_hrefs(
                        status_handle,
                        status_id,
                        all_hrefs,
                        extract_status_from_href_fn=extract_status_from_href_fn,
                    )
            sid = pick_best_status_id_fn(raw_html)
            if sid:
                return None, sid
    except Exception:
        pass
    return None, None


def collect_notification_hrefs(article, max_links=4):
    hrefs = []
    try:
        links = article.eles('tag:a', timeout=0)
        for link in links:
            href = (link.attr('href') or '').strip()
            if href:
                hrefs.append(href)
    except Exception:
        pass
    if not hrefs:
        try:
            raw_html = str(article.html or '')
            if raw_html:
                hrefs.extend(re.findall(r'href=[\'"]([^\'"]+)[\'"]', raw_html, flags=re.IGNORECASE))
        except Exception:
            pass
    if not hrefs:
        return []

    pick_best_status_id = lambda *parts: next(
        (
            match.group(1)
            for part in parts
            for match in [re.search(r'(\d{6,25})', str(part or ''))]
            if match
        ),
        '',
    )

    def normalize_href(href):
        normalized = canonical_status_url(
            href,
            normalize_handle_fn=lambda handle: str(handle or '').strip().lstrip('@').lower(),
            pick_best_status_id_fn=pick_best_status_id,
        )
        return normalized

    seen = set()
    unique_hrefs = []
    for href in hrefs:
        normalized = normalize_href(href)
        identity = status_identity(normalized, pick_best_status_id_fn=pick_best_status_id)
        if not normalized or identity in seen:
            continue
        seen.add(identity)
        unique_hrefs.append(normalized)

    # Prefer canonical user links over i/status when both point to the same tweet.
    best_by_identity = {}
    for href in unique_hrefs:
        identity = status_identity(href, pick_best_status_id_fn=pick_best_status_id)
        prev = best_by_identity.get(identity)
        if prev is None or status_url_quality(href) > status_url_quality(prev):
            best_by_identity[identity] = href
    unique_hrefs = list(best_by_identity.values())

    unique_hrefs.sort(key=lambda href: (status_url_priority(href), len(str(href or ''))), reverse=True)
    return unique_hrefs[:max_links]


def collect_notification_tweet_texts(article, max_items=2, *, normalize_one_line_fn):
    samples = []
    try:
        text_eles = article.eles('css:[data-testid="tweetText"]', timeout=0)
        for ele in text_eles:
            txt = normalize_one_line_fn(ele.text or '', 80)
            if not txt:
                continue
            samples.append(txt)
            if len(samples) >= max_items:
                break
    except Exception:
        pass
    if len(samples) < max_items:
        try:
            lang_eles = article.eles('css:div[lang]', timeout=0)
            for ele in lang_eles:
                txt = normalize_one_line_fn(ele.text or '', 80)
                if not txt or txt in samples:
                    continue
                samples.append(txt)
                if len(samples) >= max_items:
                    break
        except Exception:
            pass
    if len(samples) < max_items:
        try:
            article_text = str(getattr(article, 'text', '') or '')
            for raw_line in re.split(r'[\r\n]+', article_text):
                txt = normalize_one_line_fn(raw_line or '', 80)
                if not txt:
                    continue
                stripped = strip_notification_meta_prefix(txt)
                if stripped:
                    txt = normalize_one_line_fn(stripped, 80)
                trimmed = strip_notification_trailing_metrics(txt)
                if trimmed:
                    txt = normalize_one_line_fn(trimmed, 80)
                if not txt or txt in samples:
                    continue
                samples.append(txt)
                if len(samples) >= max_items:
                    break
        except Exception:
            pass
    return samples
