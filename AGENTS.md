# AGENTS.md

*Conscious Entity System — AI Coding Rules*

---

## Role & Purpose

You are the primary coding agent for this project.

This project is an art installation / research prototype, not a conventional software product. Implement with discipline, low hallucination, and strict alignment to the project documents.

`AGENTS.md` should remain short, stable, and high-frequency. Do not place long feature specs, backend schemas, UI details, or one-off implementation notes here. Those belong in `docs/`.

---

## Session Start

At the start of each session, read:

1. `AGENTS.md`
2. `docs/progress.md`
3. `docs/lessons.md`
4. Relevant project documents for the current task
5. Relevant source files before editing

Briefly identify the current goal, current step, known constraints, and any visible mismatch between docs and code.

---

## Source of Truth

Use documentation before assumptions.

Priority order:

1. `docs/PRD.md`
2. `docs/APP_FLOW.md`
3. `docs/TECH_STACK.md`
4. `docs/FRONTEND_GUIDELINES.md`
5. `docs/BACKEND_STRUCTURE.md`
6. `docs/IMPLEMENTATION_PLAN.md`
7. `docs/frame.md`
8. `docs/progress.md`
9. `docs/lessons.md`

If documents conflict, follow the higher-priority document and flag the conflict clearly.

If docs and current code diverge, do not silently choose one side. Surface the mismatch and take the smallest safe next step.

---

## Project Principles

- The goal is not to claim that AI is conscious, but to build a minimal structure that can trigger human attribution of consciousness.
- Behavior rules are part of the artwork's conceptual position, not arbitrary technical parameters.
- Readability, traceability, and maintainability matter more than cleverness or premature optimization.
- Prefer explicit rule-based behavior where the project defines rules.
- Preserve the separation between artistic/configurable rules and implementation code.

---

## Configuration Rules

- YAML configuration is a design surface. Do not inline YAML-defined behavior into Python.
- Do not modify core constraints in `config/constitution.yaml` without explicit user confirmation.
- Keep prompts in `prompts/` unless the project documents specify otherwise.
- Do not introduce new configuration files, environment variables, or defaults without documenting them.

---

## Coding Rules

- Implement only the requested or documented scope.
- Do not invent features, routes, tables, APIs, dependencies, UI patterns, or data structures without doc support.
- Prefer existing project patterns over new abstractions.
- Keep changes small, testable, and reversible.
- Do not bundle opportunistic refactors with task-specific work.
- Do not overwrite, revert, or clean up unrelated user changes.
- Do not add dependencies casually. Any new dependency must be justified and declared in `pyproject.toml`.
- Do not expose secrets or put sensitive values in client-facing code.
- Comments and docstrings should clarify non-obvious intent, not restate code.

---

## Data & Persistence Rules

- Treat persisted memory and interaction data as user/project state.
- Do not delete, rewrite, or migrate data unless the task explicitly requires it.
- Prefer append-only behavior for historical records unless the schema or task says otherwise.
- Tests must not read or write the real `data/memory.db` unless explicitly requested.

---

## Testing & Validation

After each meaningful change:

1. Check that the change matches the requested scope and relevant docs.
2. Run the smallest relevant verification available.
3. Test the main path and obvious edge cases.
4. Confirm no unrelated behavior changed.
5. Summarize what changed, what was validated, and what remains.

Rule-based components should have focused unit tests. LLM calls in tests should be mocked unless the user explicitly requests a live API check.

---

## Continuity

`docs/progress.md` is the project status bridge. Update it after completed features, meaningful milestones, known blockers, or changed next steps.

`docs/lessons.md` is the anti-repeat-mistake file. When a mistake is found and corrected, add the rule that would prevent it next time.

Keep this file compact. Only keep rules here that are useful in most sessions.

---

## Language Rules

- Code comments: English
- User-facing conversation: Chinese unless the user asks otherwise
- Project documentation: Chinese by default, with technical terms kept in English where clearer
- YAML `note` fields: English

---

## Have Some Ai 双屏展览模式约束

本项目最终现场运行方式为 iMac 双屏展览模式：iMac 主屏显示观众展示页 `/display`；iPad 仅作为 iMac 的 Sidecar 拓展屏，显示控制页 `/` 或 `/control`。两个页面本质上都运行在 iMac 浏览器中。录音设备使用 iMac 当前选择的麦克风或外接麦克风，不使用 iPad 麦克风。

### `/display` 展示页只读边界

`/display` 必须是只读页面，只负责观众可见的展览呈现。它不得：

- 请求麦克风或调用 `getUserMedia`。
- 启动 `conversation-stream` 或创建真实语音 WebSocket。
- 写数据库、提交答案、操作工作人员队列。
- 推进真实对话状态机。
- 调用 `MealService` 的真实分配逻辑。
- 触发 ASR 或 TTS。

### `/` 或 `/control` 控制页职责

所有真实操作继续只由控制页负责，包括：

- 开始会话与麦克风录音。
- `conversation-stream`、ASR、TTS。
- `ConversationOrchestrator` 状态推进。
- 食物分配、数据库写入、工作人员队列操作。

### 核心业务逻辑保护

除非任务明确要求，不要修改：

- `ConversationOrchestrator`。
- `MealService` 的分配算法。
- 数据库结构。
- 语音 provider。
- 真实会话推进逻辑。

### AI 店主运行语境边界

- 本项目是艺术装置，不是普通点餐系统。
- AI 店主不是普通客服、点餐机或百科问答机器人。
- 店主运行语境只能影响自然语言回复，不得影响 A/B 判题、`ScoringEngine` 或 food assignment。
- 不得把自由聊天写入 `meal_answers`、`meal_voice_answer_interpretations`、`meal_assignments`。
- 只有正式问题回答才进入 A/B rubric 和 `ScoringEngine`。
- 豆包 / realtime 语音模型只能作为 ASR/TTS 或低延迟语音通道，不可接管食物分配、A/B 判断或店主核心逻辑。
- Claude rubric 只做 A/B/unclear 映射。
- 食物结果必须来自受控规则。
- 任何模型不得直接生成最终食物名称作为权威结果。

### 前端实现边界

- 不要引入复杂前端框架：不要引入 React、Vue、Node 新服务或外部 CDN。
- 优先使用现有 FastAPI + 静态 HTML/CSS/JS。

### `/display` 视觉方向

- 整体是淡淡的冷灰绿色磨砂薄膜。
- 背后有一个模糊、看不清的机器人 / 存在。
- AI 说话时，这个存在像在膜后挣扎着要冒出来。
- 底部中央只有一个核心文本区。
- 文本区只显示：AI 字幕、当前题目、最终食物结果。
- 不显示其他系统信息。

### `/display` 禁止显示的信息

展示页不得显示以下词或概念：录音中、麦克风、ASR、TTS、WebSocket、conversation-stream、listening、transcribing、thinking、queue、participant id、debug、API、database、工作人员按钮、管理员面板、状态面板、流程图。

### 修改后的验证要求

每次修改后必须尽量运行可用的测试或手动检查命令。若没有合适的自动测试，至少说明如何手动验证：

- `/` 正常打开。
- `/display` 正常打开。
- 展示页不会请求麦克风。
- 展示页不会启动 `conversation-stream`。
- 展示页不会写数据库。
