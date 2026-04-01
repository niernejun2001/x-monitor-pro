import re


def extract_status_id_from_notification_item(item, *, pick_best_status_id_fn):
    if not isinstance(item, dict):
        return ''
    status_id = pick_best_status_id_fn(
        item.get('status_id', ''),
        item.get('status_url', ''),
        item.get('status_handle', ''),
        item.get('key', ''),
    )
    if status_id:
        return status_id
    key = str(item.get('key', '')).strip()
    match = re.match(r'^notif_status_(\d+)$', key)
    if match:
        sid = pick_best_status_id_fn(match.group(1))
        return sid or match.group(1)
    return ''


def is_reply_to_me_notification_item(item, *, reply_to_you_keywords):
    if not isinstance(item, dict):
        return False
    if item.get('source') != '通知页面':
        return False
    notify_type = str(item.get('notification_type', '') or '').strip().lower()
    if notify_type:
        return notify_type == 'reply_to_you'
    text_blob = ' '.join([
        str(item.get('notification_text', '') or ''),
        str(item.get('content', '') or ''),
    ]).lower()
    return any(keyword in text_blob for keyword in reply_to_you_keywords)


def extract_status_ids_from_article(article, *, pick_best_status_id_fn):
    ids = set()
    try:
        links = article.eles('tag:a', timeout=0)
    except Exception:
        links = []
    for link in links:
        try:
            href = (link.attr('href') or '').strip()
        except Exception:
            href = ''
        if not href:
            continue
        sid = pick_best_status_id_fn(href)
        if sid:
            ids.add(sid)
    return ids


def match_reply_target_article(page, status_id, handle, content, *, extract_status_ids_from_article_fn, normalize_handle_fn, normalize_content_for_dedupe_fn):
    target_status_id = str(status_id or '').strip()
    handle_norm = normalize_handle_fn(handle)
    content_norm = normalize_content_for_dedupe_fn(content or '')
    best_article = None
    best_score = -1
    try:
        articles = page.eles('tag:article', timeout=2)
    except Exception:
        articles = []
    for article in articles[:40]:
        score = 0
        article_status_ids = extract_status_ids_from_article_fn(article)
        if target_status_id:
            if target_status_id in article_status_ids:
                score += 220
            elif article_status_ids:
                continue
        try:
            user_ele = article.ele('css:[data-testid="User-Name"]', timeout=0)
            user_text = (user_ele.text or '').strip().lower() if user_ele else ''
            match = re.search(r'@([a-z0-9_]{1,30})', user_text)
            article_handle = match.group(1) if match else ''
            if handle_norm and article_handle:
                if article_handle == handle_norm:
                    score += 120
                elif handle_norm in article_handle:
                    score += 60
        except Exception:
            pass
        try:
            txt_ele = article.ele('css:[data-testid="tweetText"]', timeout=0)
            article_content = (txt_ele.text or '').strip() if txt_ele else ''
            article_content_norm = normalize_content_for_dedupe_fn(article_content)
            if content_norm and article_content_norm:
                if content_norm in article_content_norm or article_content_norm in content_norm:
                    score += 90
                else:
                    pivot = content_norm[:12]
                    if len(pivot) >= 6 and pivot in article_content_norm:
                        score += 30
        except Exception:
            pass
        has_reply_btn = False
        try:
            reply_btn = article.ele('css:[data-testid="reply"]', timeout=0)
            has_reply_btn = bool(reply_btn and reply_btn.states.is_displayed)
        except Exception:
            has_reply_btn = False
        if has_reply_btn:
            score += 10
        else:
            continue
        if score > best_score:
            best_score = score
            best_article = article
    if best_article is None:
        return None, 0
    return best_article, best_score


def match_notification_card_for_reply(page, status_id, handle, content, *, extract_notification_status_info_fn, extract_notification_handle_fn, extract_notification_content_fn, normalize_handle_fn, normalize_content_for_dedupe_fn):
    target_status_id = str(status_id or '').strip()
    handle_norm = normalize_handle_fn(handle)
    content_norm = normalize_content_for_dedupe_fn(content or '')
    best_article = None
    best_reply_btn = None
    best_score = -1
    try:
        articles = page.eles('tag:article', timeout=2)
    except Exception:
        articles = []
    for article in articles[:80]:
        try:
            article_text = article.text or ''
        except Exception:
            article_text = ''
        score = 0
        card_status_handle, card_status_id = extract_notification_status_info_fn(article)
        if target_status_id:
            if card_status_id == target_status_id:
                score += 260
            elif card_status_id:
                continue
        card_handle = extract_notification_handle_fn(article, article_text) or card_status_handle or ''
        card_handle_norm = normalize_handle_fn(card_handle)
        if handle_norm and card_handle_norm:
            if card_handle_norm == handle_norm:
                score += 100
            elif (handle_norm in card_handle_norm) or (card_handle_norm in handle_norm):
                score += 50
        try:
            card_content = extract_notification_content_fn(article, article_text, card_handle or '')
        except Exception:
            card_content = ''
        card_content_norm = normalize_content_for_dedupe_fn(card_content or '')
        if content_norm and card_content_norm:
            if (content_norm in card_content_norm) or (card_content_norm in content_norm):
                score += 80
            else:
                pivot = content_norm[:12]
                if len(pivot) >= 6 and pivot in card_content_norm:
                    score += 35
        try:
            reply_btn = article.ele('css:[data-testid="reply"]', timeout=0)
            if not (reply_btn and reply_btn.states.is_displayed):
                continue
        except Exception:
            continue
        score += 20
        if score > best_score:
            best_score = score
            best_article = article
            best_reply_btn = reply_btn
    return best_article, best_reply_btn, best_score
