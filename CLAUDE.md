# CLAUDE.md

*Conscious Entity System — AI 编码规则*

---

## 每次会话开始前必须读

按顺序读：

1. `CLAUDE.md`（本文件）
2. `docs/progress.md` — 当前进度和已知问题
3. `docs/frame.md` — 架构技术文档（模块接口、YAML schema、数据库结构）
4. 当前任务涉及的具体模块文件

---

## 项目性质

这是一个**艺术装置 / 研究原型混合体**，不是普通软件产品。

- 目标不是让 AI 拥有意识，而是构建能触发人类意识归因的最小组织结构
- 行为规则（YAML 配置）是艺术家的哲学立场，不是可以自由调整的技术细节
- 代码的可读性和可维护性优先于性能优化

---

## 技术栈摘要

| 组件 | 技术 |
|---|---|
| 语言 | Python 3.11+ |
| LLM | Anthropic SDK（claude-sonnet-4-6 / claude-haiku-4-5-20251001） |
| 数据库 | SQLite WAL 模式 |
| 配置 | YAML（PyYAML） |
| 测试 | pytest + pytest-mock |
| Embedding（v0.2） | sentence-transformers |
| API（v0.2） | FastAPI + uvicorn |

完整版本锁定见 `docs/TECH_STACK.md`。

---

## 文件命名约定

| 类型 | 命名规则 | 示例 |
|---|---|---|
| Python 模块 | `snake_case.py` | `state_engine.py` |
| YAML 配置 | `snake_case.yaml` | `policy_rules.yaml` |
| 测试文件 | `test_<module_name>.py` | `test_state_engine.py` |
| Prompt 文件 | `snake_case.txt` | `expression_system.txt` |
| 文档 | `SCREAMING_SNAKE_CASE.md` | `TECH_STACK.md` |

---

## 架构边界（绝不越界）

**LLM 只能用于：**
- `ExpressionEngine` — 生成文字回应
- `ReflectionEngine` — 压缩情节记忆为洞察

**LLM 绝不用于：**
- 状态更新（StateEngine）
- 策略选择（PolicySelector）
- 宪法约束判断（Constitution）
- 感知事件分类（TextParser）


---

## 禁止事项

- **禁止**修改 `config/constitution.yaml` 中的核心约束（forbidden_claims）而不经过用户确认
- **禁止**擅自新增 Python 依赖，必须在 `pyproject.toml` 中声明并得到确认
- **禁止**将 YAML 配置中的规则内联到 Python 代码中
- **禁止**在 v0.1 阶段安装 v0.2 的依赖（FastAPI、Whisper、sentence-transformers）
- **禁止**使用 LangChain 或其他 LLM 框架封装层（直接使用 Anthropic SDK）
- **禁止**在 `state_snapshots` 表上执行 UPDATE 或 DELETE（仅追加）
- **禁止**在未要求的情况下添加注释、docstring 或类型注解到未修改的代码

---

## AI 编码行为约定

- **不做未要求的重构**：只改被要求改的部分
- **不引入 feature flag 或向后兼容 shim**：直接修改代码
- **不添加推测性的错误处理**：只在 `docs/BACKEND_STRUCTURE.md §6` 定义的场景处理错误
- **遇到架构决策时停下来问**：新增 state variable、改变策略规则逻辑、修改宪法约束 — 都需要确认
- **发现需求矛盾时主动指出**：不绕过矛盾假装问题不存在

---

## 测试规则

- Rule-based 组件（StateEngine、PolicySelector、Constitution、StyleMapper）**必须有单元测试**
- LLM 调用在集成测试中**必须 mock**（不消耗 API 配额）
- 集成测试使用 `sqlite3.connect(":memory:")`，不读写实际 `data/memory.db`
- 每个 Phase 完成前，对应的测试必须全绿

---

## 开发语言规则

- 代码注释：英文
- 文档（`.md` 文件）：中文为主，技术术语保留英文
- 与用户的对话：中文
- YAML 配置中的 `note` 字段：英文

---

## 当前版本范围（v0.1）

以下功能在当前版本**不实现**，遇到相关需求时拒绝并说明：

- 访客端 Web 界面
- 运营者监控 Web 面板
- 语音输入/输出
- Embedding 语义检索
- FastAPI HTTP 服务
- 访客身份识别
- 展期终止仪式
- 硬件传感器接口
