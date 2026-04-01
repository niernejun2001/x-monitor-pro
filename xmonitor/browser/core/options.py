from DrissionPage import ChromiumOptions


def init_browser_options(port, user_data_path, deps, force_headless=None, safe_mode=False):
    co = ChromiumOptions()
    bp = deps.get_browser_path()
    if bp:
        co.set_paths(browser_path=bp)

    proxy_server = deps.get_browser_proxy()
    if proxy_server:
        co.set_argument(f'--proxy-server={proxy_server}')
        co.set_argument('--proxy-bypass-list=localhost;127.0.0.1')
        deps.log_to_ui('info', f'🌐 浏览器代理已启用: {proxy_server}')
    else:
        deps.log_to_ui('warn', '⚠️ 未检测到代理配置，当前网络环境可能无法访问 x.com')

    effective_headless = deps.headless_mode if force_headless is None else bool(force_headless)
    co.headless(effective_headless)
    if effective_headless:
        co.set_argument('--headless=new')

    if safe_mode:
        co.set_argument('--window-size=1400,900')
        co.set_argument('--mute-audio')
        co.set_argument('--disable-notifications')
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-dev-shm-usage')
        co.set_argument('--disable-setuid-sandbox')
        if effective_headless:
            co.set_argument('--disable-gpu')
        co.set_local_port(port)
        co.set_user_data_path(user_data_path)
        return co

    co.set_argument('--page-load-strategy=eager')
    co.set_argument('--window-size=1400,900')
    co.set_argument('--blink-settings=imagesEnabled=false')
    co.set_argument('--disable-images')
    co.set_pref('profile.managed_default_content_settings.images', 2)

    co.set_argument('--mute-audio')
    co.set_argument('--disable-notifications')
    co.set_pref('profile.managed_default_content_settings.notifications', 2)
    co.set_pref('profile.managed_default_content_settings.media_stream', 2)
    co.set_pref('profile.managed_default_content_settings.popups', 2)

    co.set_argument('--autoplay-policy=user-gesture-required')
    co.set_argument('--disable-features=PreloadMediaEngagementData,MediaEngagementBypassAutoplayPolicies')

    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-extensions')
    co.set_argument('--disable-plugins')
    co.set_argument('--disable-infobars')
    co.set_argument('--disable-sync')
    co.set_argument('--disable-translate')
    co.set_argument('--disable-default-apps')
    co.set_argument('--disable-setuid-sandbox')

    if effective_headless:
        co.set_argument('--disable-gpu')
        co.set_argument('--disable-software-rasterizer')
        co.set_argument('--disable-background-timer-throttling')
        co.set_argument('--disable-backgrounding-occluded-windows')
        co.set_argument('--disable-renderer-backgrounding')
    else:
        co.set_argument('--start-maximized')
        co.set_argument('--window-size=1400,900')

    co.set_argument('--disable-breakpad')
    co.set_argument('--disable-component-update')
    co.set_argument('--disable-domain-reliability')

    co.set_local_port(port)
    co.set_user_data_path(user_data_path)
    return co
