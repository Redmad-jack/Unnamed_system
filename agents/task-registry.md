# Task Registry

Tracks which files are currently being worked on by which agent.
Prevents conflicts when multiple agents operate in the same codebase.

---

## Format

```
| File | Agent | Status | Started |
|------|-------|--------|---------|
| config/entity_profile.yaml | Codex | done | 2026-05-06 |
| prompts/expression_system.txt | Codex | done | 2026-05-06 |
| src/conscious_entity/perception/relationship_detector.py | Codex | done | 2026-05-06 |
| src/conscious_entity/perception/text_parser.py | Codex | done | 2026-05-06 |
| tests/unit/test_context_builder.py | Codex | done | 2026-05-06 |
| tests/unit/test_text_parser.py | Codex | done | 2026-05-06 |
| docs/progress.md | Codex | done | 2026-05-06 |
| docs/lessons.md | Codex | done | 2026-05-06 |
| agents/task-registry.md | Codex | done | 2026-05-06 |
```

Status values: `in_progress`, `done`

---

## Current Tasks

| File | Agent | Status | Started |
|------|-------|--------|---------|
