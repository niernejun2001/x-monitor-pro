# X Monitor Pro

X/Twitter 评论、通知、私信自动化处理工具。当前版本基于 `Flask + Chromium 自动化 + SQLite 状态层`，后端已拆分为模块化单体结构，浏览器侧以单浏览器多标签页方式运行。

## 快速开始

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 启动服务

```bash
python app.py
```

可选：固定端口启动

```bash
XMONITOR_PORT=58080 python app.py
```

启动后终端会打印访问地址。默认自动选择可用端口，避免端口冲突。

## 当前能力

- 通知标签页持续扫描与自动刷新
- 评论通知捕获、公开回复、状态持久化
- 回复后复制链接并进入私信链路
- 两条私信发送
  - 第 1 条：评论链接
  - 第 2 条：模板文案或 LLM 改写文案
- 私信关闭识别
  - 资料页无私信按钮
  - 新建私信搜索无结果
  - 明确平台禁发提示
- 目标用户未开私信时，自动补充评论：
  - `大佬 您没有开私信 有需要可以给我私信呀`
- 评论模板与私信模板管理
- 通知语音播报、提示音、TTS 测试
- LLM 评论过滤与意向客户分析
- 私信第二条文案 LLM 改写

## 私信链路说明

当前通知回复链路按以下顺序执行：

1. 在通知页定位目标评论并公开回复
2. 生成或复用该评论链接
3. 判断目标用户是否可私信
4. 可私信时发送两条私信
5. 不可私信时终止私信并补充公开评论

已实现的稳定性约束：

- 私信入口支持资料页预检，不再把“无私信按钮”的用户继续当成可私信用户
- 第二条私信文案发送后会清理 composer，避免残留文本继续留在对话框里
- 同一条通知任务恢复执行时，优先复用已生成的第二条私信文案，不重复调 LLM，不重复粘贴
- 当前会话中如果已经存在第二条私信文案，会直接跳过重复发送

## LLM 能力

### 评论过滤与意向分析

前端控制区可直接使用：

- `🧪 测试模型`
- `🔍 分析评论意向`

相关接口：

- `POST /api/llm_filter/test`
- `POST /api/llm_filter/analyze`

返回字段包括：

- `intent_score`
- `intent_level`
- `is_intent_user`
- `signals`
- `reason`

当 OpenAI 兼容 `/chat/completions` 返回 `404` 时，会自动回退到 Ollama 原生 `/api/chat`。

### 第二条私信文案改写

第二条私信可由 LLM 基于模板改写生成。当前默认约束：

- 保持核心业务信息、联系方式、购买引导不变
- 保持主语和动作方向不变
- 不允许把“您在关注我们的产品”改写成“我在看你们的产品”
- 失败时可按配置降级回原模板文案

## 状态与数据

默认数据目录：

- `/home/shou/.local/share/x-monitor-pro`

主要状态文件：

- SQLite：`xmonitor_state.sqlite3`
- JSON 兼容状态：`spider_state.json`
- 已处理用户：`processed_users.json`

SQLite 结构化表已覆盖：

- `pending_results`
- `history_ids`
- `content_dedupe`
- `processed_users_items`

## 测试

运行全量测试：

```bash
venv/bin/python -m unittest discover -s tests -v
```

当前仓库已包含通知、私信、状态迁移、路由、重试、发送确认等回归测试。

## 主要目录

- `app.py`: 应用入口与运行时配置装配
- `xmonitor/browser`: 浏览器初始化、标签页与维护逻辑
- `xmonitor/runtime`: 监控循环、运行时状态、节流与关键区控制
- `xmonitor/services`: 通知扫描、回复、私信、LLM、TTS 等业务逻辑
- `xmonitor/storage`: SQLite/JSON 状态读写与仓储
- `xmonitor/web`: Flask 路由
- `static/`: 前端 JS、CSS、提示音资源
- `templates/index.html`: 前端页面
- `tests/`: 回归测试
