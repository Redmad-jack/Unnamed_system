# Tech Stack

Exhibition Systems: The "Stranger" + Have Some "Ai"

---

## 原则

- 每个版本的技术选型必须有明确理由，不随意引入新依赖
- 生产依赖与开发依赖分开管理
- 不允许在未经确认的情况下替换或升级版本
- 离线可运行是硬约束（部署环境可能无外网，文本 LLM / 语音云 API 除外）

---

## 核心技术栈

### 语言与运行时

| 项目 | 版本 | 用途 |
| --- | --- | --- |
| Python | 3.11+ | 主要开发语言 |
| pyproject.toml | PEP 517/518 | 项目配置与依赖管理 |

**当前本地已验证运行时（2026-05-04）：**

```text
Python 3.13.5
Interpreter: /Users/ecotourism/Downloads/整点艾/.venv/bin/python
Base Python: /Library/Frameworks/Python.framework/Versions/3.13/bin/python3
OpenSSL: 3.0.16 11 Feb 2025
```

说明：当前 `.venv` 必须使用 python.org Framework Python 创建。不要用 `/opt/anaconda3/bin/python` 创建本项目 `.venv`，因为该环境会在普通 `pytest` 导入 debugging 插件时触发段错误。

Framework Python 证书状态：

```text
/Library/Frameworks/Python.framework/Versions/3.13/etc/openssl/cert.pem
  -> ../../lib/python3.13/site-packages/certifi/cacert.pem
certifi==2026.4.22
urllib.request HTTPS check against https://pypi.org/simple/pip/: 200
```

### AI / ML

| 项目 | 版本 | 用途 | 版本锁定 |
| --- | --- | --- | --- |
| anthropic | latest stable | Anthropic provider 客户端（表达层、反思层、Have Some "Ai" 正式题 judge 与闲聊话术的默认 / 回退 provider） | 锁定在 pyproject.toml |
| httpx | >=0.27.0 | Anthropic 兼容网关、火山方舟 Ark Chat Completions、推理时代语音网关 HTTP 调用 | 锁定在 pyproject.toml |
| sentence-transformers | deferred | 本地 Embedding 模型（The "Stranger" 语义记忆检索，尚未接入当前主项目） | 当前未声明在 pyproject.toml |

**文本 LLM provider 分配：**

- 表达层（ExpressionEngine）→ `claude-sonnet-4-6`（语气细节、开放生成）
- 反思层（ReflectionEngine）→ `claude-haiku-4-5-20251001`（批量压缩，成本控制）
- Have Some "Ai"：`ClaudeClient` 是文本 LLM 唯一入口，`ENTITY_LLM_PROVIDER=anthropic|ark`；默认仍为 `anthropic`，Ark 默认 `doubao-seed-2-0-pro-260215` + Chat Completions + `ENTITY_LLM_ARK_THINKING=disabled`
- Have Some "Ai"：Food Gate 歧义入口可由文本 LLM 分类为 `want_food / want_chat / no_food / unclear_speech`；正式 A/B/unclear judge 只处理 `answer_attempt`；chitchat 话术层只生成 `reply_text`，不决定食物；provider 可为 Anthropic 或 Ark

**Embedding 模型：**

- 默认使用 `all-MiniLM-L6-v2`（轻量，本地运行，中英文效果可接受）
- 若效果不足，升级为 `paraphrase-multilingual-MiniLM-L12-v2`（更好的多语言支持）

### 数据库

| 项目 | 版本 | 用途 |
| --- | --- | --- |
| SQLite | 3.x（系统自带） | 主数据库，WAL 模式 |
| sqlite3 | Python 标准库 | 数据库连接 |

**选型理由：** 单机部署、无网络依赖、WAL 模式支持读写并发、无服务器进程。

两个作品各自使用独立数据库文件（`data/memory.db` 和 `data/have_some_ai.db`），不共享数据。

### 配置格式

| 项目 | 版本 | 用途 |
| --- | --- | --- |
| PyYAML | latest stable | 读取 YAML 配置文件 |

所有行为规则（状态更新、策略选择、宪法约束、表达映射、题库、评分）均存储在 YAML 文件中，不硬编码在 Python。

### 测试

| 项目 | 版本 | 用途 |
| --- | --- | --- |
| pytest | latest stable | 测试框架 |
| pytest-mock | latest stable | Mock LLM 调用 |

**当前本地完整依赖版本（2026-05-04）：**

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

---

## 可选依赖组 [api]

以下依赖通过 `pip install -e ".[api]"` 安装，两个作品的 HTTP API 均需要：

