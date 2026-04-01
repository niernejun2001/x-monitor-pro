from .analysis import register_analysis_routes
from .config import register_config_routes
from .tts import register_tts_routes


def register_ai_routes(app, deps):
    register_analysis_routes(app, deps)
    register_config_routes(app, deps)
    register_tts_routes(app, deps)


__all__ = [
    'register_ai_routes',
    'register_analysis_routes',
    'register_config_routes',
    'register_tts_routes',
]
