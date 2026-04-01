from xmonitor.services.dm.common import extract_status_id_candidates_from_text as _extract_status_id_candidates_from_text_impl
from xmonitor.services.notify.text import classify_notification_type as _classify_notification_type_impl


def build_notify_text_exports():
    return {
        '_classify_notification_type': _classify_notification_type_impl,
        '_extract_status_id_candidates_from_text': _extract_status_id_candidates_from_text_impl,
    }
