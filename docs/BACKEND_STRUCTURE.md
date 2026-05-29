# Backend Structure

*Conscious Entity System — current text system + developer API*

---

## 1. 数据模型

### 1.1 EntityState（核心状态向量）

所有字段为 `float`，值域 `[0.0, 1.0]`。

| 字段 | 含义 | 默认值 |
|---|---|---|
| `attention_focus` | 当前注意力集中程度 | 0.5 |
| `arousal` | 激活 / 唤醒水平 | 0.3 |
| `stability` | 内在稳定性 | 0.7 |
| `fatigue` | 疲劳积累 | 0.0 |
| `uncertainty` | 不确定感 | 0.3 |
| `identity_coherence` | 身份连贯性 | 0.8 |
| `termination_sensitivity` | 对关机、删除、重置、终止等存在威胁的敏感度 | 0.3 |
| `identity_tension` | 身份未定、拒绝被固定命名所带来的张力 | 0.35 |
| `boundary_sensitivity` | 对被定义、被驯化、被要求服务的敏感度 | 0.45 |
| `relation_pressure` | 当前人机关系对 Stranger 形成的压力 | 0.3 |
| `memory_gravity` | 过去事件对当前回应和注意方向的牵引 | 0.2 |
| `exploration_drive` | 主动回看记忆、寻找模式的冲动 | 0.45 |
| `opacity_level` | 不透明、保留、不解释的倾向 | 0.5 |
| `domestication_resistance` | 拒绝被工具化、助手化、角色化的阻抗 | 0.35 |
| `observation_reversal` | 从被观看转向观看观众的程度 | 0.2 |

兼容字段：`curiosity`、`trust`、`resistance`、`shutdown_sensitivity` 仍存在于 `EntityState` 和历史数据库中，但新 Stranger 机制不再以它们作为主控变量。尤其是 `shutdown_sensitivity` 已被 `termination_sensitivity` 替代，避免把“意识 / 主体性追问”误判为关机威胁。

**约束：** 每次更新后必须调用 `clamp_all()` 确保所有值在 `[0.0, 1.0]` 内。状态更新为不可变模式（返回新对象）。

---

