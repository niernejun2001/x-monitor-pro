from flask import jsonify, request

from xmonitor.services.support.template_admin import (
    TemplateAdminError,
    add_template,
    delete_template,
    update_template,
)


def register_template_management_routes(app, deps):
    @app.route('/api/template/add', methods=['POST'])
    def template_add():
        payload = request.get_json(silent=True) or {}
        template_type = str(payload.get('type', '') or '').strip().lower()
        content = str(payload.get('content', '') or '').strip()
        try:
            return jsonify(add_template(deps, template_type, content))
        except TemplateAdminError as exc:
            return jsonify({'status': 'err', 'msg': str(exc)}), 400

    @app.route('/api/template/update', methods=['POST'])
    def template_update():
        payload = request.get_json(silent=True) or {}
        template_type = str(payload.get('type', '') or '').strip().lower()
        content = str(payload.get('content', '') or '').strip()
        try:
            return jsonify(update_template(deps, template_type, payload.get('index', -1), content))
        except TemplateAdminError as exc:
            return jsonify({'status': 'err', 'msg': str(exc)}), 400

    @app.route('/api/template/delete', methods=['POST'])
    def template_delete():
        payload = request.get_json(silent=True) or {}
        template_type = str(payload.get('type', '') or '').strip().lower()
        try:
            return jsonify(delete_template(deps, template_type, payload.get('index', -1)))
        except TemplateAdminError as exc:
            return jsonify({'status': 'err', 'msg': str(exc)}), 400
