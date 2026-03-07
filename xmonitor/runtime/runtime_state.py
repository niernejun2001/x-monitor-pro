from dataclasses import dataclass
from typing import Any


@dataclass
class RuntimeState:
    monitor_active: bool = False
    monitor_thread: Any = None
    global_browser: Any = None
    global_browser_dir: str | None = None
    browser_initialized: bool = False
    browser_force_temp_profile: bool = False
    reply_work_tab: Any = None
    reply_flow_active: bool = False
    notification_tab: Any = None
    delegated_account_active: str = ''
    delegated_switch_ok: bool = False
    notification_refresh_interval: float = 0.0
    notification_last_refresh_at: float = 0.0
    notification_empty_article_streak: int = 0
    llm_filter_cache: Any = None
    dm_llm_rewrite_history: Any = None
    content_dedupe: Any = None
    pending_results: Any = None
    history_ids: Any = None
    monitor_tasks: Any = None
    last_reply_action_ts: float = 0.0
    last_dm_action_ts: float = 0.0
    reply_failure_streak: int = 0
    reply_handle_failures: Any = None



def build_runtime_state(module):
    return RuntimeState(
        monitor_active=bool(getattr(module, 'monitor_active', False)),
        monitor_thread=getattr(module, 'monitor_thread', None),
        global_browser=getattr(module, 'global_browser', None),
        global_browser_dir=getattr(module, 'global_browser_dir', None),
        browser_initialized=bool(getattr(module, 'browser_initialized', False)),
        browser_force_temp_profile=bool(getattr(module, 'browser_force_temp_profile', False)),
        reply_work_tab=getattr(module, 'reply_work_tab', None),
        reply_flow_active=bool(getattr(module, 'reply_flow_active', False)),
        notification_tab=getattr(module, 'notification_tab', None),
        delegated_account_active=str(getattr(module, 'delegated_account_active', '') or ''),
        delegated_switch_ok=bool(getattr(module, 'delegated_switch_ok', False)),
        notification_refresh_interval=float(getattr(module, 'notification_refresh_interval', 0.0) or 0.0),
        notification_last_refresh_at=float(getattr(module, 'notification_last_refresh_at', 0.0) or 0.0),
        notification_empty_article_streak=int(getattr(module, 'notification_empty_article_streak', 0) or 0),
        llm_filter_cache=getattr(module, 'llm_filter_cache', None),
        dm_llm_rewrite_history=getattr(module, 'dm_llm_rewrite_history', None),
        content_dedupe=getattr(module, 'content_dedupe', None),
        pending_results=getattr(module, 'pending_results', None),
        history_ids=getattr(module, 'history_ids', None),
        monitor_tasks=getattr(module, 'monitor_tasks', None),
        last_reply_action_ts=float(getattr(module, 'last_reply_action_ts', 0.0) or 0.0),
        last_dm_action_ts=float(getattr(module, 'last_dm_action_ts', 0.0) or 0.0),
        reply_failure_streak=int(getattr(module, 'reply_failure_streak', 0) or 0),
        reply_handle_failures=getattr(module, 'reply_handle_failures', None),
    )



def set_runtime_attr(module, name, value):
    state = getattr(module, 'runtime_state', None)
    if state is not None and hasattr(state, name):
        setattr(state, name, value)
    setattr(module, name, value)
    return value



def get_runtime_attr(module, name, default=None):
    state = getattr(module, 'runtime_state', None)
    if state is not None and hasattr(state, name):
        return getattr(state, name)
    return getattr(module, name, default)
