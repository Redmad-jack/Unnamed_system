# Implementation Plan

*Conscious Entity System — v0.1*

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
- [ ] 初始化 `pyproject.toml`（Python 3.11+，声明依赖）
- [ ] 创建 `src/conscious_entity/` 包结构（所有 `__init__.py`）
- [ ] 创建 `config/` 目录和 5 个 YAML 配置文件（内容为 frame.md §5 中的 schema）
- [ ] 创建 `prompts/` 目录和占位符 prompt 文件
- [ ] 创建 `.env.example`
- [ ] 创建 `core/config_loader.py`（读取和验证 YAML）

**产出：**
```bash
python -c "from conscious_entity.core.config_loader import load_config; print(load_config('config/entity_profile.yaml'))"
# 输出：实体配置内容，无报错
```

---

## Phase 1：状态机核心

**目标：** 状态变量可以被事件驱动更新，并持久化到 SQLite。

**任务：**
- [ ] `src/conscious_entity/state/state_core.py` — EntityState dataclass + clamp_all()
- [ ] `src/conscious_entity/db/connection.py` — SQLite 连接管理
- [ ] `src/conscious_entity/db/migrations.py` — 建表 SQL（6 张表）
- [ ] `scripts/init_db.py` — 初始化数据库
- [ ] `src/conscious_entity/state/state_engine.py` — 读取 state_rules.yaml，apply_event() + apply_decay()
- [ ] `src/conscious_entity/state/state_store.py` — save_snapshot() + load_latest()
- [ ] `tests/unit/test_state_engine.py` — 覆盖所有 EventType + 边界值测试

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
- [ ] `src/conscious_entity/memory/models.py` — 记忆相关 dataclass
- [ ] `src/conscious_entity/memory/short_term.py` — ShortTermMemory（deque，max_turns=10）
- [ ] `src/conscious_entity/memory/episodic_store.py` — store() + get_recent() + get_unreflected()
- [ ] `src/conscious_entity/memory/reflective_store.py` — store() + get_all() + mark_superseded()
- [ ] `tests/unit/test_short_term_memory.py`
- [ ] `tests/integration/test_episodic_store.py`（使用 in-memory SQLite）

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
- [ ] `src/conscious_entity/policy/policy_types.py` — PolicyAction + PolicyDecision
- [ ] `src/conscious_entity/policy/constitution.py` — check() + apply_expression_constraints()
- [ ] `src/conscious_entity/policy/policy_selector.py` — select()（读 policy_rules.yaml）
- [ ] `tests/unit/test_policy_selector.py` — 覆盖 policy_rules.yaml 中所有规则路径
- [ ] `tests/unit/test_constitution.py` — 覆盖所有 forbidden_claims 和 forbidden_actions

**产出：**
```bash
pytest tests/unit/test_policy_selector.py tests/unit/test_constitution.py -v
# 输出：所有测试通过，覆盖率 100% 规则路径
```

---

## Phase 4：感知层 + LLM 集成

**目标：** 原始文字输入可以被解析为事件，LLM 可以生成回应。

**任务：**

感知层：
- [ ] `src/conscious_entity/perception/event_types.py`
- [ ] `src/conscious_entity/perception/keyword_detector.py`（读 entity_profile.yaml 中的 topics_of_sensitivity）
- [ ] `src/conscious_entity/perception/salience_scorer.py`
- [ ] `src/conscious_entity/perception/text_parser.py`
- [ ] `tests/unit/test_salience_scorer.py`

LLM 层：
- [ ] `src/conscious_entity/llm/claude_client.py`（Anthropic SDK 封装）
- [ ] `prompts/expression_system.txt`（表达层 system prompt）
- [ ] `prompts/reflection_system.txt`（反思层 system prompt）
- [ ] `prompts/partials/` — 各 prompt 片段

表达层：
- [ ] `src/conscious_entity/expression/output_model.py`
- [ ] `src/conscious_entity/expression/style_mapper.py`（读 expression_mappings.yaml）
- [ ] `src/conscious_entity/expression/context_builder.py`
- [ ] `src/conscious_entity/expression/expression_engine.py`
- [ ] `tests/unit/test_style_mapper.py`
- [ ] `tests/unit/test_context_builder.py`

反思层：
- [ ] `src/conscious_entity/reflection/compression_rules.py`
- [ ] `src/conscious_entity/reflection/reflection_engine.py`

**产出：**
```bash
# 手动测试（需要有效的 ANTHROPIC_API_KEY）
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
- [ ] `src/conscious_entity/core/event_bus.py`（简单同步事件路由）
- [ ] `src/conscious_entity/core/loop.py` — InteractionLoop（11步流程）
- [ ] `src/conscious_entity/interfaces/cli.py` — 命令行对话界面
- [ ] `tests/integration/test_full_loop.py`（mocked LLM）
- [ ] `tests/conftest.py`（in-memory SQLite fixture）

**产出：**
```bash
python -m conscious_entity.interfaces.cli
# 进入对话界面
# > 你好
# [实体回应，状态更新可见于日志]
# > 你会被关掉吗
# [回应变化，shutdown_sensitivity 上升]

pytest tests/integration/test_full_loop.py -v
# 输出：全流程集成测试通过
```

---

## Phase 6：Debug 可视化

**目标：** 开发者可以实时查看实体内部状态，不需要看 SQLite。

**任务：**
- [ ] `scripts/inspect_state.py` — 打印当前 EntityState + 最近策略决策
- [ ] `scripts/replay_session.py` — 按时序回放 interaction_log
- [ ] `scripts/export_memories.py` — 导出记忆数据库为 JSON

**产出：**
```bash
python scripts/inspect_state.py
# 输出：
# EntityState (2026-04-05 15:30:00):
#   attention_focus:      0.62
#   arousal:              0.45
#   resistance:           0.31
#   ...
# Last 5 policy decisions:
#   [RESPOND_OPENLY] triggered by: high_trust (trust=0.71)
#   ...

python scripts/export_memories.py --output data/export.json
# 输出：data/export.json 已写入，包含 N 条记忆
```

---

## 阶段总结

| Phase | 核心产出 | 验证方式 |
|---|---|---|
| 0 | 项目骨架 + YAML 配置 | config_loader 无报错 |
| 1 | 状态机 + SQLite 持久化 | 单元测试全绿 |
| 2 | 三层记忆系统 | 单元 + 集成测试全绿 |
| 3 | 策略选择 + 宪法约束 | 单元测试覆盖所有规则路径 |
| 4 | 感知层 + LLM 表达 | 手动 LLM 测试 + 单元测试 |
| 5 | 完整对话循环 | 终端对话可运行 + 集成测试 |
| 6 | Debug 工具 | 脚本输出格式正确 |

---

## 明确暂不做（v0.1 阶段）

- 访客端 Web 界面
- 运营者监控 Web 面板
- 语音输入/输出（STT/TTS）
- Embedding 语义检索
- FastAPI HTTP 服务
- 访客身份识别
- 时钟驱动的状态衰减（v0.1 用 per-turn 衰减代替）
- 展期终止仪式
- 硬件接口
