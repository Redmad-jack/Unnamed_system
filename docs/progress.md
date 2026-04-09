# Progress

*Conscious Entity System*

---

## 已完成

- [x] `data/initial_conscious_entity_framework.md` — 原始提案（v0.1）
- [x] `docs/frame.md` — 完整架构技术文档（目录结构、模块接口、YAML schema、SQLite 建表、开发路线图、测试策略）
- [x] 需求调研（interrogation 阶段）— 明确用户、场景、记忆持久性、访客身份策略、运营者需求
- [x] 项目文档环境建设：
  - [x] `docs/PRD.md`
  - [x] `docs/APP_FLOW.md`
  - [x] `docs/TECH_STACK.md`
  - [x] `docs/FRONTEND_GUIDELINES.md`
  - [x] `docs/BACKEND_STRUCTURE.md`
  - [x] `docs/IMPLEMENTATION_PLAN.md`
  - [x] `CLAUDE.md`
  - [x] `docs/progress.md`
  - [x] `docs/lessons.md`
- [x] **Phase 0：环境搭建** — `pyproject.toml`、目录结构、5 个 YAML 配置文件、`prompts/`、`config_loader.py`、`db/migrations.py`、`tests/conftest.py`
- [x] **Phase 1：状态机核心**
  - [x] `src/conscious_entity/perception/event_types.py` — EventType + PerceptionEvent
  - [x] `src/conscious_entity/db/connection.py` — SQLite 连接管理（WAL + foreign keys）
  - [x] `scripts/init_db.py` — 数据库初始化脚本
  - [x] `src/conscious_entity/state/state_core.py` — EntityState dataclass
  - [x] `src/conscious_entity/state/state_engine.py` — 事件驱动状态更新 + 时间衰减
  - [x] `src/conscious_entity/state/state_store.py` — SQLite 快照持久化
  - [x] `tests/unit/test_state_engine.py` — 31 个单元测试全绿

---

## 进行中

- 无

- [x] **Phase 2：记忆系统**
  - [x] `src/conscious_entity/memory/models.py` — ShortTermEntry, EpisodicMemory, ReflectiveSummary
  - [x] `src/conscious_entity/memory/short_term.py` — ShortTermMemory（deque + count_repetitions）
  - [x] `src/conscious_entity/memory/episodic_store.py` — store / get_recent / get_unreflected / mark_reflected
  - [x] `src/conscious_entity/memory/reflective_store.py` — store / get_all / mark_superseded
  - [x] `tests/unit/test_short_term_memory.py` — 11 个单元测试全绿
  - [x] `tests/integration/test_episodic_store.py` — 11 个集成测试全绿（含 ReflectiveStore）

---

- [x] **Phase 3：策略与治理**
  - [x] `src/conscious_entity/policy/policy_types.py` — PolicyAction enum + PolicyDecision dataclass + action_level 排序
  - [x] `src/conscious_entity/policy/constitution.py` — action veto (check) + text post-filter (apply_expression_constraints) + forbidden_claim_detected
  - [x] `src/conscious_entity/policy/policy_selector.py` — 逐条匹配 policy_rules.yaml，Constitution 依赖注入，rationale 追踪
  - [x] `tests/unit/test_constitution.py` — 23 个单元测试全绿
  - [x] `tests/unit/test_policy_selector.py` — 22 个单元测试全绿

---

- [x] **Phase 4：LLM 层 + Expression 层**
  - [x] `src/conscious_entity/expression/output_model.py` — ExpressionOutput dataclass
  - [x] `src/conscious_entity/expression/style_mapper.py` — StyleHints + StyleMapper（读 expression_mappings.yaml）
  - [x] `src/conscious_entity/llm/claude_client.py` — Anthropic SDK 唯一接入点（model 可配置）
  - [x] `src/conscious_entity/expression/context_builder.py` — prompt 组装（template 填充 + messages 构建）
  - [x] `src/conscious_entity/expression/expression_engine.py` — 主编排器（silent 短路 + LLM fallback + constitution 后处理）
  - [x] `tests/unit/test_style_mapper.py` — 26 个单元测试全绿
  - [x] `tests/unit/test_context_builder.py` — 21 个 prompt contract 测试全绿

---

