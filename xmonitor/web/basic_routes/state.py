from flask import jsonify, render_template, request

from xmonitor.services.support.state_payload import build_api_state_payload


def register_state_routes(app, deps):
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/state')
    def state():
        return jsonify(build_api_state_payload(deps))

    @app.route('/api/updates')
    def up():
        raw_since = str(request.args.get('since_seq', '') or '').strip()
        has_since = raw_since != ''
        if not has_since:
            new_items = deps.drain_msg_queue(collect_new_data=True)
            with deps.data_lock:
                tasks_copy = list(deps.monitor_tasks)
                last_seq = int(deps.updates_event_seq)
                if (not new_items) and deps.updates_event_buffer:
                    new_items = [evt.get('data') for evt in list(deps.updates_event_buffer)[-120:] if isinstance(evt.get('data'), dict)]
            return jsonify({'new_items': new_items, 'tasks': tasks_copy, 'last_seq': last_seq, 'dropped': False})
        try:
            since_seq = max(0, int(raw_since))
        except Exception:
            since_seq = 0
        deps.drain_msg_queue(collect_new_data=False)
        with deps.data_lock:
            tasks_copy = list(deps.monitor_tasks)
            last_seq = int(deps.updates_event_seq)
            buffer_snapshot = list(deps.updates_event_buffer)
        dropped = False
        if buffer_snapshot:
            oldest_seq = int(buffer_snapshot[0].get('seq', 0) or 0)
            if since_seq > 0 and oldest_seq > (since_seq + 1):
                dropped = True
        new_items = [evt.get('data') for evt in buffer_snapshot if int(evt.get('seq', 0) or 0) > since_seq and isinstance(evt.get('data'), dict)]
        return jsonify({'new_items': new_items, 'tasks': tasks_copy, 'last_seq': last_seq, 'dropped': dropped})
