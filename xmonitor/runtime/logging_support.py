import datetime


def log_to_ui(level, msg, *, runtime_log_file, msg_queue):
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'{ts} [{str(level or "").upper()}] {msg}'
    print(line)
    try:
        with open(runtime_log_file, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass
    msg_queue.put({'type': 'log', 'level': level, 'msg': msg})


def is_headless_verbose_logging_enabled(*, headless_mode, verbose_flag):
    return bool(headless_mode and verbose_flag)


def log_headless_debug(msg, *, enabled, logger_fn):
    if enabled:
        logger_fn('debug', f'🧪 [HEADLESS] {msg}')


def log_headless_exception(context, err, *, enabled, logger_fn, traceback_module):
    if not enabled:
        return
    logger_fn('error', f'🧪 [HEADLESS] {context}异常: {err}')
    try:
        logger_fn('debug', f'🧪 [HEADLESS][TRACE] {traceback_module.format_exc()}')
    except Exception:
        pass
