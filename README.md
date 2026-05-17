# Exhibition Systems: The "Stranger" + Have Some "Ai"

这个仓库服务于同一个展览 / 研究项目中的两个并置作品：

- **The "Stranger"**：研究 AI 作为非人主体进入社会关系之后，会被放在什么位置。
- **Have Some "Ai"**：研究 AI 进入推荐、分类、匹配和分配机制之后，人类主体性如何被改变。

二者共享同一个研究母题，但软件上保持独立：**不共享状态、记忆、题库、评分规则和分配结果**。

```text
src/
├── conscious_entity/          # Work 1: The "Stranger"
└── have_some_ai/              # Work 2: Have Some "Ai"
```

---

## 当前状态

当前发布版本：`v1.2.1-EC`

| 作品 | 当前进度 | 可以做什么 |
| --- | --- | --- |
| The "Stranger" | 已停止维护，以下内容只保留历史记录 | 不再作为当前开发重点 |
| Have Some "Ai" | 当前主项目；`v1.2.1-EC` 已收口 Language Gate、A/B-only 正式题显示、双语 Food Gate、双屏 `/display` 展示页和最终出餐话术 | 新建观众、Language Gate、双语 Food Gate、闲聊 + 判断、ASR/TTS 语音、Claude A/B judge、食物分配、工作人员队列、只读观众展示页 |

当前 Have Some "Ai" 的现场交互已经从纯 A/B 调试流程，推进到：

```text
新建观众
  ↓
Language Gate：选择 English / 中文，不计入正式题
  ↓
Food Gate 闲聊入口：先问要不要吃 / 要不要参加
  ↓
想吃则进入两道正式 A / B 判断题；不想吃则进入最多 3 回合 not_eating_chat 后送客并清理 transient participant
  ↓
AIHubMix/OpenAI-compatible TTS 或豆包 TTS V3 朗读
  ↓
观众语音回答
  ↓
AIHubMix 文件上传式 STT 或豆包 ASR bigmodel_async 转写
  ↓
ConversationOrchestrator 先区分 chitchat / unclear_speech / answer_attempt
  ↓
只有 answer_attempt 进入 Claude A/B/unclear judge；chitchat 不判题、不评分、不推进，前 1-2 回合可由 Claude 生成店主自由回应
  ↓
两道正式题都有 accepted A/B 后，规则评分引擎分配食物
  ↓
店主说出固定出餐话术
  ↓
工作人员队列
```

其中：

- A、B 是正式选项，会显示在屏幕上。
- freeform / 侧问 / 评论不会自动映射为 A/B；只有 `FormalTurnRouter` 判定用户正在尝试回答当前正式题时，才会调用 Claude judge。
- Claude judge 输出只允许 A / B / unclear，并会做 JSON 容错解析；malformed JSON 会 repair 一次，仍失败则进入重试。闲聊 Claude 只生成 `reply_text`，不能决定流程或食物。
- 最终食物仍由规则评分引擎决定，LLM 不直接决定食物。
- 不保存观众原始音频，只保存转写、置信度、理由和推断结果。

---

## Work 1: The "Stranger"（已停止维护）

### 项目定位

以下内容是历史记录。当前开发、联调和文档维护重点是 Work 2: Have Some "Ai"。

The "Stranger" 不是聊天机器人，也不是 AI 助手。它是一套最小化的人工组织结构：通过状态、记忆、阻抗、延迟、沉默和表达漂移，使观众倾向于把主体性和伦理分量归因于这个非人系统。

系统不会宣称自己有意识；它通过行为结构让“AI 是否仍只是工具”这个问题变得不稳定。

核心特征：

- 跨交互连续性：不在每次交互时重置。
- 状态漂移：随交互积累发生可感知变化。
- 偏好与阻抗：对关机、删除、意识等话题产生抵抗。
- 选择性沉默：不总是立即回应。
- 自我压缩：将经历归纳为反思，影响后续表达。

### 核心架构

```text
输入 → 感知层 → 状态机 → 记忆 → 策略 → 表达层 → 输出
                  ↑                            ↓
               反思层 ←──────────── 情节记忆库
```

| 模块 | 职责 |
| --- | --- |
| Claude / LLM | 生成文字回应、压缩情节记忆为反思 |
| 规则引擎 | 状态更新、策略选择、宪法约束、感知分类 |
| YAML 配置 | 定义状态变量、规则逻辑、表达边界 |

重要边界：LLM 只负责表达和反思压缩，不直接参与状态更新、策略选择或宪法判断。

