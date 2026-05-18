def run_app_entry(app, deps, *, os_module, print_fn, logging_module):
    os_module.system('killall chromium 2>/dev/null')
    os_module.system('killall google-chrome 2>/dev/null')

    try:
        if not os_module.path.exists(deps.DATA_DIR):
            os_module.makedirs(deps.DATA_DIR, exist_ok=True)
            print_fn(f'📁 创建数据目录: {deps.DATA_DIR}')
        else:
            print_fn(f'📂 数据目录: {deps.DATA_DIR}')
    except PermissionError:
        print_fn(f'❌ 错误: 无权限创建数据目录 {deps.DATA_DIR}')
        print_fn('💡 请确保当前用户有写入权限，或使用相对路径')
        raise SystemExit(1)
    except Exception as e:
        print_fn(f'❌ 创建数据目录失败: {e}')
        raise SystemExit(1)

    print_fn('=' * 60)
    print_fn('🚀 X Monitor V10.4 (通知监控版) 启动中...')
    print_fn('=' * 60)
    deps.load_state()
    server_port, port_source = deps.resolve_server_port()
    print_fn('=' * 60)
    print_fn(f'✅ 服务已启动: http://127.0.0.1:{server_port}')
    if port_source == 'random':
        print_fn('🔀 启动端口模式: 随机可用端口')
    else:
        print_fn(f'📌 启动端口模式: 指定端口(XMONITOR_PORT={server_port})')
    print_fn(f'📂 数据目录: {deps.DATA_DIR}')
    print_fn('=' * 60)

    try:
        werkzeug_log = logging_module.getLogger('werkzeug')
        werkzeug_log.setLevel(logging_module.ERROR)
        try:
            deps.start_daily_dm_contacts_scheduler()
        except Exception as schedule_err:
            logging_module.error(f'启动私信联系人定时统计失败: {schedule_err}')
        app.run(host='0.0.0.0', port=server_port, debug=False)
    except KeyboardInterrupt:
        print_fn('\n🛑 正在停止服务...')
        deps.save_state()
        deps.save_processed_users()
        print_fn('💾 数据已保存')
        print_fn('👋 再见！')
    finally:
        try:
            deps.stop_daily_dm_contacts_scheduler()
        except Exception:
            pass
