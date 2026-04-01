from xmonitor.browser.core.maintenance import run_headful_soft_maintenance as _run_headful_soft_maintenance_impl
from xmonitor.browser.core.manager import (
    cleanup_global_browser as _cleanup_global_browser_impl,
    init_global_browser as _init_global_browser_impl,
    restart_global_browser as _restart_global_browser_impl,
)
from xmonitor.runtime.dm_critical import (
    enter_dm_critical as _enter_dm_critical_impl,
    is_dm_critical_active as _is_dm_critical_active_impl,
    leave_dm_critical as _leave_dm_critical_impl,
    maybe_log_dm_critical_skip as _maybe_log_dm_critical_skip_impl,
)
from xmonitor.runtime.monitor_runtime import monitoring_loop as _monitoring_loop_impl
from xmonitor.runtime.runtime_state import (
    build_runtime_state as _build_runtime_state_impl,
    get_runtime_attr as _get_runtime_attr_impl,
    set_runtime_attr as _set_runtime_attr_impl,
)
from xmonitor.services.support.template_utils import (
    normalize_keyword_lines as _normalize_keyword_lines_impl,
    render_llm_prompt_template as _render_llm_prompt_template_impl,
    sanitize_template_list as _sanitize_template_list_impl,
)
from xmonitor.storage.notify.facade import NotifyStateFacade
from xmonitor.storage.repositories import MonitorTasksRepository, PendingResultsRepository, ProcessedUsersRepository
from xmonitor.storage.state.io import (
    load_state as _load_state_impl,
    save_processed_users as _save_processed_users_impl,
    save_state as _save_state_impl,
)


def initialize_runtime_components(deps):
    return {
        'runtime_state': _build_runtime_state_impl(deps),
        'monitor_tasks_repo': MonitorTasksRepository(deps),
        'pending_results_repo': PendingResultsRepository(deps),
        'processed_users_repo': ProcessedUsersRepository(deps),
        'notify_state_facade': NotifyStateFacade(deps),
    }


def build_core_runtime_exports(deps):
    def _set_runtime_attr(name, value):
        return _set_runtime_attr_impl(deps, name, value)

    def _get_runtime_attr(name, default=None):
        return _get_runtime_attr_impl(deps, name, default=default)

    def _enter_dm_critical(section='dm_send'):
        return _enter_dm_critical_impl(deps, section=section)

    def _leave_dm_critical():
        return _leave_dm_critical_impl(deps)

    def _is_dm_critical_active():
        return _is_dm_critical_active_impl(deps)

    def _maybe_log_dm_critical_skip():
        return _maybe_log_dm_critical_skip_impl(deps)

    def init_global_browser():
        return _init_global_browser_impl(deps)

    def cleanup_global_browser():
        return _cleanup_global_browser_impl(deps)

    def restart_global_browser():
        return _restart_global_browser_impl(deps)

    def run_headful_soft_maintenance(blocked_users, notify_enabled):
        return _run_headful_soft_maintenance_impl(blocked_users, notify_enabled, deps)

    def monitoring_loop():
        return _monitoring_loop_impl(deps)

    def save_state():
        return _save_state_impl(deps)

    def load_state():
        return _load_state_impl(deps)

    def save_processed_users():
        return _save_processed_users_impl(deps)

    def _sanitize_template_list(raw_list, fallback_list):
        return _sanitize_template_list_impl(raw_list, fallback_list)

    def _normalize_keyword_lines(raw_text):
        return _normalize_keyword_lines_impl(raw_text)

    def _render_llm_prompt_template(template_text, content, fallback_prompt):
        return _render_llm_prompt_template_impl(template_text, content, fallback_prompt)

    return {
        '_set_runtime_attr': _set_runtime_attr,
        '_get_runtime_attr': _get_runtime_attr,
        '_enter_dm_critical': _enter_dm_critical,
        '_leave_dm_critical': _leave_dm_critical,
        '_is_dm_critical_active': _is_dm_critical_active,
        '_maybe_log_dm_critical_skip': _maybe_log_dm_critical_skip,
        'init_global_browser': init_global_browser,
        'cleanup_global_browser': cleanup_global_browser,
        'restart_global_browser': restart_global_browser,
        'run_headful_soft_maintenance': run_headful_soft_maintenance,
        'monitoring_loop': monitoring_loop,
        'save_state': save_state,
        'load_state': load_state,
        'save_processed_users': save_processed_users,
        '_sanitize_template_list': _sanitize_template_list,
        '_normalize_keyword_lines': _normalize_keyword_lines,
        '_render_llm_prompt_template': _render_llm_prompt_template,
    }
