import re
import time


def normalize_handle(handle):
    if not handle:
        return ""
    return str(handle).strip().lstrip('@').lower()


def normalize_text_for_compare(text):
    value = str(text or "")
    value = value.replace("\u200b", "").replace("\ufeff", "")
    value = re.sub(r'\s+', ' ', value).strip()
    return value


def sanitize_dm_message_text(text):
    value = str(text or "")
    if not value:
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "")
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in value.split("\n")]
    clean_lines = []
    for line in lines:
        if not line and (not clean_lines or clean_lines[-1] == ""):
            continue
        if clean_lines and line and line == clean_lines[-1]:
            continue
        clean_lines.append(line)
    while clean_lines and clean_lines[0] == "":
        clean_lines.pop(0)
    while clean_lines and clean_lines[-1] == "":
        clean_lines.pop()
    value = "\n".join(clean_lines).strip()
    compact = normalize_text_for_compare(value)
    if len(compact) >= 24 and len(compact) % 2 == 0:
        half = len(compact) // 2
        if compact[:half] == compact[half:]:
            value = compact[:half]
    return value


def is_link_only_message(text):
    value = normalize_text_for_compare(text).strip().lower()
    if not value:
        return False
    value = value.replace("https://", "").replace("http://", "")
    return bool(re.fullmatch(r'(x\.com/[^\s]+|www\.x\.com/[^\s]+|[^\s]+/status/\d+)', value))


def normalize_status_id_digits(digits):
    value = re.sub(r'\D+', '', str(digits or ''))
    if len(value) < 15:
        return ""
    if len(value) % 2 == 0:
        half = len(value) // 2
        if half >= 15 and value[:half] == value[half:]:
            value = value[:half]
    if len(value) > 20:
        value = value[:19]
    return value if len(value) >= 15 else ""


def extract_status_id_candidates_from_text(text):
    raw = str(text or "")
    if not raw:
        return []
    candidates = []
    for pattern in (r'/status/(\d{8,80})', r'conversation_id=(\d{8,80})', r'(?<!\d)(\d{15,80})(?!\d)'):
        for match in re.findall(pattern, raw):
            sid = normalize_status_id_digits(match)
            if sid:
                candidates.append(sid)
    return candidates


def pick_best_status_id(*parts):
    all_ids = []
    for part in parts:
        all_ids.extend(extract_status_id_candidates_from_text(part))
    if not all_ids:
        return ""
    max_len = max(len(x) for x in all_ids)
    long_ids = [x for x in all_ids if len(x) == max_len]
    return long_ids[-1] if long_ids else all_ids[-1]


def normalize_dm_share_link(raw_link, status_id="", status_handle="", fallback_url=""):
    raw_link = str(raw_link or "").strip()
    fallback_url = str(fallback_url or "").strip()
    handle_norm = normalize_handle(status_handle)
    if raw_link:
        sid_raw = pick_best_status_id(raw_link)
        if sid_raw:
            match = re.search(r'(?:https?://)?(?:www\.)?x\.com/([A-Za-z0-9_]+)/status/\d+', raw_link, flags=re.IGNORECASE)
            if match:
                return f"https://x.com/{match.group(1)}/status/{sid_raw}"
            path_match = re.search(r'^/([A-Za-z0-9_]+)/status/\d+', raw_link)
            if path_match:
                return f"https://x.com/{path_match.group(1)}/status/{sid_raw}"
            if handle_norm:
                return f"https://x.com/{handle_norm}/status/{sid_raw}"
            return f"https://x.com/i/status/{sid_raw}"
        http_match = re.search(r'https?://[^\s<>"\']+', raw_link)
        if http_match:
            return http_match.group(0).strip()
    if fallback_url:
        sid_fb = pick_best_status_id(fallback_url)
        if sid_fb:
            match = re.search(r'(?:https?://)?(?:www\.)?x\.com/([A-Za-z0-9_]+)/status/\d+', fallback_url, flags=re.IGNORECASE)
            if match:
                return f"https://x.com/{match.group(1)}/status/{sid_fb}"
            if handle_norm:
                return f"https://x.com/{handle_norm}/status/{sid_fb}"
            return f"https://x.com/i/status/{sid_fb}"
        http_match = re.search(r'https?://[^\s<>"\']+', fallback_url)
        if http_match:
            return http_match.group(0).strip()
    sid = pick_best_status_id(status_id)
    if sid and handle_norm:
        return f"https://x.com/{handle_norm}/status/{sid}"
    if sid:
        return f"https://x.com/i/status/{sid}"
    return ""


def build_dm_message_probes(text):
    raw = sanitize_dm_message_text(text)
    if not raw:
        return []
    compact = normalize_text_for_compare(raw)
    probes = []
    for url in re.findall(r'https?://\S+', compact, flags=re.IGNORECASE):
        url = url.strip()
        if url and url not in probes:
            probes.append(url.lower())
    if len(compact) >= 20:
        probes.append(compact[:48].lower())
        probes.append(compact[-36:].lower())
    else:
        probes.append(compact.lower())
    uniq = []
    seen = set()
    for probe in probes:
        if not probe or probe in seen:
            continue
        seen.add(probe)
        uniq.append(probe)
    return uniq


def get_dm_conversation_text(tab):
    if not tab:
        return ""
    try:
        return str(tab.run_js(
            """
            const root =
              document.querySelector('[data-testid="DmActivityViewport"]') ||
              document.querySelector('[data-testid="DmActivityContainer"]') ||
              document.querySelector('section[role="region"]');
            if (!root) return '';
            const clone = root.cloneNode(true);
            clone.querySelectorAll(
              'aside, header, [role="status"], [data-testid="dmComposerTextInput"], [data-testid="dmComposerTextInputRichTextInputContainer"], [data-testid="dmComposerTextInput_label"], [data-xm-dm-root], [data-xm-dm-target], [data-xm-dm-send-target], textarea, [role="textbox"], [contenteditable="true"], [contenteditable="plaintext-only"], input, button, [role="button"]'
            ).forEach((node) => {
              try { node.remove(); } catch (e) {}
            });
            return String(clone.innerText || clone.textContent || '');
            """
        ) or "")
    except Exception:
        return ""


def count_dm_probe_occurrence(tab, probe_text):
    if not tab or not probe_text:
        return 0
    haystack = normalize_text_for_compare(get_dm_conversation_text(tab))
    needle = normalize_text_for_compare(probe_text)
    if not haystack or not needle:
        return 0
    return haystack.count(needle)


def count_dm_sent_markers(tab):
    haystack = normalize_text_for_compare(get_dm_conversation_text(tab))
    if not haystack:
        return 0
    total = 0
    for marker in ('已发送', 'sent'):
        total += haystack.count(normalize_text_for_compare(marker))
    return total


def confirm_dm_message_sent(tab, before_counts, probes, wait_sec=1.15):
    if not probes:
        return False
    before_snapshot = normalize_text_for_compare(str((before_counts or {}).get('__snapshot', '') or ''))
    before_markers = int((before_counts or {}).get('__sent_markers', 0) or 0)
    deadline = time.time() + max(0.2, float(wait_sec))
    while time.time() < deadline:
        current_snapshot = normalize_text_for_compare(get_dm_conversation_text(tab))
        if current_snapshot:
            for probe in probes:
                prev = int(before_counts.get(probe, 0))
                now = count_dm_probe_occurrence(tab, probe)
                if now > prev:
                    return True
            now_markers = count_dm_sent_markers(tab)
            if now_markers > before_markers and current_snapshot != before_snapshot:
                return True
        time.sleep(0.12)
    return False
