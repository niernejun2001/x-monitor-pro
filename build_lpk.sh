#!/bin/bash
# X Monitor Pro - LPK 构建脚本
# 用于构建 Docker 镜像并打包成 LPK 包

set -e

echo "=========================================="
echo "  X Monitor Pro - LPK 构建脚本"
echo "=========================================="
echo

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 检查 Docker 是否运行
echo "[1/5] 检查 Docker 状态..."
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker 未运行，请先启动 Docker:"
    echo "   sudo systemctl start docker"
    exit 1
fi
echo "✅ Docker 正在运行"
echo

# 构建 Docker 镜像
echo "[2/5] 构建 Docker 镜像..."
docker build -t xmonitor-pro:latest .
echo "✅ Docker 镜像构建完成: xmonitor-pro:latest"
echo

# 创建 dist 目录 (LPK 内容目录)
echo "[3/5] 准备 LPK 内容..."
mkdir -p dist
echo "✅ dist 目录已创建"
echo

# 检查图标文件
echo "[4/5] 检查图标文件..."
if [ ! -f "lzc-icon.png" ]; then
    echo "⚠️  警告: 未找到 lzc-icon.png 图标文件"
    echo "   请添加一个 PNG 格式的应用图标"
else
    echo "✅ 图标文件已找到"
fi
echo

# 检查 lzc-cli
echo "[5/5] 检查 lzc-cli..."
if command -v lzc-cli > /dev/null 2>&1; then
    echo "✅ lzc-cli 已安装"
    echo
    echo "=========================================="
    echo "  准备工作已完成！"
    echo "=========================================="
    echo
    echo "接下来请执行以下命令完成打包和发布:"
    echo
    echo "  1. 构建 LPK 包:"
    echo "     lzc-cli project build"
    echo
    echo "  2. 推送镜像到官方仓库 (发布前必须):"
    echo "     lzc-cli appstore copy-image xmonitor-pro:latest"
    echo
    echo "  3. 发布到应用商店:"
    echo "     lzc-cli appstore publish ./cloud.lazycat.app.xmonitor-1.0.0.lpk"
    echo
else
    echo "⚠️  lzc-cli 未安装"
    echo
    echo "=========================================="
    echo "  Docker 镜像已构建完成！"
    echo "=========================================="
    echo
    echo "要继续打包 LPK，请先安装 lzc-cli:"
    echo "  参考: https://developer.lazycat.cloud/lzc-cli.html"
    echo
    echo "安装后执行:"
    echo "  lzc-cli project build"
    echo
fi

echo "Docker 镜像信息:"
docker images xmonitor-pro:latest
