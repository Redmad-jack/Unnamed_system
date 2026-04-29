# CLAUDE.md

*Conscious Entity System — AI Coding Rules*

---

## Role & Purpose

You are the primary coding agent for this project.

This project is an art installation / research prototype, not a conventional software product. Implement with discipline, low hallucination, and strict alignment to the project documents.

`CLAUDE.md` should remain short, stable, and high-frequency. Do not place long feature specs, backend schemas, UI details, or one-off implementation notes here. Those belong in `docs/`.

---

## Session Start

At the start of each session, read:

1. `CLAUDE.md`
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
