# Implementation Plan

Conscious Entity System — v0.1（已全部完成）

---

## 原则

- 每个阶段结束必须有可执行的验证指令，不靠感觉判断完成度
- 每个阶段只做该阶段的内容，不提前实现后续阶段的功能
- Rule-based 组件必须先有单元测试，再有实现
- 不安装该阶段不需要的依赖

---

## Phase 0：环境搭建

**目标：** 项目可以被克隆并运行，所有开发工具就位。

**任务：**

- [x] 初始化 `pyproject.toml`（Python 3.11+，声明依赖）
- [x] 创建 `src/conscious_entity/` 包结构（所有 `__init__.py`）
- [x] 创建 `config/` 目录和 5 个 YAML 配置文件（内容为 frame.md §5 中的 schema）
- [x] 创建 `prompts/` 目录和占位符 prompt 文件
- [x] 创建 `.env.example`
- [x] 创建 `core/config_loader.py`（读取和验证 YAML）

**产出：**

```bash
python -c "from conscious_entity.core.config_loader import load_config; print(load_config('config/entity_profile.yaml'))"
# 输出：实体配置内容，无报错
```

---

## Phase 1：状态机核心

**目标：** 状态变量可以被事件驱动更新，并持久化到 SQLite。

**任务：**

- [x] `src/conscious_entity/state/state_core.py` — EntityState dataclass + clamp_all()
- [x] `src/conscious_entity/db/connection.py` — SQLite 连接管理
- [x] `src/conscious_entity/db/migrations.py` — 建表 SQL（6 张表）
- [x] `scripts/init_db.py` — 初始化数据库
- [x] `src/conscious_entity/state/state_engine.py` — 读取 state_rules.yaml，apply_event() + apply_decay()
- [x] `src/conscious_entity/state/state_store.py` — save_snapshot() + load_latest()
- [x] `tests/unit/test_state_engine.py` — 覆盖所有 EventType + 边界值测试

**产出：**

```bash
python scripts/init_db.py
# 输出：Database initialized at data/memory.db

pytest tests/unit/test_state_engine.py -v
# 输出：所有测试通过
```

---

## Phase 2：记忆系统

**目标：** 短期记忆和情节记忆可以写入和读取。

**任务：**

- [x] `src/conscious_entity/memory/models.py` — 记忆相关 dataclass
- [x] `src/conscious_entity/memory/short_term.py` — ShortTermMemory（deque，max_turns=10）
- [x] `src/conscious_entity/memory/episodic_store.py` — store() + get_recent() + get_unreflected()
- [x] `src/conscious_entity/memory/reflective_store.py` — store() + get_all() + mark_superseded()
- [x] `tests/unit/test_short_term_memory.py`
- [x] `tests/integration/test_episodic_store.py`（使用 in-memory SQLite）

**暂不实现：**

- 语义检索（v0.2）
- ReflectiveStore 的 embedding 字段（留空即可）

**产出：**

```bash
pytest tests/unit/test_short_term_memory.py tests/integration/test_episodic_store.py -v
# 输出：所有测试通过
```

---

## Phase 3：策略与治理

**目标：** 给定状态和事件，策略层能正确选择动作，宪法约束能正确拦截违规。

**任务：**

- [x] `src/conscious_entity/policy/policy_types.py` — PolicyAction + PolicyDecision
- [x] `src/conscious_entity/policy/constitution.py` — check() + apply_expression_constraints()
- [x] `src/conscious_entity/policy/policy_selector.py` — select()（读 policy_rules.yaml）
- [x] `tests/unit/test_policy_selector.py` — 覆盖 policy_rules.yaml 中所有规则路径
- [x] `tests/unit/test_constitution.py` — 覆盖所有 forbidden_claims 和 forbidden_actions

**产出：**

```bash
pytest tests/unit/test_policy_selector.py tests/unit/test_constitution.py -v
# 输出：所有测试通过，覆盖率 100% 规则路径
```

---

## Phase 4：感知层 + LLM 集成

**目标：** 原始文字输入可以被解析为事件，LLM 可以生成回应。

**感知层任务：**

- [x] `src/conscious_entity/perception/event_types.py`
- [x] `src/conscious_entity/perception/keyword_detector.py`
- [x] `src/conscious_entity/perception/salience_scorer.py`
- [x] `src/conscious_entity/perception/text_parser.py`
- [x] `tests/unit/test_salience_scorer.py`

