import datetime
import json
import os
import random
import re
import time


def as_json_safe(obj):
    """将对象转换为可 JSON 序列化内容。"""
    try:
        json.dumps(obj, ensure_ascii=False)
        return obj
    except Exception:
        return str(obj)


def probe_selectors_snapshot(tab, selectors):
    """抓取一组选择器命中状态，便于定位无头偶发问题。"""
    snapshot = []
    for selector in selectors or []:
        item = {
            'selector': selector,
            'matched': False,
            'displayed': False,
            'disabled': False,
            'error': '',
        }
        try:
            node = tab.ele(selector, timeout=0.25)
            item['matched'] = bool(node)
            if node:
                try:
                    item['displayed'] = bool(node.states.is_displayed)
                except Exception:
                    item['displayed'] = False
                try:
                    aria_disabled = (node.attr('aria-disabled') or '').lower() == 'true'
                    html_disabled = node.attr('disabled') is not None
                    item['disabled'] = bool(aria_disabled or html_disabled)
                except Exception:
                    item['disabled'] = False
        except Exception as e:
            item['error'] = str(e)
        snapshot.append(item)
    return snapshot


def capture_runtime_diagnostic(tab, stage, deps, err=None, selectors=None, extra=None):
    """落盘失败现场（json + screenshot），用于无头稳定性排查。"""
    try:
        os.makedirs(deps.DIAG_DIR, exist_ok=True)
    except Exception:
        return ''

    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    base = re.sub(r'[^a-zA-Z0-9_.-]', '_', str(stage or 'runtime'))[:64]
    prefix = f'{ts}-{base}-{random.randint(1000, 9999)}'
    json_path = os.path.join(deps.DIAG_DIR, f'{prefix}.json')
    png_path = os.path.join(deps.DIAG_DIR, f'{prefix}.png')

    payload = {
        'time': datetime.datetime.now().isoformat(),
        'stage': str(stage or ''),
        'error': str(err or ''),
        'headless_mode': bool(deps.headless_mode),
        'selectors': probe_selectors_snapshot(tab, selectors),
        'extra': as_json_safe(extra or {}),
        'screenshot_saved': False,
        'screenshot_path': png_path,
        'screenshot_error': '',
    }

    if tab is not None:
        try:
            payload['url'] = str(tab.url or '')
        except Exception:
            payload['url'] = ''
        try:
            payload['ready_state'] = tab.run_js('return document.readyState')
        except Exception:
            payload['ready_state'] = ''
        try:
            payload['title'] = str(tab.run_js("return document.title || ''") or '')
        except Exception:
            payload['title'] = ''
        try:
            payload['dialog_guard_logs'] = as_json_safe(
                tab.run_js('return Array.isArray(window.__xmonDialogGuardLogs) ? window.__xmonDialogGuardLogs : []') or []
            )
        except Exception:
            payload['dialog_guard_logs'] = []
        try:
            html_text = str(getattr(tab, 'html', '') or '')
            max_chars = max(1000, int(deps.HEADLESS_DIAG_MAX_HTML_CHARS))
            payload['html_head'] = html_text[:max_chars]
            payload['html_len'] = len(html_text)
        except Exception as e:
            payload['html_head'] = ''
            payload['html_len'] = -1
            payload['html_error'] = str(e)

        def _try_capture_screenshot_once():
            local_saved = False
            local_err = ''
            for method_name in ('get_screenshot', 'save_screenshot'):
                method = getattr(tab, method_name, None)
                if not callable(method):
                    continue
                try:
                    try:
                        method(path=png_path, full_page=True)
                    except TypeError:
                        try:
                            method(path=png_path)
                        except TypeError:
                            method(png_path)
                    local_saved = os.path.exists(png_path)
                    if local_saved:
                        break
                except Exception as e:
                    local_err = str(e)
            return local_saved, local_err

        shot_saved, shot_err = _try_capture_screenshot_once()
        if (not shot_saved) and deps._is_unhandled_prompt_error(shot_err):
            deps._dismiss_pending_browser_prompt(tab, max_rounds=(5 if deps.headless_mode else 2))
            time.sleep(0.12)
            shot_saved, shot_err = _try_capture_screenshot_once()
        payload['screenshot_saved'] = shot_saved
        payload['screenshot_error'] = shot_err

    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        deps.log_to_ui('warn', f'🧪 失败现场已落盘: {json_path}')
        if payload.get('screenshot_saved'):
            deps.log_to_ui('warn', f'🧪 失败截图已保存: {png_path}')
    except Exception as e:
        deps.log_to_ui('warn', f'⚠️ 写入失败诊断文件失败: {e}')
        return ''
    return json_path
