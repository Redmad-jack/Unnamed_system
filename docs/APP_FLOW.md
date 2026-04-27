# Application Flow

*Conscious Entity System — v0.1*

---

## 1. 系统路径概览

系统有两条并行的主路径：

```
访客路径：  [输入] → 感知层 → 状态更新 → 策略选择 → LLM 表达 → [输出]
运营者路径：[监控面板] ← 实时状态 / 对话历史 / 决策日志
```

---

## 2. 访客路径

### 2.1 进入（Session 启动）

**触发条件：** 新的 CLI 会话启动，或访客接近展览装置（v0.2 presence detection）

**流程：**
```
系统加载最新状态快照（来自 SQLite）
  ↓
短期记忆缓冲区清空（仅当前 session 上下文）
  ↓
实体触发 USER_ENTERED 事件
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

**流程（12步，见 `src/conscious_entity/core/loop.py`）：**

```
Step 1   感知层解析输入 → 生成 PerceptionEvent 列表
          └─ 可能产生多个事件：USER_SPOKE + SHUTDOWN_KEYWORD_DETECTED 等

Step 2   加载当前 EntityState

Step 3   对每个事件应用状态增量（state_rules.yaml）
          └─ 返回新 EntityState（不可变更新）

Step 4   应用时间衰减（per-turn 模式在 v0.1）

Step 5   持久化状态快照到 SQLite（state_snapshots 表）

Step 6   将显著事件（salience ≥ 0.5）存入情节记忆（episodic_memories 表）

Step 7   策略选择
          └─ PolicySelector 从上到下匹配 policy_rules.yaml
          └─ Constitution 先行检查是否允许
          └─ 返回 PolicyDecision（含 action + rationale）

Step 8   [条件] 若 action == RETRIEVE_MEMORY_FIRST
          └─ 检索相关记忆（v0.1 使用时序检索，v0.2 改为 embedding 检索）
          └─ 重新进行策略选择

Step 9   店主 scene router 生成结构化回合
          └─ language / scene / action / state_updates / next_scene
          └─ 菜单归一化只允许 ai_miao / no_ai

Step 10  表达层生成输出
          └─ ShopkeeperPromptBuilder 组装受控 prompt
          └─ StyleMapper 计算 StyleHints（tone, delay, fragmentation, visual_mode）
          └─ ClaudeClient 调用 LLM
          └─ Constitution + ResponseGuard 过滤输出文本

Step 11  将店主状态写入 shop_state_snapshots，并将实体回应加入短期记忆缓冲

Step 12  触发反思检查
          └─ 若未反思事件数 ≥ threshold → 调用 ReflectionEngine
          └─ 存储反思摘要到 reflective_summaries 表
          └─ 标记已处理的情节记忆
```

**成功状态：** 返回 ExpressionOutput（text + delay_ms + visual_mode + turn）
**错误状态：**
- LLM 调用失败 → 使用规则生成 fallback 回应（简短、中性）
- 数据库写入失败 → 记录日志，但不中断对话流程

**店主模式输入：**
- CLI 仍使用纯文本输入。
- API `POST /api/v1/dialog` 支持 `text`、`asr_text`、`visual_tags`、`retrieved_context`。
- `visual_tags` 只接受配置白名单内的保守标签，未知标签会被忽略。

---

### 2.3 离开（Session 关闭）

**触发条件：** 访客停止输入，或 `USER_LEFT` 事件（presence detection，v0.2）

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

## 3. 运营者路径（v0.1 为 debug 脚本，v0.2 升为面板）

### 3.1 查看当前状态

**v0.1 方式：**
```bash
python scripts/inspect_state.py
```
输出当前 EntityState 所有字段值 + 最近 5 条策略决策

**v0.2 方式：** FastAPI `/state` 端点 → 运营者专用 Web 界面（观众不可见）

---

### 3.2 查看对话历史

**v0.1 方式：**
```bash
python scripts/export_memories.py
```
导出 interaction_log 和 episodic_memories 为 JSON

**v0.2 方式：** FastAPI `/memory` 端点

---

### 3.3 重播会话

**触发条件：** 研究者需要重现特定行为轨迹

```bash
python scripts/replay_session.py --session-id <id>
```

---

## 4. 系统内部：完整 Turn 状态机

```
                    ┌──────────────────────┐
                    │   raw user input     │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   TextParser         │ → [PerceptionEvent, ...]
                    │   KeywordDetector    │
                    │   SalienceScorer     │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   StateEngine        │ → new EntityState
                    │   (apply deltas)     │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   StateStore         │ → SQLite snapshot
                    │   EpisodicStore      │ → SQLite episodic row
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   PolicySelector     │ → PolicyDecision
                    │   + Constitution     │   (action + rationale)
                    └──────────┬───────────┘
                               │
               ┌───────────────┼───────────────┐
               │ RETRIEVE_MEMORY_FIRST?         │
               │               │               │
          ┌────▼────┐   ┌──────▼──────┐        │
          │Retriever│   │ skip memory │        │
          └────┬────┘   └──────┬──────┘        │
               └───────────────┘               │
                               │               │
                    ┌──────────▼───────────┐   │
                    │   ExpressionEngine   │   │
                    │   ContextBuilder     │   │
                    │   StyleMapper        │   │
                    │   ClaudeClient       │   │
                    │   Constitution filter│   │
                    └──────────┬───────────┘   │
                               │               │
                    ┌──────────▼───────────┐   │
                    │   ExpressionOutput   │   │
                    │   text + delay_ms    │   │
                    │   visual_mode        │   │
                    └──────────┬───────────┘   │
                               │               │
                    ┌──────────▼───────────┐   │
                    │   ReflectionEngine   │   │
                    │   (maybe_reflect)    │   │
                    └──────────────────────┘   │
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

---

## 6. 待确认

- **[ 待确认 ]** 访客端展示界面的具体页面结构（v0.2 视觉层尚未设计）
- **[ 待确认 ]** 运营者面板的具体页面布局和访问方式（本地 localhost？还是局域网访问？）
- **[ 待确认 ]** presence detection 的具体触发机制（摄像头？距离传感器？）
