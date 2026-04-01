from xmonitor.services.dm.common import (
    build_dm_message_probes as _build_dm_message_probes_impl,
    confirm_dm_message_sent as _confirm_dm_message_sent_impl,
    conversation_contains_dm_text as _conversation_contains_dm_text_impl,
    count_dm_probe_occurrence as _count_dm_probe_occurrence_impl,
    count_dm_sent_markers as _count_dm_sent_markers_impl,
    get_dm_conversation_text as _get_dm_conversation_text_impl,
    is_link_only_message as _is_link_only_message_impl,
    normalize_dm_share_link as _normalize_dm_share_link_impl,
)


def build_dm_common_exports():
    return {
        '_normalize_dm_share_link': _normalize_dm_share_link_impl,
        '_is_link_only_message': _is_link_only_message_impl,
        '_build_dm_message_probes': _build_dm_message_probes_impl,
        '_get_dm_conversation_text': _get_dm_conversation_text_impl,
        '_conversation_contains_dm_text': _conversation_contains_dm_text_impl,
        '_confirm_dm_message_sent': _confirm_dm_message_sent_impl,
        '_count_dm_probe_occurrence': _count_dm_probe_occurrence_impl,
        '_count_dm_sent_markers': _count_dm_sent_markers_impl,
    }
