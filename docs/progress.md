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
- [x] 文档审计更新（2026-05-09）：README、`docs/HAVE_SOME_AI_STRUCTURE.md`、`docs/TECH_STACK.md` 已同步当前主链路；明确 freeform/chitchat 不会自动映射 A/B，语音排障先检查 8010 服务监听和 `/api/v1/voice-config`
- [x] 闲聊话术接入 Claude（2026-05-09）：Food Gate chitchat、`not_eating_chat` 与正式题 chitchat 的前 1-2 回合可由 `ShopkeeperReplyService` 用 Claude 生成自由 `reply_text`；第 3 回合仍按本地状态机送客或拉回题目，LLM 失败走模板兜底
- [x] 清理审计执行（2026-05-09）：删除本地 pytest / Python cache 与旧 egg-info，移除 Have Some "Ai" 运行时代码和前端里的旧 realtime 残留字段 / 分支，补齐 API 与语音配置文档冲突
- [x] Language gate（2026-05-09）：正式题前新增非评分语言选择；English / en / 英文或明显英文输入固定本次会话 `response_language=en`，中文 / Chinese / zh 或明显中文输入走中文默认逻辑；不改题库 id、选项 id、scores、模块结构或数据库结构
- [x] 正式题选项显示收口（2026-05-09）：屏幕和 Claude judge 的 visible choices 只保留 A/B；freeform/chitchat 仍不写入正式答案
- [x] Food Gate 语言选择后路径修正（2026-05-09）：选择 English 后进入 `questions.yaml` 的 13 条英文开场轮换 + “Want something to eat?”；中文继续使用 13 条中文开场 + “想来点吃的吗？”
- [x] `v1.2.1-EC` 发布前收口（2026-05-09）：README / 结构文档同步 Language Gate、A/B-only 显示、双语 Food Gate、最终固定出餐话术与测试合同
- [x] 双屏展示第 3 步（2026-05-10）：新增只读 `/display`、内存级 `GET/POST /api/v1/display-state` 和基础 `display.html`；完整验证 `pytest` 296 passed，本地 curl 验证 `/`、`/display`、display-state GET/POST 可用
- [x] 双屏展示控制页同步（2026-05-10）：`index.html` 新增统一 `updateDisplayState()`，在初始化、创建观众、题目/AI 回复、TTS 结束、结果和错误节点同步观众可见状态；完整验证 `pytest` 297 passed，本地 curl 验证 `/`、`/display`、display-state question / robot_speaking / result 可用
- [x] 双屏展览模式最终验收（2026-05-10）：复核 `/display` 只读安全边界、`POST /api/v1/display-state` 仅更新内存状态、控制页仍为唯一真实录音/会话推进入口；补充边界回归测试，完整验证 `pytest` 298 passed
- [x] `/display` 字号与文本同步修补（2026-05-10）：展示页底部文本字号约减半并保留换行；控制页同步题目时包含题干和 A/B 选项，普通 AI 回复继续同步整段 `reply_text`；display_text 上限放宽到 800，完整验证 `pytest` 298 passed
- [x] 豆包 TTS 展示同步修补（2026-05-10）：`conversation-stream` 的 `mic.muted_for_tts` 事件携带实际 TTS 文本；控制页在豆包真正开始说话时再同步展示页，正式判断题说话时仍显示题干和 A/B 选项；完整验证 `pytest` 298 passed
- [x] `/display` Avatar 动画状态机（2026-05-11）：新增 `idle_breathing` / `greeting_wave` / `system_speaking` / `audience_speaking` 四态优先级控制；控制页通过 display-state 传入 avatar 布尔信号，展示页仍只读且不接入真实语音链路；完整验证 `pytest` 299 passed，HTML 内联脚本解析通过
- [x] `/display` SilhouetteStage 组件化（2026-05-11）：将背景微光、人形虚影、浅绿色磨砂薄膜、高光噪声边缘、局部压痕撕扯假象收拢到独立 `#avatarStage` 五层结构；根节点按 avatar state 写入 `data-state` 和状态 class；完整验证 `pytest` 299 passed，本地 `/`、`/display`、display-state HTTP 200
- [x] `/display` 浅绿色磨砂薄膜细化（2026-05-11）：膜层改为可调 CSS 变量、多层渐变、轻颗粒、高光边缘和 no-backdrop fallback；未引入图片或新依赖；完整验证 `pytest` 299 passed，HTML 内联脚本解析通过
- [x] `/display` 代码生成人形虚影（2026-05-11）：AvatarStage 中人形改为 head / torso / upper arm / forearm / hand / mouth shadow / mouth opening 独立 DOM 图层，支持呼吸、挥手、开口和轻量贴膜撕扯动作；未引入图片或第三方库；完整验证 `pytest` 299 passed
- [x] `/display` idle / audience 呼吸动画（2026-05-11）：`idle_breathing` 新增整体慢浮动、torso 缩放和 head 延迟移动；`audience_speaking` 关闭嘴部、挥手和撕扯动作，只保留更低幅度呼吸；支持 `prefers-reduced-motion` 降低幅度；完整验证 `pytest` 299 passed
- [x] `/display` greeting_wave 挥手动画（2026-05-11）：`greeting_wave` 改为一次 2.05s CSS 动画，右上臂、前臂、手掌分层挥动两次，头身轻微跟随，膜层轻微同步波动；展示页本地 avatar controller 通过 `animationend` 回落到 system/audience/idle，并支持重复 greeting 触发重播；完整验证 `pytest` 299 passed
- [x] `/display` system_speaking 嘴部开合动画（2026-05-11）：人形虚影嘴部改为 CSS 变量驱动的模糊暗影开合，展示页本地 controller 在 `system_speaking` 内轻量随机调节开合幅度、透明度和横向微偏移；离开 system 或进入 audience 时立即闭合；完整验证 `pytest` 299 passed，HTML 内联脚本解析通过
- [x] `/display` system_speaking 薄膜撕扯假象（2026-05-11）：`membrane-stress` 内新增双手局部压痕和淡拉伸纹理 overlay；展示页本地 controller 只在 `system_speaking` 内随机短促调节压痕强度和膜面 tremble，切到 greeting/audience/idle 会清零；完整验证 `pytest` 299 passed，`/display` 禁止入口扫描无命中
- [x] Avatar 业务状态接入（2026-05-11）：控制页新增 `createDisplayAvatarStateAdapter()`，集中把 Language Gate greeting、TTS/robot speaking、文件录音/VAD、豆包流式麦克风采集与 ASR partial/final 映射为 avatar 布尔信号；debug 仅 `?avatarDebug` 开启；完整验证 `pytest` 299 passed，HTML 内联脚本解析通过
- [x] Avatar 开发面板（2026-05-11）：`/display` 新增本地开发限定的 Avatar Dev 面板，仅 `localhost/127.0.0.1/0.0.0.0/::1 + ?avatarPanel=1` 时动态创建；支持 Auto、idle、重复 greeting、system、audience 手动切换，并显示当前 avatarState 与 business/applied 输入；完整验证 `pytest` 299 passed，`/display` 禁止入口扫描无命中
- [x] Avatar 状态切换收尾优化（2026-05-11）：`greeting_wave` 手臂 keyframes 末尾回到自然位，避免回落 idle/system 时跳变；状态变量和手臂过渡统一到 260-320ms；离开 system 前先关闭嘴部和膜面压力，进入 system 后延迟 220-400ms 干净启动撕扯假象；完整验证 `pytest` 299 passed，HTML 内联脚本解析通过
- [x] Avatar 动画性能优化（2026-05-11）：高频挥手 keyframes 改为只修改 `transform`，降低膜面/虚影 blur 与 `backdrop-filter` 强度；关键动画层少量使用 `will-change` 和 `contain`；展示页隐藏或离开时清理 polling interval、嘴部 interval 与膜面 timer；完整验证 `pytest` 299 passed，`/display` 禁止入口扫描无命中
- [x] Avatar 最终验收修补（2026-05-11）：复核四态动画、膜后层次、主 UI 遮挡、状态收尾与性能边界；补充 `pageshow` 恢复轮询和销毁时 greeting replay 标记清理；项目无独立 lint/typecheck/build 脚本，已用 HTML 解析、展示页边界扫描和完整 `pytest` 299 passed 验收
- [x] Avatar 灰色虚影可见度修补（2026-05-11）：人形肢体改为中性灰色剪影，降低虚影 blur、提高 idle/audience/system/greeting 可见度，并略降薄膜不透明度；保持人形仍在膜层之后；完整验证 `pytest` 299 passed
- [x] Avatar 强可见灰色剪影调参（2026-05-11）：进一步把人形改为深灰高不透明剪影，显著降低 blur 和薄膜遮挡，用于现场优先确认挥手、说话和贴膜动作可读性；验证 `test_have_some_ai_api.py` 40 passed，展示页禁用入口扫描无命中
- [x] Avatar 薄膜图片纹理叠加（2026-05-12）：将 `pu/aa117.png` 复制为展示页静态纹理资产，新增 `.membrane-texture` 层叠在人形之后、膜面高光之前；保留原 CSS tint / blur / 高光 / dent / tremble，并让 system_speaking 时纹理只做极小幅同步抖动；完整验证 `pytest` 303 passed，展示页禁用入口扫描无命中
- [x] AI 店主运行语境注入机制（2026-05-11）：新增 `backend/prompts/shopkeeper_runtime_context.md` 和缓存 loader；仅注入 `ShopkeeperReplyService` 的自由闲聊 Claude prompt，`conversation-turn` / `conversation-audio` / `conversation-stream` 通过同一 Orchestrator 受益；Claude rubric、`ScoringEngine`、food assignment 和 `meal_*` 落库逻辑保持隔离。运行语境正文待用户提供后填入 prompt 文件；完整验证 `pytest` 302 passed
- [x] Language Gate 开场语调整（2026-05-12）：豆包/店主固定开场语改为 `Hi. 你好～ Do you want to talk in 中文 or English?`；同步控制页、展示页 greeting 检测、README、结构文档和测试断言；完整验证 `pytest` 303 passed
- [x] 正式题跑题口述闲聊修复（2026-05-17）：`FormalTurnRouter` 在默认进入 Claude A/B judge 前新增明显跑题实质句识别；正式题期间和当前题目无关的口述先进入 `chitchat`，不写 `meal_answers`、不调用 rubric、第 3 句仍按本地规则拉回当前题；完整验证 `pytest` 310 passed，`/display` 禁止入口扫描无命中，`index.html` / `display.html` HTML 解析通过

### 进行中（Work 2）

- 语音层真实端到端联调：AIHubMix file-STT 已保留；豆包主链路已改为 ASR/TTS 分离 WebSocket，仍需用真实火山凭证和浏览器麦克风确认 ASR definite 分句、Claude judge、TTS PCM 播放、barge-in 和完整答题流程
- 本地 8010 服务当前未监听；如需重新测试，运行 `./.venv/bin/python scripts/start_have_some_ai.py --port 8010`，再用 `lsof`、`/health`、`/api/v1/voice-config` 确认服务可达
- 最近完整测试套件：`310 passed`

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