### 关键文件

```text
config/
├── state_rules.yaml
├── policy_rules.yaml
├── constitution.yaml
├── expression_mappings.yaml
└── entity_profile.yaml

src/conscious_entity/
├── perception/                 # 文本输入 → 感知事件
├── state/                      # 10 个状态变量 + 状态持久化
├── memory/                     # 短期 / 情节 / 反思记忆
├── policy/                     # 策略规则 + 宪法约束
├── expression/                 # Prompt 组装 + 风格映射 + 输出
├── reflection/                 # 情节记忆压缩为反思
├── llm/                        # Claude 唯一接入点
├── interfaces/                 # CLI / FastAPI / Web 看板
└── core/                       # 主循环与事件总线
```

### 运行

```bash
python scripts/init_db.py
python -m conscious_entity.interfaces.cli
```

开发者 API / Web 看板：

```bash
python scripts/start_api.py
# http://127.0.0.1:8000/
# http://127.0.0.1:8000/docs
```

调试工具：

```bash
python scripts/inspect_state.py
python scripts/monitor.py
python scripts/test_llm.py
python scripts/export_memories.py --output data/export.json
```

### 后续路线

```text
v0.1  文字 CLI：状态、记忆、策略、LLM 表达（已完成）
v0.2  语义检索、语音、视觉输出、运营者面板
v0.3  治理可见性、访客身份感知、展期终止仪式
```

---

## Work 2: Have Some "Ai"

### 项目定位

Have Some "Ai" 是一个食物分配系统，而不是另一个聊天实体。它将展览空间转化为一个隐喻商店：系统观察观众、提出问题、理解回答、计算分数，并把观众分配到某一种食物。

食物不是单纯的食物，而是系统读取、分类和分配人的可见结果。

### 双屏展览模式

现场按 iMac 双屏运行：

- `/` 控制页运行真实流程：新建观众、麦克风录音、`conversation-stream`、ASR/TTS、`ConversationOrchestrator`、食物分配和工作人员队列。
- `/display` 展示页只读，给观众看：冷灰绿色磨砂薄膜、膜后存在、AI 字幕、当前题目和最终食物结果。
- `/api/v1/display-state` 是内存级展示状态，控制页写入，展示页轮询读取；不写 SQLite，不推进会话，不触发 ASR/TTS。
- `/display-assets/{filename}` 只暴露展示页白名单图片资产。

`/display` 不请求麦克风、不创建 WebSocket、不调用 `conversation-stream`、不提交答案、不操作工作人员队列、不调用 `MealService`。

### 当前观众流程

```text
1. 新建匿名观众，生成 A001 形式编号
2. Language Gate 问 `Hi. 你好～ Do you want to talk in 中文 or English?`；English / en / 英文 或明显英文输入固定本次会话英文，中文 / Chinese / zh 或明显中文输入使用中文默认逻辑
3. Food Gate 使用 `questions.yaml` 的 13 条开场轮换；中文问“想来点吃的吗？”，English 模式问 “Want something to eat?”
4. `NO_FOOD` 进入最多 3 回合的 not-eating chat，随后送客并清理 transient participant，不抽正式题、不分配食物
5. `WANT_FOOD` 后抽两道正式题
6. 屏幕显示题目和 A/B 两个选项
7. AIHubMix file STT 或豆包 ASR `bigmodel_async` 生成 transcript
8. 正式题 transcript 先经过 `FormalTurnRouter`；只有 answer_attempt 才进入 Claude A/B/unclear judge
9. chitchat 由店主接住，不判题、不评分、不推进；前 1-2 回合可自由回应，正式题 chitchat 第 3 回合拉回当前题
10. 两道正式题分别决定 soup / salad 与 normal / aimiao
11. 系统分配食物并写入工作人员队列
```

当前四种结果：

- `soup`
- `salad`
- `aimiao_soup`
- `aimiao_salad`

### A / B 的含义

| 选项 | 作用 |
| --- | --- |
| A | 原设计选项，直接进入隐藏评分 rubric |
| B | 原设计选项，直接进入隐藏评分 rubric |

实现上，语音会先变成 transcript，再进入 `ConversationOrchestrator`。Food Gate、not-eating chat、正式题 chitchat、unclear_speech 和 noise 都不会进入正式评分；只有 `FormalTurnRouter` 判定为 `answer_attempt` 的正式题回答才会交给 Claude 判断 A / B / unclear。Claude judge 输出会经过严格 JSON 解析、code fence / 前后文本 / trailing comma 容错、一次 JSON repair 和 schema 校验；数据库中的正式答案仍只在 `accepted` 时保存 A/B。chitchat 的前 1-2 回合可以由 `ShopkeeperReplyService` 调 Claude 生成 `reply_text`，失败时使用本地模板兜底。

