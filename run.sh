#!/bin/bash
# X Monitor Pro - macOS 启动脚本
# 给脚本添加执行权限: chmod +x run.sh
# 然后双击运行或在终端中执行: ./run.sh

echo ""
echo "======================================================"
echo "  X Monitor Pro - PyQt6 Desktop Application"
echo "======================================================"
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 Python 3"
    echo "请先安装 Python 3.8+ (https://www.python.org/downloads/)"
    read -p "按 Enter 键关闭..."
    exit 1
fi

echo "📦 正在安装依赖..."
python3 -m pip install -q -r requirements_gui.txt

if [ $? -ne 0 ]; then
    echo "❌ 依赖安装失败"
    read -p "按 Enter 键关闭..."
    exit 1
fi

echo "✅ 依赖安装完成"
echo ""
echo "🚀 启动应用..."
echo ""

# 启动应用
python3 main_gui.py

# 应用关闭后显示消息
echo ""
echo "👋 应用已关闭"
read -p "按 Enter 键关闭..."
