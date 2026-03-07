from flask import Flask
from xmonitor.web.routes_ai import register_ai_routes
from xmonitor.web.routes_basic import register_basic_routes
from xmonitor.web.routes_notify import register_notify_routes


def create_flask_app(import_name, deps):
    app = Flask(import_name)
    register_basic_routes(app, deps)
    register_notify_routes(app, deps)
    register_ai_routes(app, deps)
    return app
