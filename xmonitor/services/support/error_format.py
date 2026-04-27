def format_runtime_error(err):
    err_type = type(err).__name__
    err_text = str(err or '').strip()
    return f'{err_type}: {err_text}' if err_text else err_type