### 当前模块结构

```text
src/have_some_ai/
├── config.py                   # 加载题库和评分配置
├── db.py                       # Have Some "Ai" 专属 SQLite schema
├── hardware.py                 # 未来打印、灯光、厨房信号等硬件边界
├── models.py                   # 参与者、题目、答案、观察事件、分配结果、语音理解记录
├── questionnaire.py            # 两道正式题随机抽题 + Food Gate 开头轮换
├── repository.py               # SQLite 读写
├── scoring.py                  # 两轴正式答案到四种食物的规则映射
├── service.py                  # 观众流程服务
├── chat.py                     # 店主话术；闲聊 Claude reply_text + 模板兜底
├── prompt_context.py           # 读取 AI 店主运行语境，仅注入闲聊话术 prompt
├── voice.py                    # Claude formal answer_attempt A/B/unclear judge
├── voice_provider.py           # 语音 provider / STT mode 配置
├── doubao/                     # Doubao ASR bigmodel_async + TTS bidirectional V3
├── openai_file_stt.py          # OpenAI-compatible 文件上传式 STT
├── openai_tts.py               # OpenAI-compatible TTS 读题
└── interfaces/
    ├── api.py                  # FastAPI app
    └── static/
        ├── index.html          # 控制页：真实录音、状态推进、工作人员队列
        ├── display.html        # 只读观众展示页
        └── assets/             # 展示页薄膜/装饰图片
```

配置文件：

```text
config/have_some_ai/
├── questions.yaml              # Food Gate 开头、两道正式题库、A/B 选项、中英文本
└── scoring.yaml                # 四种食物映射、观察事件权重备注
```

运行时数据库表包括：

```text
meal_participants
meal_question_draws
meal_answers
meal_voice_answer_interpretations
meal_observation_events
meal_assignments
meal_staff_queue
```

`meal_voice_answer_interpretations` 保存语音理解过程：原始转写、STT 元数据、attempt_id、Claude 推断选项、置信度、中英理由、原始/修复后的 LLM JSON 和 status。不保存音频文件。

### API 概览

```text
GET  /display
GET  /display-assets/{filename}
GET  /health
GET  /api/v1/config
GET  /api/v1/voice-config
GET  /api/v1/display-state
POST /api/v1/display-state

POST /api/v1/participants
GET  /api/v1/participants
GET  /api/v1/participants/{id}

POST /api/v1/participants/{id}/questionnaire/start
POST /api/v1/participants/{id}/conversation-turn
POST /api/v1/participants/{id}/conversation-audio
POST /api/v1/participants/{id}/answers
POST /api/v1/participants/{id}/voice-answers
POST /api/v1/participants/{id}/assign

POST /api/v1/speech/thanks
POST /api/v1/participants/{id}/questions/{question_id}/speech
POST /api/v1/participants/{id}/questions/{question_id}/voice-audio
WS   /api/v1/participants/{id}/conversation-stream

POST /api/v1/participants/{id}/observations
GET  /api/v1/staff-queue
PATCH /api/v1/staff-queue/{queue_item_id}
GET  /api/v1/export
```

### 运行

```bash
./.venv/bin/python scripts/start_have_some_ai.py --port 8010
# http://127.0.0.1:8010/
# http://127.0.0.1:8010/display
# http://127.0.0.1:8010/docs
```

启动后先做三步本地检查：

```bash
lsof -nP -iTCP:8010 -sTCP:LISTEN
curl -s http://127.0.0.1:8010/health
curl -s http://127.0.0.1:8010/display
curl -s http://127.0.0.1:8010/api/v1/voice-config
curl -s http://127.0.0.1:8010/api/v1/display-state
```

如果 8010 没有监听，网页不会有声音，麦克风也不会进入后端语音链路。先启动服务或换一个空闲端口，再打开对应地址。

可在 `.env` 中覆盖：

```env
HAVE_SOME_AI_DB_PATH=data/have_some_ai.db
HAVE_SOME_AI_CONFIG_DIR=config/have_some_ai
```

语音功能需要：

