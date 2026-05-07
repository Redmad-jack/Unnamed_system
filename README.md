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

**核心逻辑与 Stranger 文本协议已可运行。**

| Phase | 内容 | 状态 |
|---|---|---|
| Phase 0 | 环境搭建（依赖、目录结构、YAML 配置、数据库迁移） | ✅ 完成 |
| Phase 1 | 状态机核心（底层运行状态 + Stranger 关系状态，事件驱动更新，时间衰减） | ✅ 完成 |
| Phase 2 | 记忆系统（短期 / 情节 / 反思三层） | ✅ 完成 |
| Phase 3 | 策略与治理（YAML 规则驱动的行为决策 + 宪法约束层） | ✅ 完成 |
| Phase 4 | LLM 层 + 表达层（Claude API 接入，风格映射，Prompt 组装） | ✅ 完成 |
| Phase 5 | 感知层 + 反思层 + 主循环 + CLI | ✅ 完成，CLI 冒烟测试通过 |
| Phase 6 | Debug 工具脚本 + FastAPI 开发者 API + Web 看板 | ✅ 完成 |
| Phase 7 | Stranger 文本协议（身份拒绝、命名失败、拒绝服务、局部追溯、选择性记忆） | ✅ 完成 |
| Phase 8 | 记忆召回增强（可解释召回 + 可选 embedding 语义召回 + Memory Preview） | ✅ 完成 |

**现在可以运行：** 通过命令行或本地 Web 看板与 Stranger 交互，实体有状态记忆、行为规则、LLM 表达和文本关系姿态识别，一切持久化到 SQLite。

**还未做的（后续阶段）：** 语音输入/输出、摄像头/空间感知、访客身份识别、展期终止仪式。

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
| **LLM（Claude）** | 生成文字回应、将情节记忆压缩为洞察、提出可审计的 managed memory 候选 |
| **规则引擎（YAML + Python）** | 状态更新、策略选择、宪法约束、感知分类、控制 managed memory 的可预览影响边界 |
| **艺术家** | 定义状态变量的含义、规则的逻辑、宪法的边界 |

LLM 不直接改写 YAML、宪法、核心状态权重或策略规则。它可以通过 proposal → commit 的 managed memory 流程参与长期记忆形成；进入行为路径的影响必须可预览、可记录、可回滚。

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
| `src/conscious_entity/interfaces/api.py` | FastAPI app 入口，保持 `conscious_entity.interfaces.api:app` 稳定 |
| `src/conscious_entity/interfaces/api_models.py` | API 请求模型 |
| `src/conscious_entity/interfaces/api_runtime.py` | API lifespan、runtime 配置、数据库辅助函数 |
| `src/conscious_entity/interfaces/api_routes.py` | API 路由处理函数 |
| `src/conscious_entity/interfaces/cli.py` | 终端 REPL 界面 |
| `data/memory.db` | SQLite 运行时数据库（gitignored，首次运行自动创建） |

---

## 本地运行

以下命令默认在项目根目录执行：

```bash
cd /Users/jackzhang/Unnamed_sys
```

**前置要求：**
- Python 3.11+
- 可用的 LLM 凭证，三选一：
  - 官方 Anthropic：`ANTHROPIC_API_KEY`
  - 供应商 Anthropic 兼容接口：`ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` + `ENTITY_LLM_MODEL`
  - 非标准供应商网关：`ANTHROPIC_AUTH_TOKEN` + `ENTITY_LLM_MODEL` + `ENTITY_LLM_MESSAGES_ENDPOINT`

**安装：**
```bash
pip install -e ".[dev]"
```

如果要运行 Web 看板 / API，再安装 API 依赖：

```bash
pip install -e ".[dev,api]"
```

**配置 `.env`：**

项目启动时会自动读取仓库根目录的 `.env`，如果 shell 里已经 `export` 了同名变量，则以 shell 环境变量为准。

供应商接口示例：

```env
ANTHROPIC_AUTH_TOKEN=your_supplier_token_here
ANTHROPIC_BASE_URL=https://code.newcli.com/claude/aws
ENTITY_LLM_MODEL=your_supplier_model_name
ENTITY_DB_PATH=data/memory.db
ENTITY_SESSION_ID=shared
ENTITY_CONFIG_DIR=config/
ENTITY_PROMPTS_DIR=prompts/
ENTITY_LOG_LEVEL=INFO
```

非标准网关示例（当供应商给的是完整消息接口，而不是标准 `base_url` 时）：

