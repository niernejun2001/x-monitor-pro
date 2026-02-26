# X Monitor Pro - PyQt6 版本

将 Flask Web 应用打包为原生 PyQt6 桌面应用

## 📋 前置要求

- Python 3.8+
- pip

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements_gui.txt
pip install pyinstaller
```

### 2. 运行 PyQt6 版本

不需要打包，直接运行：

```bash
python main_gui.py
```

应用会自动：
- ✅ 在后台启动 Flask 服务器
- ✅ 打开 PyQt6 窗口
- ✅ 加载 Web 界面

### 3. 打包为可执行文件

#### Windows (.exe)

```bash
python build.py
```

生成的文件在 `dist` 目录下，可以直接分发使用。

#### macOS (.app)

```bash
python build.py
```

生成的应用可以直接运行，也可以放入 Applications 文件夹。

#### Linux

```bash
python build.py
```

生成的可执行文件可以直接运行。

## 📂 文件说明

| 文件 | 说明 |
|-----|------|
| `main_gui.py` | PyQt6 应用主文件（启动 Flask + Web 显示） |
| `app.py` | Flask 后端应用（核心逻辑） |
| `build.py` | PyInstaller 打包脚本 |
| `requirements_gui.txt` | PyQt6 版本依赖列表 |
| `requirements.txt` | Flask 原始版本依赖列表 |

## 🎯 功能特性

- ✅ **无头浏览器** - 后台运行 Chromium，无窗口打开
- ✅ **多线程扫描** - 同时扫描推文和通知
- ✅ **快速通知扫描** - 5-10 秒内获取最新通知
- ✅ **原生桌面应用** - 像其他 Windows/Mac 应用一样使用
- ✅ **自动启动** - 双击即可运行
- ✅ **系统集成** - 支持快捷键、最小化等桌面功能

## 💡 使用技巧

### 修改配置

修改 `main_gui.py` 中的配置：

```python
# 修改窗口大小
self.setGeometry(100, 100, 1400, 900)  # x, y, 宽, 高

# 修改标题
self.setWindowTitle("X Monitor Pro - 推文评论监控")

# 修改服务器端口
self.web_view.load(QUrl("http://127.0.0.1:5000"))  # 改端口号
```

### 添加窗口图标

将图标文件放在同目录下，命名为 `xmonitor.ico`，打包时会自动使用。

### 后台运行

打包后的应用支持后台运行：
- 最小化到系统托盘（可选）
- 继续扫描数据
- 不占用焦点

## 🔧 故障排除

### 打包后黑屏

- 等待 5-10 秒，Flask 服务器在启动
- 检查 `requirements_gui.txt` 是否完整安装

### 无法访问通知页面

- 确保 auth_token 正确配置
- 检查网络连接
- 查看日志中的错误信息

### PyInstaller 打包失败

```bash
# 清理之前的构建
rm -rf build dist *.spec

# 重新打包
python build.py
```

## 📝 许可证

MIT License

## 🤝 贡献

欢迎提出问题和建议！
