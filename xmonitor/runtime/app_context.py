import os


def initialize_app_context(
    deps,
    *,
    base_dir,
    env,
    logging_module,
    get_default_user_data_dir_impl,
    get_data_dir_impl,
    ensure_directory_impl,
    migrate_legacy_state_files_impl,
    load_local_json_config_impl,
    save_local_json_config_impl,
):
    env = env or {}
    local_tts_config_file = os.path.join(base_dir, 'data', 'local_tts_config.json')

    def get_default_user_data_dir():
        """返回当前用户默认数据目录。"""
        return get_default_user_data_dir_impl()

    def get_data_dir():
        """根据运行环境自动选择数据目录"""
        return get_data_dir_impl(base_dir)

    data_dir = get_data_dir()
    state_file = os.path.join(data_dir, 'spider_state.json')
    processed_file = os.path.join(data_dir, 'processed_users.json')
    sqlite_state_file = os.path.join(data_dir, 'xmonitor_state.sqlite3')
    runtime_log_file = os.path.join(data_dir, 'runtime.log')
    diag_dir = os.path.join(data_dir, 'diagnostics')
    browser_profile_dir = os.environ.get(
        'XMONITOR_BROWSER_PROFILE_DIR',
        os.path.join(data_dir, 'chromium-profile'),
    )
    browser_profile_dir = os.path.abspath(os.path.expanduser(browser_profile_dir))
    browser_profile_persist = str(
        env.get('XMONITOR_PERSIST_BROWSER_PROFILE', '1')
    ).strip().lower() not in {'0', 'false', 'no', 'off'}

    def ensure_data_dir():
        """确保数据目录存在。"""
        return ensure_directory_impl(data_dir, logging_module=logging_module)

    def migrate_legacy_state_files():
        """迁移历史版本写在项目根目录的数据文件到 data/ 目录。"""
        return migrate_legacy_state_files_impl(
            base_dir,
            state_file,
            processed_file,
            logging_module=logging_module,
        )

    def _load_local_tts_config():
        """读取本地私有TTS配置（git忽略），用于保存密钥。"""
        return load_local_json_config_impl(local_tts_config_file, logging_module=logging_module)

    def _save_local_tts_config(cfg):
        """保存本地私有TTS配置（不进入git）。"""
        return save_local_json_config_impl(local_tts_config_file, cfg)

    return {
        'BASE_DIR': base_dir,
        'LOCAL_TTS_CONFIG_FILE': local_tts_config_file,
        'get_default_user_data_dir': get_default_user_data_dir,
        'get_data_dir': get_data_dir,
        'DATA_DIR': data_dir,
        'STATE_FILE': state_file,
        'PROCESSED_FILE': processed_file,
        'SQLITE_STATE_FILE': sqlite_state_file,
        'STATE_JSON_FALLBACK': str(env.get('XMONITOR_STATE_JSON_FALLBACK', '1')).strip().lower() not in {'0', 'false', 'no', 'off'},
        'RUNTIME_LOG_FILE': runtime_log_file,
        'DIAG_DIR': diag_dir,
        'BROWSER_PROFILE_DIR': browser_profile_dir,
        'BROWSER_PROFILE_PERSIST': browser_profile_persist,
        'ensure_data_dir': ensure_data_dir,
        'migrate_legacy_state_files': migrate_legacy_state_files,
        '_load_local_tts_config': _load_local_tts_config,
        '_save_local_tts_config': _save_local_tts_config,
        'LOCAL_TTS_CONFIG': _load_local_tts_config(),
    }
