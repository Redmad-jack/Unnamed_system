# Tech Stack

Exhibition Systems: The "Stranger" + Have Some "Ai"

---

## 原则

- 每个版本的技术选型必须有明确理由，不随意引入新依赖
- 生产依赖与开发依赖分开管理
- 不允许在未经确认的情况下替换或升级版本
- 离线可运行是硬约束（部署环境可能无外网，Claude API 除外）

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
| anthropic | latest stable | Claude API 客户端（表达层、反思层） | 锁定在 pyproject.toml |
| httpx | >=0.27.0 | Anthropic 兼容网关、推理时代语音网关 HTTP 调用 | 锁定在 pyproject.toml |
| sentence-transformers | latest stable | 本地 Embedding 模型（语义记忆检索，v0.2 引入） | 锁定在 pyproject.toml |

**Claude 模型分配：**

- 表达层（ExpressionEngine）→ `claude-sonnet-4-6`（语气细节、开放生成）
- 反思层（ReflectionEngine）→ `claude-haiku-4-5-20251001`（批量压缩，成本控制）

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
| Have Some "Ai" | `src/have_some_ai/interfaces/static/index.html` |

选型理由：展览环境下零依赖、完全可控、无需 Node.js 构建链，2s 轮询 + 原生 fetch 满足当前需求。

---

## v0.2 已选型接口

以下接口已在 Have Some "Ai" 语音原型中使用：

| 项目 | 用途 |
| --- | --- |
| AIHubMix OpenAI-compatible file STT | Have Some "Ai" 语音转文字，默认模型 `whisper-large-v3`，走 `/audio/transcriptions` |
| OpenAI-compatible TTS | 非豆包 provider 的店主回复 fallback，默认模型 `gpt-4o-mini-tts` |
| 火山引擎豆包 realtime dialogue | Have Some "Ai" 后端 WebSocket 桥接实时听说，输入 `pcm_s16le` 16k mono，输出 `pcm_s16le` 24k；正常麦克风链路使用 server VAD，开场和主语音按钮共用长连接；播放中前端用静音帧降低回声自触发，确认 provider `ASRInfo=450` 后通过 `ClientInterrupt=515` 打断；豆包 provider 下店主发声全走此通道，正式 A/B 判题仍由 Claude rubric interpreter 执行 |
| sentence-transformers | Conscious Entity 语义记忆检索（Embedding） |

豆包 realtime 调试脚本：

```bash
.venv/bin/python scripts/diagnose_doubao_realtime.py --variant full_server_vad_pcm --probe-mode say_hello
```

该脚本只连接火山 WebSocket，不写入项目数据库；输出事件 ID、payload 摘要与 `X-Tt-Logid`，不会输出密钥和音频正文。

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
# ANTHROPIC_API_KEY=your_key_here

# Supplier / Anthropic-compatible mode
# ANTHROPIC_AUTH_TOKEN=your_supplier_token_here
# ANTHROPIC_BASE_URL=https://your-provider.example
# ENTITY_LLM_MODEL=your_supplier_model_name

# Supplier / non-standard full endpoint mode
# ANTHROPIC_AUTH_TOKEN=your_supplier_token_here
# ENTITY_LLM_MODEL=your_supplier_model_name
# ENTITY_LLM_MESSAGES_ENDPOINT=https://your-provider.example/path/to/messages

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

# Doubao realtime dialogue
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

### 开发环境假设

- macOS 或 Linux（Windows 未测试）
- Python 3.11+ 已安装
- 本机优先使用 python.org Framework Python 3.13.5；不要使用 Anaconda Python 创建 `.venv`
- 网络可访问 Anthropic API
- 无需 Docker 或容器化（v0.1 阶段）

---

## 禁止事项

- 不允许在 Python 代码中硬编码 API Key
- 不允许未经确认擅自替换已锁定的依赖版本
- 不允许为 LLM 调用引入 LangChain 等框架（直接使用 Anthropic SDK）
- 不允许把 v0.2 语音 / Embedding 依赖伪装成 v0.1 核心依赖；新增依赖必须记录在 `pyproject.toml` 和本文件
