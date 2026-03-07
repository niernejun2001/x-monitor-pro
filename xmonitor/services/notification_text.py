import re


NOTIFICATION_LIKE_REPLY_KEYWORDS = (
    '喜欢了你的回复',
    'liked your reply',
)

NOTIFICATION_INTERACTION_SKIP_KEYWORDS = (
    '点赞了', 'liked', 'liked your', '转发了', 'reposted', 'retweeted',
    '关注了你', 'followed you', '视频来源', '点赞了你的帖子', 'liked your post',
    '转发了你的帖子', 'reposted your', 'retweet了'
)

NOTIFICATION_REPLY_TO_YOU_KEYWORDS = (
    '回复了你',
    '回复了你的帖子',
    '回复了你的贴文',
    '回复了你的推文',
    'replied to you',
    'replied to your post',
    'replied to your tweet',
)

NOTIFICATION_MENTION_YOU_KEYWORDS = (
    '提到了你',
    '在帖子中提到了你',
    'mentioned you',
    'mentioned you in a post',
)


def normalize_notification_text(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip()


def classify_notification_type(article_text):
    normalized = normalize_notification_text(article_text or '')
    low = normalized.lower()
    is_like_reply = any(k in low for k in NOTIFICATION_LIKE_REPLY_KEYWORDS)
    is_reply_to_me = any(k in low for k in NOTIFICATION_REPLY_TO_YOU_KEYWORDS)
    if not is_reply_to_me:
        reply_hint_patterns = (
            r'(^|\s)回复\s*@['r'\w_]{1,30}',
            r'\breplying to\s+@[\w_]{1,30}',
            r'\bin reply to\s+@[\w_]{1,30}',
        )
        is_reply_to_me = any(re.search(p, normalized, flags=re.IGNORECASE) for p in reply_hint_patterns)
    is_mention_to_me = any(k in low for k in NOTIFICATION_MENTION_YOU_KEYWORDS)
    is_reply_like = is_like_reply or is_reply_to_me or is_mention_to_me
    is_interaction_only = (not is_like_reply) and any(k in low for k in NOTIFICATION_INTERACTION_SKIP_KEYWORDS)
    if is_reply_to_me:
        notification_type = 'reply_to_you'
    elif is_mention_to_me:
        notification_type = 'mention_you'
    elif is_like_reply:
        notification_type = 'liked_your_reply'
    elif is_interaction_only:
        notification_type = 'interaction'
    else:
        notification_type = 'unknown'
    return {
        'notification_type': notification_type,
        'is_reply_to_me': is_reply_to_me,
        'is_mention_to_me': is_mention_to_me,
        'is_reply_like': is_reply_like,
        'is_interaction_only': is_interaction_only,
        'normalized_text': normalized,
        'low_text': low,
    }


def is_display_name_like(text, user_name_candidates):
    if text in user_name_candidates:
        return True
    return any(len(name) >= 4 and (text.startswith(name) or name.startswith(text)) for name in user_name_candidates)


def is_noise_notification_text(text, handle, user_name_candidates):
    if not text:
        return True
    low = text.lower()
    if handle and low == handle.lower():
        return True
    if re.fullmatch(r'@\w+', text):
        return True
    if re.fullmatch(r'\d+[smhd]', low):
        return True
    if text in {'·', '-', '|'}:
        return True
    if is_display_name_like(text, user_name_candidates):
        return True
    action_keywords = [
        'replied to you', 'mentioned you', 'liked', 'retweeted', 'reposted', 'followed you',
        '回复了你', '提到了你', '点赞了', '转发了', '关注了你'
    ]
    if any(k in low for k in action_keywords) and len(text) <= 40:
        cleaned = re.sub(r'@\w+', ' ', low)
        cleaned = re.sub(r'\b\d+[smhd]\b', ' ', cleaned, flags=re.IGNORECASE)
        for keyword in action_keywords:
            cleaned = cleaned.replace(keyword, ' ')
        cleaned = re.sub(r'[\W_]+', ' ', cleaned).strip()
        if len(cleaned) < 2:
            return True
    return False


def score_notification_candidate(text, source, user_name_candidates):
    low = text.lower()
    source_score = {
        'tweetText': 120,
        'lang': 95,
        'tail': 85,
        'line': 70,
        'cleaned': 60,
    }.get(source, 50)
    score = source_score
    length = len(text)
    if 6 <= length <= 180:
        score += 15
    elif length < 4:
        score -= 20
    elif length > 240:
        score -= 10
    if re.search(r'[\u4e00-\u9fffA-Za-z0-9]', text):
        score += 8
    if is_display_name_like(text, user_name_candidates):
        score -= 80
    if re.match(r'^\s*@\w+\s*$', text):
        score -= 40
    if any(k in low for k in ['replied to you', 'mentioned you', '回复了你', '提到了你']):
        score -= 25
    return score


def normalize_one_line(text, limit=120):
    if not text:
        return ''
    compact = re.sub(r'\s+', ' ', str(text)).strip()
    if len(compact) > limit:
        return compact[:limit] + '...'
    return compact
