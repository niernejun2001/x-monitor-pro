# X Monitor Pro - LazyCat VNC 版

本目录用于把 `x-monitor-pro` 以 **VNC 应用** 形式部署到懒猫微服。

## 文件说明
- `lzc-manifest.yml`：VNC 应用清单（路由到 `6901`）
- `lzc-build.yml`：LPK 构建配置
- `content/`：打包所需内容目录（可为空）

## 镜像构建要点
- 使用根目录的 `Dockerfile.vnc`
- 基础镜像：`kasmweb/core-ubuntu-focal:1.15.0`
- 容器内自动启动：
  1. `python3 app.py`（监听 `56125`）
  2. 桌面浏览器自动打开 `http://127.0.0.1:56125`

## 一键部署（复用现有脚本）
在项目根目录执行：

```bash
LPK_DIR=./lazycat-lpk-vnc \
MANIFEST_PATH=./lazycat-lpk-vnc/lzc-manifest.yml \
APP_PACKAGE=cloud.lazycat.app.xmonitor-vnc \
SRC_IMAGE_REPO=registry.cn-hangzhou.aliyuncs.com/shoxk8s/x-monitor-pro-vnc \
DOCKERFILE=./Dockerfile.vnc \
./scripts/deploy_lazycat.sh
```

脚本会自动：构建并推送镜像 -> copy-image 到微服仓库 -> 更新 manifest 镜像和版本 -> 构建 LPK -> 安装应用。

## 运行说明
- 打开应用后会进入 VNC 桌面。
- 桌面浏览器会自动打开监控页面；如未自动打开，可手动访问 `http://127.0.0.1:56125`。
- 默认密码在 `lzc-manifest.yml` 中 `VNC_PW`（建议上线前改掉）。
