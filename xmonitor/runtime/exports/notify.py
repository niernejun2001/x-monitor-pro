from xmonitor.runtime.exports.notify_browser import build_notify_browser_exports
from xmonitor.runtime.exports.notify_extract import build_notify_extract_exports
from xmonitor.runtime.exports.notify_flow import build_notify_flow_exports
from xmonitor.runtime.exports.notify_scan import build_notify_scan_exports
from xmonitor.runtime.exports.notify_text import build_notify_text_exports


def build_notify_runtime_exports(
    deps,
    *,
    is_noise_notification_text_fn,
    normalize_content_for_dedupe_fn,
    normalize_handle_fn,
    normalize_one_line_fn,
    pick_best_status_id_fn,
    reply_to_you_keywords,
    score_notification_candidate_fn,
):
    exports = {}
    exports.update(build_notify_browser_exports(deps))
    exports.update(build_notify_flow_exports())
    exports.update(build_notify_text_exports())
    exports.update(
        build_notify_extract_exports(
            pick_best_status_id_fn=pick_best_status_id_fn,
            reply_to_you_keywords=reply_to_you_keywords,
            normalize_handle_fn=normalize_handle_fn,
            normalize_content_for_dedupe_fn=normalize_content_for_dedupe_fn,
            normalize_one_line_fn=normalize_one_line_fn,
            is_noise_notification_text_fn=is_noise_notification_text_fn,
            score_notification_candidate_fn=score_notification_candidate_fn,
        )
    )
    exports.update(build_notify_scan_exports(deps))
    return exports