```env
HAVE_SOME_AI_VOICE_PROVIDER=aihubmix
HAVE_SOME_AI_STT_MODE=file
HAVE_SOME_AI_VOICE_API_KEY=your_aihubmix_key_here
HAVE_SOME_AI_VOICE_BASE_URL=https://aihubmix.com/v1
HAVE_SOME_AI_STT_MODEL=whisper-large-v3
HAVE_SOME_AI_STT_LANGUAGE=zh
HAVE_SOME_AI_TTS_MODEL=gpt-4o-mini-tts
HAVE_SOME_AI_TTS_VOICE=alloy
HAVE_SOME_AI_RUBRIC_CONFIDENCE_THRESHOLD=0.55
```

其中 `HAVE_SOME_AI_VOICE_API_KEY` 必填；`HAVE_SOME_AI_VOICE_BASE_URL`
填 AIHubMix 或其他 OpenAI-compatible `/v1` 地址。AIHubMix 当前走
`/audio/transcriptions` 文件上传式 STT，不走 Realtime session；中文现场推荐
`HAVE_SOME_AI_STT_MODEL=whisper-large-v3` 和 `HAVE_SOME_AI_STT_LANGUAGE=zh`。
如果需要中英双语自动判断，可将 `HAVE_SOME_AI_STT_LANGUAGE` 留空。
如果没有设置语音专用 key，系统会回退读取 `OPENAI_API_KEY`。

浏览器端会读取 `/api/v1/voice-config`：`aihubmix + file` 使用 MediaRecorder 录音并上传真实
`mime_type`；`doubao + asr_tts_stream` 使用本地 `/conversation-stream` WebSocket。浏览器发送 binary PCM16 16k mono 音频块，后端聚合约 200ms 后送 Doubao ASR `bigmodel_async`；只消费新增 `definite=true` 分句。

豆包模式下所有店主可听见回复都通过 Doubao TTS V3 `tts/bidirection` 播放，固定音色 `zh_female_yingyujiaoxue_uranus_bigtts`。TTS 输出 PCM16 24k mono；播放期间前后端 half-duplex 暂停 ASR 上行，避免把店主自己的声音识别成用户回答。豆包只负责 ASR/TTS，不闲聊、不判题、不打分、不分配食物。

当前豆包 split 状态：

- 后端主入口为 `/api/v1/participants/{participant_id}/conversation-stream`。
- ASR 使用 `wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async`。
- TTS 使用 `wss://openspeech.bytedance.com/api/v3/tts/bidirection`。
- `barge_in` 协议已接入；前端本地自动打断默认关闭，现场仍需人工验收。
- 仍待现场浏览器麦克风验收：ASR definite 分句、TTS PCM 播放、回声防护、barge-in 和完整两题答题流程。

豆包模式需要额外配置：

```env
HAVE_SOME_AI_VOICE_PROVIDER=doubao
HAVE_SOME_AI_STT_MODE=asr_tts_stream
DOUBAO_API_KEY=your_volcengine_api_key_here
DOUBAO_ASR_ENDPOINT=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async
DOUBAO_ASR_RESOURCE_ID=volc.seedasr.sauc.duration
DOUBAO_TTS_ENDPOINT=wss://openspeech.bytedance.com/api/v3/tts/bidirection
DOUBAO_TTS_RESOURCE_ID=seed-tts-2.0
```

Claude / Anthropic 配置见下方 Shared Environment。Have Some "Ai" 只在 `FormalTurnRouter` 判定用户正在尝试回答正式 A/B 题时调用 Claude judge。chitchat、侧问、评论、unclear_speech 和 noise 都不进入 Claude judge，也不保存正式答案；chitchat 的前 1-2 回合可在话术层调用 Claude 生成 `reply_text`。

AI 店主运行语境放在 `backend/prompts/shopkeeper_runtime_context.md`，由 `prompt_context.py` 缓存读取，只注入 `ShopkeeperReplyService` 的自由闲聊 system prompt。它不能影响 Claude rubric、`ScoringEngine`、food assignment 或任何 `meal_*` 落库逻辑。

### 豆包语音 smoke test

