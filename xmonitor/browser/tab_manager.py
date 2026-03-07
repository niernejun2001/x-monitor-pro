
def ensure_worker_tab(*, current_tab, tab_lock_obj, browser_factory, warmup_func, force_recreate=False, reuse_log='', create_log=''):
    tab = None
    with tab_lock_obj:
        if force_recreate and current_tab[0]:
            try:
                current_tab[0].close()
            except Exception:
                pass
            current_tab[0] = None

        if current_tab[0] is not None:
            try:
                _ = current_tab[0].url
                if reuse_log:
                    reuse_log()
                tab = current_tab[0]
            except Exception:
                current_tab[0] = None

        if tab is None:
            browser = browser_factory()
            current_tab[0] = browser.new_tab()
            tab = current_tab[0]
            if create_log:
                create_log()

    warmup_func(tab)
    return tab
