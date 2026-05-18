# Application Flow

*Conscious Entity System — current text system + developer API*

---

## 1. 系统路径概览

系统有两条并行的主路径：

```
访客路径：  [输入/观察] → 感知层 → 状态更新 → managed memory preview → 策略/记忆召回 → LLM 表达 → [身体呈现]
治理观测：  Runtime Harness Trace 旁路记录 input/state/memory/policy/prompt/generation/output/presentation
运营者路径：[本地开发者面板] ← 实时状态 / 对话历史 / Memory Preview / Managed Memory Curation / Harness Trace
```

访客路径最终不是传统 user interface。当前 CLI / Web 输入只是开发阶段入口；第一版 `/visitor` 只作为临时 body-facing surface。当前可选 audio adapter 已能把浏览器麦克风 final transcript 送入现有 turn loop，并把合法 `ExpressionOutput` 转成火山 TTS stream id 播放。物理移动、循路和避障是更后面的身体层，在非移动的声音/视觉/外观能力稳定前不进入主实现。

---

## 2. 访客路径

### 2.1 进入（Session 启动）

**触发条件：** 新的 CLI / API runtime 会话启动，或可选 vision runtime 的 presence detection 触发访客进入

**流程：**
```
系统加载最新状态快照（来自 SQLite）
  ↓
从 interaction_log 恢复当前 session 最近对话窗口，作为短期上下文
  ↓
如有 presence event，则触发 USER_ENTERED
  ↓
Identity & Session Gating 记录 encounter_candidate，但不创建 session / 不切 visitor
  ↓
状态更新：arousal +0.15, attention_focus +0.2, fatigue -0.05
  ↓
策略可能触发欢迎或沉默（取决于当前 resistance / trust 水平）
```

**成功状态：** 系统就绪，等待访客输入
**错误状态：** 数据库连接失败 → fallback 到默认初始状态，记录错误日志

**当前视觉入口：** 可选 vision runtime 使用 Mac 摄像头 + 本地 YOLO 模型，只检测 `person` class。稳定检测到人会触发 `USER_ENTERED`，人离开超过阈值会触发 `USER_LEFT`，持续存在但长时间没有文字交互会触发 `LONG_SILENCE_DETECTED`。这些事件同时进入 `loop.handle_system_event(...)` 和 Identity & Session Gating：前者更新状态，后者只记录 encounter / intent 状态。presence 不等于对话意图，不会自动创建新 session 或切换 visitor。

**macOS 摄像头权限注意：** 摄像头授权绑定启动 API 的宿主进程。Codex 启动的 Python 可能无法获得 Camera 权限；若出现 `Could not open camera index N`，优先从已授权的 Terminal / VS Code 启动同一 API 进程。

**后续身体阶段：** 进入不一定来自文字输入，也可以来自靠近、停留、被观察、被呼唤或空间位置变化。当前不实现移动、循路或避障。

---

### 2.2 对话回合（Turn Loop）

**触发条件：** 访客提交文字输入，或 audio adapter 送入 STT final transcript

**当前流程（见 `src/conscious_entity/core/loop.py`）：**

