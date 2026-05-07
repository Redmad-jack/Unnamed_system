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

下一阶段只扩展文本事件，不引入视觉、语音或硬件输入。新增事件用于识别观众对 Stranger 的关系姿态，而不是识别观众身份。

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

## 2. 数据库表结构（SQLite）

### 2.1 sessions

```sql
CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,      -- UUID
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at        TEXT,
    visitor_count   INTEGER DEFAULT 0,
    notes           TEXT
);
```

**说明：** 一个 session 对应一次连续的装置运行周期。早期文本 MVP 全部使用单一 session；当前系统支持多 session 跨天记录，并通过 `session_type` 区分 test / exhibition 池。

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
| `src/conscious_entity/interfaces/api_runtime.py` | lifespan、runtime 配置、DB helper、loop rebuild |
| `src/conscious_entity/interfaces/api_routes.py` | HTTP 路由处理 |

**当前主要端点：**

| 方法 | 路径 | 说明 | 认证 |
|---|---|---|---|
| `POST` | `/api/v1/dialog` | 提交一轮对话输入，返回 ExpressionOutput | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/state` | 获取当前 EntityState | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/sessions` | 获取 session 列表 | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/sessions/reset` | 归档当前 session 并创建新 session | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/memory/preview?query=...` | 预览指定 query 会召回的记忆材料 | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/managed-memory` | 查看 committed managed memories | 本地开发面板，当前无认证 |
| `POST` | `/api/v1/managed-memory/commit` | commit pending proposal 或手动 operation | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/curation/memories` | 查看可整理记忆 | 本地开发面板，当前无认证 |
| `GET` | `/api/v1/conversation/export` | 导出当前或指定 session 对话 JSON | 本地开发面板，当前无认证 |

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
| 当前系统 | 使用 session 与 `session_type = test / exhibition` 区分测试池和展览池，不保存访客身份 |
| 后续展览阶段 | 如需访客识别，再设计 `visitor_id` 或其它匿名识别方式（待确认：语音声纹、视觉识别或对话引导） |

**注：** 不引入账户注册或密码机制。

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
- Stranger 文本协议阶段不保存原始音视频，也不新增访客身份画像；所有关系姿态只作为事件 metadata 保存
- 自动调参建议不得直接写回 YAML；必须先作为待确认记录进入运营者流程

---

## 8. 展期终止框架（待确认）

**[ 待确认 ]** 终止仪式的具体设计尚未确定。

预留的框架性要求：
- 系统应能导出所有记忆和状态为可归档格式（JSON / CSV）
- 终止事件应作为最后一条 `interaction_log` 记录（role = 'system'）
- 终止后的数据不被自动删除
- `scripts/export_memories.py` 应在终止流程中自动调用
