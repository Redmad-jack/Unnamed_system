# Collaborator Workspace Limits: Output Latency + Behavior Tuning

本文档给负责 **输出延迟调优 + 行为状态微调** 的协作者使用。目标是降低对话响应和语音输出延迟，同时微调 Stranger 的行为状态、表达倾向和运行时表现。该工作不负责访客库、访客身份识别、face / voice signature 或 visitor profile 持久化。

## Ownership

建议工作分支：

```bash
git worktree add ../Unnamed_sys_latency_behavior -b feat/latency-behavior-tuning
```

主要目标：

- 优化 STT final transcript 到 turn loop 的路径。
- 优化 LLM 输出后的 TTS 创建、播放、停止、恢复和 barge-in。
- 维护 step-level latency、audio latency、TTS/STT 状态可见性。
- 微调 state、policy、prompt、expression，让 Stranger 的回应节奏、沉默、拒绝、延迟和状态变化更符合设定。
- 保持现有访客身份接口兼容，不新增或重构访客库 schema。

## Preferred Write Scope

输出延迟相关优先修改：

- `src/conscious_entity/audio/`
- `src/conscious_entity/interfaces/api_audio.py`
- `src/conscious_entity/telemetry/`
- audio / latency 相关测试

行为状态相关优先修改：

- `config/`
- `prompts/`
- `src/conscious_entity/state/`
- `src/conscious_entity/policy/`
- `src/conscious_entity/expression/`
- `src/conscious_entity/harness/`
- 行为、prompt、state、policy 相关测试

开发者面板可修改：

- `src/conscious_entity/interfaces/static/dashboard.js`
- `src/conscious_entity/interfaces/static/dashboard.css`

但仅限：

- Audio Adapter 状态显示。
- Latency / diagnostics 显示。
- Harness / state / policy / expression 的可观察性。
- 不加入访客识别配置、访客库管理或 biometric 详情展示。

## Avoided Scope

未经协调不要修改：

- `src/conscious_entity/identity/`
- `src/conscious_entity/vision/` 中的人脸识别、身份匹配相关未来实现。
- `src/conscious_entity/interfaces/api_runtime.py` 中 visitor profile 创建、绑定、切换逻辑。
- `src/conscious_entity/interfaces/api_routes.py` 中 `/api/v1/visitors*` 和 `/api/v1/identity/status` 的 visitor schema 语义。
- `src/conscious_entity/db/migrations.py` 中 visitor profile / biometric / identity schema。
- `src/conscious_entity/memory/retrieval.py` 中 visitor scope 召回规则，除非只修复明显 bug 且先协调。

不要做这些事：

- 不要新增 face signature / voice signature 字段。
- 不要改变 `visitor_profiles.metadata` 的结构。
- 不要把 identity confidence 硬编码进 prompt 或 policy。
- 不要把语音说话人变化直接绑定为 visitor 切换。
- 不要为了降低延迟跳过 constitution filter 或绕过 `ExpressionOutput`。
- 不要把原始音频、原始图像、人脸 embedding、声纹 embedding 暴露到开发者面板。

## Shared Files

这些文件属于高冲突区，修改前需要和访客库负责人确认：

- `src/conscious_entity/core/loop.py`
- `src/conscious_entity/interfaces/api_runtime.py`
- `src/conscious_entity/interfaces/api_routes.py`
- `src/conscious_entity/interfaces/static/dashboard.js`
- `src/conscious_entity/interfaces/static/dashboard.css`
- `docs/APP_FLOW.md`
- `docs/BACKEND_STRUCTURE.md`
- `docs/progress.md`
- `docs/testlist.md`

如果必须修改 `loop.py`：

- 延迟/行为侧可以调整 latency trace、background task、state、policy、prompt、constitution、expression 的执行方式。
- 不改变 `identity_session` metadata 的字段名、含义和传递位置。
- 不删除 visitor scope、visitor memory continuity 或 identity/session gating 进入 harness trace 的逻辑。
- 如果重排同步/异步路径，必须确认访客识别负责人仍能在 turn 前注入 identity context。

## Interface Contract

延迟/行为侧可以影响：

- `ExpressionOutput.text`
- `ExpressionOutput.spoken_text`
- `ExpressionOutput.delay_ms`
- `ExpressionOutput.visual_mode`
- state snapshot
- policy action
- harness trace summary / metadata
- STT/TTS/playback/barge-in 生命周期
- latency step 统计

延迟/行为侧不应该影响：

- `visitor_profiles` schema。
- `visitor_id` 绑定语义。
- face / voice / combined confidence 的计算逻辑。
- candidate visitor 的确认流程。
- 访客库持久化。
- 同一 visitor 跨 session 的记忆召回边界。

TTS 输入必须来自已过滤后的输出：

- 优先 `ExpressionOutput.spoken_text`。
- 为空时使用 `ExpressionOutput.text`。
- 不允许 visitor/body 直接提交任意 raw text 让 Stranger 朗读，除非显式处于 debug raw TTS 模式。

## Required Checks

提交前至少运行：

```bash
PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_api_audio.py
PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_audio_manager.py
PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_harness_trace.py
PYTHONPATH=src python3 -m pytest -p no:debugging
```

如果修改前端 dashboard：

```bash
node --check src/conscious_entity/interfaces/static/dashboard.js
```

## Handoff Checklist

合入前说明：

- 改了哪些 STT/TTS、playback、barge-in 或 latency 路径。
- 改了哪些 state、policy、prompt、constitution 或 expression 行为。
- 是否新增、删除或重命名 API 返回字段。
- 是否触碰了 visitor / identity 相关共享文件。
- 是否改变了 `ExpressionOutput` 字段含义。
- 真实供应商测试结果：每轮 STT、LLM、TTS、playback 的大致耗时和失败情况。
- 哪些行为需要人工观察。

最终同步时，本工作区的验收标准是：输出更快、更稳定、更容易打断，行为状态更贴近目标设定，但不改变访客识别、访客库和跨 session 访客记忆的职责边界。
