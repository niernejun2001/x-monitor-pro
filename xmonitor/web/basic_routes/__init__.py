from .management import register_management_routes
from .results_management import register_results_management_routes
from .runtime import register_runtime_routes
from .runtime_control import register_runtime_control_routes
from .state import register_state_routes
from .task_management import register_task_management_routes
from .template_management import register_template_management_routes
from .twitter_cli import register_twitter_cli_routes


def register_basic_routes(app, deps):
    register_state_routes(app, deps)
    register_management_routes(app, deps)
    register_runtime_routes(app, deps)


__all__ = [
    'register_basic_routes',
    'register_management_routes',
    'register_results_management_routes',
    'register_runtime_routes',
    'register_runtime_control_routes',
    'register_state_routes',
    'register_task_management_routes',
    'register_template_management_routes',
    'register_twitter_cli_routes',
]
