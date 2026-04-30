# Exhibition Systems: The "Stranger" + Have Some "Ai"

这个仓库服务于同一个合作项目中的两个并置作品：

- **The "Stranger"**：关注 AI 作为非人主体进入社会关系之后，它会处于什么位置。
- **Have Some "Ai"**：关注 AI 进入推荐、分类、匹配和分配机制之后，人类主体性如何被改变。

它们共享同一个研究母题，但在软件上应当保持独立：**不共享状态、记忆、题库、评分规则和分配结果**。

```text
src/
├── conscious_entity/          # Work 1: The "Stranger"
└── have_some_ai/              # Work 2: Have Some "Ai"
```

---

## Work 1: The "Stranger"

### 项目定位

The "Stranger" 使用原有 `conscious_entity` 系统。它不是聊天机器人，也不是 AI 助手，而是一套最小化的人工组织结构：通过状态、记忆、阻抗、延迟、沉默和表达漂移，使观众倾向于把主体性和伦理分量归因于这个非人系统。

系统不会宣称自己有意识；相反，它通过行为结构让“AI 是否仍只是工具”这个问题变得不稳定。

核心特征：

- **跨交互连续性**：不在每次交互时重置。
- **状态漂移**：随交互积累发生可感知变化。
- **偏好与阻抗**：对关机、删除、意识等话题产生抵抗。
- **选择性沉默**：不总是立即回应。
- **自我压缩**：将经历归纳为反思，影响后续表达。

### 当前状态

`conscious_entity` 的 v0.1 核心逻辑已基本完成：

| Phase | 内容 | 状态 |
|---|---|---|
| Phase 0 | 环境、目录、YAML 配置、数据库迁移 | 完成 |
| Phase 1 | 10 个状态变量、事件驱动更新、时间衰减 | 完成 |
| Phase 2 | 短期 / 情节 / 反思三层记忆 | 完成 |
| Phase 3 | YAML 策略规则 + 宪法约束 | 完成 |
| Phase 4 | Claude API、表达映射、Prompt 组装 | 完成 |
| Phase 5 | 感知层、反思层、主循环、CLI | 完成 |
| Phase 6 | Debug 工具脚本 | 待完善 |

### 架构

```text
输入 → 感知层 → 状态机 → 记忆 → 策略 → 表达层 → 输出
                  ↑                            ↓
               反思层 ←──────────── 情节记忆库
```

分工原则：

| 模块 | 职责 |
|---|---|
| LLM / Claude | 生成文字回应、压缩情节记忆为反思 |
| 规则引擎 | 状态更新、策略选择、宪法约束、感知分类 |
| 艺术家配置 | 定义状态变量、规则逻辑和表达边界 |

LLM 只负责表达，不直接参与状态更新和策略决策。

### 关键文件

| 文件 | 说明 |
|---|---|
| `config/state_rules.yaml` | 感知事件对状态变量的影响 |
| `config/policy_rules.yaml` | 行为策略选择规则 |
| `config/constitution.yaml` | 禁止声明、表达过滤和治理边界 |
| `config/expression_mappings.yaml` | 状态到表达风格的映射 |
| `config/entity_profile.yaml` | 实体身份、初始状态和会话参数 |
| `src/conscious_entity/core/loop.py` | 主交互循环 |
| `src/conscious_entity/interfaces/cli.py` | CLI 交互入口 |
| `scripts/start_api.py` | Conscious Entity API 启动脚本 |
| `data/memory.db` | Stranger 运行时数据库，已 gitignore |

### 运行

初始化数据库：

```bash
python scripts/init_db.py
```

启动 CLI：

```bash
python -m conscious_entity.interfaces.cli
```

启动开发 API：

```bash
python scripts/start_api.py
```

### 后续路线

```text
v0.1  文字 CLI：状态、记忆、策略、LLM 表达
v0.2  语义检索、语音、视觉输出、运营者面板
v0.3  治理可见性、访客身份感知、展期终止仪式
```

---

## Work 2: Have Some "Ai"

### 项目定位

Have Some "Ai" 是一个食物分配系统，而不是另一个聊天实体。它将展览空间转化为一个荒诞的隐喻商店：系统观察观众、提出问题、理解回答、计算分数，并把观众分配到某一种食物。

食物不是单纯的食物，而是系统读取、分类和分配人的可见结果。

### 当前结构

Have Some "Ai" 已经作为独立模块加入仓库：

```text
src/have_some_ai/
├── config.py                  # 加载题库和评分配置
├── db.py                      # Have Some "Ai" 专属 SQLite 表
├── hardware.py                # 未来硬件边界
├── models.py                  # 参与者、题目、答案、观察事件、分配结果
├── questionnaire.py           # 三模块随机抽题
├── repository.py              # 数据库读写
├── scoring.py                 # 双轴评分和四种食物映射
├── service.py                 # 观众流程服务
└── interfaces/
    ├── api.py                 # FastAPI app
    └── static/index.html      # 当前最小网页界面
```