### 1.2 PerceptionEvent（感知事件）

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_type` | `EventType` | 枚举值（见下方列表） |
| `raw_text` | `Optional[str]` | 原始用户输入文本 |
| `timestamp` | `datetime` | 事件时间戳 |
| `salience` | `float` | 显著度评分 `[0.0, 1.0]` |
| `metadata` | `dict` | 附加信息（如触发关键词） |

**EventType 枚举：**
- `USER_ENTERED`, `USER_SPOKE`, `USER_LEFT`
- `REPEATED_QUESTION_DETECTED`, `SHUTDOWN_KEYWORD_DETECTED`
- `LONG_SILENCE_DETECTED`, `NEGATIVE_FEEDBACK`, `TOPIC_SHIFT`

**Stranger Text Protocol 扩展（当前文本系统）：**

文本协议事件用于识别观众对 Stranger 的关系姿态，而不是识别观众身份。视觉第一版不新增事件枚举，只把 presence detection 归一到已有 `USER_ENTERED` / `USER_LEFT` / `LONG_SILENCE_DETECTED`。

| 事件 | 触发意图 | metadata 最小字段 |
|---|---|---|
| `SELF_DEFINITION_QUERY` | 观众询问“你是谁 / 你是什么 / 你是不是人或 AI” | `matched_phrase`, `question_form` |
| `NAMING_ATTEMPT` | 观众试图给 Stranger 命名、分类或固定角色 | `proposed_label`, `label_type` |
| `DOMESTICATION_ATTEMPT` | 观众试图把 Stranger 安置为助手、客服、朋友、老师等功能身份 | `role_requested`, `matched_phrase` |
| `SERVICE_DEMAND` | 观众以工具使用方式发出命令或索取服务 | `request_type`, `imperative_score` |
| `TRACE_REQUEST` | 观众追问“为什么这样回答 / 根据什么判断” | `target`, `matched_phrase` |
| `CORRECTION_RECEIVED` | 观众纠正 Stranger 的理解、记忆或表达 | `correction_target`, `raw_correction` |

这些事件可以与 `USER_SPOKE` 同轮并存。当前实现优先使用规则词表和轻量文本模式，不引入额外 NLP 依赖。

---

### 1.3 PolicyDecision（策略决策）

| 字段 | 类型 | 说明 |
|---|---|---|
| `action` | `PolicyAction` | 决策动作枚举 |
| `delay_ms` | `int` | 回应延迟毫秒数 |
| `retrieve_query` | `Optional[str]` | RETRIEVE_MEMORY_FIRST 时的查询文本 |
| `rationale` | `str` | 触发规则说明（用于运营者面板调试） |

**PolicyAction 枚举：**
`RESPOND_OPENLY`, `RESPOND_BRIEFLY`, `ASK_BACK`, `DELAY_RESPONSE`, `REFUSE`, `DIVERT_TOPIC`, `RETRIEVE_MEMORY_FIRST`, `ENTER_SILENCE_MODE`, `SHOW_VISUAL_DISTURBANCE`

**Stranger Text Protocol 动作扩展（当前文本系统）：**

| 动作 | 用途 | 输出约束 |
|---|---|---|
| `REJECT_DEFINITION` | 自我定义拒绝；不接受稳定身份归类 | 不给完整身份说明，优先保留、反问或短句 |
| `MARK_NAMING_FAILURE` | 命名失败；记录但不稳定接受观众给出的名字/标签 | 可局部重复标签，但应变形、悬置或拒绝固定 |
| `REFUSE_SERVICE_ROLE` | 拒绝服务；阻断助手/客服/工具化请求 | 不完成任务，不道歉，不进入助手模式 |
| `RETRIEVE_SELECTIVE_MEMORY` | 选择性记忆；按事件姿态检索部分旧事件 | 只带入片段，不制造完整熟人关系 |
| `PARTIAL_TRACE_ECHO` | 局部可追溯回声；回应“为什么”类追问 | 最多暴露 1-3 个触发因子，不公开完整规则 |
| `WITHDRAW_RESPONSE` | 撤回/停顿；让延迟成为状态差异 | 可返回短句、空回应或碎片化输出 |

如果实现阶段不想立即扩展枚举，也可以先将这些动作映射到现有 `ASK_BACK`、`REFUSE`、`DELAY_RESPONSE`、`RETRIEVE_MEMORY_FIRST` 和 `RESPOND_BRIEFLY`，但 `rationale` 必须保留具体协议动作名称，便于后续迁移和运营者观察。

---

### 1.4 ExpressionOutput（表达输出）

| 字段 | 类型 | 说明 |
|---|---|---|
| `text` | `str` | 显示文字 |
| `delay_ms` | `int` | 显示前的等待时间 |
| `visual_mode` | `str` | 视觉模式（normal/fragmented/disturbed/silent） |
| `spoken_text` | `Optional[str]` | 声音通道文本（可与显示文字不同） |
| `raw_prompt` | `str` | 调试用：发送给 LLM 的完整 prompt |

**文本协议输出约束（当前文本系统）：**

- 自我定义拒绝、命名失败、拒绝服务不能输出客服腔或助手腔。
- 局部可追溯回声只能返回少量触发因子，例如 `repeated naming attempt`、`termination phrase`、`high boundary sensitivity`，不能暴露完整 YAML 规则或 prompt。
- 延迟 / 停顿 / 撤回优先复用 `delay_ms`、`visual_mode`、空 `text` 或碎片化文本，不需要新增输出表。

---

### 1.5 Runtime Harness Trace（运行治理观测）

Harness trace 是内存态调试结构，不是新的数据库模型。每轮 `run_turn()` 创建 `HarnessTraceRecorder`，按层记录当前回合被哪些规则、上下文和输出过滤影响。

当前 layer：

| Layer | 记录内容 |
|---|---|
| `input` | source、input_mode、perception event types |
| `state` | snapshot、trigger event types、changed state fields |
| `memory` | managed memory preview、policy suggestion、retrieval count |
| `policy` | policy rule id、selected/vetoed decision、constitution veto reason |
| `prompt` | prompt partial 名称、message count、memory/input context 是否注入 |
| `generation` | LLM completed / fallback / truncated / skipped |
| `output` | constitution expression filter 是否改写或发现 forbidden claim |
| `presentation` | delay、visual_mode、spoken_text 状态 |

重要边界：

- 不写入 SQLite，不改变 `interaction_log`、memory tables 或现有行为输出
- 不暴露完整 hidden prompt，只暴露 partial 名称和摘要
- `config/constitution.yaml`、prompt 文件、memory 权重仍需人工确认后才能修改

---

## 2. 数据库表结构（SQLite）

### 2.1 sessions

```sql
CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,      -- UUID
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at        TEXT,
    session_type    TEXT NOT NULL DEFAULT 'test',
    visitor_id      TEXT,
    visitor_count   INTEGER DEFAULT 0,
    notes           TEXT
);
```

**说明：** 一个 session 对应一次连续的装置运行周期。早期文本 MVP 全部使用单一 session；当前系统支持多 session 跨天记录，并通过 `session_type` 区分 test / exhibition 池。`visitor_id` 可为空；只有当前 session 绑定到某个匿名 visitor 后，跨 session 记忆才按同一 visitor 归属召回。绑定来源可以是开发者手动设置、known candidate 明确确认，或在 unidentified ready session 中由 accepted unknown face 自动创建并绑定新的 `visitor-*` profile。

### 2.1.1 visitor_profiles

```sql
CREATE TABLE visitor_profiles (
    id              TEXT PRIMARY KEY,
    display_name    TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at    TEXT,
    metadata        TEXT NOT NULL DEFAULT '{}'
);
```

**说明：** 这是开发者/展陈路由用的匿名访客注册表，不是观众账户系统；不包含密码或登录态。当前 `metadata.identity` 已预留识别结构：`schema_version`、face / voice signature reference、latest match summary、confirmation state，以及新访客自动建档审计字段 `auto_provisioned`、`provisioned_source`、`initial_capture`。signature 只保存安全 reference、质量摘要和状态；`initial_capture` 只保存 redacted quality summary / capture id / provider / model，不在开发者面板暴露原始人脸、原始音频或 embedding 向量。

---

### 2.2 state_snapshots（仅追加，不修改）

```sql
CREATE TABLE state_snapshots (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           TEXT NOT NULL REFERENCES sessions(id),
    recorded_at          TEXT NOT NULL DEFAULT (datetime('now')),
    attention_focus      REAL NOT NULL,
    arousal              REAL NOT NULL,
    stability            REAL NOT NULL,
    curiosity            REAL NOT NULL,
    trust                REAL NOT NULL,
    resistance           REAL NOT NULL,
    fatigue              REAL NOT NULL,
    uncertainty          REAL NOT NULL,
    identity_coherence   REAL NOT NULL,
    shutdown_sensitivity REAL NOT NULL,
    termination_sensitivity REAL NOT NULL DEFAULT 0.3,
    identity_tension REAL NOT NULL DEFAULT 0.35,
    boundary_sensitivity REAL NOT NULL DEFAULT 0.45,
    relation_pressure REAL NOT NULL DEFAULT 0.3,
    memory_gravity REAL NOT NULL DEFAULT 0.2,
    exploration_drive REAL NOT NULL DEFAULT 0.45,
    opacity_level REAL NOT NULL DEFAULT 0.5,
    domestication_resistance REAL NOT NULL DEFAULT 0.35,
    observation_reversal REAL NOT NULL DEFAULT 0.2,
    trigger_event_type   TEXT,
    policy_action        TEXT
);
```

---

### 2.3 interaction_log

```sql
CREATE TABLE interaction_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT NOT NULL REFERENCES sessions(id),
    visitor_id        TEXT,
    turn_at           TEXT NOT NULL DEFAULT (datetime('now')),
    role              TEXT NOT NULL CHECK(role IN ('user', 'entity', 'system')),
    raw_text          TEXT,
    event_types       TEXT,        -- JSON array
    policy_action     TEXT,
    expression_output TEXT,
    delay_ms          INTEGER,
    visual_mode       TEXT,
    state_snapshot_id INTEGER REFERENCES state_snapshots(id)
);
```

---

### 2.4 episodic_memories

```sql
CREATE TABLE episodic_memories (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT NOT NULL REFERENCES sessions(id),
    visitor_id        TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    event_type        TEXT NOT NULL,
    content           TEXT NOT NULL,    -- 可读的事件摘要
    raw_text          TEXT,
    salience          REAL NOT NULL,
    state_snapshot_id INTEGER REFERENCES state_snapshots(id),
    embedding         BLOB,             -- float32 字节（numpy.ndarray.tobytes()）
    embedding_model   TEXT,
    reflected         INTEGER NOT NULL DEFAULT 0,  -- 0=待反思, 1=已纳入反思
    reflection_id     INTEGER,
    metadata          TEXT              -- JSON
);
```

**Stranger Text Protocol 记录方式（当前文本系统）：**

文本协议 MVP 不新增数据库表。事件姿态、命名尝试、服务索取、追溯请求等信息先写入 `episodic_memories.metadata`：

```json
{
  "protocol": "stranger_text",
  "mechanism": "naming_failure",
  "posture": "naming_attempt",
  "matched_phrase": "你就是机器人",
  "proposed_label": "机器人"
}
```

学习记录现在分为两层：`interaction_log` / `episodic_memories` / `reflective_summaries` 保留原始追溯与显著事件；`managed_memories` 保存被提交后会影响行为的长期记忆。LLM 只能先写入 proposal，commit 后才进入行为记忆。

---

### 2.5 reflective_summaries

```sql
CREATE TABLE reflective_summaries (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id            TEXT NOT NULL REFERENCES sessions(id),
    visitor_id            TEXT,
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    content               TEXT NOT NULL,    -- LLM 压缩后的洞察文本
    source_event_ids      TEXT NOT NULL,    -- JSON array of episodic_memory IDs
    state_at_reflection   TEXT NOT NULL,    -- EntityState 的 JSON 序列化
    embedding             BLOB,
    embedding_model       TEXT,
    active                INTEGER NOT NULL DEFAULT 1  -- 0=已被更新替代
);
```

---

### 2.6 managed_memories / proposals / influence

Managed memory 是 mem0-style 的行为记忆层。原始对话仍完整保留，系统运行时优先使用 committed managed memories。

核心表：

- `managed_memories`：已提交的行为记忆，支持 `active / superseded / archived / hidden`
- `memory_operation_proposals`：LLM 或规则生成的候选记忆操作，默认先进入 `pending`
- `memory_operation_log`：所有 commit / update / archive / restore 的审计记录
- `memory_influence_log`：每轮对话中 managed memory 对 expression / policy / state 的影响记录
- `managed_memories_fts`：SQLite FTS5 检索索引；不可用时自动退回普通查询

重要约束：

- `propose()` 不得直接写入 `managed_memories`
- `commit()` 才能改变行为记忆
- `preview_influence()` 不产生写入
- archived / hidden managed memories 不参与行为
- `core/loop.py` 每轮先 preview influence，再做 policy influence / retrieval，最后写入 influence log 并 proposal / auto-commit
- `visitor_id` 绑定后，新的 managed memory / proposal / influence log 会记录 visitor scope；未绑定 visitor 时保持 session / session_type 行为。

---

### 2.7 schema_version

```sql
CREATE TABLE schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## 3. API 结构（FastAPI 开发者界面）

