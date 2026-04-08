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

---

## 下一步

- [ ] **Phase 6：Debug 工具** — `scripts/inspect_state.py`、`scripts/replay_session.py`、`scripts/export_memories.py`

---

## 已知问题 / 待确认事项

| 项目 | 状态 | 影响 |
|---|---|---|
| 访客身份识别方式 | 待确认（v0.3） | 影响 BACKEND_STRUCTURE 中 visitor_id 字段设计 |
| 视觉风格 / 设计语言 | 待确认 | 影响 FRONTEND_GUIDELINES + 展览界面开发 |
| 前端技术选型 | 待确认 | 影响 v0.2 开发路径 |
| 展期终止仪式设计 | 待确认 | 影响 v0.3 功能范围 |
| 运营者面板访问方式 | 待确认 | 影响 FastAPI 部署配置 |
| TTS 具体选型 | 待确认 | 影响 v0.2 语音输出实现 |

---

## 当前重点

完成 v0.1 核心逻辑（Phase 0 → Phase 6），优先顺序：

```
Phase 0（环境）→ Phase 1（状态机）→ Phase 2（记忆）
→ Phase 3（策略）→ Phase 4（LLM）→ Phase 5（主循环）→ Phase 6（Debug 工具）
```
