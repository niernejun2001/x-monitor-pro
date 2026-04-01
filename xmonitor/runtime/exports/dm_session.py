from xmonitor.services.dm.context_service import ensure_dm_session_ready_for_handle as _ensure_dm_session_ready_for_handle_impl
from xmonitor.services.dm.flow_service import (
    ensure_dm_context_for_handle as _ensure_dm_context_for_handle_impl,
    should_use_share_link_quick_path as _should_use_share_link_quick_path_impl,
)
from xmonitor.services.dm.open_service import open_dm_editor_for_handle as _open_dm_editor_for_handle_impl
from xmonitor.services.dm.recovery_service import (
    read_dm_session_state as _read_dm_session_state_impl,
    run_dm_send_sequence_once as _run_dm_send_sequence_once_impl,
    run_dm_send_with_recovery as _run_dm_send_with_recovery_impl,
)
from xmonitor.services.dm.send_service import (
    send_dm_message as _send_dm_message_impl,
    send_dm_message_with_retry as _send_dm_message_with_retry_impl,
)
from xmonitor.services.notify.reply_service import send_notification_reply as _send_notification_reply_impl


def build_dm_session_exports(deps):
    def _should_use_share_link_quick_path():
        return _should_use_share_link_quick_path_impl(deps)

    def _open_dm_editor_for_handle(tab, handle, ignore_cached_unavailable=False):
        return _open_dm_editor_for_handle_impl(tab, handle, deps=deps, ignore_cached_unavailable=ignore_cached_unavailable)

    def _send_dm_message(tab, text):
        return _send_dm_message_impl(tab, text, deps)

    def _send_dm_message_with_retry(tab, text, handle=''):
        return _send_dm_message_with_retry_impl(tab, text, handle=handle, deps=deps)

    def _read_dm_session_state(tab, handle=''):
        return _read_dm_session_state_impl(tab, handle=handle, deps=deps)

    def _ensure_dm_session_ready_for_handle(tab, handle, allow_reopen=True):
        return _ensure_dm_session_ready_for_handle_impl(tab, handle, deps, allow_reopen=allow_reopen)

    def _ensure_dm_context_for_handle(tab, handle):
        return _ensure_dm_context_for_handle_impl(tab, handle, deps)

    def _run_dm_send_sequence_once(tab, dm_handle, share_link, dm_text, mark_func=None, progress=None, dm_text_supplier=None):
        return _run_dm_send_sequence_once_impl(
            tab,
            dm_handle,
            share_link,
            dm_text,
            deps,
            mark_func=mark_func,
            progress=progress,
            dm_text_supplier=dm_text_supplier,
        )

    def _run_dm_send_with_recovery(tab, dm_handle, share_link, dm_text, mark_func=None, best_effort=False, progress=None, dm_text_supplier=None):
        return _run_dm_send_with_recovery_impl(
            tab,
            dm_handle,
            share_link,
            dm_text,
            deps,
            mark_func=mark_func,
            best_effort=best_effort,
            progress=progress,
            dm_text_supplier=dm_text_supplier,
        )

    def send_notification_reply(item, message, dm_message=''):
        return _send_notification_reply_impl(item, message, deps, dm_message=dm_message)

    return {
        '_should_use_share_link_quick_path': _should_use_share_link_quick_path,
        '_open_dm_editor_for_handle': _open_dm_editor_for_handle,
        '_send_dm_message': _send_dm_message,
        '_send_dm_message_with_retry': _send_dm_message_with_retry,
        '_read_dm_session_state': _read_dm_session_state,
        '_ensure_dm_session_ready_for_handle': _ensure_dm_session_ready_for_handle,
        '_ensure_dm_context_for_handle': _ensure_dm_context_for_handle,
        '_run_dm_send_sequence_once': _run_dm_send_sequence_once,
        '_run_dm_send_with_recovery': _run_dm_send_with_recovery,
        'send_notification_reply': send_notification_reply,
    }
