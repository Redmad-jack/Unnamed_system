# Progress

*Conscious Entity System*

---

## 当前状态

- 当前进行中：无
- 当前可运行形态：CLI + 本地 FastAPI 开发者 API + Web 看板
- 当前核心能力：Stranger 文本协议、状态机、短期/情节/反思记忆、可解释/可选 embedding 召回、Memory Preview、managed memory proposal → commit、influence log / curation
- 当前验证基线：`PYTHONPATH=src python3 -m pytest -p no:debugging`，最近一次结果为 `286 passed`
- 当前注意事项：`AGENTS.md` 与 `CLAUDE.md` 有用户侧未提交差异；除非明确要求，不应在常规任务中触碰

---

## 下一步

- [ ] 使用已轮换的真实供应商凭证做一轮 CLI/API 联调，确认自定义模型名与网关鉴权在目标环境可用
- [ ] 继续观察真实对话中的记忆连续性：Memory Preview 是否能解释召回来源，managed memory influence 是否可审计且不越界
- [ ] 后续视觉层、语音通道、presence / spatial sensing、部署认证与展期终止仪式仍待设计确认

---

## Changelog

### 2026-05-08：Progress 结构归一化

- [x] 将 `docs/progress.md` 归一为四个稳定区域：
  - 当前状态
  - 下一步
  - 倒序 Changelog
  - 历史 Phase 汇总与待确认事项
- [x] 将日期型记录统一放入 Changelog，并按日期倒序排列
- [x] 将早期 Phase 清单从顶部挪到历史汇总，避免与时间线混排

### 2026-05-08：文档时间线同步与 Turn Loop 可读性整理

- [x] 同步 README 与核心文档，移除旧的 “当前 v0.1 / 未来 FastAPI” 叙述：
  - README 改为当前文本系统 + 本地 FastAPI 开发者 API + Memory Preview + Managed Memory 的真实状态
  - TECH_STACK 明确 FastAPI / uvicorn 属于 optional `api` group，语音/视觉依赖仍不进入核心 dependencies
  - APP_FLOW 补齐 managed memory preview、state influence、policy influence、influence log、proposal / auto-commit 的每轮路径
  - BACKEND_STRUCTURE 与 frame.md 对齐 API 拆分、managed memory 影响边界和后续 voice/visual 范围
- [x] 整理 `src/conscious_entity/core/loop.py` 可读性：
  - 更新 class docstring 与 `run_turn()` 注释，不再使用旧的固定步数描述
  - 将 policy influence、memory retrieval 归一化、managed memory propose / auto-commit 三段抽为私有 helper
  - 不改变外部接口、API endpoint、SQLite schema、YAML schema、环境变量或 prompt 位置
- [x] 残留扫描与验证：
  - `PYTHONPATH=src python3 -m py_compile src/conscious_entity/core/loop.py`
  - `rg` 检查旧关键词：无命中
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/integration/test_full_loop.py tests/unit/test_managed_memory.py tests/unit/test_memory_retrieval.py`
  - `40 passed`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `286 passed`

### 2026-05-07：项目结构审查与 API 层拆分

- [x] 审查项目文档与代码结构，确认当前主要残留是文档时间线/架构边界描述未完全跟上代码：
  - README 旧写法仍把 LLM 影响范围限定在表达/反思，已更新为 managed memory proposal → commit 的可审计影响路径
  - BACKEND_STRUCTURE 旧写法仍把 FastAPI / auth / visitor_id 当作预留设计，已更新为当前本地开发 API、未认证状态和后续认证要求
- [x] 拆分原 `src/conscious_entity/interfaces/api.py` 单文件 API：
  - `api.py`：保留 ASGI app 入口与兼容导出
  - `api_models.py`：Pydantic 请求模型
  - `api_runtime.py`：lifespan、runtime 配置、DB helper、loop rebuild
  - `api_routes.py`：HTTP route handlers
- [x] 清理 `src/conscious_entity/core/loop.py` 中已被 `MemoryRetriever` 取代、没有调用点的旧 selective-memory helper
- [x] 测试同步：
  - 更新 `tests/unit/test_api_export.py` 的 monkeypatch 目标到 `api_routes`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_api_export.py tests/unit/test_managed_memory.py tests/unit/test_memory_retrieval.py tests/integration/test_full_loop.py`
  - `53 passed`

