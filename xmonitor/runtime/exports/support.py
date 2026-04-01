from xmonitor.runtime.exports.support_analysis import build_support_analysis_exports
from xmonitor.runtime.exports.support_audio import build_support_audio_exports
from xmonitor.runtime.exports.support_browser_dom import build_support_browser_dom_exports
from xmonitor.runtime.exports.support_browser_profile import build_support_browser_profile_exports
from xmonitor.runtime.exports.support_platform import build_support_platform_exports
from xmonitor.runtime.exports.support_system import build_support_system_exports


def build_support_runtime_exports(
    deps,
    *,
    safe_float_fn,
    safe_int_fn,
    clamp_llm_timeout_fn,
    env_port_getter,
    logging_module,
):
    exports = {}
    exports.update(
        build_support_system_exports(
            safe_float_fn=safe_float_fn,
            safe_int_fn=safe_int_fn,
            env_port_getter=env_port_getter,
            proxy_env_keys=getattr(deps, 'PROXY_ENV_KEYS', ()),
            logging_module=logging_module,
        )
    )
    exports.update(
        build_support_analysis_exports(
            deps,
            clamp_llm_timeout_fn=clamp_llm_timeout_fn,
        )
    )
    exports.update(build_support_browser_dom_exports())
    exports.update(build_support_browser_profile_exports(deps))
    exports.update(build_support_audio_exports(deps))
    exports.update(build_support_platform_exports(deps))
    return exports
