def ensure_dm_session_ready_for_handle(tab, handle, deps, allow_reopen=True):
    """发送前会话闸门：保证在目标私信会话中且编辑器可用。"""
    handle_norm = deps.normalize_handle(handle)
    state = deps._read_dm_session_state(tab, handle_norm)
    if state.get('ready'):
        return state
    if not allow_reopen:
        return state
    editor, err = deps._open_dm_editor_for_handle(tab, handle_norm)
    state2 = deps._read_dm_session_state(tab, handle_norm)
    state2['reopen_err'] = str(err or '')
    state2['reopen_editor_found'] = bool(editor)
    state2['ready'] = bool(state2.get('url_ok') and state2.get('editor_ok') and state2.get('conversation_ok'))
    return state2