```env
ANTHROPIC_AUTH_TOKEN=your_supplier_token_here
ENTITY_LLM_MODEL=your_supplier_model_name
ENTITY_LLM_MESSAGES_ENDPOINT=https://your-provider.example/path/to/messages
ENTITY_DB_PATH=data/memory.db
ENTITY_SESSION_ID=shared
ENTITY_CONFIG_DIR=config/
ENTITY_PROMPTS_DIR=prompts/
ENTITY_LOG_LEVEL=INFO
```

官方 Anthropic 示例：

```env
ANTHROPIC_API_KEY=your_official_key_here
# Optional: disable inherited system proxy variables if your local proxy breaks TLS
# ENTITY_LLM_DISABLE_SYSTEM_PROXY=1
ENTITY_DB_PATH=data/memory.db
ENTITY_SESSION_ID=shared
ENTITY_CONFIG_DIR=config/
ENTITY_PROMPTS_DIR=prompts/
ENTITY_LOG_LEVEL=INFO
```

**初始化数据库：**
```bash
python3 scripts/init_db.py
```

**启动 CLI：**
```bash
PYTHONPATH=src python3 -m conscious_entity.interfaces.cli

# 显示实体内部状态（debug 模式）：
PYTHONPATH=src python3 -m conscious_entity.interfaces.cli --debug
```

CLI 启动后，直接输入文本即可对话；输入空行或按 `Ctrl+C` 退出。

**会话和历史继承：**

默认会复用 `ENTITY_SESSION_ID` 指定的 session；如果没有设置，会自动继承数据库中最近一次使用的 session；如果数据库为空，则使用 `shared`。状态快照、情节记忆、反思摘要和对话记录都保存在 `ENTITY_DB_PATH` 指向的 SQLite 数据库中。程序重启后会恢复最近状态，并把最近的对话窗口重新放回短期上下文，使 Stranger 能继续承接之前的交流。

**启动 Web 看板 / API：**

```bash
PYTHONPATH=src python3 scripts/start_api.py --host 127.0.0.1 --port 8000
```

启动后打开：

```text
http://127.0.0.1:8000/
```

API 文档：

```text
http://127.0.0.1:8000/docs
```

Web 看板顶部的 `Save Dialog` 会把当前 session 的对话导出为 JSON。也可以直接访问：

```text
http://127.0.0.1:8000/api/v1/conversation/export?download=true
```

**回答长度：**

非沉默状态下的生成上限已放宽到 `2000` tokens。若需要继续调整，在 `config/expression_mappings.yaml` 中修改各 tone 的 `max_tokens`。

**记忆召回与 Memory Preview：**

当前系统会在记忆、连续性、纠正、重复追问等场景下检索当前 session 的最近对话、情节记忆和反思摘要。开发者面板的 Memory System 区域可以输入一条 query，点击 `Preview` 查看本轮会取用哪些记忆材料。

默认使用可解释检索，不需要额外服务。若要启用 embedding 语义召回，在 `.env` 中配置：

```env
ENTITY_EMBEDDING_MODE=openai_compatible
ENTITY_EMBEDDING_MODEL=text-embedding-3-small
ENTITY_EMBEDDING_BASE_URL=https://api.openai.com/v1
ENTITY_EMBEDDING_API_KEY=your_embedding_key_here
```

已有历史记忆可补生成 embedding：

```bash
PYTHONPATH=src python3 scripts/backfill_embeddings.py
```

embedding 调用失败不会中断对话，系统会自动退回可解释检索。

**运行测试：**
```bash
PYTHONPATH=src python3 -m pytest -p no:debugging
```
所有测试中的 LLM 调用均为 mock，不消耗 API 配额。

**常见启动报错：**
- `LLM configuration error: Missing LLM credentials...`
  说明 `.env` 或 shell 环境里没有配置凭证。
- `LLM configuration error: Supplier mode is incomplete...`
  说明供应商模式缺少 `ANTHROPIC_BASE_URL` 或 `ENTITY_LLM_MODEL`。
- CLI 启动正常，但回复总是 fallback 文本
  说明项目本身能启动，但上游网关可能不兼容标准 Anthropic `base_url`，可改用 `ENTITY_LLM_MESSAGES_ENDPOINT`。
- CLI 只有在关闭代理后才能正常请求
  可在 `.env` 中设置 `ENTITY_LLM_DISABLE_SYSTEM_PROXY=1`，让 LLM 请求不继承系统代理环境变量。

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