```
Step 0   创建 HarnessTraceRecorder
          └─ 只记录运行时治理 trace，不改变本轮决策结果，不写 SQLite
          └─ 进入前由 VisitorSessionGatingController 补充 identity/session metadata

Step 1   感知层解析输入 → 生成 PerceptionEvent 列表
          └─ 可能产生多个事件：USER_SPOKE + SHUTDOWN_KEYWORD_DETECTED 等
          └─ Input Harness 记录 source、input_mode、event_types、session_decision

Step 2   加载当前 EntityState，并对每个事件应用状态增量（state_rules.yaml）
          └─ 返回新 EntityState（不可变更新）

Step 3   应用 per-turn 时间衰减
          └─ State Harness 记录 snapshot、trigger events、changed fields

Step 4   生成低延迟 `first_unit`
          └─ 发生在本轮 `short_term.add_user`、managed memory preview、retrieval 和主 LLM 前
          └─ 只使用当前输入、事件、状态/表达姿态，以及上一轮 user / first / second 的轻量 bridge
          └─ progressive callback 可立即发出 `first_unit`

Step 5   将本轮用户输入加入短期记忆
          └─ 后续 policy、memory 和 main response 可看见当前输入

Step 6   预览 managed memory influence
          └─ preview_influence() 不写入数据库
          └─ 只应用被允许的 state deltas，并通过 clamp_all() 限制到 [0,1]
          └─ Memory Harness 记录 expression context 数量、policy suggestion、state delta keys

Step 7   持久化状态快照到 SQLite（state_snapshots 表）

Step 8   将显著事件（salience ≥ 0.5）存入情节记忆（episodic_memories 表）
          └─ embedding 可用时补写向量；失败时退回可解释召回

Step 9   策略选择
          └─ PolicySelector 从上到下匹配 policy_rules.yaml
          └─ Constitution 先行检查是否允许
          └─ 返回 PolicyDecision（含 action + rationale）
          └─ managed memory policy influence 可把开放回应牵引为选择性记忆召回
          └─ Policy Harness 记录 rule id、selected / vetoed、decision

Step 10  [条件] 若策略或 managed memory 要求检索记忆
          └─ 检索当前 session 的最近对话、情节记忆和反思摘要
          └─ 若当前 session 绑定匿名 visitor_id，同一 visitor 的旧 session 可作为 continuity hint 参与召回
          └─ embedding 启用时，同 `session_type` 的语义池可参与 hybrid retrieval
          └─ 默认使用可解释排序；启用 embedding 时使用 hybrid retrieval
          └─ `RETRIEVE_MEMORY_FIRST` 取回材料后进入开放表达，其它检索策略保持原 action
          └─ Memory Harness 记录 retrieval 路径和取回数量

Step 11  表达层生成 `second_unit`
          └─ ContextBuilder 组装 ExpressionContext
          └─ prompt 明确知道本轮 `first_unit` 已经说出口，主回应只续写、不重答
          └─ StyleMapper 计算 StyleHints（tone, delay, fragmentation, visual_mode）
          └─ ClaudeClient 调用 LLM
          └─ Constitution 过滤输出文本
          └─ Prompt / Generation / Output Harness 记录 prompt partial、LLM 状态、constitution filter

Step 12  将实体回应加入短期记忆缓冲
          └─ content 仍只保存 `second_unit`；完整 response_plan 仅作为 metadata 供下一轮 bridge 使用

Step 13  写入 interaction_log，并记录 memory_influence_log
          └─ influence log 记录 expression / policy / state 影响，不公开 prompt 或 YAML 全量规则

Step 14  生成 managed memory proposal，并在 auto-commit 开启时提交
          └─ propose() 不直接改变行为记忆
          └─ commit() 后才进入 committed managed memories

Step 15  触发反思检查
          └─ 若未反思事件数 ≥ threshold → 调用 ReflectionEngine
          └─ 存储反思摘要到 reflective_summaries 表
          └─ 标记已处理的情节记忆

Step 16  发送 turn_complete 到 EventBus，供调试或后续 instrumentation 使用
          └─ Presentation Harness 记录 delay、visual_mode、spoken_text 状态
```

**成功状态：** 返回 ExpressionOutput（text + delay_ms + visual_mode），后续由身体呈现层映射为文字、声音、光、投影、停留或其它非 UI 输出

**当前语音入口：** 可选 audio runtime 使用火山 STT/TTS。浏览器或未来身体节点只把 16k / 16bit / mono PCM chunk 发到 `/api/v1/audio/stt/stream`；只有 `transcript.final` 可以通过 `/api/v1/audio/dialog` 进入现有 `run_turn()`。TTS 只朗读最终已过滤的 `ExpressionOutput` 派生文本，并通过 `tts_stream_id` 播放，不允许 visitor/body 直接指定任意 TTS 文本。

**当前身份/会话入口：** V1 不做自动人脸/声纹识别。已绑定 visitor 时本轮标记为 `continue_current`；未绑定 visitor 时标记为 `continue_unidentified`；显式插入信号只记录 interruption，默认不替换当前 primary visitor。下一优先级是在这个边界上补齐声纹识别、视觉识别、历史匹配、自然确认和访客库。

**错误状态：**
- LLM 调用失败 → 使用规则生成 fallback 回应（简短、中性）
- 数据库写入失败 → 记录日志，但不中断对话流程
- embedding、managed memory proposal/commit、reflection 失败 → 记录日志，并降级继续主对话

---

### 2.3 离开（Session 关闭）

**触发条件：** 访客停止输入，或 vision / 后续身体 presence detection 触发 `USER_LEFT` 事件

**流程：**
```
触发 USER_LEFT 事件
  ↓
状态更新：arousal -0.2, attention_focus -0.3, fatigue -0.1, trust +0.02
  ↓
持久化最终状态（跨天保留，不重置）
  ↓
Session 记录写入 interaction_log
```

**成功状态：** 状态持久化完成，下次进入时可以恢复
**错误状态：** 持久化失败 → 记录错误，状态在下次启动时以最近一次成功快照为基础

---

## 3. 运营者路径（当前为本地开发者 API + Web 看板）

### 3.1 查看当前状态

**脚本方式：**
```bash
python scripts/inspect_state.py
```
输出当前 EntityState 所有字段值 + 最近 5 条策略决策

**当前 API 方式：** FastAPI `/api/v1/state` 端点 → 本地开发者 Web 看板（观众不可见）

**Vision 工作区：** 开发者 Web 看板左侧 `Entity State` 下方显示 Vision 面板，可启动/停止摄像头与 YOLO worker，查看 runtime status、模型路径状态、camera index、FPS、detections、最近 vision events，并通过 WebSocket JPEG frames 显示后端标注后的实时画面。

**Audio 工作区：** 开发者 Web 看板 `Runtime` 区域显示 Audio Adapter，可启动/停止浏览器麦克风，查看 provider、disabled reason、STT partial/final transcript、TTS stream id 和错误，并将 final transcript 送入现有对话回合。

**Harness 工作区：** 开发者 Web 看板 `Runtime` 区域显示最近一轮 Harness layer 状态、decision 和摘要。Prompt Harness 只显示 partial 名称与摘要，不显示完整 hidden prompt。

