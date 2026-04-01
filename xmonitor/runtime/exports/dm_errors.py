from xmonitor.services.dm.error_classifier import (
    classify_dm_error_text as _classify_dm_error_text_impl,
    is_dm_closed_error_text as _is_dm_closed_error_text_impl,
    is_dm_context_or_editor_error_text as _is_dm_context_or_editor_error_text_impl,
    is_dm_context_url as _is_dm_context_url_impl,
    is_dm_send_fallback_continuable_error as _is_dm_send_fallback_continuable_error_impl,
    is_dm_soft_send_error_text as _is_dm_soft_send_error_text_impl,
)


def build_dm_error_exports():
    return {
        '_classify_dm_error_text': _classify_dm_error_text_impl,
        '_is_dm_closed_error_text': _is_dm_closed_error_text_impl,
        '_is_dm_context_or_editor_error_text': _is_dm_context_or_editor_error_text_impl,
        '_is_dm_context_url': _is_dm_context_url_impl,
        '_is_dm_send_fallback_continuable_error': _is_dm_send_fallback_continuable_error_impl,
        '_is_dm_soft_send_error_text': _is_dm_soft_send_error_text_impl,
    }
