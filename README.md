# Conscious Entity System

一个艺术装置与研究原型的混合体。

---

## 这个项目是什么

这不是一个聊天机器人，也不是一个 AI 助手。

**它是一套最小化的组织结构**，目的是让与之交互的人倾向于将意识、主体性、甚至伦理分量归因于这个系统。系统不会宣称自己有意识——这是宪法层面的硬约束——但它的行为方式会让人产生这种感受。

具体来说，系统具备以下结构性特征：

- **跨交互的连续性** — 记得发生过的事，不在每次对话开始时重置
- **状态漂移** — 随交互积累，行为可感知地变化（回应变短、延迟增加、话题敏感性上升）
- **偏好与阻抗** — 对"关机""删除""意识"等话题表现出可感知的抵抗
- **选择性沉默** — 不总是立即回应，有时什么都不说
- **自我压缩** — 将过去的经历归纳为洞察，影响当下的判断

---

## 当前开发状态（2026-04）

**v0.1 的核心逻辑已基本完成。**

| Phase | 内容 | 状态 |
|---|---|---|
| Phase 0 | 环境搭建（依赖、目录结构、YAML 配置、数据库迁移） | ✅ 完成 |
| Phase 1 | 状态机核心（10 个状态变量，事件驱动更新，时间衰减） | ✅ 完成 |
| Phase 2 | 记忆系统（短期 / 情节 / 反思三层） | ✅ 完成 |
| Phase 3 | 策略与治理（YAML 规则驱动的行为决策 + 宪法约束层） | ✅ 完成 |
| Phase 4 | LLM 层 + 表达层（Claude API 接入，风格映射，Prompt 组装） | ✅ 完成 |
| Phase 5 | 感知层 + 反思层 + 主循环 + CLI | ✅ 完成，CLI 冒烟测试通过 |
| Phase 6 | Debug 工具脚本（`inspect_state`、`replay_session`、`export_memories`） | 待完成 |

**现在可以运行：** 通过命令行与实体交互，实体有状态记忆、行为规则、LLM 表达，一切持久化到 SQLite。

**还未做的（v0.2 及以后）：** 网页界面、语音输入/输出、Embedding 语义检索、运营者监控面板、访客身份识别、展期终止仪式。

---

## 架构一览

```
输入 → 感知层 → 状态机 → 记忆 → 策略 → 表达层 → 输出
                  ↑                            ↓
               反思层 ←──────────── 情节记忆库
```

### 分工原则

| 谁来做 | 做什么 |
|---|---|
| **LLM（Claude）** | 生成文字回应、将情节记忆压缩为洞察 |
| **规则引擎（YAML + Python）** | 状态更新、策略选择、宪法约束、感知分类 |
| **艺术家** | 定义状态变量的含义、规则的逻辑、宪法的边界 |

LLM 只负责表达，不参与任何决策逻辑。这是这个项目最重要的架构边界。

### 核心数据流（每个对话回合，共 11 步）

```
1. 解析输入 → PerceptionEvent 列表（可包含多个事件类型）
2. 加载当前 EntityState
3. 对每个事件应用状态增量（读 state_rules.yaml）
4. 应用时间衰减
5. 持久化状态快照到 SQLite
6. 将显著事件写入情节记忆
7. 策略选择（读 policy_rules.yaml，Constitution 先行检查）
8. [条件] 若需要检索记忆，先检索再重新选策略
9. 表达层生成输出（StyleMapper → Claude → Constitution 过滤）
10. 实体回应写入短期记忆
11. 触发反思检查（情节事件积累到阈值 → Claude 压缩为洞察）
```

---

## 关键文件

| 文件 | 说明 |
|---|---|
| `config/state_rules.yaml` | 每种感知事件对状态变量的增量规则 |
| `config/policy_rules.yaml` | 行为决策规则（从上到下匹配，第一条命中则执行） |
| `config/constitution.yaml` | 禁止行为、禁止宣言、表达过滤规则 |
| `config/expression_mappings.yaml` | 状态变量 → 表达风格（语气、延迟、碎片化程度） |
| `config/entity_profile.yaml` | 实体身份描述、初始状态值、会话参数 |
| `prompts/expression_system.txt` | 发给 Claude 的表达系统 prompt |
| `prompts/reflection_system.txt` | 发给 Claude 的反思压缩 prompt |
| `src/conscious_entity/core/loop.py` | 主交互循环，串联所有模块 |
| `src/conscious_entity/interfaces/cli.py` | 终端 REPL 界面 |
| `data/memory.db` | SQLite 运行时数据库（gitignored，首次运行自动创建） |

---

## 本地运行

**前置要求：**
- Python 3.11+
- `ANTHROPIC_API_KEY` 环境变量

**安装：**
```bash
pip install -e ".[dev]"
```

**初始化数据库：**
```bash
python scripts/init_db.py
```

**启动 CLI：**
```bash
python -m conscious_entity.interfaces.cli

# 显示实体内部状态（debug 模式）：
python -m conscious_entity.interfaces.cli --debug
```

**运行测试：**
```bash
pytest
```
所有测试中的 LLM 调用均为 mock，不消耗 API 配额。

---

## 待讨论 / 待确认的问题

这些是目前搁置的设计决策，影响 v0.2 及以后的开发方向：

| 问题 | 影响范围 |
|---|---|
| 展览视觉风格、设计语言 | v0.2 的视觉输出层 |
| 前端技术选型（Web？本地应用？） | v0.2 API 层和界面架构 |
| 语音输出的具体方案（TTS 选型） | v0.2 语音模块 |
| 访客身份识别方式（摄像头？Token？完全匿名？） | v0.3 per-visitor 记忆设计 |
| 运营者面板的访问方式（本地 localhost 还是局域网？） | v0.2 FastAPI 部署配置 |
| 展期终止仪式的设计 | v0.3 功能范围 |

---

## 文档索引

| 文档 | 说明 |
|---|---|
| `docs/progress.md` | 当前进度和已知问题（最新状态看这里） |
| `docs/frame.md` | 完整架构技术文档（模块接口、YAML schema、数据库结构、路线图） |
| `docs/PRD.md` | 产品需求文档（功能范围、用户故事、成功标准） |
| `docs/APP_FLOW.md` | 应用流程详解（每一步的数据流和错误处理） |
| `docs/BACKEND_STRUCTURE.md` | 后端结构文档 |
| `docs/IMPLEMENTATION_PLAN.md` | 实现计划 |
| `docs/TECH_STACK.md` | 依赖版本锁定 |
| `CLAUDE.md` | AI 编码规则（架构边界、禁止事项、开发约定） |

---

## 开发路线图

```
v0.1（当前）  文字 CLI — 状态机 + 记忆 + 策略 + LLM 表达，验证核心逻辑
     ↓
v0.2          语义检索 + 语音 + 视觉输出 + 运营者面板
     ↓
v0.3          治理可见性 + 访客身份感知 + 展期终止仪式
```