**Identity & Session Gating 工作区：** 开发者 Web 看板 `Runtime` 区域显示当前 runtime state、session decision、primary visitor、candidate、encounter/intent、confidence level、是否等待确认和 interruption count。V1 不展示原始人脸、原始音频、embedding 向量或完整身份库。

**访客 surface：** `/visitor` 只读取最新 `ExpressionOutput` 与少量 state 映射为文字、扰动、沉默和延迟感；如已启用声音，也只播放后端已创建的 `tts_stream_id`，不显示 dashboard 控件、内部规则、memory、prompt 或调试指标。

---

### 3.2 查看对话历史

**脚本方式：**
```bash
python scripts/export_memories.py
```
导出 interaction_log 和 episodic_memories 为 JSON

**当前 API 方式：** FastAPI `/api/v1/history`、`/api/v1/conversation/export` 与 Memory Curation 相关端点

---

### 3.3 重播会话

**触发条件：** 研究者需要重现特定行为轨迹

```bash
python scripts/replay_session.py --session-id <id>
```

---

## 4. 系统内部：完整 Turn 状态机

```
raw user input
  ↓
HarnessTraceRecorder.start(...)
  ↓
TextParser / KeywordDetector / SalienceScorer
  → [PerceptionEvent, ...]
  ↓
StateEngine.apply_event(...) + apply_decay(...)
  → new EntityState
  ↓
ExpressionEngine.plan_first_unit(...)
  → progressive first_unit callback
  ↓
ShortTermMemory.add(user)
  ↓
ManagedMemory.preview_influence(...)
  → expression_context / policy_influence / bounded state_influence
  ↓
StateStore.save_snapshot(...) + EpisodicStore.store(...)
  ↓
PolicySelector + Constitution
  → PolicyDecision
  ↓
Managed memory policy influence may request RETRIEVE_SELECTIVE_MEMORY
  ↓
MemoryRetriever.retrieve(...) or managed expression_context fallback
  ↓
ExpressionEngine
  → ContextBuilder + already-spoken first_unit + StyleMapper + ClaudeClient + Constitution filter
  ↓
ExpressionOutput
  ↓
ShortTermMemory.add(entity) + interaction_log + memory_influence_log
  ↓
ManagedMemory.propose(...) → optional commit(...)
  ↓
ReflectionEngine.maybe_reflect(...)
  ↓
EventBus.emit("turn_complete")
  ↓
HarnessTraceStore.record(...)
```

---

## 5. 错误状态汇总

| 场景 | 系统行为 |
|---|---|
| LLM 调用超时/失败 | fallback 回应（简短中性文本），记录错误日志 |
| SQLite 写入失败 | 跳过本次持久化，继续对话，写入错误日志 |
| YAML 配置文件格式错误 | 启动时报错退出，输出明确的错误字段位置 |
| 状态数值超出 [0,1] | clamp_all() 在每次状态更新后强制修正，不抛出异常 |
| 反思 LLM 调用失败 | 跳过本次反思，不影响对话流程，记录失败事件 |
| Embedding 计算失败 | 跳过向量写入或语义召回，退回可解释召回 |
| Managed memory proposal / commit 失败 | 记录错误，不影响本轮 ExpressionOutput |
| Vision optional deps 未安装或模型路径缺失 | `/api/v1/vision/status` 返回 disabled reason；启动 worker 时返回明确 400，不影响文本系统 |
| 摄像头无法打开或帧读取失败 | vision worker 记录 runtime error，释放摄像头；主 loop 继续运行 |
| Audio optional deps / 火山凭证 / 音色缺失 | `/api/v1/audio/status` 返回 disabled reason；文本系统继续运行 |
| STT / TTS 流式连接失败 | 记录 sanitized error 与 logid，不保存原始音频，不影响现有文本 dialog |
| Identity/session gating 状态异常 | 降级为未确认 visitor 的当前 session，不自动创建新 session，不影响主 turn loop |

---

## 6. 待办与待确认

**P0 交接优先级：**
- 完整声纹识别、视觉识别与访客库：基于当前 V1 gating，完成 signature capture、质量门控、历史匹配、combined confidence、自然确认和 visitor profile metadata。
- 能力自我描述回归测试与优化：确保 Stranger 对看见、听见、识别、记忆、身体、移动等能力的描述与 runtime 上下文一致。
- 行为测试与调优：统一见 `docs/testlist.md`，本文件不展开测试清单。

**已完成第一版但仍需现场校准：**
- STT / TTS Audio Adapter：火山 STT/TTS，可降级 disabled，不改变核心 turn loop。
- 视觉 presence detection：Mac 摄像头 + 本地 YOLO，后续空间感知和视觉身份识别仍待扩展。
- Visitor Identity & Session Gating V1：单 primary visitor session、presence 不创建 session、插入只记录事件。

**后续待确认：**
- Stranger 身体外观、材料、尺度、显示/投影/光等呈现方式。
- 物理移动、循路、避障和底盘方案。
- 运营者面板的局域网访问、部署认证和展览现场隔离方式。
