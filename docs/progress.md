# Progress

**⚠️ Work 1 (The "Stranger" / Conscious Entity) 已停止维护。本项目现阶段只关注 Work 2 (Have Some "Ai")。**

Exhibition System: Have Some "Ai"

---

## 每次会话开始前按顺序读

1. `AGENTS.md`
2. 本文件（`docs/progress.md`）
3. 当前任务涉及的模块文件

---

## Work 1: The "Stranger" (Conscious Entity) — 已停止维护

以下为历史记录，不再更新。

### 已完成

- [x] `data/initial_conscious_entity_framework.md` — 原始提案（v0.1）
- [x] `docs/frame.md` — 完整架构技术文档
- [x] 需求调研 — 明确用户、场景、记忆持久性、访客身份策略、运营者需求
- [x] 项目文档环境建设（PRD、APP_FLOW、TECH_STACK、BACKEND_STRUCTURE、IMPLEMENTATION_PLAN、CLAUDE.md）

#### Phase 0：环境搭建

- [x] `pyproject.toml`、目录结构、5 个 YAML 配置文件、`prompts/`
- [x] `src/conscious_entity/core/config_loader.py`、`db/migrations.py`、`tests/conftest.py`

#### Phase 1：状态机核心

- [x] `src/conscious_entity/perception/event_types.py` — EventType + PerceptionEvent
- [x] `src/conscious_entity/db/connection.py` — SQLite 连接管理（WAL + foreign keys）
- [x] `scripts/init_db.py` — 数据库初始化脚本
- [x] `src/conscious_entity/state/state_core.py` — EntityState dataclass
- [x] `src/conscious_entity/state/state_engine.py` — 事件驱动状态更新 + 时间衰减
- [x] `src/conscious_entity/state/state_store.py` — SQLite 快照持久化
- [x] `tests/unit/test_state_engine.py` — 31 个单元测试全绿

#### Phase 2：记忆系统

- [x] `src/conscious_entity/memory/models.py` — ShortTermEntry, EpisodicMemory, ReflectiveSummary
- [x] `src/conscious_entity/memory/short_term.py` — ShortTermMemory（deque + count_repetitions）
- [x] `src/conscious_entity/memory/episodic_store.py` — store / get_recent / get_unreflected / mark_reflected
- [x] `src/conscious_entity/memory/reflective_store.py` — store / get_all / mark_superseded
- [x] `tests/unit/test_short_term_memory.py` — 11 个单元测试全绿
- [x] `tests/integration/test_episodic_store.py` — 11 个集成测试全绿（含 ReflectiveStore）

#### Phase 3：策略与治理

- [x] `src/conscious_entity/policy/policy_types.py` — PolicyAction enum + PolicyDecision dataclass
- [x] `src/conscious_entity/policy/constitution.py` — action veto + text post-filter + forbidden_claim_detected
- [x] `src/conscious_entity/policy/policy_selector.py` — 逐条匹配 policy_rules.yaml，Constitution 依赖注入
- [x] `tests/unit/test_constitution.py` — 23 个单元测试全绿
- [x] `tests/unit/test_policy_selector.py` — 22 个单元测试全绿

#### Phase 4：LLM 层 + Expression 层

- [x] `src/conscious_entity/expression/output_model.py` — ExpressionOutput dataclass
- [x] `src/conscious_entity/expression/style_mapper.py` — StyleHints + StyleMapper
- [x] `src/conscious_entity/llm/claude_client.py` — Anthropic SDK 唯一接入点
- [x] `src/conscious_entity/expression/context_builder.py` — prompt 组装
- [x] `src/conscious_entity/expression/expression_engine.py` — 主编排器
- [x] `tests/unit/test_style_mapper.py` — 26 个单元测试全绿
- [x] `tests/unit/test_context_builder.py` — 21 个 prompt contract 测试全绿

#### Phase 5：感知层 + 反思层 + 主循环 + CLI

