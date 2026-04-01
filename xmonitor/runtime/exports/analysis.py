from xmonitor.runtime.exports.analysis_dm import build_analysis_dm_exports
from xmonitor.runtime.exports.analysis_filtering import build_analysis_filtering_exports
from xmonitor.runtime.exports.analysis_intent import build_analysis_intent_exports
from xmonitor.runtime.exports.analysis_llm import build_analysis_llm_exports


def build_analysis_runtime_exports(deps):
    exports = {}
    exports.update(build_analysis_llm_exports(deps))
    exports.update(build_analysis_dm_exports(deps))
    exports.update(build_analysis_intent_exports(deps))
    exports.update(build_analysis_filtering_exports(deps))
    return exports