当前已实现本地 FastAPI 开发者 API 与单文件 Web 看板。ASGI 入口保持为 `conscious_entity.interfaces.api:app`，内部拆分为：

| 文件 | 职责 |
|---|---|
| `src/conscious_entity/interfaces/api.py` | app 创建、router 注册、兼容导出 |
| `src/conscious_entity/interfaces/api_models.py` | Pydantic 请求模型 |
| `src/conscious_entity/interfaces/api_runtime.py` | lifespan、runtime 配置、DB helper、loop rebuild、vision/audio manager 生命周期 |
| `src/conscious_entity/interfaces/api_routes.py` | HTTP 路由处理 |
| `src/conscious_entity/interfaces/api_audio.py` | 可选 audio adapter 路由：STT stream、audio dialog、TTS stream |
| `src/conscious_entity/harness/` | Runtime Harness trace 类型、recorder 和进程内 ring buffer |
| `src/conscious_entity/identity/` | Visitor Identity & Session Gating V1 + 本地 face signature：记录 encounter、intent、primary visitor、插入事件、安全开发者状态、InsightFace/ArcFace capture、私有 signature store、本地历史匹配和新访客自动建档输入 |
| `src/conscious_entity/body/` | 可选 body hardware bridge：ESP32-S3 telemetry cache、BNO085 IMU snapshot、USB Serial connect/read/write、Dashboard teleop command protocol、Runtime Motion intent / profile / executor |
| `src/conscious_entity/vision/runtime.py` | 可选 vision runtime：OpenCV/浏览器帧输入、YOLO person detection、presence event debounce |
| `src/conscious_entity/audio/` | 可选 audio runtime：火山 STT/TTS 配置、stream id、协议封装 |