- [x] `src/conscious_entity/perception/keyword_detector.py` — 关键词检测（word boundary regex，CJK 兼容）
- [x] `src/conscious_entity/perception/salience_scorer.py` — 规则驱动显著度评分
- [x] `src/conscious_entity/perception/text_parser.py` — 文本 → PerceptionEvent 列表
- [x] `src/conscious_entity/reflection/compression_rules.py` — 反思触发阈值判断
- [x] `src/conscious_entity/reflection/reflection_engine.py` — LLM 情节记忆压缩 + 存储
- [x] `src/conscious_entity/core/event_bus.py` — 同步 EventBus
- [x] `src/conscious_entity/core/loop.py` — InteractionLoop（11步管道）
- [x] `src/conscious_entity/interfaces/cli.py` — 终端 REPL（`--debug` 显示 state）
- [x] `tests/unit/test_salience_scorer.py` — 13 个单元测试全绿
- [x] `tests/integration/test_full_loop.py` — 20 个集成测试全绿（mocked LLM）
- [x] CLI 冒烟测试通过（真实 API 响应正常）

#### Phase 6：Debug 工具 + 开发者 API（2026-04-10）

- [x] `scripts/inspect_state.py` — rich 美化（Panel + 进度条 + 策略决策表格）
- [x] `scripts/monitor.py` — 实时 TUI 看板（rich.live，2s 轮询，四栏布局）
- [x] `scripts/test_llm.py` — LLM 连通性测试（配置展示 + 延迟测量）
- [x] `src/conscious_entity/llm/stats_tracker.py` — LLM 调用统计单例
- [x] `src/conscious_entity/interfaces/api.py` — FastAPI 开发者 API（11 个端点）
- [x] `src/conscious_entity/interfaces/static/index.html` — Web 看板（状态仪表盘 + 对话区 + 记忆面板）
- [x] `scripts/start_api.py` — uvicorn 启动脚本（默认端口 8000）

#### 供应商兼容接口（2026-04-09）

- [x] 官方 `ANTHROPIC_API_KEY` 与供应商 `ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL + ENTITY_LLM_MODEL` 双模式
- [x] `ENTITY_LLM_MESSAGES_ENDPOINT` — 非标准消息接口直连支持
- [x] `ENTITY_LLM_DISABLE_SYSTEM_PROXY` — 系统代理绕过
- [x] `src/conscious_entity/runtime_env.py` — 项目级 `.env` 自动加载
- [x] `.env.example`、`.gitignore` 更新
- [x] 相关测试：`test_claude_client.py`、`test_runtime_env.py`、`test_cli.py`

### 下一步

- 已停止，不再跟进

---

## Work 2: Have Some "Ai"（当前主项目）

### 已完成（Work 2）

#### v0.1 最小闭环

- [x] `src/have_some_ai/models.py` — Participant, Question, Answer, ObservationEvent, AllocationResult
- [x] `src/have_some_ai/config.py` — 加载题库和评分配置
- [x] `src/have_some_ai/db.py` — 专属 SQLite 表建立
- [x] `src/have_some_ai/questionnaire.py` — 正式题随机抽题
- [x] `src/have_some_ai/scoring.py` — 两道正式题 + 四种食物映射
- [x] `src/have_some_ai/repository.py` — 数据库读写
- [x] `src/have_some_ai/service.py` — 观众流程应用服务
- [x] `src/have_some_ai/hardware.py` — 未来硬件边界占位
- [x] `src/have_some_ai/interfaces/api.py` — FastAPI app（15 个 schema 端点）
- [x] `src/have_some_ai/interfaces/static/index.html` — 最小 Web 界面
- [x] `scripts/start_have_some_ai.py` — uvicorn 启动脚本（默认端口 8010）
- [x] `config/have_some_ai/questions.yaml` — Food Gate 开头、正式题库、隐藏选项和分数
- [x] `config/have_some_ai/scoring.yaml` — 食物映射、观察事件权重备注
- [x] `tests/unit/test_have_some_ai_scoring.py` — 评分逻辑单元测试
- [x] `tests/unit/test_have_some_ai_service.py` — 服务层单元测试

闭环流程：新建观众 → 生成编号（A001…）→ Food Gate → 想吃才抽两道正式题 → A/B 判题 → 四种食物映射 → 写入工作人员队列 → 更新发餐状态 → 数据导出

