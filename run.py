#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X Monitor Pro - 快速启动脚本
用于开发和测试，无需打包直接运行
"""

import subprocess
import sys
import os

def install_deps():
    """安装依赖"""
    print("📦 检查依赖...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements_gui.txt"])
        print("✅ 依赖安装完成\n")
    except subprocess.CalledProcessError:
        print("❌ 依赖安装失败，请手动运行:")
        print("   pip install -r requirements_gui.txt")
        sys.exit(1)

def run_app():
    """启动应用"""
    print("=" * 60)
    print("🚀 启动 X Monitor Pro PyQt6 版本...")
    print("=" * 60)
    print()

    try:
        subprocess.run([sys.executable, "main_gui.py"], check=True)
    except KeyboardInterrupt:
        print("\n\n👋 应用已关闭")
    except subprocess.CalledProcessError as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # 检查必要文件
    if not os.path.exists("main_gui.py"):
        print("❌ 错误: 找不到 main_gui.py")
        sys.exit(1)

    if not os.path.exists("app.py"):
        print("❌ 错误: 找不到 app.py")
        sys.exit(1)

    # 安装依赖
    install_deps()

    # 启动应用
    run_app()