| 项目 | 版本 | 用途 |
| --- | --- | --- |
| fastapi | >=0.115.0 | HTTP API 服务（开发者面板 + Web 界面） |
| uvicorn | >=0.32.0 | FastAPI ASGI 服务器 |

---

## 前端技术

**已确定**：两个作品均使用**原生 HTML/CSS/JS**（单文件，无构建工具）。

| 作品 | 文件 |
| --- | --- |
| The "Stranger" | `src/conscious_entity/interfaces/static/index.html` |
| Have Some "Ai" 控制页 | `src/have_some_ai/interfaces/static/index.html` |
| Have Some "Ai" 只读展示页 | `src/have_some_ai/interfaces/static/display.html` + `src/have_some_ai/interfaces/static/assets/` |

选型理由：展览环境下零依赖、完全可控、无需 Node.js 构建链，2s 轮询 + 原生 fetch 满足当前需求。

Have Some "Ai" 双屏模式中，`/` 控制页承担真实录音、ASR/TTS、状态机推进和工作人员队列；`/display` 展示页只轮询内存级 `/api/v1/display-state`，不得请求麦克风、创建语音 WebSocket、写数据库或推进业务流程。

---

## v0.2 已选型接口

以下接口已在 Have Some "Ai" 语音原型中使用：

| 项目 | 用途 |
| --- | --- |
| AIHubMix OpenAI-compatible file STT | Have Some "Ai" 语音转文字，默认模型 `whisper-large-v3`，走 `/audio/transcriptions` |
| OpenAI-compatible TTS | 非豆包 provider 的店主回复 fallback，默认模型 `gpt-4o-mini-tts` |
| 火山引擎豆包 ASR 2.0 + TTS/ICL 2.0 | Have Some "Ai" 后端 WebSocket 分离接入：ASR 使用 `bigmodel_async` 常驻 session，只消费 `definite=true` 分句；TTS 使用 V3 双向流式 `tts/bidirection`，声音复刻资源 `seed-icl-2.0`，按 `response_language` 选择复刻音色（中文 `S_sd9II0522`，英文 `S_r98II0522`，fallback 中文），输出 PCM 24k；Food Gate 歧义入口、正式 A/B/unclear 判题和 chitchat 话术走配置的文本 LLM provider（Anthropic 或 Ark） |
| sentence-transformers | Conscious Entity 语义记忆检索（Embedding），当前仍为 deferred，未安装为项目依赖 |

Have Some "Ai" 的 AI 店主运行语境保存在 `backend/prompts/shopkeeper_runtime_context.md`，只作为 `ShopkeeperReplyService` 自由闲聊 system prompt 的附加上下文，不进入 Food Gate 入口分类、正式 A/B rubric、`ScoringEngine`、food assignment 或数据库写入决策。

Have Some "Ai" 豆包音频接口：

- 浏览器输入：`getUserMedia()` 采集 Float32，downmix mono，重采样到 16000 Hz，转换为 PCM s16le，通过 binary WebSocket frame 发送。
- 后端 ASR：`/conversation-stream` 聚合约 200ms PCM 后发送给 Doubao ASR `bigmodel_async`；只在 participant session 结束、cancel、浏览器断开或后端重连时发送 ASR final packet。
- 后端 TTS：Doubao TTS V3 `tts/bidirection` 输出 PCM s16le 24k mono，通过 WebSocket binary frame 直接回浏览器。
- 浏览器输出：按后端 `audio.output_config` 的 `sample_rate=24000` 创建 AudioBuffer 队列播放，不把 24k PCM 当作浏览器默认采样率。
- half-duplex：TTS 播放期间前后端暂停 ASR 上行；`mic.muted_for_tts` / `mic.resumed_after_tts` 是预期状态事件。
- barge-in：协议和后端 `CancelSession=101` 已接入；前端本地自动打断默认关闭，现场体验仍需验收。

豆包手动 smoke test：

```bash
./.venv/bin/python scripts/start_have_some_ai.py --port 8010
lsof -nP -iTCP:8010 -sTCP:LISTEN
curl -s http://127.0.0.1:8010/health
curl -s http://127.0.0.1:8010/api/v1/voice-config
```

打开 `http://127.0.0.1:8010/`，新建观众后使用 Start Voice；确认 Food Gate TTS、`mic.muted_for_tts` / `mic.resumed_after_tts`、ASR partial/final、Food Gate 歧义入口分类、正式 answer_attempt 的 LLM judge、TTS PCM 播放和两道正式题后的食物分配。若 8010 没有监听，先不要诊断浏览器麦克风或 TTS。

---

## 环境配置

### 目录结构

```text
.env.example          ← 环境变量模板（提交到 git）
.env                  ← 实际环境变量（不提交到 git）
pyproject.toml        ← 项目配置 + 依赖声明
```

