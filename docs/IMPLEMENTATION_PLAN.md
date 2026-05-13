# Implementation Plan Archive

*Conscious Entity System*

---

## 状态

本文档是历史实现计划归档，不再作为活跃待办列表使用。

当前协作交接时应优先阅读：

1. `docs/progress.md` - 当前状态、交接优先级、最新 changelog
2. `docs/testlist.md` - 需要真实设备、真实供应商、现场环境或人工观察的测试列表
3. `docs/APP_FLOW.md` - 当前 turn loop、audio、vision、harness 和 identity/session gating 运行路径
4. `docs/BACKEND_STRUCTURE.md` - 数据模型、API、持久化和安全边界

旧版 checklist 中的未勾选项目不再代表当前未完成任务，避免把早期边界误读为现阶段计划。

---

## 当前交接优先级

### P0

- 完整声纹识别、视觉识别与访客库
  - 在现有 Visitor Identity & Session Gating V1 上继续做
  - 完成 voice signature / face signature capture、质量门控、历史匹配、combined confidence、自然确认和 visitor profile metadata
  - 不要求观众硬性输入身份；不因未确认身份阻断对话
- 能力自我描述回归测试与优化
  - 对齐 Stranger 对看见、听见、记得、识别、身体和移动能力的描述
  - 具体测试见 `docs/testlist.md`
- 行为测试与调优
  - 统一按 `docs/testlist.md` 执行

### P1

- 真实记忆连续性观察
- Audio / LLM / Embedding 真实供应商联调与延迟观察
- Vision 现场联调
- 多人并发 routing / 仲裁策略设计

### P2

- 非移动身体外观、声音、显示、投影和光的呈现映射
- 物理移动、循路、避障、底盘控制和安全边界
- 部署认证、展览访问控制和展期终止仪式

---

## 已完成阶段摘要

- Phase 0: 环境搭建、依赖、目录结构、YAML 配置、数据库迁移
- Phase 1: 状态机核心
- Phase 2: 短期 / 情节 / 反思记忆系统
- Phase 3: YAML 策略与 constitution 治理
- Phase 4: Claude 表达层与反思层
- Phase 5: 感知层、反思层、主循环和 CLI
- Phase 6: FastAPI 开发者 API 与 Web 看板
- Phase 7: Stranger 文本协议
- Phase 8: 可解释记忆召回、可选 embedding、Memory Preview
- Phase 9: Managed Memory proposal -> commit、influence preview/log、curation
- Phase 10: 非移动视觉层第一版，Mac 摄像头 + YOLO person detection + presence events
- Phase 11: Audio Adapter，火山 STT/TTS、stream id 安全边界、barge-in 和开发者 Audio workspace
- Phase 12: Runtime Harness System v1 与 Visitor Identity & Session Gating V1

详细 changelog 以 `docs/progress.md` 为准。
