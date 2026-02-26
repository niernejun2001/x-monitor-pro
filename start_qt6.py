#!/usr/bin/env python3
import sys


def _print_missing_dep_and_exit(exc):
    print("❌ 启动 Qt6 失败：缺少依赖")
    print(f"   {exc}")
    print("💡 请先安装 Qt 依赖：")
    print("   ./venv/bin/python -m pip install PyQt6 PyQt6-WebEngine requests")
    sys.exit(1)


def main():
    try:
        from main_gui import main as gui_main
    except ModuleNotFoundError as e:
        _print_missing_dep_and_exit(e)

    gui_main()


if __name__ == "__main__":
    main()
