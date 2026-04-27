import logging

from xmonitor.services.support.error_format import format_runtime_error
from xmonitor.services.support.state_payload import build_storage_state_payload
from xmonitor.storage.state.io_common import write_json_snapshot
from xmonitor.storage.state.sqlite import (
    APP_STATE_KEY,
    PROCESSED_USERS_KEY,
    save_blob as _save_sqlite_blob,
    save_processed_users_set as _save_processed_users_set,
    save_structured_state as _save_structured_state,
    sqlite_json_fallback_enabled as _sqlite_json_fallback_enabled,
)


def save_state(deps):
    deps.ensure_data_dir()
    state = build_storage_state_payload(deps)
    sqlite_ok = False
    try:
        _save_sqlite_blob(deps, APP_STATE_KEY, state)
        _save_structured_state(deps, deps.pending_results, deps.history_ids, deps.content_dedupe)
        sqlite_ok = True
    except Exception as e:
        logging.error(f'保存SQLite状态失败: {format_runtime_error(e)}')

    json_ok = False
    if _sqlite_json_fallback_enabled(deps):
        try:
            write_json_snapshot(deps.STATE_FILE, state)
            json_ok = True
        except Exception as e:
            logging.error(f'保存JSON状态失败: {format_runtime_error(e)}')

    if sqlite_ok or json_ok:
        logging.info(
            f"💾 状态已保存: {len(deps.pending_results)} 条待处理，{len(deps.history_ids)} 条历史ID，{len(deps.content_dedupe)} 条内容签名"
        )
    else:
        logging.error('保存状态失败: SQLite 与 JSON 均未成功')


def save_processed_users(deps):
    deps.ensure_data_dir()
    payload = sorted(str(x) for x in deps.processed_users)
    sqlite_ok = False
    try:
        _save_sqlite_blob(deps, PROCESSED_USERS_KEY, payload)
        _save_processed_users_set(deps, payload)
        sqlite_ok = True
    except Exception as e:
        logging.error(f'保存SQLite黑名单失败: {format_runtime_error(e)}')

    json_ok = False
    if _sqlite_json_fallback_enabled(deps):
        try:
            write_json_snapshot(deps.PROCESSED_FILE, payload)
            json_ok = True
        except Exception as e:
            logging.error(f'保存JSON黑名单失败: {format_runtime_error(e)}')

    if sqlite_ok or json_ok:
        logging.info(f'💾 已保存 {len(deps.processed_users)} 个已处理用户')
    else:
        logging.error('保存黑名单失败: SQLite 与 JSON 均未成功')
