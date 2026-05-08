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

| 作品 | 当前进度 | 可以做什么 |
| --- | --- | --- |
| The "Stranger" | v0.1 核心完成，开发者 API / Web 看板已起步 | CLI 对话、状态漂移、记忆、策略、Claude 表达、反思、调试看板 |
| Have Some "Ai" | v0.1 最小闭环完成，v0.2 语音原型已接入；豆包 realtime 已到电话式打断 v1 | 新建观众、Food Gate、实时/文件语音识别、LLM 映射 A/B、食物分配、工作人员队列 |

当前 Have Some "Ai" 的现场交互已经从纯 A/B 调试流程，推进到：

```text
新建观众
  ↓
Food Gate 闲聊入口
  ↓
想吃则进入两道正式 A / B 判断题；不想吃则进入普通闲聊
  ↓
AIHubMix/OpenAI-compatible TTS 或豆包 realtime 朗读
  ↓
观众语音回答
  ↓
AIHubMix 文件上传式 STT 或豆包 realtime 转写
  ↓
Claude 将转写映射为 A/B；低置信度或格式异常时要求重说
  ↓
规则评分引擎分配食物
  ↓
工作人员队列
```

其中：

- A、B 是原设计选项，会显示在屏幕上。
- C 是 `Other / 其他`，表示观众可以随便说。
- C 不参与评分；LLM 会把 C 或自由回答理解为更接近 A 或 B。
- Claude 输出会做 JSON 容错解析；malformed JSON 会 repair 一次，仍失败则进入重试。
- 最终食物仍由规则评分引擎决定，LLM 不直接决定食物。
- 不保存观众原始音频，只保存转写、置信度、理由和推断结果。

---

## Work 1: The "Stranger"

### 项目定位

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

### 当前观众流程

```text
1. 新建匿名观众，生成 A001 形式编号
2. Food Gate 问“想来点吃的吗？”
3. `NO_FOOD` 进入普通闲聊，不抽正式题、不分配食物
4. `WANT_FOOD` 后抽两道正式题
5. 屏幕显示题目和 A/B/C 三个选项
6. AIHubMix file STT 或豆包 realtime 生成 transcript
7. Claude 只在正式题阶段将 transcript 映射到 A/B
8. 映射 accepted 后进入下一题；低置信度、无效选项、打岔或 Claude JSON repair 失败时回到当前题
9. 两道正式题分别决定 soup / salad 与 normal / aimiao
10. 系统分配食物并写入工作人员队列
```

当前四种结果：

- `soup`
- `salad`
- `aimiao_soup`
- `aimiao_salad`

### A / B / C 的含义

| 选项 | 作用 |
| --- | --- |
| A | 原设计选项，直接进入隐藏评分 rubric |
| B | 原设计选项，直接进入隐藏评分 rubric |
| C | Other / 其他，观众可以随便说 |

实现上，A/B/C 或任何自由回答都会先变成一段语音转写，再交给 Claude 判断最终更接近 A 还是 B。Claude 输出会经过严格 JSON 解析、code fence / 前后文本 / trailing comma 容错、一次 JSON repair 和 schema 校验；数据库中的正式答案仍只在 `accepted` 时保存 A/B。

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
├── voice.py                    # Claude 将语音转写映射到 A/B
├── voice_provider.py           # 语音 provider / STT mode 配置
├── voice_realtime.py           # 豆包 realtime dialogue 后端 WebSocket 适配器
├── openai_file_stt.py          # OpenAI-compatible 文件上传式 STT
├── openai_tts.py               # OpenAI-compatible TTS 读题
└── interfaces/
    ├── api.py                  # FastAPI app
    └── static/index.html       # 单文件网页界面
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
GET  /health
GET  /api/v1/config
GET  /api/v1/voice-config

POST /api/v1/participants
GET  /api/v1/participants
GET  /api/v1/participants/{id}

POST /api/v1/participants/{id}/questionnaire/start
POST /api/v1/participants/{id}/answers
POST /api/v1/participants/{id}/voice-answers
POST /api/v1/participants/{id}/assign

POST /api/v1/speech/thanks
POST /api/v1/participants/{id}/questions/{question_id}/speech
POST /api/v1/participants/{id}/questions/{question_id}/voice-audio
WS   /api/v1/participants/{id}/conversation-realtime

POST /api/v1/participants/{id}/observations
GET  /api/v1/staff-queue
PATCH /api/v1/staff-queue/{queue_item_id}
GET  /api/v1/export
```

### 运行

```bash
python scripts/start_have_some_ai.py
# http://127.0.0.1:8010/
# http://127.0.0.1:8010/docs
```

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
HAVE_SOME_AI_RUBRIC_CONFIDENCE_THRESHOLD=0.65
```

