from flask import jsonify, request


def register_task_management_routes(app, deps):
    @app.route('/api/task/add', methods=['POST'])
    def add_t():
        url = request.json['url']
        deps.monitor_tasks_repo.add(url)
        deps.save_state()
        return jsonify({'status': 'ok', 'tasks': deps.monitor_tasks_repo.snapshot()})

    @app.route('/api/task/remove', methods=['POST'])
    def rem_t():
        url = request.json['url']
        deps.monitor_tasks_repo.remove(url)
        deps.save_state()
        return jsonify({'status': 'ok', 'tasks': deps.monitor_tasks_repo.snapshot()})