### 必要环境变量

```env
# Official Anthropic mode
# ENTITY_LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=your_key_here

# Supplier / Anthropic-compatible mode
# ENTITY_LLM_PROVIDER=anthropic
# ANTHROPIC_AUTH_TOKEN=your_supplier_token_here
# ANTHROPIC_BASE_URL=https://your-provider.example
# ENTITY_LLM_MODEL=your_supplier_model_name

# Supplier / non-standard full endpoint mode
# ENTITY_LLM_PROVIDER=anthropic
# ANTHROPIC_AUTH_TOKEN=your_supplier_token_here
# ENTITY_LLM_MODEL=your_supplier_model_name
# ENTITY_LLM_MESSAGES_ENDPOINT=https://your-provider.example/path/to/messages

# Volcengine Ark / Doubao Chat Completions mode
# ENTITY_LLM_PROVIDER=ark
# ARK_API_KEY=your_ark_api_key_here
# ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
# ENTITY_LLM_MODEL=doubao-seed-2-0-pro-260215
# ENTITY_LLM_ARK_THINKING=disabled

# Optional: bypass system proxy
# ENTITY_LLM_DISABLE_SYSTEM_PROXY=true

ENTITY_DB_PATH=data/memory.db
ENTITY_CONFIG_DIR=config/
ENTITY_PROMPTS_DIR=prompts/
ENTITY_LOG_LEVEL=INFO

HAVE_SOME_AI_DB_PATH=data/have_some_ai.db
HAVE_SOME_AI_CONFIG_DIR=config/have_some_ai
HAVE_SOME_AI_VOICE_PROVIDER=aihubmix
HAVE_SOME_AI_STT_MODE=file
HAVE_SOME_AI_VOICE_API_KEY=your_voice_provider_key_here
HAVE_SOME_AI_VOICE_BASE_URL=https://your-voice-provider.example/v1
HAVE_SOME_AI_STT_MODEL=whisper-large-v3
HAVE_SOME_AI_STT_LANGUAGE=zh
HAVE_SOME_AI_TTS_MODEL=gpt-4o-mini-tts
HAVE_SOME_AI_TTS_VOICE=alloy

# Doubao ASR/TTS split streaming
HAVE_SOME_AI_VOICE_PROVIDER=doubao
HAVE_SOME_AI_STT_MODE=asr_tts_stream
DOUBAO_API_KEY=your_volcengine_api_key_here
DOUBAO_ASR_ENDPOINT=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async
DOUBAO_ASR_RESOURCE_ID=volc.seedasr.sauc.duration
DOUBAO_ASR_ENABLE_NONSTREAM=true
DOUBAO_ASR_END_WINDOW_SIZE_MS=800
DOUBAO_ASR_FORCE_TO_SPEECH_TIME_MS=1000
DOUBAO_ASR_RESULT_TYPE=single
DOUBAO_ASR_AUDIO_FORMAT=pcm
DOUBAO_ASR_SAMPLE_RATE=16000
DOUBAO_ASR_BITS=16
DOUBAO_ASR_CHANNELS=1
DOUBAO_TTS_ENDPOINT=wss://openspeech.bytedance.com/api/v3/tts/bidirection
DOUBAO_TTS_RESOURCE_ID=seed-icl-2.0
DOUBAO_TTS_SPEAKER_ZH=S_sd9II0522
DOUBAO_TTS_SPEAKER_EN=S_r98II0522
DOUBAO_TTS_AUDIO_FORMAT=pcm
DOUBAO_TTS_SAMPLE_RATE=24000
DOUBAO_TTS_SPEECH_RATE=0
DOUBAO_TTS_LOUDNESS_RATE=0
```

### 开发 / 现场环境假设

- macOS 本机开发已验证；不要使用 Anaconda Python 创建 `.venv`
- Windows 拯救者主控部署见 `docs/windows_lenovo_deployment.md` 和 `scripts/setup_windows.ps1`
- Python 3.11+ 已安装，Windows 推荐 Python 3.13 x64
- 网络可访问配置的文本 LLM API（Anthropic 或 Ark）和语音 API（豆包或 AIHubMix）
- 无需 Docker 或容器化

---

## 禁止事项

- 不允许在 Python 代码中硬编码 API Key
- 不允许未经确认擅自替换已锁定的依赖版本
- 不允许为 LLM 调用引入 LangChain 等框架（直接使用 provider SDK 或 `httpx`）
- 不允许把 v0.2 语音 / Embedding 依赖伪装成 v0.1 核心依赖；新增依赖必须记录在 `pyproject.toml` 和本文件