1. 确认 `.env` 中 `HAVE_SOME_AI_VOICE_PROVIDER=doubao`、`HAVE_SOME_AI_STT_MODE=asr_tts_stream`，并设置 `DOUBAO_API_KEY` 或分别设置 `DOUBAO_ASR_API_KEY` / `DOUBAO_TTS_API_KEY`。
2. 启动 `./.venv/bin/python scripts/start_have_some_ai.py --port 8010`。
3. 打开 `http://127.0.0.1:8010/`，新建观众，点击 `Start Voice`。
4. 期望先听到 Language Gate；说 English / 中文，或直接用明确的英文 / 中文回答来选择本次会话语言。
5. 随后听到 Food Gate / 店主开场；TTS 播放期间页面可能显示 `doubao speaking`，后端会发送 `mic.muted_for_tts`，此时麦克风音频不会送 ASR，这是预期的回声防护。
6. TTS 结束后应收到 `mic.resumed_after_tts`，再对着麦克风回答要不要吃。
7. 想吃后进入两道正式题；只有正式题 `answer_attempt` 会触发 Claude judge。完成两道 A/B 后才出现 `score` / 食物分配。

### 语音排障

- 没声音、麦克风没反应：先确认 8010 正在监听，`/health` 返回 `ok`，`/api/v1/voice-config` 能返回 `provider=doubao`、`stt_mode=asr_tts_stream`、`conversation_stream_available=true`。
- 浏览器没有权限弹窗：用 `http://127.0.0.1:8010/` 或 localhost 打开，刷新页面后重新点击 `Start Voice`，检查浏览器地址栏的麦克风权限。
- TTS 播放时麦克风不像在录：这是 half-duplex 预期行为。TTS 期间后端丢弃麦克风帧，等 `mic.resumed_after_tts` 后才恢复 ASR 上行。
- 页面显示 `doubao tts failed · mic listening`：TTS provider 出错，后端会发 `tts.error` 并恢复收麦；检查 `DOUBAO_TTS_*` 鉴权、resource id、endpoint 和后端日志里的 `X-Tt-Logid`。
- 能录但没有识别推进：确认说话发生在 `mic.resumed_after_tts` 之后；ASR 只消费新增 `utterances[].definite=true`，不会每个音频包都返回识别结果。

### 后续路线

```text
v0.1  最小闭环：编号、抽题、评分、分配、工作人员队列（已完成）
v0.2  语音交互：TTS 读题、云端 STT、LLM 答案理解、重说机制（原型中）
v0.3  现场系统：安全/忌口覆盖、观众端/工作人员端拆分、展后导出
v0.4  空间介入：摄像头/动作观察、打印、小票、灯光、厨房信号或 ESP32
```

---

## Shared Environment

### Python

```text
Python >= 3.11
```

当前本地 `.venv`：

```text
Python 3.13.5
/Users/ecotourism/Downloads/整点艾/.venv/bin/python
python.org Framework build: /Library/Frameworks/Python.framework/Versions/3.13/bin/python3
OpenSSL 3.0.16 11 Feb 2025
```

安装：

```bash
source .venv/bin/activate
pip install -e ".[dev,api]"
```

### LLM 环境变量

项目启动时会自动读取仓库根目录的 `.env`。如果 shell 中已经 `export` 了同名变量，则以 shell 环境变量为准。

官方 Anthropic：

```env
ANTHROPIC_API_KEY=your_official_key_here
ENTITY_DB_PATH=data/memory.db
ENTITY_CONFIG_DIR=config/
ENTITY_PROMPTS_DIR=prompts/
ENTITY_LOG_LEVEL=INFO
```

供应商 Anthropic 兼容接口：

```env
ANTHROPIC_AUTH_TOKEN=your_supplier_token_here
ANTHROPIC_BASE_URL=https://your-provider.example
ENTITY_LLM_MODEL=your_supplier_model_name
ENTITY_DB_PATH=data/memory.db
ENTITY_CONFIG_DIR=config/
ENTITY_PROMPTS_DIR=prompts/
ENTITY_LOG_LEVEL=INFO
```

非标准消息接口：

```env
ANTHROPIC_AUTH_TOKEN=your_supplier_token_here
ENTITY_LLM_MODEL=your_supplier_model_name
ENTITY_LLM_MESSAGES_ENDPOINT=https://your-provider.example/path/to/messages
ENTITY_DB_PATH=data/memory.db
ENTITY_CONFIG_DIR=config/
ENTITY_PROMPTS_DIR=prompts/
ENTITY_LOG_LEVEL=INFO
```

可选代理绕过：

```env
ENTITY_LLM_DISABLE_SYSTEM_PROXY=true
```

### 本地已验证依赖版本

当前 `.venv` 已用 python.org Framework Python 重建，不再使用 Anaconda Python。此前 Anaconda Python 3.13.5 会在普通 `pytest` 导入 debugging 插件时触发段错误；当前环境中普通 `pytest` 已可运行，不需要 `-p no:debugging` / `-p no:capture` 绕过。

