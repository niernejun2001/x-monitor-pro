import datetime
import random
import time

from xmonitor.services.scan.tweet_scan import scan_page_content as _scan_page_content_impl


def _task_url(task):
    if isinstance(task, dict):
        return str(task.get('url', '') or '').strip()
    return str(task or '').strip()


def _update_task_last_check(task, deps, text):
    if not isinstance(task, dict):
        return
    url = _task_url(task)
    with deps.data_lock:
        rows = []
        for row in deps.monitor_tasks:
            if isinstance(row, dict) and row.get('url') == url:
                updated = dict(row)
                updated['last_check'] = text
                rows.append(updated)
            else:
                rows.append(row)
        setter = getattr(deps, '_set_runtime_attr', None)
        if callable(setter):
            setter('monitor_tasks', rows)
        else:
            deps.monitor_tasks = rows


def _store_scan_results(results, deps):
    added = 0
    duplicate_content = 0
    for item in results or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get('key', '') or '').strip()
        handle = str(item.get('handle', '') or '').strip()
        content = str(item.get('content', '') or '').strip()
        if not key:
            key = f'{handle}_{content[:50]}'

        with deps.data_lock:
            if key in deps.history_ids:
                continue
            if deps.should_skip_duplicate_content(handle, content):
                deps.history_ids.add(key)
                duplicate_content += 1
                continue
            deps.history_ids.add(key)
            deps.pending_results.append(dict(item, key=key))
        deps.enqueue_new_data(dict(item, key=key))
        added += 1

    if duplicate_content:
        deps.log_to_ui('debug', f'📋 [TweetScan] 跳过同用户重复内容: {duplicate_content}')
    return added


def scan_task_worker(task, page, blocked_users, deps):
    url = _task_url(task)
    if not url:
        deps.log_to_ui('warn', '⚠️ 推文扫描任务缺少 URL，已跳过')
        return 0

    deps.log_to_ui('info', f'🔍 开始扫描任务: {url}')
    results, err = deps.scan_page_content(page, url, blocked_users)
    if err:
        _update_task_last_check(task, deps, f'失败: {err}')
        deps.log_to_ui('warn', f'⚠️ 推文扫描失败: {err}')
        return 0

    added = _store_scan_results(results, deps)
    now_text = datetime.datetime.now().strftime('%H:%M:%S')
    _update_task_last_check(task, deps, f'{now_text} 新增 {added}')
    if added > 0:
        deps.save_state()
        deps.log_to_ui('success', f'📝 推文扫描新增 {added} 条评论')
    else:
        deps.log_to_ui('debug', '📝 推文扫描未发现新评论')
    return added


def scan_task_with_tab(task, blocked_users, deps):
    if not getattr(deps, 'browser_initialized', False) or getattr(deps, 'global_browser', None) is None:
        deps.log_to_ui('warn', '⚠️ 浏览器未初始化，跳过推文扫描任务')
        return 0

    url = _task_url(task)
    if not url:
        deps.log_to_ui('warn', '⚠️ 推文扫描任务缺少 URL，已跳过')
        return 0

    tab = None
    try:
        time.sleep(random.uniform(deps.TAB_OPEN_JITTER_MIN_SEC, deps.TAB_OPEN_JITTER_MAX_SEC))
        with deps.tab_lock:
            tab = deps.global_browser.new_tab()
        deps.log_to_ui('debug', f'🧭 已创建推文扫描标签页: {url}')
        results, err = deps.scan_page_content_with_tab(tab, url, blocked_users)
        if err:
            _update_task_last_check(task, deps, f'失败: {err}')
            deps.log_to_ui('warn', f'⚠️ 推文扫描失败: {err}')
            return 0

        added = _store_scan_results(results, deps)
        now_text = datetime.datetime.now().strftime('%H:%M:%S')
        _update_task_last_check(task, deps, f'{now_text} 新增 {added}')
        if added > 0:
            deps.save_state()
            deps.log_to_ui('success', f'📝 推文扫描新增 {added} 条评论')
        else:
            deps.log_to_ui('debug', '📝 推文扫描未发现新评论')
        return added
    except Exception as err:
        err_text = str(err) or type(err).__name__
        _update_task_last_check(task, deps, f'异常: {err_text}')
        deps.log_to_ui('error', f'推文扫描任务异常: {err_text}')
        return 0
    finally:
        if tab is not None:
            try:
                tab.close()
            except Exception:
                pass


def scan_page_content_with_tab(tab, url, blocked_list, deps):
    return _scan_page_content_impl(tab, url, blocked_list, deps)
