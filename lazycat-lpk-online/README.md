# X Monitor Pro - LazyCat LPK（在线版）

## 目录说明
- `manifest.yml`: 懒猫微服应用描述
- `lzc-build.yml`: 构建配置
- `content/`: 应用静态内容目录（本项目使用容器服务，保持为空即可）
- `dist/`: 构建输出目录

## 构建 LPK
在本目录执行：

```bash
lzc-cli project build .
```

构建完成后，`dist/` 下会生成 `.lpk`。

## 安装到微服
```bash
lzc-cli app install ./dist/cloud.lazycat.app.xmonitor-v1.1.0.lpk
```

## 镜像说明
当前配置使用：`shouz/x-monitor-pro:latest`

如你的设备不允许直接拉取 Docker Hub，请先把镜像同步到微服可访问的镜像仓库，然后把 `manifest.yml` 中 `services.xmonitor.image` 改为目标镜像地址再构建。
