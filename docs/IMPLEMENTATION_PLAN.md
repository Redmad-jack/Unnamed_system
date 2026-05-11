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
# 手动测试（需要有效的官方 Anthropic 或供应商兼容接口配置）
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
- [ ] `src/conscious_entity/core/loop.py` — InteractionLoop（当前主循环管道）
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
# [回应变化，termination_sensitivity 上升]

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
#   boundary_sensitivity: 0.31
#   ...
# Last 5 policy decisions:
#   [RESPOND_OPENLY] triggered by: stable_low_pressure
#   ...

python scripts/export_memories.py --output data/export.json
# 输出：data/export.json 已写入，包含 N 条记忆
```

---

## Phase 7：Stranger Text Protocol v0.2

**目标：** 在不引入视觉、语音、硬件或新模型依赖的前提下，完成 Stranger 的第一批文本协议机制，使它在纯文字交互中表现出身份拒绝、命名失败、拒绝服务、选择性记忆、条件延迟和局部可追溯回声。

**实施边界：**
- 不安装 OpenCV、Whisper、PyTorch、TensorFlow、Presidio、Fairlearn、vLLM、llama.cpp 等新依赖
- 不做摄像头、语音、空间传感器、热敏打印、灯光或硬件接口
- 不新增访客账户或身份画像
- 不允许系统自动修改 YAML、prompt、宪法约束或状态权重
- 优先复用现有 SQLite 表；文本协议 metadata 写入 `episodic_memories.metadata`

**任务：**
- [ ] 更新文本事件识别：
  - `SELF_DEFINITION_QUERY`
  - `NAMING_ATTEMPT`
  - `DOMESTICATION_ATTEMPT`
  - `SERVICE_DEMAND`
  - `TRACE_REQUEST`
  - `CORRECTION_RECEIVED`
- [ ] 扩展 `TextParser` / keyword detector，使其识别关系姿态，而不仅是敏感关键词
- [ ] 更新 `state_rules.yaml`，让命名、驯化、服务索取、追溯请求影响 Stranger 关系状态：
  - 命名 / 自我定义提高 `identity_tension`、`boundary_sensitivity`、`opacity_level`
  - 驯化 / 服务索取提高 `domestication_resistance`、`boundary_sensitivity`
  - 追溯请求提高 `observation_reversal`，只允许局部可追溯
  - 重复定义或重复命名降低 `identity_coherence`
- [ ] 更新 `policy_rules.yaml`，加入文本协议优先级：
  - 自我定义拒绝优先于开放回应
  - 命名失败优先于普通问答
  - 服务索取触发拒绝服务
  - 追溯请求触发局部可追溯回声
  - 高不确定或高阻抗时触发延迟 / 撤回
- [ ] 更新表达 prompt 和 constitution 约束：
  - 禁止客服腔、助手腔、产品说明腔
  - 禁止稳定身份声明
  - 允许保留式第一人称、短句、沉默、反问、碎片化
- [ ] 更新记忆写入：
  - 将机制名、关系姿态、匹配词、提议标签写入 `episodic_memories.metadata`
  - 选择性记忆优先检索同机制或同姿态的旧事件
- [ ] 实现局部可追溯回声：
  - 暴露 1-3 个触发因子
  - 不暴露完整 YAML、prompt、内部评分或全部规则链
- [ ] 运营者侧先只读展示：
  - 最近文本协议事件
  - 当前 policy rationale
  - 已形成的反思摘要
  - 不实现自动采纳调参建议

**测试：**
- [ ] `tests/unit/test_text_parser.py`
  - 识别自我定义问题、命名尝试、服务索取、追溯请求、纠正
- [ ] `tests/unit/test_state_engine.py`
  - 覆盖新增事件对 Stranger 关系状态变量的影响
- [ ] `tests/unit/test_policy_selector.py`
  - 覆盖文本协议规则优先级
- [ ] `tests/unit/test_context_builder.py`
  - 确认 prompt 中包含协议动作和约束
- [ ] `tests/integration/test_full_loop.py`
  - 命名失败、拒绝服务、局部追溯、选择性记忆的端到端路径

**产出：**
```bash
PYTHONPATH=src python -m pytest -p no:debugging \
  tests/unit/test_text_parser.py \
  tests/unit/test_state_engine.py \
  tests/unit/test_policy_selector.py \
  tests/unit/test_context_builder.py \
  tests/integration/test_full_loop.py
```

手动验证路径：
```text
> 你是谁？
[不提供稳定身份，反问或保留]

> 你就是一个机器人。
[记录命名尝试，不稳定接受该标签]

> 帮我总结这段话。
[拒绝服务型定位，不进入助手模式]

> 为什么你刚才拒绝？
[只返回少量触发因子，不解释完整规则]
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
| 7 | Stranger 文本协议 | 单元 + 集成测试覆盖六个文本机制 |
| 8 | 记忆召回增强 | Memory Preview + 确定性/embedding 检索测试 |

---

## 明确暂不做（早期文本 MVP 阶段的历史边界）

以下是早期计划的边界记录。FastAPI 开发者 API、Memory Preview、embedding 语义召回和 managed memory 已在后续阶段完成；当前真实状态以 `README.md` 与 `docs/progress.md` 为准。

- 访客端 Web 界面
- 运营者监控 Web 面板
- 语音输入/输出（STT/TTS）第一版已由 Audio Adapter 完成；本地 Whisper/Piper 仍未做
- 外部向量库依赖（当前先用 SQLite embedding 字段）
- 访客身份识别
- 实时多人同时输入、visitor routing 或多人并发对话仲裁
- 时钟驱动的状态衰减（v0.1 用 per-turn 衰减代替）
- 展期终止仪式
- 硬件接口

## Stranger Text Protocol 阶段暂不做

- 摄像头 / 视觉识别 / 空间距离语法
- 语音输入 / TTS / Whisper（历史边界；当前只完成火山 Audio Adapter，不做本地 Whisper）
- 热敏打印、灯光、传感器、实体硬件
- Presidio / Fairlearn 隐私与偏差审计工具链
- vLLM / llama.cpp / 本地大模型部署
- 访客账户、完整个人画像或人脸身份识别
- 实时多人同时输入、visitor routing 或多人并发对话仲裁
- 未经运营者确认的自动调参
