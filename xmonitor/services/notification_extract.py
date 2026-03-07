import re


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
        key = normalized.lower()
        if key in seen:
            return
        seen.add(key)
        candidates.append((source, normalized))
        if source == 'tweetText':
            tweet_text_candidates.append(normalized)

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
            r'(?:回复了你|replied to you)[:：]\s*(.+)$',
            r'(?:提到了你|mentioned you)[:：]\s*(.+)$',
        ]
        for pattern in tail_patterns:
            match = re.search(pattern, one_line, flags=re.IGNORECASE)
            if match:
                add_candidate('tail', match.group(1))

        cleaned = one_line
        cleaned = re.sub(r'@\w+', ' ', cleaned)
        cleaned = re.sub(r'(回复了你|提到了你|点赞了|转发了|关注了你)', ' ', cleaned)
        cleaned = re.sub(r'\b(replied to you|mentioned you|liked|retweeted|reposted|followed you)\b', ' ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b\d+[smhd]\b', ' ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip(' -:|')
        add_candidate('cleaned', cleaned)

    if tweet_text_candidates:
        best_tweet = ''
        best_tweet_score = -10**9
        for txt in tweet_text_candidates:
            if is_noise_notification_text_fn(txt, handle, user_name_candidates):
                continue
            score = score_notification_candidate_fn(txt, 'tweetText', user_name_candidates)
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
    raw = str(href or '').strip()
    if not raw:
        return None, None
    match = re.search(r'/(?:i/(?:web/)?status|web/status)/(\d{6,25})', raw)
    if match:
        sid = pick_best_status_id_fn(match.group(1), raw)
        if sid:
            return None, sid
    user_matches = list(re.finditer(r'/([A-Za-z0-9_]+)/status/(\d{6,25})', raw))
    if user_matches:
        best = None
        best_len = -1
        for match in user_matches:
            uname = str(match.group(1) or '').strip().lower()
            if uname in {'i', 'web'}:
                continue
            sid = pick_best_status_id_fn(match.group(2), raw)
            if sid and len(sid) > best_len:
                best = (match.group(1), sid)
                best_len = len(sid)
        if best:
            return f'@{best[0]}', best[1]
    match = re.search(r'conversation_id=(\d{6,25})', raw)
    if match:
        sid = pick_best_status_id_fn(match.group(1), raw)
        if sid:
            return None, sid
    return None, None


def extract_notification_status_info(article, *, extract_status_from_href_fn, pick_best_status_id_fn):
    try:
        links = article.eles('tag:a', timeout=0)
        for link in links:
            href = (link.attr('href') or '').strip()
            if not href:
                continue
            status_handle, status_id = extract_status_from_href_fn(href)
            if status_id:
                return status_handle, status_id
    except Exception:
        pass
    try:
        raw_html = str(article.html or '')
        if raw_html:
            time_href_matches = re.findall(
                r'<a[^>]+href=[\'"]([^\'"]+)[\'"][^>]*>\s*<time\b',
                raw_html,
                flags=re.IGNORECASE | re.DOTALL,
            )
            for href in reversed(time_href_matches):
                status_handle, status_id = extract_status_from_href_fn(href)
                if status_id:
                    return status_handle, status_id
            href_matches = re.findall(r'href=[\'"]([^\'"]+)[\'"]', raw_html, flags=re.IGNORECASE)
            for href in reversed(href_matches):
                status_handle, status_id = extract_status_from_href_fn(href)
                if status_id:
                    return status_handle, status_id
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
            if len(hrefs) >= max_links:
                break
    except Exception:
        pass
    return hrefs


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
    return samples
