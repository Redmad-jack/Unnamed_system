# Display Stage 2 Status

本文件记录双屏展览模式从计划到实现后的状态。不要在本文档中记录密钥、`.env`、API key、真实数据库隐私内容或观众隐私数据。

## 当前状态

双屏展览模式已实现到可验证状态：

- `GET /display` 返回只读观众展示页 `src/have_some_ai/interfaces/static/display.html`。
- `GET /api/v1/display-state` 返回内存级展示状态。
- `POST /api/v1/display-state` 只更新内存状态，不写 SQLite。
- `GET /display-assets/{filename}` 只返回白名单展示页图片资产。
- 控制页 `/` 通过统一 helper 同步观众可见状态到 display-state。

## display-state schema

```json
{
  "mode": "idle",
  "display_text": "",
  "food_name": null,
  "food_subtitle": null,
  "robot_active": false,
  "avatar_greeting": false,
  "avatar_system_speaking": false,
  "avatar_audience_speaking": false,
  "updated_at": "ISO timestamp"
}
```

字段说明：

| 字段 | 允许值 / 类型 | 默认值 | 含义 |
| --- | --- | --- | --- |
| `mode` | `idle` / `question` / `robot_speaking` / `result` / `error` | `idle` | 观众可见展示状态，不是技术状态 |
| `display_text` | string，最多 800 字符 | `""` | 底部核心文本区显示的 AI 字幕或当前题目 |
| `food_name` | string 或 null，最多 80 字符 | null | 最终食物名称，仅 `result` 模式需要 |
| `food_subtitle` | string 或 null，最多 160 字符 | null | 最终食物补充文本，例如中英文副标题 |
| `robot_active` | boolean | false | 兼容字段，表示膜后存在是否活跃 |
| `avatar_greeting` | boolean | false | 展示页本地 avatar 进入挥手状态 |
| `avatar_system_speaking` | boolean | false | 展示页本地 avatar 进入 AI 说话状态 |
| `avatar_audience_speaking` | boolean | false | 展示页本地 avatar 进入观众说话状态 |
| `updated_at` | ISO timestamp string | 当前更新时间 | 状态最后更新时间 |

不要加入技术字段，例如 ASR、TTS、WebSocket、queue、participant id、database、debug、listening、transcribing、thinking。

## 只读边界

`/display` 页面必须保持只读：

- 不请求麦克风。
- 不调用 `getUserMedia`。
- 不启动 `conversation-stream`。
- 不创建真实语音 WebSocket。
- 不提交答案。
- 不操作工作人员队列。
- 不写数据库。
- 不调用 `ConversationOrchestrator`。
- 不调用 `MealService`。
- 不触发 ASR/TTS。

真实操作继续只由 `/` 控制页负责。

## 当前实现位置

- 后端路由与内存状态：`src/have_some_ai/interfaces/api.py`
- 控制页同步逻辑：`src/have_some_ai/interfaces/static/index.html`
- 展示页：`src/have_some_ai/interfaces/static/display.html`
- 展示页图片资产：`src/have_some_ai/interfaces/static/assets/`
- 边界测试：`tests/unit/test_have_some_ai_api.py`

## 验证命令

```bash
./.venv/bin/pytest tests/unit/test_have_some_ai_api.py
./.venv/bin/pytest
rg -n "getUserMedia|conversation-stream|WebSocket|PATCH|staff-queue|participants/.*/conversation|voice-audio|conversation-audio" src/have_some_ai/interfaces/static/display.html
```

期望：

- API 单测通过。
- 全量测试通过。
- `/display` 禁止入口扫描无命中。

当前最新验证：`pytest` 310 passed；`/display` 禁止入口扫描无命中。
