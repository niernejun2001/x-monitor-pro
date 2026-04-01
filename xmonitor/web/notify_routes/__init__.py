from .reply import register_notify_reply_routes
from .retry import register_notify_retry_routes


def register_notify_routes(app, deps):
    register_notify_reply_routes(app, deps)
    register_notify_retry_routes(app, deps)


__all__ = [
    'register_notify_routes',
    'register_notify_reply_routes',
    'register_notify_retry_routes',
]
