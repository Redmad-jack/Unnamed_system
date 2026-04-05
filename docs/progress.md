# Progress

*Conscious Entity System*

---

## 已完成

- [x] `data/initial_conscious_entity_framework.md` — 原始提案（v0.1）
- [x] `docs/frame.md` — 完整架构技术文档（目录结构、模块接口、YAML schema、SQLite 建表、开发路线图、测试策略）
- [x] 需求调研（interrogation 阶段）— 明确用户、场景、记忆持久性、访客身份策略、运营者需求
- [x] 项目文档环境建设：
  - [x] `docs/PRD.md`
  - [x] `docs/APP_FLOW.md`
  - [x] `docs/TECH_STACK.md`
  - [x] `docs/FRONTEND_GUIDELINES.md`
  - [x] `docs/BACKEND_STRUCTURE.md`
  - [x] `docs/IMPLEMENTATION_PLAN.md`
  - [x] `CLAUDE.md`
  - [x] `docs/progress.md`
  - [x] `docs/lessons.md`

---

## 进行中

- 无

---

## 下一步

- [ ] **Phase 0：环境搭建** — `pyproject.toml`、目录结构、YAML 配置文件、`config_loader.py`
- [ ] **Phase 1：状态机核心** — `EntityState`、`StateEngine`、`StateStore`、数据库迁移

---

## 已知问题 / 待确认事项

| 项目 | 状态 | 影响 |
|---|---|---|
| 访客身份识别方式 | 待确认（v0.3） | 影响 BACKEND_STRUCTURE 中 visitor_id 字段设计 |
| 视觉风格 / 设计语言 | 待确认 | 影响 FRONTEND_GUIDELINES + 展览界面开发 |
| 前端技术选型 | 待确认 | 影响 v0.2 开发路径 |
| 展期终止仪式设计 | 待确认 | 影响 v0.3 功能范围 |
| 运营者面板访问方式 | 待确认 | 影响 FastAPI 部署配置 |
| TTS 具体选型 | 待确认 | 影响 v0.2 语音输出实现 |

---

## 当前重点

完成 v0.1 核心逻辑（Phase 0 → Phase 6），优先顺序：

```
Phase 0（环境）→ Phase 1（状态机）→ Phase 2（记忆）
→ Phase 3（策略）→ Phase 4（LLM）→ Phase 5（主循环）→ Phase 6（Debug 工具）
```
