# Tech Stack

*Conscious Entity System — v0.1*

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
|---|---|---|
| Python | 3.11+ | 主要开发语言 |
| pyproject.toml | PEP 517/518 | 项目配置与依赖管理 |

### AI / ML

| 项目 | 版本 | 用途 | 版本锁定 |
|---|---|---|---|
| anthropic | latest stable | Claude API 客户端（表达层、反思层） | 锁定在 pyproject.toml |
| sentence-transformers | latest stable | 本地 Embedding 模型（语义记忆检索，v0.2 引入） | 锁定在 pyproject.toml |

**Claude 模型分配：**
- 表达层（ExpressionEngine）→ `claude-sonnet-4-6`（语气细节、开放生成）
- 反思层（ReflectionEngine）→ `claude-haiku-4-5-20251001`（批量压缩，成本控制）

**Embedding 模型：**
- 默认使用 `all-MiniLM-L6-v2`（轻量，本地运行，中英文效果可接受）
- 若效果不足，升级为 `paraphrase-multilingual-MiniLM-L12-v2`（更好的多语言支持）

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

### 测试

| 项目 | 版本 | 用途 |
|---|---|---|
| pytest | latest stable | 测试框架 |
| pytest-mock | latest stable | Mock LLM 调用 |

---

## v0.2 新增依赖

以下依赖在 v0.1 中**不引入**，v0.2 才添加：

| 项目 | 用途 |
|---|---|
| fastapi | HTTP API 服务（运营者面板 + 访客 Web 界面） |
| uvicorn | FastAPI ASGI 服务器 |
| openai-whisper | STT 语音转文字 |
| 系统 TTS / gTTS | TTS 文字转语音（具体选型待确认） |

---

## 前端技术

**[ 待确认 ]** 前端技术选型尚未决定。

候选方案（供决策参考）：

| 方案 | 优点 | 缺点 | 适合场景 |
|---|---|---|---|
| 原生 HTML/CSS/JS | 零依赖，完全可控 | 开发效率低 | 极简展览界面 |
| React SPA | 组件化，状态管理清晰 | 需要 Node.js 构建链 | 复杂运营者面板 |
| FastAPI + Jinja2 SSR | Python 全栈，无独立前端 | 动态交互受限 | MVP 快速落地 |

决策前不引入任何前端构建工具或框架。

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
```

### 开发环境假设

- macOS 或 Linux（Windows 未测试）
- Python 3.11+ 已安装
- 网络可访问 Anthropic API
- 无需 Docker 或容器化（v0.1 阶段）

---

## 禁止事项

- 不允许在 Python 代码中硬编码 API Key
- 不允许未经确认擅自替换已锁定的依赖版本
- 不允许为 LLM 调用引入 LangChain 等框架（直接使用 Anthropic SDK）
- 不允许在 v0.1 阶段引入 v0.2 的依赖（避免依赖膨胀）
