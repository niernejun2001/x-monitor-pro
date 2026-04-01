from .runtime_control import register_runtime_control_routes
from .twitter_cli import register_twitter_cli_routes


def register_runtime_routes(app, deps):
    register_runtime_control_routes(app, deps)
    register_twitter_cli_routes(app, deps)