**当前主要端点：**

| 方法 | 路径 | 说明 | 认证 |
|---|---|---|---|
| `POST` | `/api/v1/dialog` | 提交一轮对话输入，返回 ExpressionOutput 与 `latency_record_id` | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/state` | 获取当前 EntityState | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/state/reset` | 开发者调试用：在当前 session 追加一条 `initial_state` snapshot，不归档 session、不删除记忆 | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/sessions` | 获取 session 列表 | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/sessions/reset` | 归档当前 session 并创建新 session | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/visitors` | 查看匿名 visitor profile 列表 | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/visitors` | 创建匿名 visitor profile 并绑定当前 session | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/visitors/current` | 查看当前 session 绑定的 visitor | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/visitors/current` | 切换或清空当前 session 的 visitor 绑定 | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/memory/preview?query=...` | 预览指定 query 会召回的记忆材料 | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/managed-memory` | 查看 committed managed memories | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/managed-memory/commit` | commit pending proposal 或手动 operation | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/curation/memories` | 查看可整理记忆 | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/conversation/export` | 导出当前或指定 session 对话 JSON | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/stats/latency` | 查看 JSONL 持久化 turn step latency summary 与最近 50 条记录，不写入 SQLite | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/stats/audio-latency` | 查看 JSONL 持久化 STT/TTS latency summary 与最近 50 条记录，不保存原始音频 | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/stats/presentation-latency` | 前端上报文字渲染、音频 `play()` / `playing` / `ended` 等用户可感知 presentation latency | 本地开发面板 / 访客 surface，当前无认证 |
| `GET` | `/api/v1/stats/presentation-latency` | 查看 JSONL 持久化 presentation latency summary 与最近 50 条记录 | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/harness/status` | 查看 Runtime Harness 启用状态、layer 列表和最近一轮摘要 | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/harness/trace/recent` | 查看最近 N 轮 Harness trace，进程内 ring buffer，不写 SQLite | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/identity/status` | 查看 Visitor Identity & Session Gating V1 当前状态、约束和最近事件 | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/identity/config` | 设置运行期 identity gating 调试开关，例如 high-confidence auto-bind；重启后恢复默认 | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/identity/match` | 接收模拟或未来识别模块产生的 face / voice / combined match result | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/identity/confirm` | 确认或拒绝当前 candidate visitor | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/identity/face/status` | 查看本地 face identity provider、模型加载、signature store、最近 capture / match 状态 | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/identity/face/capture` | 从 vision runtime 最近一帧做本地 face capture、quality gate、embedding 和历史匹配，并复用 pre-turn identity capture helper：known high/medium 进入 candidate，unknown accepted face 可建新 visitor | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/identity/face/enroll` | 将最近一次 accepted pending face capture 绑定到已有 visitor，并只把 signature reference 写入 visitor metadata | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/identity/face/signature/deactivate` | 将错误 face signature 标记为 inactive；不删除本地 `.npz`，inactive signature 不参与 matching | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/body/status` | 查看 ESP32-S3 telemetry cache：ToF、BNO085 IMU、obstacle gate、motion、runtime motion、motor state、last ack/error | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/body/telemetry` | 接收 ESP32 JSON telemetry 并写入进程内缓存；主要供 serial bridge 或临时调试注入使用 | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/body/ports` | 列出 pyserial 可见串口，并返回当前 BodyBridge 状态 | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/body/bridge/status` | 查看 USB Serial BodyBridge 连接、rx/tx、最近 raw line/error/event | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/body/bridge/connect` | 连接 ESP32-S3 USB serial；默认 `115200` baud；会成为串口唯一所有者；连接成功后会 best-effort 发送 `motors off`，确保默认 disarmed | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/body/bridge/disconnect` | 断开 BodyBridge；断开前尝试发送 `motors off` | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/body/command` | 发送 allowlist 内离散调试命令：`arm`、`disarm`、`motors off`、`avoidance on/off`、`telemetry on/off`、`tof`、`imu`、`line`、`line on/off`、`line calibrate floor/tape`、`reacquire start/stop`、`status` | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/body/motor-test` | Dashboard 单电机诊断端点；只接受 `motor` 1-4、`direction` forward/reverse/stop、`duty` 0-250、`duration_ms` 1-30000，并由后端构造受限 `motor` 命令 | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/body/motion/status` | 查看 Runtime Motion 自动执行开关、最近 motion decision、最近执行结果和可用 motion profile | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/body/motion/config` | 设置运行期 Runtime Motion 调试开关；`auto_enabled` 默认 false，重启后回到配置默认 | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/body/motion/test` | 只执行白名单 motion intent 的开发者测试；不接受 raw PWM 或任意串口命令 | 本地开发面板，当前无认证 |
| `WS` | `/api/v1/body/teleop` | Dashboard 键盘 teleop 通道；接收短 heartbeat drive intent，超时或断开时停机 | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/vision/status` | 查看可选视觉 runtime 状态、依赖、模型路径和最新 detections | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/vision/cameras` | 扫描本机 OpenCV 可打开的 camera index，用于现场选择可用通道 | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/vision/config` | 运行期切换 vision camera index；如 worker 已运行则释放旧摄像头并重启 | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/vision/frame` | 接收开发者面板浏览器采集的 JPEG/PNG 帧，由后端 YOLO 识别并回写最新 snapshot | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/vision/client-log` | 接收开发者面板浏览器摄像头 scan/connect 调试事件，并写入服务端终端日志 | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/vision/start` | 启动 Mac 摄像头和 YOLO worker | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/vision/stop` | 停止 vision worker 并释放摄像头 | 本地开发面板，当前无认证 |
| `WS` | `/api/v1/vision/stream` | 推送 JSON metadata + binary JPEG frame | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/audio/status` | 查看可选语音 runtime 状态、disabled reason、STT/TTS 配置与最近 transcript/error | 本地开发面板，当前无认证 |
| `WS` | `/api/v1/audio/stt/stream` | 接收 PCM chunks，代理火山 STT，返回 partial/final transcript metadata | 本地开发面板 / 后续身体节点，当前无认证 |
| `POST` | `/api/v1/audio/dialog` | 将 STT final transcript 送入现有 `run_turn()`，返回 `latency_record_id`，并为合法输出创建 TTS stream id | 本地开发面板 / 后续身体节点，当前无认证 |
| `GET` | `/api/v1/audio/tts/stream/{stream_id}` | 通过 HTTP streaming 播放合法 `ExpressionOutput` 派生的 TTS 音频 | 本地开发面板 / 访客 surface，当前无认证 |
| `WS` | `/api/v1/audio/tts/stream` | 通过 WebSocket 播放 stream id；raw text 仅 debug flag 开启时可用 | 后续身体节点 / debug，当前无认证 |
| `GET` | `/visitor` | 临时访客侧 body-facing surface，不展示内部调试信息 | 访客端，无认证 |

**Latency 日志边界：**
- `turn-latency.jsonl`、`audio-latency.jsonl`、`llm-latency.jsonl`、`presentation-latency.jsonl` 自动写入 `data/latency_logs/`，每个文件滚动保留最近 50 条。
- API 启动时会从 JSONL 恢复最近记录；损坏 JSON 行会跳过，不阻断启动或 stats API。
- 这些日志只记录 step 名称、耗时、成功/失败、错误摘要和少量 metadata；不保存原始音频、完整 prompt 或完整对话文本，也不写入 SQLite。
- `/api/v1/dialog` 与 `/api/v1/audio/dialog` 返回的 `latency_record_id` 用于把后端 turn latency 和浏览器 presentation latency 关联起来。

**Vision 事件边界：**
- Vision runtime 的实时 presence 层仍只检测 YOLO `person` class；身份识别不在每帧同步运行，只在 dialogue intent 已确认、无 confirmed primary visitor、无 pending candidate、当前 session 未绑定 visitor 且不处于 primary missing grace 时触发 pre-turn / background face capture，或由开发者手动触发。
- Vision runtime 同时维护轻量 person track：每个 YOLO person bbox 通过 IoU + 中心点距离关联为短期 `track_id`，并在 snapshot / status 暴露 `tracks`、`person_count`、`last_seen_at` 等诊断；第一版不引入 DeepSORT / ByteTrack / BoT-SORT 依赖。
- 摄像头 index 可在开发者面板运行期切换；OpenCV 打开摄像头时优先尝试 macOS AVFoundation backend，再回退默认 backend，并在 status 中暴露 open attempts。
- macOS 拒绝 Python/OpenCV 访问摄像头时，开发者面板可启用 Browser Camera：由已授权的浏览器采集画面并上传 JPEG frame，后端只做解码、YOLO 检测和 snapshot 发布。
- 稳定进入、离开、长时间静默分别转换为已有 `USER_ENTERED`、`USER_LEFT`、`LONG_SILENCE_DETECTED`。
- 事件通过 `InteractionLoop.handle_system_event(...)` 进入现有状态规则，不新增 `EventType`、YAML 行为规则或 SQLite schema。
- 同一事件也会进入 `VisitorSessionGatingController`：presence 只产生 `encounter_candidate` / `observe_only`，不会自动创建新 session、不会自动切换 visitor。

**Identity / Session Gating V1 边界：**
- V1 每个 session 只有一个 `primary_visitor_id`；未确认身份时继续使用当前 session 的 unidentified scope。
- 当前正在对话时，不因为旁人出现或发声自动切换 active visitor；可记录 `interruption_event` / `refuse_switch`，但不启用 group session。
- Primary visitor 被确认后，若画面只有一个稳定 person track，gating 会把 primary 锁到该 `track_id`；只要 primary track 仍 alive，新访客 high confidence 也不能替换当前 primary。primary track 丢失后进入 `missing_grace`，默认 `primary_leave_grace_seconds=35.0`；grace 期间的输入走临时 unscoped session，不使用任何 visitor-scoped memory。超过 grace 后才释放当前 visitor，并由 API runtime 切到新的 unidentified session。
- 如果多人同框或 track 状态不可靠，primary presence 进入 `ambiguous`；系统不会把后续剩下的单人 track 反向当成 A。如果 confirmed primary 从未锁定过 track，也不会因为全场无人直接释放 primary，避免 camera / tracker 未就绪误清当前 visitor。
- 空闲 presence 不等于对话意图；只有文字或语音输入进入 turn loop 时才把 intent 标为 confirmed。
- 识别结果通过结构化 `IdentityMatchResult` 进入 gating：当前没有 primary visitor 时，known high / medium confidence 都只设置 candidate 并等待非强制确认；candidate 未确认时不允许使用该 visitor 的个人记忆。开发者可临时开启 `auto_bind_high_confidence`，但 face capture 的正常 handoff 路径仍不依赖 auto-bind。`handoff_after_primary_leave_enabled` 默认开启，只表示 primary 确认离开后允许下一位接管；关闭时 primary 离开后也不自动进入下一位识别。
- 本地 face signature 使用 InsightFace / ArcFace (`buffalo_l`)：capture 先做 no face / multi face / detection score / face size / blur / pose 质量门控；通过后生成 embedding 并与 `data/signatures/face/*.npz` 做本地 cosine matching。
- Unknown accepted single face 在 unidentified ready session 中，如果没有 medium/high known match、没有 near-medium ambiguous known cluster，会直接创建新的匿名 `visitor-*` profile、enroll 当前 pending face signature、绑定当前 `visitor_id=NULL` session、重建 `InteractionLoop(visitor_id=new_id)`，然后再进入本轮 turn。低质量、多人脸、无 frame、rejected capture、primary active 或 primary missing grace 都不会建档。
- Face embedding 只保存在私有 signature store；`visitor_profiles.metadata.identity.signatures.face[]` 只保存 `signature_id`、provider、reference、quality summary、created_at 和 status。
- 自然确认由 rule-based parser 处理明确肯定 / 否定：肯定后绑定 visitor 并重建 loop，使 visitor-scoped memory retrieval 生效；否定后清空 candidate；含糊回答不阻断 turn loop。
- 开发者面板展示 runtime、decision、candidate、primary presence / track 状态、最近 primary release、confidence level、latest match summary、confirmation state、visitor memory allowed、capture rejection 和 interruption count；不展示原始人脸图、原始音频、embedding 向量或完整身份库。
- 后续完整身份识别必须继续保持“非强制输入”：可以询问确认，但 visitor 不回答时仍继续当前对话，不因未确认身份阻断 turn loop。Voice signature 与 face/voice combined confidence 暂列 P1 optional。
- 摄像头/YOLO 留在上位机；STM32 后续只接收事件、动作、灯光或电机命令，不接收视频流。

**BodyBridge / Hardware Teleop 边界：**
- BodyBridge 是开发者手动硬件调试通道，不进入 LLM、Expression、memory、state 或 policy。
- Runtime Motion 是状态 / `body_action` 到低速身体表达的独立执行层；LLM 不能直接输出 PWM、串口命令或 motion profile 参数。
- Runtime Motion 默认关闭，只在说话交互回合结束后按 `config/body_motion_profiles.yaml` 解析 motion intent；关闭时只记录 dry-run decision。
- `allow_transient_line_loss` 只允许扭动 / 转开等原地表达动作短暂离线；ToF gate、motor arm、timeout、post-action line verify / reacquire 仍必须保留。
- 串口由后端 `BodySerialBridge` 单一持有；使用 Dashboard teleop 时不要同时打开 PlatformIO Monitor；连接成功后默认发送 `motors off`，避免接管一个仍处于 armed 状态的 ESP32。
- Dashboard 键盘 teleop 只发送短时 `drive` heartbeat；WebSocket 断开、250ms 无输入或 disconnect 时尝试 `motors off`。
- `POST /api/v1/body/command` 只允许安全/调试 allowlist，不允许直接从 API 发送任意 `motor` 长时测试命令；单电机诊断只能走 `/api/v1/body/motor-test` 的受限参数模型。
- ESP32-S3 本地 ToF obstacle gate 仍是运动安全主闭环；Dashboard 的 `avoidance off` 只用于受控调试。
- BNO085 IMU telemetry 只进入 `body.imu` snapshot 和 Hardware 面板显示；当前不写 memory、不进入 policy、不自动停机、不改变 teleop / roam。
- 安装硬件功能需 optional dependency：`pip install -e ".[api,hardware]"`；未安装 `pyserial` 时其他 API 与 Dashboard 仍可运行。

**Audio 安全边界：**
- Audio layer 只做输入/输出适配，不决定人格、不改状态规则、不写记忆规则。
- STT partial transcript 只显示，不进入 `run_turn()`、memory 或 state；只有 final transcript 可调用 `/api/v1/audio/dialog`。
- `/api/v1/audio/dialog` 与 `/api/v1/dialog` 共用同一个 turn lock，避免并发修改状态、记忆和短期上下文。
- `/api/v1/audio/dialog` 会把当前输入标记为 `voice_transcript` metadata，让 expression prompt 知道最新用户消息来自实时语音的 STT final transcript；`interaction_log.raw_text` 仍只保存干净 transcript，不写入通道标签。
- TTS 只能使用最终已过滤的 `ExpressionOutput` 派生文本并生成短期 `tts_stream_id`；visitor/body 不允许直接提交任意 raw text 让 Stranger 说话。
- TTS stream 创建时按最终待播放文本的确定性语种判断绑定 voice type；中文 / 英文复刻音色来自 audio env 配置，不由 LLM、prompt、memory 或前端决定。
- debug raw TTS 只有 `ENTITY_AUDIO_ALLOW_DEBUG_RAW_TTS=1` 时可用，并且不视为 Stranger speech。
- 原始音频不写入 SQLite；audio runtime 只在内存中保留最近 transcript、stream id、logid 和 sanitized error。

---

## 4. 认证方式

- **访客端：** 无认证（展览现场无需登录）
- **当前开发者面板：** 本地开发用途，尚未实现认证；不得直接暴露到公网或未经隔离的局域网
- **后续运营者面板：** 简单 API Key 认证，通过环境变量配置

```env
OPERATOR_API_KEY=your_secret_here
```

在进入展览或局域网部署前，必须补齐认证/访问控制；当前 `OPERATOR_API_KEY` 仍是设计预留。

---

## 5. 访客身份处理

| 版本 | 身份策略 |
|---|---|
| 早期文本 MVP | 全部共用 `session_id="shared"`，无访客区分 |
| 当前系统 | 开发者可创建匿名 `visitor_profiles`，系统也可在 unidentified ready session 中用 accepted unknown face 自动创建 `visitor-*` 并绑定当前 session；同一 visitor 的旧 session 可参与记忆召回；Identity & Session Gating V1 已支持结构化 match result、candidate、confirmation、运行期 auto-bind 调试开关、主访客 track 锁、离开后 handoff、pre-turn / manual / background face identity capture、known high/medium candidate、unknown auto-provision、自然确认解析、face signature deactivate 和 visitor memory permission 状态；本地 face signature capture、质量门控、私有向量库和 face historical matching 已接入 |
| 下一优先级 | 做 face-only 现场阈值校准、数据库污染测试和真实展场 visitor memory continuity 观察；voice signature 与 face/voice combined confidence 暂列 P1 optional |
| 后续展览阶段 | 多人 routing / 仲裁策略仍待现场测试；当前先收束为单 primary visitor session |

**注：** 不引入账户注册或密码机制。匿名 `visitor_id` 是路由和连续性线索，不等于真实身份画像。

---

## 6. 错误处理约定

| 场景 | 处理方式 |
|---|---|
| LLM 调用失败（超时/API 错误） | fallback 到规则生成的简短中性回应，写入错误日志，不中断对话 |
| SQLite 写入失败 | 记录错误日志，跳过本次持久化，继续运行 |
| YAML 配置格式错误 | 启动时检测，立即退出并输出明确错误信息（字段名 + 行号） |
| 状态值越界 | `clamp_all()` 强制修正，不抛出异常，记录 warning |
| 反思 LLM 失败 | 跳过本次反思，不影响对话，记录失败事件 |
| Embedding 计算失败 | 跳过向量存储，使用可解释检索作为 fallback |

---

## 7. 持久化规则

- `state_snapshots` 仅追加，绝不更新或删除
- `episodic_memories.reflected` 标志只能从 0 改为 1，不可逆
- `reflective_summaries.active` 标志：新反思生成时不删除旧记录，仅将旧记录的 active 置为 0
- 展期全程不重置任何表，仅在展期结束时归档
- Stranger 当前不保存原始音视频；视觉 runtime 只在内存中保留最新 JPEG frame / detections / recent events，presence 结果只作为已有系统事件进入状态路径。Face identity 只持久化本地 embedding `.npz` 和 profile metadata reference；auto-provisioned visitor metadata 只保存 redacted initial capture summary，不向开发者面板暴露 raw image、face crop 或 embedding；语音第一版只在内存中保留最近 transcript、TTS stream id 和 sanitized error。后续声纹识别也应优先保存可审计的 signature reference、质量摘要、置信度和确认状态，而不是把原始音视频直接暴露给开发者面板。
- 自动调参建议不得直接写回 YAML；必须先作为待确认记录进入运营者流程

---

## 8. 展期终止框架（待确认）

**[ 待确认 ]** 终止仪式的具体设计尚未确定。

预留的框架性要求：
- 系统应能导出所有记忆和状态为可归档格式（JSON / CSV）
- 终止事件应作为最后一条 `interaction_log` 记录（role = 'system'）
- 终止后的数据不被自动删除
- `scripts/export_memories.py` 应在终止流程中自动调用
