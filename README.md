# X Monitor Pro

X/Twitter 评论与通知监控工具（Qt6 + Flask）。

## 主要能力

- 通知与推文评论并行扫描
- 通知扫描随机化节奏（降低固定行为特征）
- 内容提取优化（避免把用户名误识别为正文）
- 去重策略：同用户 + 同内容去重（不再按用户永久屏蔽）
- 代理支持：读取 `XMONITOR_PROXY` / `ALL_PROXY` / `HTTPS_PROXY` / `HTTP_PROXY`

## 运行方式（源码）

```bash
python app.py
```

## Qt6 二进制包

本项目可使用 Qt6 启动器二进制：`xmonitor-qt6`。

发布包建议内容：

- `xmonitor-qt6`
- `start_qt6.py`
- `main_gui.py`
- `app.py`
- `templates/`
- `requirements.txt`
- `requirements_gui.txt`

## 代理说明

如果你使用 Clash Verge，建议以同一终端启动并显式导出代理：

```bash
export XMONITOR_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890
export HTTP_PROXY=http://127.0.0.1:7890
./xmonitor-qt6
```

## 数据安全

仓库已通过 `.gitignore` 排除本地运行数据，不上传 `data/`、日志和状态文件。