#### v0.2 语音层原型

- [x] 推理时代 / OpenAI-compatible 语音网关配置：`HAVE_SOME_AI_VOICE_API_KEY + HAVE_SOME_AI_VOICE_BASE_URL`
- [x] Provider 配置：`HAVE_SOME_AI_VOICE_PROVIDER + HAVE_SOME_AI_STT_MODE`
- [x] AIHubMix 文件上传式 STT：`/audio/transcriptions`，默认模型 `whisper-large-v3`
- [x] STT language 配置：`HAVE_SOME_AI_STT_LANGUAGE` 有值时传入，留空时自动判断
- [x] TTS 默认模型：`gpt-4o-mini-tts`
- [x] API：TTS 读题、语音答案提交与解释结果存储
- [x] 前端语音启动顺序修正：先请求麦克风权限，再请求 STT session，并显示明确失败状态
- [x] API：文件上传式 `voice-audio`，带 `attempt_id` 幂等和真实 `mime_type`
- [x] 前端：AIHubMix file-STT 模式下使用 MediaRecorder + VAD 静音检测 + 2s 题目播放后录音延迟
- [x] 播放流程：首题中英问候、第二题 next-question 过渡、TTS 只读题干、答案 accepted 后播放 thank you
- [x] Claude A/B 映射支持 unclear / needs_retry，低置信度不保存正式答案，malformed JSON 会 repair 或降级重试
- [x] 本地 `.venv` 已重建到 python.org Framework Python 3.13.5，普通 pytest 不再因 Anaconda debugging 插件段错误中断
- [x] 统一店主对话状态机后端 transcript 版：`ConversationOrchestrator` + `/conversation-turn`，模板回复，不接豆包、不改前端、不处理音频
- [x] 店主自然回复服务：`ShopkeeperReplyService` 只生成 `reply_text`，不决定 stage / 题目 / A-B / assignment / next_action
- [x] `/conversation-turn` 正式题阶段接入 A/B/unclear judge：accepted 写正式答案，judge unclear 留在当前题，两道正式题完成后才 `assign_food()`
- [x] 统一语音入口：新增 `/conversation-audio`，流程为 file STT → `ConversationOrchestrator` → `reply_text` → TTS，前端主语音按钮改走统一状态机；旧 `voice-audio` / `voice-answers` 保留兼容
- [x] 修复店主不出声：`/conversation-turn` 支持 `include_audio` 返回 TTS，前端新建观众后的 Food Gate 和手动 transcript fallback 会播放 `reply_text`
- [x] 废码清理：关闭本地 8010 服务，移除旧 OpenAI Realtime STT session 入口、前端 WebRTC 死代码、豆包 direct A/B 提交实验路径
- [x] 店主对话重构：新增 Food Gate 与 `A_NO_FOOD` / `B_WANT_FOOD` chat mode；`NO_FOOD` 只闲聊不分配，`WANT_FOOD` 进入两道正式题；移除早期多余正式判断题，结果改为 `soup` / `salad` / `aimiao_soup` / `aimiao_salad`
- [x] 豆包 ASR/TTS split migration：新增 ASR `bigmodel_async` 协议/client、TTS V3 `tts/bidirection` 协议/client，本地主 WebSocket 改为 `/conversation-stream`
- [x] 豆包职责收口：豆包只负责 ASR 与 TTS；店主话术由 `ConversationOrchestrator` + `ShopkeeperReplyService` 产生，A/B/unclear 由 Claude judge，食物由 `ScoringEngine`
- [x] 流式音频硬化：前端发送 binary PCM16 16k mono，后端聚合 200ms 音频；TTS 输出 binary PCM16 24k mono，并在播放期间 half-duplex 暂停 ASR 上行
- [x] 旧豆包端到端语音链路移出运行时代码；相关诊断脚本删除，避免恢复旧主链路
- [x] 真实联调前修复：ASR client 改为收到实际麦克风音频后懒连接，避免开场 TTS 阶段因 ASR 握手失败/延迟导致页面“无声音且无法录音”；初始 TTS 任务创建前后端先暂停 ASR 上行
- [x] 店主式“闲聊 + 判断”边界修正：`ConversationOrchestrator` 内新增 Food Gate / Formal turn routing，chitchat 不再进入 Claude judge；`NO_FOOD` 进入 3 回合 `not_eating_chat` 后送客并删除 transient participant；正式题 chitchat 最多 3 回合后拉回当前 A/B 问题
- [x] session cleanup：`farewell` / `done` 后 WebSocket 主链路会结束 ASR session 并停止继续收麦克风；前端对 deleted/end_session 不再刷新已删除 participant
- [x] 豆包新版控制台鉴权修正：ASR/TTS 均使用 `X-Api-Key + X-Api-Resource-Id`，不要求 App ID / Access Key；TTS 失败仍会返回 `tts.error` 并恢复收麦
- [x] 文档审计更新（2026-05-09）：README、`docs/HAVE_SOME_AI_STRUCTURE.md`、`docs/TECH_STACK.md` 已同步当前主链路；明确 C/freeform/chitchat 不会自动映射 A/B，语音排障先检查 8010 服务监听和 `/api/v1/voice-config`
- [x] 闲聊话术接入 Claude（2026-05-09）：Food Gate chitchat、`not_eating_chat` 与正式题 chitchat 的前 1-2 回合可由 `ShopkeeperReplyService` 用 Claude 生成自由 `reply_text`；第 3 回合仍按本地状态机送客或拉回题目，LLM 失败走模板兜底
- [x] 清理审计执行（2026-05-09）：删除本地 pytest / Python cache 与旧 egg-info，移除 Have Some "Ai" 运行时代码和前端里的旧 realtime 残留字段 / 分支，补齐 API 与语音配置文档冲突

