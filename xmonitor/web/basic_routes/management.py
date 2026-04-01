from .results_management import register_results_management_routes
from .task_management import register_task_management_routes
from .template_management import register_template_management_routes


def register_management_routes(app, deps):
    register_task_management_routes(app, deps)
    register_results_management_routes(app, deps)
    register_template_management_routes(app, deps)