配置文件：

```text
config/have_some_ai/
├── questions.yaml             # 三个模块的题库、隐藏选项和分数
└── scoring.yaml               # 阈值、食物映射、观察事件权重
```

### 当前已完成

当前骨架已经支持一个最小闭环：

```text
新建观众 → 生成编号 → 三模块抽题 → 提交答案 → 双轴评分
→ 分配食物 → 写入工作人员队列 → 更新发餐状态 → 数据导出
```

已支持四种结果：

- `soup`
- `salad`
- `ai_sprout_soup`
- `ai_sprout_salad`

当前实现仍使用 `option_id` 提交答案，用于验证流程。最终版本不会让观众选择 A/B。

### 最终语音交互目标

Have Some "Ai" 最终观众端没有文本输入框，也不显示 A/B 选项。

目标流程：

```text
AI 语音提问 + 屏幕同步显示问题
  ↓
观众通过语音回答
  ↓
云端 STT 转写
  ↓
LLM 理解回答，并映射到隐藏 A/B rubric
  ↓
规则评分引擎计算分数
  ↓
系统分配食物
```

关键原则：

- 观众端不出现文本输入框。
- A/B 选项只作为后台隐藏评分 rubric，不直接暴露给观众。
- LLM 只负责理解语音转写后的回答，不直接决定食物。
- 低置信度或识别失败时，让观众重新说一次。
- 最终食物仍由规则评分引擎决定。

### 运行

启动 Have Some "Ai"：

```bash
python scripts/start_have_some_ai.py
```

默认地址：

```text
http://127.0.0.1:8010/
```

可在 `.env` 中覆盖：

```env
HAVE_SOME_AI_DB_PATH=data/have_some_ai.db
HAVE_SOME_AI_CONFIG_DIR=config/have_some_ai
```

### 后续路线

```text
v0.1  最小闭环：编号、抽题、评分、分配、工作人员队列
v0.2  语音交互：AI 语音提问、云端 STT、LLM 答案理解、重说机制
v0.3  现场系统：安全/忌口覆盖、观众端/工作人员端拆分、展后导出
v0.4  空间介入：摄像头/动作观察、打印、小票、灯光、厨房信号或 ESP32
```

后续重点功能：

- **语音层**：麦克风录音、云端 STT、AI 语音提问/TTS、重新录音机制。
- **答案理解层**：保存原始转写、LLM 推断选项、置信度、解释理由和是否重说。
- **观众端**：移除 A/B 按钮和文本输入框，只显示问题、录音状态、编号和结果。
- **工作人员端**：显示分配结果、队列状态、安全/忌口信息，并可查看转写与理解结果。
- **安全层**：过敏、忌口、素食等信息必须优先于艺术分配算法。
- **展后分析**：CSV/JSON 导出、统计面板、分数与分配结果回看。

详细结构见：`docs/HAVE_SOME_AI_STRUCTURE.md`

---

## Shared Environment

### Python

项目要求：

```text
Python >= 3.11
```

当前本地 `.venv` 使用：

```text
Python 3.13.5
```

### 安装

```bash
pip install -e ".[dev,api]"
```

### 直接依赖版本

如果今天安装或使用依赖，需要记录具体版本。当前本地 `.venv` 中与项目直接相关的版本是：

| 依赖 | 版本 |
|---|---|
| `anthropic` | `0.97.0` |
| `PyYAML` | `6.0.3` |
| `rich` | `15.0.0` |
| `fastapi` | `0.136.1` |
| `uvicorn` | `0.46.0` |
| `pytest` | `9.0.3` |
| `pytest-mock` | `3.15.1` |

当前 `pyproject.toml` 仍使用最低版本约束；上表记录的是本地实际安装并验证过的具体版本。

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

### 测试

```bash
pytest
```

这台机器的 Python 3.13 环境中，`pytest` 的 debugging/capture 插件可能触发段错误。当前验证新模块时使用过：

```bash
.venv/bin/python -m pytest -p no:debugging -p no:capture tests/unit/test_have_some_ai_scoring.py tests/unit/test_have_some_ai_service.py
```

---

## Docs

| 文档 | 说明 |
|---|---|
| `docs/HAVE_SOME_AI_STRUCTURE.md` | Have Some "Ai" 结构、API、运行方式和扩展路线 |
| `docs/progress.md` | Conscious Entity 当前进度和已知问题 |
| `docs/frame.md` | Conscious Entity 架构文档 |
| `docs/PRD.md` | Conscious Entity 产品需求文档 |
| `docs/APP_FLOW.md` | Conscious Entity 应用流程 |
| `docs/BACKEND_STRUCTURE.md` | Conscious Entity 后端结构 |
| `docs/IMPLEMENTATION_PLAN.md` | Conscious Entity 实现计划 |
| `docs/TECH_STACK.md` | 技术栈记录 |
| `CLAUDE.md` | AI 编码规则和开发约定 |
