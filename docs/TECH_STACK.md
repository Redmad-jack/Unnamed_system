# Tech Stack

*Conscious Entity System — current text system + developer API*

---

## 原则

- 每个版本的技术选型必须有明确理由，不随意引入新依赖
- 核心运行依赖、API 依赖、开发测试依赖分开管理
- 不允许在未经确认的情况下替换或升级版本
- 离线可运行是硬约束（部署环境可能无外网，Claude API 除外）

---

## 核心技术栈

以下是默认安装路径需要的依赖。FastAPI、uvicorn 和 pytest 等不放入核心 `dependencies`。

### 语言与运行时

| 项目 | 版本 | 用途 |
|---|---|---|
| Python | 3.11+ | 主要开发语言 |
| pyproject.toml | PEP 517/518 | 项目配置与依赖管理 |

### AI / ML

| 项目 | 版本 | 用途 | 版本锁定 |
|---|---|---|---|
| anthropic | latest stable | Claude API 客户端（表达层、反思层） | 锁定在 pyproject.toml |
| httpx | latest stable | Anthropic 兼容网关与 OpenAI-compatible embedding HTTP 调用 | 锁定在 pyproject.toml |

**Claude 模型分配：**
- 表达层（ExpressionEngine）→ `claude-sonnet-4-6`（语气细节、开放生成）
- 反思层（ReflectionEngine）→ `claude-haiku-4-5-20251001`（批量压缩，成本控制）
- Managed memory proposal → 复用注入的 ClaudeClient，通过 proposal → commit 路径进入行为记忆

**Embedding 模型：**
- 默认关闭：`ENTITY_EMBEDDING_MODE=disabled`，只使用可解释记忆召回
- 可选启用 OpenAI-compatible embedding 接口：`ENTITY_EMBEDDING_MODE=openai_compatible`
- 向量存储仍使用 SQLite `embedding` / `embedding_model` 字段，不引入 Chroma、pgvector 或本地 `sentence-transformers` 重依赖

**Managed Memory：**
- 默认本地实现：SQLite + FTS5 + 可选 embedding BLOB
- 可选 `ENTITY_MEMORY_BACKEND=mem0`，作为 mem0ai 后端预留；未安装时安全回退到本地 provider
- 记忆形成采用 proposal → commit：第一版默认 auto-commit，但仍保留审批接口

### 数据库

| 项目 | 版本 | 用途 |
|---|---|---|
| SQLite | 3.x（系统自带） | 主数据库，WAL 模式 |
| sqlite3 | Python 标准库 | 数据库连接 |

**选型理由：** 单机部署、无网络依赖、WAL 模式支持读写并发、无服务器进程。

### 配置格式

| 项目 | 版本 | 用途 |
|---|---|---|
| PyYAML | latest stable | 读取 YAML 配置文件 |

所有行为规则（状态更新、策略选择、宪法约束、表达映射）均存储在 YAML 文件中，不硬编码在 Python。

## Optional Dependency Groups

`pyproject.toml` 使用 optional dependency groups 控制非核心能力：

| Group | 项目 | 用途 | 当前状态 |
|---|---|---|---|
| `api` | fastapi | 本地开发者 API 与 Web 看板 | 已实现，按需安装 |
| `api` | uvicorn | FastAPI ASGI 服务器 | 已实现，按需安装 |
| `vision` | opencv-python | Mac 摄像头采集、JPEG 编码、标注帧绘制 | 已实现，按需安装 |
| `vision` | ultralytics | 本地 YOLO person detection | 已实现，按需安装 |
| `dev` | pytest | 测试框架 | 已实现，开发时安装 |
| `dev` | pytest-mock | Mock LLM 调用 | 已实现，开发时安装 |
| 后续待定 | Whisper / 系统 TTS / gTTS | STT/TTS 语音通道 | 未引入，待设计确认 |

原则：后续语音、硬件或前端构建依赖不得并入核心 `dependencies`；只有完成设计确认并声明安装路径后，才加入对应 optional group。视觉第一版已进入 `vision` optional group，但默认安装路径仍不包含 OpenCV / ultralytics。

---

## 前端技术

当前开发者面板使用 FastAPI 静态页面 + 原生 HTML/CSS/JS，服务于本地调试、Memory Preview、managed memory curation 和 Vision worker 监控。访客侧第一版 `/visitor` 也是原生 HTML/CSS/JS，只作为非 dashboard 的临时 body-facing surface，不暴露内部规则、memory 或 prompt。

访客端候选方案（供后续决策参考）：

| 方案 | 优点 | 缺点 | 适合场景 |
|---|---|---|---|
| 原生 HTML/CSS/JS | 零依赖，完全可控 | 开发效率低 | 极简展览界面 |
| React SPA | 组件化，状态管理清晰 | 需要 Node.js 构建链 | 复杂运营者面板 |
| FastAPI + Jinja2 SSR | Python 全栈，无独立前端 | 动态交互受限 | MVP 快速落地 |

在身体外观、投影、屏幕或光的具体方案确认前，不引入任何前端构建工具或框架。

---

## 环境配置

### 目录结构

```
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
# ANTHROPIC_BASE_URL=https://code.newcli.com/claude/aws
# ENTITY_LLM_MODEL=your_supplier_model_name

# Supplier / non-standard full endpoint mode
# ANTHROPIC_AUTH_TOKEN=your_supplier_token_here
# ENTITY_LLM_MODEL=your_supplier_model_name
# ENTITY_LLM_MESSAGES_ENDPOINT=https://your-provider.example/path/to/messages

ENTITY_DB_PATH=data/memory.db
ENTITY_CONFIG_DIR=config/
ENTITY_PROMPTS_DIR=prompts/
ENTITY_LOG_LEVEL=INFO

# Managed memory
ENTITY_MEMORY_BACKEND=local
ENTITY_MEMORY_AUTO_COMMIT=true
ENTITY_MEMORY_INFERENCE=true
ENTITY_MEMORY_POLICY_INFLUENCE=true
ENTITY_MEMORY_STATE_INFLUENCE=true

# Optional vision runtime
# ENTITY_VISION_MODEL_PATH=/absolute/path/to/yolo-model.pt
ENTITY_VISION_CAMERA_INDEX=0
ENTITY_VISION_WIDTH=1280
ENTITY_VISION_HEIGHT=720
ENTITY_VISION_FPS=10
ENTITY_VISION_CONFIDENCE=0.45
```

### 开发环境假设

- macOS 或 Linux（Windows 未测试）
- Python 3.11+ 已安装
- 网络可访问 Anthropic API
- 无需 Docker 或容器化

---

## 禁止事项

- 不允许在 Python 代码中硬编码 API Key
- 不允许未经确认擅自替换已锁定的依赖版本
- 不允许为 LLM 调用引入 LangChain 等框架（直接使用 Anthropic SDK）
- 不允许把后续语音、硬件或前端构建依赖并入核心 `dependencies`
- FastAPI / uvicorn 必须继续保留在 `api` optional group 中
- OpenCV / ultralytics 必须继续保留在 `vision` optional group 中，且模型路径必须显式配置，不自动下载模型