- [x] **Phase 5：感知层 + 反思层 + 主循环 + CLI**
  - [x] `src/conscious_entity/perception/keyword_detector.py` — 关键词检测（word boundary regex，CJK 兼容）
  - [x] `src/conscious_entity/perception/salience_scorer.py` — 规则驱动显著度评分（含 sensitivity/repetition boost）
  - [x] `src/conscious_entity/perception/text_parser.py` — 文本 → PerceptionEvent 列表
  - [x] `src/conscious_entity/reflection/compression_rules.py` — 反思触发阈值判断
  - [x] `src/conscious_entity/reflection/reflection_engine.py` — LLM 情节记忆压缩 + 存储
  - [x] `src/conscious_entity/core/event_bus.py` — 同步 EventBus（v0.3 治理面板预留接口）
  - [x] `src/conscious_entity/core/loop.py` — InteractionLoop（11步管道 + handle_system_event）
  - [x] `src/conscious_entity/interfaces/cli.py` — 终端 REPL（`--debug` 显示 state）
  - [x] `tests/unit/test_salience_scorer.py` — 13 个单元测试全绿
  - [x] `tests/integration/test_full_loop.py` — 20 个集成测试全绿（mocked LLM）
  - [x] CLI 冒烟测试通过（真实 API 响应正常）

- [x] **2026-04-09：供应商 Anthropic 兼容 API 接入**
  - [x] `src/conscious_entity/llm/claude_client.py` — 扩展为同时支持官方 `ANTHROPIC_API_KEY` 与供应商 `ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL + ENTITY_LLM_MODEL`
  - [x] `src/conscious_entity/runtime_env.py` — 新增项目级 `.env` 自动加载，默认不覆盖 shell 环境变量
  - [x] `src/conscious_entity/interfaces/cli.py` — 启动前加载 `.env` 并显式校验 LLM 配置，避免首轮对话才失败
  - [x] `scripts/init_db.py`
  - [x] `scripts/inspect_state.py`
  - [x] `scripts/replay_session.py`
  - [x] `scripts/export_memories.py`
    - 统一在入口最早阶段加载 `.env`，与 APP_FLOW 中 v0.1 调试脚本路径保持一致
  - [x] `.env.example`
  - [x] `README.md`
  - [x] `docs/TECH_STACK.md`
  - [x] `docs/IMPLEMENTATION_PLAN.md`
    - 文档已更新为“官方 Anthropic / 供应商兼容接口”双模式说明
  - [x] `tests/unit/test_claude_client.py`
  - [x] `tests/unit/test_runtime_env.py`
  - [x] `tests/unit/test_cli.py`
    - 新增 9 个测试，覆盖配置解析、`.env` 加载与 CLI 启动时报错

- [x] **2026-04-09：非标准供应商 messages endpoint 兼容**
  - [x] `src/conscious_entity/llm/claude_client.py`
    - 新增 `ENTITY_LLM_MESSAGES_ENDPOINT` 支持
    - 保留标准 Anthropic SDK 模式，同时支持直接 POST 到完整消息接口
    - 增加非标准响应解析兜底：Anthropic `content[].text`、`output_text`、`choices[0].message.content`、纯文本 body
  - [x] `.env.example`
  - [x] `README.md`
  - [x] `tests/unit/test_claude_client.py`
    - 新增自定义 endpoint 模式测试，覆盖 Bearer / X-Api-Key 认证和响应解析分支

---

## 下一步

- [ ] **Phase 6：Debug 工具** — `scripts/inspect_state.py`、`scripts/replay_session.py`、`scripts/export_memories.py`
- [ ] 使用已轮换的真实供应商凭证做一轮 CLI 联调，确认自定义模型名与网关鉴权在目标环境可用

---

## 本次 API 接入说明（2026-04-09）

### 1. 修改了哪些文件

