#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X Monitor Pro - PyInstaller 打包脚本
打包PyQt6应用为可执行文件
"""

import subprocess
import sys
import os
from pathlib import Path


def build_exe():
    """使用PyInstaller打包为exe/app"""

    script_path = Path(__file__).parent / "main_gui.py"
    output_dir = Path(__file__).parent / "dist"
    build_dir = Path(__file__).parent / "build"

    print("=" * 60)
    print("🚀 开始打包 X Monitor Pro...")
    print("=" * 60)

    # PyInstaller 命令
    cmd = [
        "pyinstaller",
        "--name", "X Monitor Pro",  # 应用名称
        "--onefile",  # 生成单一可执行文件
        "--windowed",  # 不显示控制台窗口
        "--icon", "xmonitor.ico" if Path("xmonitor.ico").exists() else None,  # 图标（如果存在）
        "--add-data", f"data{os.pathsep}data",  # 数据目录
        "--hidden-import", "flask",
        "--hidden-import", "PyQt6",
        "--hidden-import", "PyQt6.QtWebEngineWidgets",
        "--hidden-import", "DrissionPage",
        str(script_path),
    ]

    # 移除None值
    cmd = [c for c in cmd if c is not None]

    print(f"📦 执行命令: {' '.join(cmd)}\n")

    # 执行打包
    try:
        result = subprocess.run(cmd, check=True)
        print("\n" + "=" * 60)
        print("✅ 打包成功！")
        print("=" * 60)
        print(f"\n📁 可执行文件位置:")

        if sys.platform == "win32":
            exe_path = output_dir / "X Monitor Pro.exe"
            print(f"   {exe_path}")
        elif sys.platform == "darwin":
            app_path = output_dir / "X Monitor Pro.app"
            print(f"   {app_path}")
        else:
            exe_path = output_dir / "X Monitor Pro"
            print(f"   {exe_path}")

        print(f"\n💡 使用方法:")
        print(f"   双击可执行文件或应用即可运行")
        print(f"\n⚠️ 首次运行可能需要几秒钟启动Flask服务器")

    except subprocess.CalledProcessError as e:
        print("\n" + "=" * 60)
        print("❌ 打包失败！")
        print("=" * 60)
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    build_exe()
