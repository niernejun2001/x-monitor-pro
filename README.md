# X Monitor Pro

X/Twitter 评论与通知自动化处理工具（Flask + Chromium 自动化）。

## 快速开始

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 启动服务

```bash
python app.py
```

启动后终端会打印访问地址（默认随机可用端口，避免端口冲突）。

## 主要功能

- 通知捕获与评论回复
- 私信发送
- 评论模板与私信模板管理（增删改）
- 单浏览器多标签复用，降低风控与切换成本

## 主要目录

- `app.py`: 后端主程序
- `templates/index.html`: 前端页面
- `twitter-reply-jumper/`: 扩展相关代码