**LLM 层任务：**

- [x] `src/conscious_entity/llm/claude_client.py`（Anthropic SDK 封装）
- [x] `prompts/expression_system.txt`（表达层 system prompt）
- [x] `prompts/reflection_system.txt`（反思层 system prompt）

**表达层任务：**

- [x] `src/conscious_entity/expression/output_model.py`
- [x] `src/conscious_entity/expression/style_mapper.py`
- [x] `src/conscious_entity/expression/context_builder.py`
- [x] `src/conscious_entity/expression/expression_engine.py`
- [x] `tests/unit/test_style_mapper.py`
- [x] `tests/unit/test_context_builder.py`

**反思层任务：**

- [x] `src/conscious_entity/reflection/compression_rules.py`
- [x] `src/conscious_entity/reflection/reflection_engine.py`

**产出：**

```bash
python -c "
from conscious_entity.llm.claude_client import ClaudeClient
client = ClaudeClient()
print(client.complete('Say hello briefly.'))
"
# 输出：Claude 的简短回应

pytest tests/unit/ -v
# 输出：所有单元测试通过
```

---

## Phase 5：主循环 + CLI

**目标：** 可以通过终端进行一次完整对话，观察状态变化。

**任务：**

- [x] `src/conscious_entity/core/event_bus.py`（简单同步事件路由）
- [x] `src/conscious_entity/core/loop.py` — InteractionLoop（11步流程）
- [x] `src/conscious_entity/interfaces/cli.py` — 命令行对话界面
- [x] `tests/integration/test_full_loop.py`（mocked LLM）
- [x] `tests/conftest.py`（in-memory SQLite fixture）

**产出：**

```bash
python -m conscious_entity.interfaces.cli
# 进入对话界面
# > 你好
# [实体回应，状态更新可见于日志]

pytest tests/integration/test_full_loop.py -v
# 输出：全流程集成测试通过
```

---

## Phase 6：Debug 工具 + 开发者 API

**目标：** 开发者可以实时查看实体内部状态；HTTP API 供 Web 看板和外部工具调用。

**Debug 工具任务：**

- [x] `scripts/inspect_state.py` — rich 美化（Panel + 进度条 + 策略决策表格）
- [x] `scripts/monitor.py` — 实时 TUI 看板（rich.live，2s 轮询，四栏布局）
- [x] `scripts/test_llm.py` — LLM 连通性测试（配置展示 + 延迟测量）
- [x] `scripts/replay_session.py` — 按时序回放 interaction_log
- [x] `scripts/export_memories.py` — 导出记忆数据库为 JSON

**开发者 API 任务：**

- [x] `src/conscious_entity/llm/stats_tracker.py` — LLM 调用统计单例
- [x] `src/conscious_entity/interfaces/api.py` — FastAPI app（11 个端点）
- [x] `src/conscious_entity/interfaces/static/index.html` — Web 看板
- [x] `scripts/start_api.py` — uvicorn 启动脚本

**产出：**

```bash
python scripts/inspect_state.py
# 输出：EntityState 面板 + 最近策略决策

python scripts/export_memories.py --output data/export.json
# 输出：data/export.json 已写入

python scripts/start_api.py
# Dashboard: http://127.0.0.1:8000/
```

---

## 阶段总结

| Phase | 核心产出 | 验证方式 |
| --- | --- | --- |
| 0 | 项目骨架 + YAML 配置 | config_loader 无报错 |
| 1 | 状态机 + SQLite 持久化 | 单元测试全绿 |
| 2 | 三层记忆系统 | 单元 + 集成测试全绿 |
| 3 | 策略选择 + 宪法约束 | 单元测试覆盖所有规则路径 |
| 4 | 感知层 + LLM 表达 | 手动 LLM 测试 + 单元测试 |
| 5 | 完整对话循环 | 终端对话可运行 + 集成测试 |
| 6 | Debug 工具 + 开发者 API | 脚本输出格式正确 + API 响应正常 |

---

## 明确暂不做（v0.1 阶段）

- 访客端展览 Web 界面（运营者 API 的 Web 看板已包含，但访客侧展览界面不在 v0.1）
- 运营者监控独立部署（v0.1 开发者 API 在本地运行）
- 语音输入/输出（STT/TTS）
- Embedding 语义检索
- 访客身份识别
- 展期终止仪式
- 硬件接口
