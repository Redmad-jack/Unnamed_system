# Harness Architecture

*Runtime Harness System v1*

---

## 1. 目标

Harness 不是一个新的模型，也不是新的 constitution。第一版目标是把当前分散在 perception、state、memory、policy、prompt、generation、output、audio/presentation 中的约束和影响整理成可观察的运行结构。

当前策略：

- 不训练模型
- 不修改 `config/constitution.yaml`
- 不改变现有 `/dialog`、`/audio/dialog`、`/visitor` 行为契约
- 不新增数据库表
- 只做 trace、命名、开发者可见性和测试基线

---

## 2. 分层

| Layer | 当前职责 | 能否拒绝 | 能否改写 | 能否影响长期记忆 |
|---|---|---:|---:|---:|
| Input Harness | 标注输入来源、输入模式和 perception event | 否 | 否 | 否 |
| State Harness | 记录 state rules、decay、bounded memory deltas 的影响 | 否 | 否 | 间接影响 |
| Memory Harness | 记录 managed memory preview 和 retrieval 路径 | 否 | 否 | 是，但只通过 proposal/commit |
| Policy Harness | 记录 policy rule 命中、constitution veto、managed memory policy influence | 是 | 否 | 否 |
| Prompt Harness | 记录 prompt partial 注入情况 | 否 | 否 | 否 |
| Generation Harness | 记录 LLM generation / fallback / truncation | 否 | 否 | 否 |
| Output Harness | 记录 constitution expression filter 和 forbidden claim 检测 | 是，当前只警告/过滤 | 是，regex filter | 否 |
| Presentation Harness | 记录 `ExpressionOutput` 如何进入文字、视觉、声音呈现 | 否 | 否 | 否 |

第一版 `Generation Harness` 只预留观测位置，不做 streaming guard。后续如要做流式拦截，应在这一层扩展。

---

## 3. Trace 类型

内部类型位于 `src/conscious_entity/harness/`：

- `HarnessLayer`
- `HarnessLayerTrace`
- `HarnessTrace`
- `HarnessTraceRecorder`
- `HarnessTraceStore`

每层 trace 记录：

- `layer`
- `status`
- `rule_ids`
- `decision`
- `summary`
- `metadata`
- `timestamp`

`HarnessTraceStore` 是进程内 ring buffer。它不会写入 SQLite，进程重启后清空。这样第一版不会引入迁移风险，也不会污染 interaction log 或 memory tables。

---

## 4. Prompt 与敏感信息边界

开发者 API 和面板不暴露完整 hidden prompt。Prompt Harness 只显示：

- partial 名称，例如 `expression_system`、`state_context`、`memory_context`、`input_context`
- 是否注入 memory context
- 是否注入 voice transcript input context
- message count
- max tokens

完整 `raw_prompt` 仍只留在 `ExpressionOutput` 的调试字段中，现有行为不在本次重构中改变。

---

## 5. API

只读端点：

- `GET /api/v1/harness/status`
  - 返回启用状态、layer 列表、ring buffer 类型、最近一轮 summary
- `GET /api/v1/harness/trace/recent?limit=20`
  - 返回最近 N 轮 public trace

这些端点用于开发者面板和调试，不面向 visitor surface。

---

## 6. 人工确认边界

以下内容仍必须人工确认，不能由 harness 自动修改：

- constitution 内容
- prompt 文件语义规则
- managed memory 权重或全局策略
- 展陈模式下的访客身份、多用户仲裁、路由策略
- 任何会改变核心人格边界的 policy rule

Harness v1 只把这些影响变得可见，不替研究者做价值判断。