- `src/conscious_entity/llm/claude_client.py`
- `src/conscious_entity/runtime_env.py`
- `src/conscious_entity/interfaces/cli.py`
- `src/conscious_entity/core/config_loader.py`
- `scripts/init_db.py`
- `scripts/inspect_state.py`
- `scripts/replay_session.py`
- `scripts/export_memories.py`
- `.env.example`
- `README.md`
- `docs/TECH_STACK.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `tests/unit/test_claude_client.py`
- `tests/unit/test_runtime_env.py`
- `tests/unit/test_cli.py`

### 2. 为什么这样改

- 根据 `docs/frame.md` 的架构边界，LLM 只负责表达与压缩，因此接入改动集中在 `ClaudeClient` 这一唯一外部调用点，不改状态机、记忆、策略逻辑。
- 根据 `docs/APP_FLOW.md` 的启动与调试脚本路径，CLI 和 `scripts/*.py` 都需要在最早阶段拿到一致的环境变量，因此增加项目级 `.env` 自动加载。
- 供应商接口需要 `base_url`、鉴权 token 和自定义模型名，所以新增 `ENTITY_LLM_MODEL`，并把配置校验前置到 CLI 启动阶段。
- 官方 Anthropic 直连模式仍需保留，避免破坏现有 `ANTHROPIC_API_KEY` 使用方式。
- README / TECH_STACK / IMPLEMENTATION_PLAN 同步更新，避免文档继续误导为“只能用官方 API Key”。

### 3. 如何手动测试

- 在项目根目录创建 `.env`，二选一配置：
  - 官方模式：`ANTHROPIC_API_KEY=...`
  - 供应商模式：`ANTHROPIC_AUTH_TOKEN=...`、`ANTHROPIC_BASE_URL=...`、`ENTITY_LLM_MODEL=...`
- 初始化数据库：
  - `python scripts/init_db.py`
- 启动 CLI：
  - `python -m conscious_entity.interfaces.cli --debug`
- 在 CLI 中输入一轮消息，确认返回真实文本而不是 fallback 文本 `Something is here. I am attending.` 这一类兜底回应。
- 验证调试脚本也能读取同一套 `.env`：
  - `python scripts/inspect_state.py`
  - `python scripts/replay_session.py`
  - `python scripts/export_memories.py --output data/export.json`
- 已通过的自动化验证：
  - `PYTHONPATH=src python -m pytest -p no:debugging tests/unit/test_claude_client.py tests/unit/test_runtime_env.py tests/unit/test_cli.py`
  - `PYTHONPATH=src python -m pytest -p no:debugging tests/integration/test_full_loop.py`

### 4. 是否有潜在风险

- 还没有使用真实供应商接口做联网联调；目前验证的是配置解析、启动行为和 mocked integration，真实网关仍需一轮手工确认。
- 供应商若不完全兼容 Anthropic SDK 的 `auth_token` / `base_url` 语义，可能会在真实请求阶段报认证或路由错误。
- 自定义模型名 `ENTITY_LLM_MODEL` 如果填写错误，CLI 能启动，但首次真实调用时仍会失败并走 fallback。
- 用户之前暴露过一把 API key；即使本次未写入代码，也应先轮换再测试。
- 即使启用了 `ENTITY_LLM_MESSAGES_ENDPOINT`，如果供应商连请求体字段名也不是 Anthropic Messages 格式，仍然需要进一步做协议映射。

## 已知问题 / 待确认事项

| 项目 | 状态 | 影响 |
|---|---|---|
| 访客身份识别方式 | 待确认（v0.3） | 影响 BACKEND_STRUCTURE 中 visitor_id 字段设计 |
| 视觉风格 / 设计语言 | 待确认 | 影响 FRONTEND_GUIDELINES + 展览界面开发 |
| 前端技术选型 | 待确认 | 影响 v0.2 开发路径 |
| 展期终止仪式设计 | 待确认 | 影响 v0.3 功能范围 |
| 运营者面板访问方式 | 待确认 | 影响 FastAPI 部署配置 |
| TTS 具体选型 | 待确认 | 影响 v0.2 语音输出实现 |
| 供应商 Anthropic 兼容接口联调 | 待完成 | 影响真实 CLI 输出是否能走供应商网关而不是 fallback |

---

## 当前重点

完成 v0.1 核心逻辑（Phase 0 → Phase 6），优先顺序：

```
Phase 0（环境）→ Phase 1（状态机）→ Phase 2（记忆）
→ Phase 3（策略）→ Phase 4（LLM）→ Phase 5（主循环）→ Phase 6（Debug 工具）
```