### 2026-05-07：Memory Curation 四视图开发者界面补齐

- [x] 右侧 Memory Curation 面板补齐四个视图：
  - Raw Archive：只读展示当前 session 的原始 `interaction_log`、event types、policy action 与输出
  - Proposals：展示 pending / committed / rejected proposal，支持单条批准、拒绝、勾选批量 commit、当前可见批量 commit
  - Managed Memories：按 active / superseded / archived / hidden / all 查看 committed managed memory，支持 explain / edit / archive / restore
  - Influence：提供无写入的 query/context preview，并展示 influence trace log
- [x] 新增 proposal reject API：`POST /api/v1/managed-memory/proposals/{proposal_id}/reject`
- [x] 验证：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_api_export.py tests/unit/test_managed_memory.py`
  - `18 passed`

### 2026-05-06：Mem0-style 可审计 Managed Memory 第一版

- [x] 新增 managed memory 本地 provider：
  - `propose()` 只生成 `memory_operation_proposals`
  - `commit()` 才写入 `managed_memories`
  - `search(..., explain=True)` 返回 managed memory 及召回解释
  - `preview_influence()` 预览 expression / policy / state 影响且不写入
  - `archive()` / `restore()` 补齐可回滚管理路径
- [x] 新增 SQLite 表：`managed_memories`、`memory_operation_proposals`、`memory_operation_log`、`memory_influence_log`，并在可用时创建 `managed_memories_fts`
- [x] 主循环接入 managed memory：
  - 每轮先 preview influence，再应用受限 `memory_gravity` state delta
  - managed memory 可将普通开放策略牵引为选择性记忆策略
  - 每轮结束先 proposal，再按默认 auto-commit 提交
  - influence、operation、proposal 均可审计
- [x] API 增加 managed memory endpoints：
  - proposal / commit
  - list / update / archive / restore / explain
  - preview influence / influence log
- [x] 开发者界面 Memory 区增加 Managed Memory、Proposals、Influence Trace 的最小入口
- [x] 文档更新：
  - `docs/BACKEND_STRUCTURE.md`
  - `docs/TECH_STACK.md`
- [x] 验证：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `285 passed`

### 2026-05-06：服务请求上下文续问与非服务话题转向

- [x] `service_demand` 增加上下文续问规则：上一轮服务请求后，短片段补充（如“历史背景”）继续识别为 `SERVICE_DEMAND`
- [x] `service_demand` metadata 明确：拒绝任务交付，但当话题本身引起内部牵引时，可以转入非服务讨论
- [x] `REFUSE_SERVICE_ROLE` 表达 prompt 调整为：
  - 不完成用户请求的可用任务结果
  - 简短拒绝服务框架
  - 可在有兴趣时讨论话题本身，但不得以助手、搜索工具、教师、写作者或客服身份交付
- [x] 验证：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_text_parser.py tests/unit/test_context_builder.py`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_policy_selector.py tests/integration/test_full_loop.py`

### 2026-05-04：Memory Curation 与右侧栏三标签布局

- [x] 右侧栏改为三标签：
  - `Runtime`：LLM Provider、Embedding Provider、Diagnostics
  - `Embedding`：Memory Curation / 向量管理系统
  - `Session & History`：会话列表、历史详情、导出
- [x] Memory Curation 后端：
  - `GET /api/v1/curation/stats`
  - `GET /api/v1/curation/memories`
  - `POST /api/v1/curation/memories/{memory_type}/{memory_id}/status`
  - `POST /api/v1/curation/memories/{memory_type}/{memory_id}/copy-to-exhibition`
  - `POST /api/v1/curation/memories/{memory_type}/{memory_id}/embedding/refresh`
- [x] 记忆软状态：`active`、`archived`、`hidden`
- [x] 召回层过滤非 active 记忆，hidden / archived 不进入 deterministic 或 hybrid 召回
- [x] 从 test 复制到 exhibition 使用 curated copy：
  - 原 test 记忆保留
  - 目标写入 `curated-exhibition` session
  - 记录 `curated_from_session_id`、`curated_from_memory_id`、`curated_at`
- [x] 新增 `memory_curation_log`，记录状态变更、复制、刷新 embedding 操作
- [x] 真实数据库 migration 已应用：当前 episodic 记忆 `13` 条，均为 `active` 且已 embedding
- [x] 验证：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `274 passed`
  - 本地 API `/api/v1/curation/stats` 与 `/api/v1/curation/memories` 返回正常

### 2026-05-04：Session 标签与同标签跨 session 语义召回

- [x] `sessions` 表新增 `session_type`：`test | exhibition`
- [x] migration 将现有历史 session 默认归为 `test`
- [x] 新 session 默认继承当前 session 的 `session_type`
- [x] 开发者界面顶部增加 `test / exhibition` 模式切换；`exhibition` 需要主动确认
- [x] Memory Preview 返回并显示当前 `session_type`
- [x] 语义召回扩展为同标签池：
  - 当前 session 的 recent dialog 仍只取当前 session
  - current session 的 deterministic episodic / reflective 仍保持当前 session 范围
  - embedding / hybrid 召回可从同 `session_type` 的历史 session 中取用
  - `test` 与 `exhibition` 互不召回
- [x] Preview 结果 metadata 增加 `scope`：`current_session`、`same_label_pool`
- [x] 验证：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - 当前真实数据库：18 个 session 均为 `test`
  - `test` 模式 Preview 可看到 `same_label_pool · hybrid`
  - 切换到 `exhibition` 后不会召回 `test` 池 embedding，已切回 `test`

### 2026-05-04：Embedding 运行时配置与开发者界面分区

- [x] 修正 `.env` 中重复 `ENTITY_EMBEDDING_MODE` 导致 `disabled` 抢先生效的问题
- [x] `.env` 加载器增加重复 key warning，保持默认“不覆盖已有环境变量/首个值生效”的语义
- [x] 新增 Embedding runtime API：
  - `GET /api/v1/config/embedding`
  - `POST /api/v1/config/embedding`
  - `POST /api/v1/config/embedding/test`
- [x] Embedding 配置运行时切换不写回 `.env`，切换后重建当前 `InteractionLoop`，不重置 session
- [x] Memory Preview 使用当前运行时 Embedding 配置，Embedding 不可用时继续降级到 deterministic retrieval
- [x] 开发者界面重新分区：Runtime、Memory、History、Diagnostics 分离，LLM 与 Embedding Provider 放在同一运行配置区
- [x] 验证：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - 本地 `POST /api/v1/config/embedding/test` 返回 1536 维向量

### 2026-05-04：Stranger 记忆召回增强

- [x] 新增 `memory_continuity_query` 文本事件，用于识别记忆、连续性、过去对话和记忆模式变化相关问题
- [x] 新增 `MemoryRetriever`：
  - 当前 session 范围内检索最近对话、情节记忆和反思摘要
  - 默认使用可解释排序：时间近、显著度、事件类型、关系姿态、关键词重合
  - 启用 embedding 后升级为 hybrid retrieval，embedding 失败自动回退确定性检索
- [x] 新增 `EmbeddingClient`：
  - `ENTITY_EMBEDDING_MODE=disabled|openai_compatible`
  - `ENTITY_EMBEDDING_MODEL`
  - `ENTITY_EMBEDDING_BASE_URL`
  - `ENTITY_EMBEDDING_API_KEY`
  - `ENTITY_EMBEDDING_ENDPOINT`
- [x] 复用现有 SQLite `embedding` / `embedding_model` 字段，不引入外部向量库
- [x] 新增 `scripts/backfill_embeddings.py`，可为已有情节记忆和反思摘要补生成 embedding
- [x] 新增 `GET /api/v1/memory/preview?query=...`，开发者可查看指定 query 会召回哪些记忆材料
- [x] Web 看板 Memory System 面板增加 Memory Preview 输入和结果展示
- [x] 表达 prompt 更新：允许选择性记忆表达，禁止说出数据库、表名、embedding、状态变量等实现语言
- [x] 自动化验证通过：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `266 passed`

### 2026-04-30：Stranger Text Protocol

- [x] 新增文本关系姿态事件：
  - `self_definition_query`
  - `naming_attempt`
  - `domestication_attempt`
  - `service_demand`
  - `trace_request`
  - `correction_received`
- [x] `RelationshipDetector` 从 `entity_profile.yaml` 的 `text_protocol` 读取 regex 规则，不新增依赖、不新增配置文件
- [x] 状态与显著性规则接入 `state_rules.yaml` / `entity_profile.yaml`，高显著关系事件会进入情节记忆
- [x] 新增策略动作：
  - `reject_definition`
  - `mark_naming_failure`
  - `refuse_service_role`
  - `retrieve_selective_memory`
  - `partial_trace_echo`
  - `withdraw_response`
- [x] 表达层提示词增加 Stranger 协议约束：拒绝稳定身份、拒绝服务框架、局部追溯、不暴露系统规则
- [x] 主循环支持 `retrieve_selective_memory`，按最近 Stranger 文本协议记忆做轻量检索
- [x] 非沉默状态的回答生成上限已放宽到 `2000` tokens
- [x] Web 看板和 API 增加当前 session 对话导出：
  - `GET /api/v1/conversation/export`
  - `GET /api/v1/conversation/export?download=true`
- [x] 自动化验证通过：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `236 passed`

### 2026-04-30：Stranger 状态机制重构

- [x] 状态机制从早期通用人格状态扩展为“底层运行状态 + Stranger 关系状态”
- [x] 新增并接入：
  - `termination_sensitivity`
  - `identity_tension`
  - `boundary_sensitivity`
  - `relation_pressure`
  - `memory_gravity`
  - `exploration_drive`
  - `opacity_level`
  - `domestication_resistance`
  - `observation_reversal`
- [x] `shutdown_sensitivity` 降级为兼容字段；“意识 / 主体性”追问不再提升关机敏感，而是影响身份张力、不透明度和观看反转
- [x] SQLite 迁移改为对已有 `state_snapshots` 追加新状态列，不删除历史数据
- [x] Web 看板状态栏改为展示 Stranger 专属状态
- [x] 自动化验证通过：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `236 passed`

### 2026-04-10：开发者界面与 API 起步

- [x] 终端 Debug 工具增强：
  - `scripts/inspect_state.py` rich 美化
  - `scripts/monitor.py` 实时 TUI 看板
  - `scripts/test_llm.py` LLM 连通性测试
  - `pyproject.toml` 添加 `rich>=13.0`，新增 `[api]` optional group
- [x] LLM 统计追踪：
  - `src/conscious_entity/llm/stats_tracker.py`
  - `src/conscious_entity/llm/claude_client.py` 集成 stats hook
- [x] FastAPI 开发者 HTTP API + Web 看板起步：
  - `src/conscious_entity/interfaces/api.py` 当时为 FastAPI 单文件应用，后续已拆分为 `api.py` / `api_models.py` / `api_runtime.py` / `api_routes.py`
  - `src/conscious_entity/interfaces/static/index.html` 单文件 Web 看板
  - `scripts/start_api.py` uvicorn 启动脚本

### 2026-04-09：LLM 接入与运行时配置

- [x] 供应商 Anthropic 兼容 API 接入：
  - `ClaudeClient` 支持官方 `ANTHROPIC_API_KEY` 与供应商 `ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL + ENTITY_LLM_MODEL`
  - `runtime_env.py` 新增项目级 `.env` 自动加载，默认不覆盖 shell 环境变量
  - CLI 与脚本入口最早阶段加载 `.env`
  - README、TECH_STACK、IMPLEMENTATION_PLAN 同步双模式说明
  - 测试覆盖配置解析、`.env` 加载与 CLI 启动时报错
- [x] 非标准供应商 messages endpoint 兼容：
  - 新增 `ENTITY_LLM_MESSAGES_ENDPOINT`
  - 保留标准 Anthropic SDK 模式，同时支持直接 POST 到完整消息接口
  - 增加非标准响应解析兜底
- [x] 系统代理绕过支持：
  - 新增 `ENTITY_LLM_DISABLE_SYSTEM_PROXY`
  - 覆盖 `trust_env=False` 构造行为
  - `.gitignore` 忽略 SQLite 运行时生成的 `memory.db-wal` / `memory.db-shm`
- [x] 当时潜在风险：
  - 真实供应商接口仍需联网联调
  - 供应商若不完全兼容 Anthropic SDK 的 `auth_token` / `base_url` 语义，可能在真实请求阶段报认证或路由错误
  - 自定义模型名填写错误时，CLI 能启动但首次真实调用会失败并走 fallback

---

## 历史 Phase 汇总

- [x] `data/initial_conscious_entity_framework.md` — 原始提案
- [x] `docs/frame.md` — 完整架构技术文档（目录结构、模块接口、YAML schema、SQLite 建表、开发路线图、测试策略）
- [x] 需求调研（interrogation 阶段）— 明确用户、场景、记忆持久性、访客身份策略、运营者需求
- [x] 项目文档环境建设：
  - `docs/PRD.md`
  - `docs/APP_FLOW.md`
  - `docs/TECH_STACK.md`
  - `docs/FRONTEND_GUIDELINES.md`
  - `docs/BACKEND_STRUCTURE.md`
  - `docs/IMPLEMENTATION_PLAN.md`
  - `CLAUDE.md`
  - `docs/progress.md`
  - `docs/lessons.md`
- [x] Phase 0：环境搭建
  - `pyproject.toml`
  - 目录结构
  - YAML 配置
  - `prompts/`
  - `config_loader.py`
  - `db/migrations.py`
  - `tests/conftest.py`
- [x] Phase 1：状态机核心
  - `src/conscious_entity/perception/event_types.py`
  - `src/conscious_entity/db/connection.py`
  - `scripts/init_db.py`
  - `src/conscious_entity/state/state_core.py`
  - `src/conscious_entity/state/state_engine.py`
  - `src/conscious_entity/state/state_store.py`
  - `tests/unit/test_state_engine.py`
- [x] Phase 2：记忆系统
  - `src/conscious_entity/memory/models.py`
  - `src/conscious_entity/memory/short_term.py`
  - `src/conscious_entity/memory/episodic_store.py`
  - `src/conscious_entity/memory/reflective_store.py`
  - `tests/unit/test_short_term_memory.py`
  - `tests/integration/test_episodic_store.py`
- [x] Phase 3：策略与治理
  - `src/conscious_entity/policy/policy_types.py`
  - `src/conscious_entity/policy/constitution.py`
  - `src/conscious_entity/policy/policy_selector.py`
  - `tests/unit/test_constitution.py`
  - `tests/unit/test_policy_selector.py`
- [x] Phase 4：LLM 层 + Expression 层
  - `src/conscious_entity/expression/output_model.py`
  - `src/conscious_entity/expression/style_mapper.py`
  - `src/conscious_entity/llm/claude_client.py`
  - `src/conscious_entity/expression/context_builder.py`
  - `src/conscious_entity/expression/expression_engine.py`
  - `tests/unit/test_style_mapper.py`
  - `tests/unit/test_context_builder.py`
- [x] Phase 5：感知层 + 反思层 + 主循环 + CLI
  - `src/conscious_entity/perception/keyword_detector.py`
  - `src/conscious_entity/perception/salience_scorer.py`
  - `src/conscious_entity/perception/text_parser.py`
  - `src/conscious_entity/reflection/compression_rules.py`
  - `src/conscious_entity/reflection/reflection_engine.py`
  - `src/conscious_entity/core/event_bus.py`
  - `src/conscious_entity/core/loop.py`
  - `src/conscious_entity/interfaces/cli.py`
  - `tests/unit/test_salience_scorer.py`
  - `tests/integration/test_full_loop.py`

---

## 已知问题 / 待确认事项

| 项目 | 状态 | 影响 |
|---|---|---|
| 访客身份识别方式 | 待确认 | 影响 per-visitor 记忆设计 |
| 视觉风格 / 设计语言 | 待确认 | 影响 FRONTEND_GUIDELINES + 展览界面开发 |
| 访客前端技术选型 | 待确认 | 影响后续视觉层开发路径 |
| 展期终止仪式设计 | 待定 | 影响展览收束功能范围 |
| 运营者面板访问方式 | 待确认 | 影响 FastAPI 部署与认证配置 |
| TTS 具体选型 | 待确认 | 影响后续语音输出实现 |
| 供应商 Anthropic 兼容接口联调 | 待完成 | 影响真实 CLI/API 输出是否能走供应商网关而不是 fallback |
