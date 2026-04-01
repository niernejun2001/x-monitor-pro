from xmonitor.runtime.exports.core_events import build_core_event_exports
from xmonitor.runtime.exports.core_runtime import (
    build_core_runtime_exports as _build_core_runtime_exports_impl,
    initialize_runtime_components,
)


def build_core_runtime_exports(
    deps,
    *,
    runtime_log_file,
    msg_queue,
    headless_mode_getter,
    verbose_flag_getter,
    traceback_module,
):
    exports = {}
    exports.update(_build_core_runtime_exports_impl(deps))
    exports.update(
        build_core_event_exports(
            deps,
            runtime_log_file=runtime_log_file,
            msg_queue=msg_queue,
            headless_mode_getter=headless_mode_getter,
            verbose_flag_getter=verbose_flag_getter,
            traceback_module=traceback_module,
        )
    )
    return exports
