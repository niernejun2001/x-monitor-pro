from xmonitor.browser.core.profile_service import (
    auto_cleanup_profile_runtime as _auto_cleanup_profile_runtime_impl,
    cleanup_browser_user_data_dir as _cleanup_browser_user_data_dir_impl,
    cleanup_stale_profile_singletons as _cleanup_stale_profile_singletons_impl,
    create_browser_user_data_dir as _create_browser_user_data_dir_impl,
    is_persistent_browser_profile_dir as _is_persistent_browser_profile_dir_impl,
    is_profile_locked_by_alive_process as _is_profile_locked_by_alive_process_impl,
)


def build_support_browser_profile_exports(deps):
    def _is_profile_locked_by_alive_process(profile_dir):
        return _is_profile_locked_by_alive_process_impl(profile_dir)

    def _auto_cleanup_profile_runtime(profile_dir):
        return _auto_cleanup_profile_runtime_impl(profile_dir)

    def _cleanup_stale_profile_singletons(profile_dir):
        return _cleanup_stale_profile_singletons_impl(profile_dir)

    def create_browser_user_data_dir(prefer_persistent=True):
        return _create_browser_user_data_dir_impl(
            prefer_persistent,
            persistent_dir=deps.BROWSER_PROFILE_DIR,
            data_dir=deps.DATA_DIR,
        )

    def cleanup_browser_user_data_dir(profile_dir):
        return _cleanup_browser_user_data_dir_impl(
            profile_dir,
            persistent_dir=deps.BROWSER_PROFILE_DIR,
        )

    def is_persistent_browser_profile_dir(profile_dir):
        return _is_persistent_browser_profile_dir_impl(
            profile_dir,
            deps.BROWSER_PROFILE_DIR,
        )

    return {
        '_is_profile_locked_by_alive_process': _is_profile_locked_by_alive_process,
        '_auto_cleanup_profile_runtime': _auto_cleanup_profile_runtime,
        '_cleanup_stale_profile_singletons': _cleanup_stale_profile_singletons,
        'create_browser_user_data_dir': create_browser_user_data_dir,
        'cleanup_browser_user_data_dir': cleanup_browser_user_data_dir,
        'is_persistent_browser_profile_dir': is_persistent_browser_profile_dir,
    }
