@echo off
REM X Monitor Pro - Windows 启动脚本
REM 双击运行此文件启动应用

echo.
echo ======================================================
echo   X Monitor Pro - PyQt6 Desktop Application
echo ======================================================
echo.

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未找到 Python
    echo 请先安装 Python 3.8+ 并加入 PATH
    pause
    exit /b 1
)

echo 📦 正在安装依赖...
python -m pip install -q -r requirements_gui.txt
if errorlevel 1 (
    echo ❌ 依赖安装失败
    pause
    exit /b 1
)

echo ✅ 依赖安装完成
echo.
echo 🚀 启动应用...
echo.

REM 启动应用
python main_gui.py
pause
