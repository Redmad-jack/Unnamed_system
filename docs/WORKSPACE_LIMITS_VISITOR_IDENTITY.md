# User Workspace Limits: Visitor Library + Visitor Recognition

本文档给负责 **访客库 + 访客识别** 的工作区使用。目标是在现有 Visitor Identity & Session Gating V1 基础上，补齐访客注册表、face / voice signature、历史匹配、combined confidence、自然确认和跨 session 记忆连续性。该工作不负责输出延迟、TTS/STT 协议、barge-in 播放链路或行为状态微调。

## Ownership

建议工作分支：

```bash
git worktree add ../Unnamed_sys_visitor_identity -b feat/visitor-identity-library
```

主要目标：

- 设计并实现访客库 V1 schema / metadata。
- 接入 face signature 和 voice signature 的采集结果。
- 做质量门控：人脸清晰度、角度、遮挡、尺寸；语音长度、质量、噪声。
- 做历史匹配：face confidence、voice confidence、combined confidence。
- 做自然确认：高置信候选时非强制询问，不回答也继续对话。
- 保护当前 V1 约束：单 primary visitor session，presence 不创建 session，插入只记录事件。

## Preferred Write Scope

优先修改这些文件或目录：

- `src/conscious_entity/identity/`
- `src/conscious_entity/vision/`
- `src/conscious_entity/db/migrations.py`
- `src/conscious_entity/interfaces/api_runtime.py`
- `src/conscious_entity/interfaces/api_routes.py`
- `src/conscious_entity/interfaces/api_models.py`
- `src/conscious_entity/memory/retrieval.py`
- `src/conscious_entity/core/loop.py`
- `docs/APP_FLOW.md`
- `docs/BACKEND_STRUCTURE.md`
- `docs/progress.md`
- `docs/testlist.md`
- visitor / identity / memory continuity 相关测试

可以新增的内容：

- visitor profile metadata 结构。
- face / voice signature reference，不直接暴露 raw biometric data。
- identity match result 类型。
- candidate visitor、confirmation pending、confirmation accepted / rejected 状态。
- combined confidence 算法。
- 访客识别 API 和开发者状态展示。
- 跨 session visitor memory continuity 测试。

## Avoided Scope

未经协调不要修改：

- `src/conscious_entity/audio/volcengine_*`
- `src/conscious_entity/audio/manager.py`
- `src/conscious_entity/interfaces/api_audio.py`
- TTS playback queue、barge-in、音频 WebSocket 协议。
- latency tracker 的计时语义。
- state / policy / prompt 的人格和行为微调，除非只是为了注入 identity context 且先协调。

不要做这些事：

- 不要因为检测到人就自动创建 session。
- 不要在 active dialogue 中直接切换 primary visitor。
- 不要启用 group session，当前 V1 仍保持单 primary visitor。
- 不要要求观众必须输入姓名或 ID。
- 不要把未确认 candidate 当成已确认 visitor。
- 不要把 face / voice 原始数据直接展示在开发者面板。
- 不要把低置信匹配写成确定身份。

## Shared Files

这些文件属于高冲突区，修改前需要和延迟/行为负责人确认：

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

- 访客识别侧只负责 turn 前 identity/session metadata、visitor scope、candidate confirmation 和 memory retrieval 边界。
- 不改变延迟侧的 latency step、background task、audio scheduling 或 TTS playback hooks。
- 不改变行为侧的 state、policy、prompt、constitution、expression 语义结果，除非该结果明确依赖 identity context。
- 保持 `/dialog`、`/audio/dialog` 的输入契约兼容。

## Interface Contract

访客识别侧可以影响：

- `identity_session` metadata。
- `primary_visitor_id`。
- `candidate_visitor_id`。
- `face_confidence_level`。
- `voice_confidence_level`。
- `combined_confidence_level`。
- `waiting_for_identity_confirmation`。
- `interruption_count`。
- visitor profile metadata。
- visitor-scoped memory retrieval。

访客识别侧不应该影响：

- TTS session 协议。
- STT chunk 格式。
- playback ready / speaking / stopped 状态。
- latency step 统计语义。
- Stranger 的通用人格规则。
- `ExpressionOutput` 播放方式。

开发者面板展示原则：

- 可以展示 runtime state、session decision、candidate、confidence level、confirmation state、质量摘要、signature reference。
- 不展示原始人脸图、原始音频、face embedding、voice embedding。
- 不把完整访客库暴露给 visitor-facing surface。

## Required Checks

提交前至少运行：

```bash
PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_identity_session_gating.py
PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_memory_retrieval.py
PYTHONPATH=src python3 -m pytest -p no:debugging tests/integration/test_full_loop.py
PYTHONPATH=src python3 -m pytest -p no:debugging
```

如果修改前端 dashboard：

```bash
node --check src/conscious_entity/interfaces/static/dashboard.js
```

如果修改数据库迁移：

```bash
PYTHONPATH=src python3 -m py_compile src/conscious_entity/db/migrations.py
```

## Handoff Checklist

合入前说明：

- 改了哪些 visitor schema、metadata 或 migration。
- face / voice signature 是否只保存 reference 和质量摘要。
- confidence 阈值和 combined confidence 逻辑是什么。
- candidate visitor 如何确认、拒绝或降级为 unidentified。
- active dialogue 中插入者如何记录，是否仍保持单 primary visitor。
- 是否改变 visitor-scoped memory retrieval。
- 是否触碰了 audio / latency / behavior 共享文件。
- 哪些现场测试仍需执行，尤其是数据库污染、误识别、记忆泄漏和跨 session continuity。

最终同步时，本工作区的验收标准是：系统能更可靠地判断“可能是谁”、以非强制方式确认身份，并把确认后的 visitor 用于跨 session 记忆连续性，同时不干扰输出延迟调优和行为状态微调。