### 进行中（Work 2）

- 语音层真实端到端联调：AIHubMix file-STT 已保留；豆包主链路已改为 ASR/TTS 分离 WebSocket，仍需用真实火山凭证和浏览器麦克风确认 ASR definite 分句、Claude judge、TTS PCM 播放、barge-in 和完整答题流程
- 本地 8010 服务当前未监听；如需重新测试，运行 `./.venv/bin/python scripts/start_have_some_ai.py --port 8010`，再用 `lsof`、`/health`、`/api/v1/voice-config` 确认服务可达
- 最近 Have Some "Ai" voice / conversation / API / chat / service 单元测试子集：`79 passed`

### 下一步（Work 2）

- [ ] 细化 `questions.yaml` 与 `scoring.yaml`，确定最终分配机制
- [ ] 语音层：继续浏览器端到端联调，确认 `/conversation-audio` fallback 与 `/conversation-stream` 的 Food Gate、not-eating 送客、正式答题、chitchat 拉回、两题完成后分配食物
- [ ] 语音层：打磨低置信度重新录音机制
- [ ] 观众端 / 工作人员端拆分为两个独立页面
- [ ] 安全 / 忌口覆盖逻辑（必须优先于艺术算法）

---

## 已知问题 / 待确认事项

| 项目 | 状态 | 影响 |
| --- | --- | --- |
| Have Some "Ai" 语音 STT/TTS 选型 | AIHubMix 走 file STT：`whisper-large-v3` + OpenAI-compatible TTS；豆包走 ASR `bigmodel_async` + TTS V3 双向流式，输入 PCM16 16k，输出 PCM16 24k，正式判题仍交给 Claude | 待真实浏览器麦克风完整验收 |
| 本机 8010 服务 | 当前未监听；`/health` 连不上时，网页语音不会工作 | 排障时先启动服务，不要先误判为麦克风或 TTS bug |
| Have Some "Ai" 最终题库与评分 | 待细化 | 影响 questions.yaml / scoring.yaml |
| 访客身份识别方式 | 待确认（v0.3） | 影响 visitor_id 字段设计 |
| 视觉风格 / 设计语言 | 待确认 | 影响展览界面开发 |
| 展期终止仪式设计 | 待确认 | 影响 v0.3 功能范围 |
