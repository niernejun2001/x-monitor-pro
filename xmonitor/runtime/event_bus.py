import queue
import time


def publish_new_data_event(item, deps):
    """发布前端增量事件（广播语义，多客户端互不抢占）。"""
    if not isinstance(item, dict):
        return 0
    snapshot = dict(item)
    with deps.data_lock:
        deps.updates_event_seq += 1
        seq = int(deps.updates_event_seq)
        deps.updates_event_buffer.append({
            'seq': seq,
            'ts': time.time(),
            'data': snapshot,
        })
    return seq


def drain_msg_queue(deps, collect_new_data=False):
    """
    清理旧队列消息，避免日志消息堆积导致内存持续增长。
    仅用于兼容旧逻辑；新前端增量基于 updates_event_buffer。
    """
    out = []
    try:
        while True:
            msg = deps.msg_queue.get_nowait()
            if collect_new_data and isinstance(msg, dict) and msg.get('type') == 'new_data':
                out.append(msg.get('data'))
    except queue.Empty:
        pass
    return out