其中 `HAVE_SOME_AI_VOICE_API_KEY` 必填；`HAVE_SOME_AI_VOICE_BASE_URL`
填 AIHubMix 或其他 OpenAI-compatible `/v1` 地址。AIHubMix 当前走
`/audio/transcriptions` 文件上传式 STT，不走 Realtime session；中文现场推荐
`HAVE_SOME_AI_STT_MODEL=whisper-large-v3` 和 `HAVE_SOME_AI_STT_LANGUAGE=zh`。
如果需要中英双语自动判断，可将 `HAVE_SOME_AI_STT_LANGUAGE` 留空。
如果没有设置语音专用 key，系统会回退读取 `OPENAI_API_KEY`。

浏览器端会读取 `/api/v1/voice-config`：`aihubmix + file` 使用 MediaRecorder 录音并上传真实
`mime_type`；`doubao + realtime_dialogue` 使用本地 `/conversation-realtime` WebSocket 桥接火山引擎，浏览器发送
PCM16 16k base64 音频块（前端按约 20ms/640 bytes 切包），正常语音轮次依赖豆包 server VAD 判断结束；手动停止时仍可发送 `audio.end`，由后端映射为豆包 EndASR `400`。豆包返回 PCM16 24k 音频给浏览器播放；播放中前端默认上传静音帧抑制扬声器回声，只有检测到较明显真人说话才恢复真实麦克风流；收到 provider `ASRInfo=450` 后会停止 WebAudio 播放并通知后端发送 `ClientInterrupt=515`。
豆包模式下所有店主可听见回复都通过豆包 realtime TTS 播放；OpenAI-compatible TTS 只用于非豆包 provider。
豆包 v1 只负责实时听说和 transcript，不负责正式 A/B 判题。

当前豆包 realtime 状态：

- 真实 `StartConnection=50`、`StartSession=150`、`SayHello=300`、`TTSResponse=352` 已通过诊断脚本验证。
- 本地 `/conversation-realtime` WebSocket 已验证 `client.interrupt` 能转发为豆包 `ClientInterrupt=515`，TTS-only 桥接能返回 `audio.delta`。
- 前端主语音按钮和新建观众开场会进入同一个长连接通话；active capture 时不再按单轮音频自动关闭麦克风。
- 播放中默认用静音帧保活，减少豆包把自己的 TTS 回声识别成用户输入；本地 RMS 不再直接打断播放，打断主信号以 provider `ASRInfo=450` 为准。
- 仍待现场浏览器麦克风验收：ASR 文本稳定性、回声门限、真实插话手感和完整两题答题流程。

豆包模式需要额外配置：

```env
HAVE_SOME_AI_VOICE_PROVIDER=doubao
HAVE_SOME_AI_STT_MODE=realtime_dialogue
HAVE_SOME_AI_DOUBAO_APP_ID=your_volcengine_app_id_here
HAVE_SOME_AI_DOUBAO_APP_KEY=PlgvMymc7f3tQnJ6
HAVE_SOME_AI_DOUBAO_ACCESS_TOKEN=your_volcengine_access_token_here
HAVE_SOME_AI_DOUBAO_RESOURCE_ID=volc.speech.dialog
HAVE_SOME_AI_DOUBAO_WS_URL=wss://openspeech.bytedance.com/api/v3/realtime/dialogue
HAVE_SOME_AI_DOUBAO_MODEL=1.2.1.1
HAVE_SOME_AI_DOUBAO_SPEAKER=zh_female_vv_jupiter_bigtts
HAVE_SOME_AI_DOUBAO_BOT_NAME=Have Some Ai
HAVE_SOME_AI_DOUBAO_SPEAKING_STYLE=用简短、温和、带一点展览店主感的中文或英文回答。
```

Claude / Anthropic 配置见下方 Shared Environment。Have Some "Ai" 使用 Claude 理解语音转写，但不让 Claude 决定最终食物。Claude 返回 malformed JSON 时会本地容错解析并最多 repair 一次；repair 仍失败会返回 `unclear`，前端要求观众重说，不保存正式答案。

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
conscious-entity==0.1.0
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

当前针对 Have Some "Ai" 的验证命令是：

```bash
.venv/bin/python -m pytest \
  tests/unit/test_have_some_ai_scoring.py \
  tests/unit/test_have_some_ai_service.py \
  tests/unit/test_have_some_ai_api.py \
  tests/unit/test_have_some_ai_voice.py \
  -q
```

当前结果：Have Some "Ai" 单元测试子集为 `81 passed`；前端单文件 JS 语法检查通过。

全项目 `pytest -q` 当前可以正常运行到断言阶段，不再段错误；现存失败为 11 个 Work 1 测试失败，集中在 mocked LLM metadata 返回值和 style mapper 期望值，属于代码/测试契约问题，不是 Python 环境问题。

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
