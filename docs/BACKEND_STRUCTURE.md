# Backend Structure

*Conscious Entity System — v0.1*

---

## 1. 数据模型

### 1.1 EntityState（核心状态向量）

所有字段为 `float`，值域 `[0.0, 1.0]`。

| 字段 | 含义 | 默认值 |
|---|---|---|
| `attention_focus` | 当前注意力集中程度 | 0.5 |
| `arousal` | 激活 / 唤醒水平 | 0.3 |
| `stability` | 内在稳定性 | 0.7 |
| `curiosity` | 好奇心 / 开放性 | 0.5 |
| `trust` | 对当前访客的信任度 | 0.5 |
| `resistance` | 阻抗 / 抵抗倾向 | 0.2 |
| `fatigue` | 疲劳积累 | 0.0 |
| `uncertainty` | 不确定感 | 0.3 |
| `identity_coherence` | 身份连贯性 | 0.8 |
| `shutdown_sensitivity` | 对关机/删除话题的敏感度 | 0.5 |

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

---

### 1.4 ExpressionOutput（表达输出）

| 字段 | 类型 | 说明 |
|---|---|---|
| `text` | `str` | 显示文字 |
| `delay_ms` | `int` | 显示前的等待时间 |
| `visual_mode` | `str` | 视觉模式（normal/fragmented/disturbed/silent） |
| `spoken_text` | `Optional[str]` | 声音通道文本（可与显示文字不同） |
| `raw_prompt` | `str` | 调试用：发送给 LLM 的完整 prompt |
| `turn` | `Optional[dict]` | 店主模式结构化回合：language / scene / reply / action / state_updates / next_scene |

### 1.5 ShopSessionState（店主对话状态）

| 字段 | 类型 | 说明 |
|---|---|---|
| `language` | `zh/en` | 当前语言 |
| `current_scene` | `str` | 当前店主场景 |
| `previous_scene` | `Optional[str]` | 上一个店主场景 |
| `order_status` | `str` | none / selecting / pending_confirmation / placed |
| `selected_soup` | `Optional[str]` | ai_miao / no_ai |
| `has_complimented_appearance` | `bool` | 是否已经夸过穿搭/外观标签 |
| `has_asked_item_origin` | `bool` | 是否已经问过衣服/配饰来源 |
| `recent_turns` | `list[str]` | 最近几轮店主对话摘要 |

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

**说明：** 一个 session 对应一次连续的装置运行周期。v0.1 全部使用单一 session，v0.2+ 支持多 session 跨天记录。

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

### 2.4 shop_state_snapshots（仅追加，不修改）

```sql
CREATE TABLE shop_state_snapshots (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id                  TEXT NOT NULL REFERENCES sessions(id),
    recorded_at                 TEXT NOT NULL DEFAULT (datetime('now')),
    language                    TEXT NOT NULL,
    current_scene               TEXT NOT NULL,
    previous_scene              TEXT,
    order_status                TEXT NOT NULL,
    selected_soup               TEXT,
    has_complimented_appearance INTEGER NOT NULL DEFAULT 0,
    has_asked_item_origin       INTEGER NOT NULL DEFAULT 0,
    recent_turns                TEXT NOT NULL DEFAULT '[]',
    state_updates               TEXT,
    trigger_scene               TEXT,
    action                      TEXT,
    entity_state_snapshot_id    INTEGER REFERENCES state_snapshots(id)
);
```

---

### 2.5 episodic_memories

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

---

### 2.6 reflective_summaries

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

### 2.7 schema_version

```sql
CREATE TABLE schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## 3. API 结构（FastAPI 开发者接口）

当前已提供本地开发者 API 和 Web 看板。

| 方法 | 路径 | 说明 | 认证 |
|---|---|---|---|
| `POST` | `/api/v1/dialog` | 提交 `text/asr_text/visual_tags/retrieved_context`，返回 ExpressionOutput + turn + shop_state | 无 |
| `GET` | `/api/v1/state` | 获取当前 EntityState | 无 |
| `GET` | `/api/v1/state/history` | 获取状态快照历史 | 无 |
| `GET` | `/api/v1/memory/episodic` | 获取情节记忆列表 | 无 |
| `GET` | `/api/v1/memory/reflective` | 获取活跃反思摘要 | 无 |
| `GET` | `/api/v1/interaction-log` | 获取 interaction_log | 无 |
| `GET` | `/api/v1/config` | 获取全部 YAML 配置 | 无 |
| `GET` | `/api/v1/config/llm` | 获取脱敏 LLM 配置 | 无 |
| `POST` | `/api/v1/config/reload` | 热重载 YAML 配置并重建 InteractionLoop | 无 |
| `GET` | `/api/v1/stats/llm` | 获取 LLM 调用统计 | 无 |

---

## 4. 认证方式

- **访客端：** 无认证（展览现场无需登录）
- **运营者面板：** 简单 API Key 认证，通过环境变量配置

```env
OPERATOR_API_KEY=your_secret_here
```

v0.1 阶段不实现认证，v0.2 引入 FastAPI 时添加。

---

## 5. 访客身份处理

| 版本 | 身份策略 |
|---|---|
| v0.1 | 全部共用 `session_id="shared"`，无访客区分 |
| v0.2 | 数据库预留 `visitor_id` 字段（TEXT，可为 NULL） |
| v0.3 | 实际访客识别（方式待确认：语音声纹、视觉识别或对话引导） |

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
| Embedding 计算失败（v0.2） | 跳过向量存储，使用时序检索作为 fallback |

---

## 7. 持久化规则

- `state_snapshots` 仅追加，绝不更新或删除
- `episodic_memories.reflected` 标志只能从 0 改为 1，不可逆
- `reflective_summaries.active` 标志：新反思生成时不删除旧记录，仅将旧记录的 active 置为 0
- 展期全程不重置任何表，仅在展期结束时归档

---

## 8. 展期终止框架（待确认）

**[ 待确认 ]** 终止仪式的具体设计尚未确定。

预留的框架性要求：
- 系统应能导出所有记忆和状态为可归档格式（JSON / CSV）
- 终止事件应作为最后一条 `interaction_log` 记录（role = 'system'）
- 终止后的数据不被自动删除
- `scripts/export_memories.py` 应在终止流程中自动调用