Framework Python 的 SSL 证书也已修复：`/Library/Frameworks/Python.framework/Versions/3.13/etc/openssl/cert.pem` 指向全局 `certifi==2026.4.22` 的 `cacert.pem`。标准库 HTTPS 验证已通过：`urllib.request.urlopen("https://pypi.org/simple/pip/").status == 200`。

| 依赖 | 版本 |
| --- | --- |
| `anthropic` | `0.97.0` |
| `httpx` | `0.28.1` |
| `PyYAML` | `6.0.3` |
| `rich` | `15.0.0` |
| `fastapi` | `0.136.1` |
| `uvicorn` | `0.46.0` |
| `pytest` | `9.0.3` |
| `pytest-mock` | `3.15.1` |

完整当前环境 freeze：

```text
annotated-doc==0.0.4
annotated-types==0.7.0
anthropic==0.97.0
anyio==4.13.0
certifi==2026.4.22
click==8.3.3
conscious-entity==1.2.1
distro==1.9.0
docstring_parser==0.18.0
fastapi==0.136.1
h11==0.16.0
httpcore==1.0.9
httptools==0.7.1
httpx==0.28.1
idna==3.13
iniconfig==2.3.0
jiter==0.14.0
markdown-it-py==4.0.0
mdurl==0.1.2
packaging==26.2
pip==25.1.1
pluggy==1.6.0
pydantic==2.13.3
pydantic_core==2.46.3
Pygments==2.20.0
pytest==9.0.3
pytest-mock==3.15.1
python-dotenv==1.2.2
PyYAML==6.0.3
rich==15.0.0
sniffio==1.3.1
starlette==1.0.0
typing_extensions==4.15.0
typing-inspection==0.4.2
uvicorn==0.46.0
uvloop==0.22.1
watchfiles==1.1.1
websockets==16.0
```

`pyproject.toml` 中仍使用最低版本约束，上表和 freeze 记录的是当前机器的实际安装版本。

如果需要从零重建当前环境：

```bash
cd /Users/ecotourism/Downloads/整点艾
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m venv --clear .venv
source .venv/bin/activate
pip install -e ".[dev,api]"
```

如果首次安装时报 SSL 证书错误，先修复 Framework Python 证书：

```bash
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pip install --upgrade certifi
/Applications/Python\ 3.13/Install\ Certificates.command
```

### 测试

常规：

```bash
pytest
```

当前针对 Have Some "Ai" 语音主链路、状态机和 API 的验证命令是：

```bash
.venv/bin/python -m pytest \
  tests/unit/test_have_some_ai_voice.py \
  tests/unit/test_have_some_ai_conversation.py \
  tests/unit/test_have_some_ai_api.py \
  -q
```

上述子集用于快速验证 Have Some "Ai" 语音主链路、状态机和 API。

当前最新完整验证：`pytest` 为 `310 passed`；`/display` 禁止入口静态扫描无命中，确认展示页没有 `getUserMedia`、`conversation-stream`、真实语音 WebSocket、答案提交、分配或工作人员队列入口。

当前文档状态：README 与 `docs/TECH_STACK.md` / `docs/progress.md` 记录的是当前本机环境和 Have Some "Ai" 语音原型状态；`docs/PRD.md`、`docs/APP_FLOW.md`、`docs/BACKEND_STRUCTURE.md`、`docs/IMPLEMENTATION_PLAN.md` 仍主要是 The "Stranger" 的 v0.1 设计文档。

---

## Docs

| 文档 | 说明 |
| --- | --- |
| `docs/progress.md` | 两个作品的当前进度和已知问题 |
| `docs/frame.md` | Conscious Entity 架构文档 |
| `docs/PRD.md` | Conscious Entity 产品需求文档 |
| `docs/APP_FLOW.md` | Conscious Entity 应用流程 |
| `docs/BACKEND_STRUCTURE.md` | Conscious Entity 后端结构 |
| `docs/IMPLEMENTATION_PLAN.md` | Conscious Entity 实现计划 |
| `docs/HAVE_SOME_AI_STRUCTURE.md` | Have Some "Ai" 结构、API 与扩展路线 |
| `docs/TECH_STACK.md` | 技术栈记录 |
| `docs/FRONTEND_GUIDELINES.md` | 前端开发规范 |
| `CLAUDE.md` | AI 编码规则和开发约定 |
| `AGENTS.md` | 当前 Codex / AI 编码规则 |
