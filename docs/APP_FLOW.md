# Application Flow

*Conscious Entity System — current text system + developer API*

---

## 1. 系统路径概览

系统有两条并行的主路径：

```
访客路径：  [输入] → 感知层 → 状态更新 → managed memory preview → 策略/记忆召回 → LLM 表达 → [输出]
运营者路径：[本地开发者面板] ← 实时状态 / 对话历史 / Memory Preview / Managed Memory Curation
```

---

## 2. 访客路径

### 2.1 进入（Session 启动）

**触发条件：** 新的 CLI / API runtime 会话启动，或后续 presence detection 触发访客进入

**流程：**
```
系统加载最新状态快照（来自 SQLite）
  ↓
从 interaction_log 恢复当前 session 最近对话窗口，作为短期上下文
  ↓
如有 presence event，则触发 USER_ENTERED
  ↓
状态更新：arousal +0.15, attention_focus +0.2, fatigue -0.05
  ↓
策略可能触发欢迎或沉默（取决于当前 resistance / trust 水平）
```

**成功状态：** 系统就绪，等待访客输入
**错误状态：** 数据库连接失败 → fallback 到默认初始状态，记录错误日志

---

### 2.2 对话回合（Turn Loop）

**触发条件：** 访客提交文字输入

**当前流程（见 `src/conscious_entity/core/loop.py`）：**

```
Step 1   感知层解析输入 → 生成 PerceptionEvent 列表
          └─ 可能产生多个事件：USER_SPOKE + SHUTDOWN_KEYWORD_DETECTED 等

Step 2   将用户输入加入短期记忆
          └─ 重复追问、连续服务请求等判断可以看见当前输入

Step 3   加载当前 EntityState，并对每个事件应用状态增量（state_rules.yaml）
          └─ 返回新 EntityState（不可变更新）

Step 4   应用 per-turn 时间衰减

Step 5   预览 managed memory influence
          └─ preview_influence() 不写入数据库
          └─ 只应用被允许的 state deltas，并通过 clamp_all() 限制到 [0,1]

Step 6   持久化状态快照到 SQLite（state_snapshots 表）

Step 7   将显著事件（salience ≥ 0.5）存入情节记忆（episodic_memories 表）
          └─ embedding 可用时补写向量；失败时退回可解释召回

Step 8   策略选择
          └─ PolicySelector 从上到下匹配 policy_rules.yaml
          └─ Constitution 先行检查是否允许
          └─ 返回 PolicyDecision（含 action + rationale）
          └─ managed memory policy influence 可把开放回应牵引为选择性记忆召回

Step 9   [条件] 若策略或 managed memory 要求检索记忆
          └─ 检索当前 session 的最近对话、情节记忆和反思摘要
          └─ embedding 启用时，同 `session_type` 的语义池可参与 hybrid retrieval
          └─ 默认使用可解释排序；启用 embedding 时使用 hybrid retrieval
          └─ `RETRIEVE_MEMORY_FIRST` 取回材料后进入开放表达，其它检索策略保持原 action

Step 10  表达层生成输出
          └─ ContextBuilder 组装 ExpressionContext
          └─ StyleMapper 计算 StyleHints（tone, delay, fragmentation, visual_mode）
          └─ ClaudeClient 调用 LLM
          └─ Constitution 过滤输出文本

Step 11  将实体回应加入短期记忆缓冲

Step 12  写入 interaction_log，并记录 memory_influence_log
          └─ influence log 记录 expression / policy / state 影响，不公开 prompt 或 YAML 全量规则

Step 13  生成 managed memory proposal，并在 auto-commit 开启时提交
          └─ propose() 不直接改变行为记忆
          └─ commit() 后才进入 committed managed memories

Step 14  触发反思检查
          └─ 若未反思事件数 ≥ threshold → 调用 ReflectionEngine
          └─ 存储反思摘要到 reflective_summaries 表
          └─ 标记已处理的情节记忆

Step 15  发送 turn_complete 到 EventBus，供调试或后续 instrumentation 使用
```

**成功状态：** 返回 ExpressionOutput（text + delay_ms + visual_mode）
**错误状态：**
- LLM 调用失败 → 使用规则生成 fallback 回应（简短、中性）
- 数据库写入失败 → 记录日志，但不中断对话流程
- embedding、managed memory proposal/commit、reflection 失败 → 记录日志，并降级继续主对话

---

### 2.3 离开（Session 关闭）

**触发条件：** 访客停止输入，或后续 presence detection 触发 `USER_LEFT` 事件

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
TextParser / KeywordDetector / SalienceScorer
  → [PerceptionEvent, ...]
  ↓
ShortTermMemory.add(user)
  ↓
StateEngine.apply_event(...) + apply_decay(...)
  → new EntityState
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
  → ContextBuilder + StyleMapper + ClaudeClient + Constitution filter
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

---

## 6. 待确认

- **[ 待确认 ]** 访客端展示界面的具体页面结构（后续视觉层尚未设计）
- **[ 待确认 ]** 运营者面板的具体页面布局和访问方式（本地 localhost？还是局域网访问？）
- **[ 待确认 ]** presence detection 的具体触发机制（摄像头？距离传感器？）
