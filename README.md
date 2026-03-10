# X Monitor Pro

X/Twitter 评论、通知、私信自动化处理工具。

## 快速开始

```bash
pip install -r requirements.txt
python app.py
```

可选固定端口：

```bash
XMONITOR_PORT=58080 python app.py
```

## 主要功能

- 通知扫描与自动刷新
- 评论捕获与公开回复
- 两条私信发送
- 私信关闭识别与补评
- 评论模板、私信模板管理
- 通知语音播报与提示音
- LLM 评论过滤、意向分析、私信文案改写

## 数据文件

- 数据目录：`/home/shou/.local/share/x-monitor-pro`
- SQLite：`xmonitor_state.sqlite3`
- JSON：`spider_state.json`
- 已处理用户：`processed_users.json`

## 测试

```bash
venv/bin/python -m unittest discover -s tests -v
```

## 目录

- `app.py`：入口
- `xmonitor/browser`：浏览器逻辑
- `xmonitor/runtime`：运行时与监控循环
- `xmonitor/services`：通知、回复、私信、LLM、TTS
- `xmonitor/storage`：SQLite/JSON 状态层
- `xmonitor/web`：Flask 路由
- `static/` `templates/`：前端资源
- `tests/`：回归测试
