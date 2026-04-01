import re


def sanitize_template_list(raw_list, fallback_list):
    """清洗模板列表：去空、去重、保序；若为空则回退默认。"""
    cleaned = []
    seen = set()
    if isinstance(raw_list, list):
        for item in raw_list:
            text = str(item or '').strip()
            if not text or text in seen:
                continue
            seen.add(text)
            cleaned.append(text)
    if cleaned:
        return cleaned
    return list(fallback_list)


def normalize_keyword_lines(raw_text):
    """将多行/逗号分隔关键词清洗为去重后的列表。"""
    cleaned = []
    seen = set()
    raw = str(raw_text or '')
    for part in re.split(r'[\n,，;；]+', raw):
        kw = str(part or '').strip()
        if not kw:
            continue
        low = kw.lower()
        if low in seen:
            continue
        seen.add(low)
        cleaned.append(kw)
    return cleaned


def render_llm_prompt_template(template_text, content, fallback_prompt):
    """
    渲染可配置 prompt：
    - 支持 {content} 或 {{content}} 占位
    - 若未包含占位，自动在末尾追加评论内容
    """
    tpl = str(template_text or '').strip()
    content_text = str(content or '')
    if not tpl:
        return str(fallback_prompt or '')
    if '{content}' in tpl or '{{content}}' in tpl:
        return tpl.replace('{{content}}', content_text).replace('{content}', content_text)
    return f'{tpl}\n评论内容: {content_text}'
