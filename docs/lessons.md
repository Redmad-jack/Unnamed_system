# Lessons Learned

*Conscious Entity System*

规则：每次发现新的易错点，立即在此补充。每次 AI 纠偏后，更新对应条目并标注原因。

---

## 架构原则

**L01：状态更新必须是不可变的**
- 规则：`StateEngine.apply_event()` 必须返回新的 `EntityState`，不得修改输入对象
- 原因：可变更新导致难以追踪的状态污染，单元测试也会因此变复杂
- 如何应用：所有状态操作结果赋值给新变量，旧变量只读

**L02：YAML 配置是艺术家的设计界面，不内联到 Python**
- 规则：状态更新规则、策略规则、宪法约束、表达映射 — 全部存 YAML，绝不硬编码
- 原因：项目的核心价值之一是让"规则"可见、可调整、与代码分离
- 如何应用：任何行为参数出现在 `.py` 文件中都是 code smell，应提取到 YAML

**L03：LLM 可以参与记忆和状态影响，但必须有结构化记录**
- 规则：LLM 可以参与记忆抽取、策略影响和状态影响，但所有影响必须有结构化记录、可预览、可回滚
- 原因：纯规则驱动的记忆系统在展览场景中缺乏灵活性，LLM 抽取能提供更精准的长期记忆
- 如何应用：任何 LLM 驱动的记忆/状态影响，必须写入对应的 operation/influence log，Memory Preview 能解释影响路径

---

## 开发流程

**L04：不做架构决策，要先问**
- 规则：新增 state variable、调整策略规则逻辑、改变宪法约束 — 都需要先与用户确认，不擅自补全
- 原因：这些设计选择是项目的哲学立场，不是技术细节
- 如何应用：遇到"这里可以加一个..."的念头时，停下来写进 progress.md 的"待确认"而不是直接实现

**L05：每个阶段先写测试，再写实现**
- 规则：rule-based 组件（StateEngine、PolicySelector、Constitution）必须先有测试，再写实现
- 原因：这类组件的正确性完全可以在不调用 LLM 的情况下验证
- 如何应用：每开始一个新的 rule-based 模块，先写 `tests/unit/test_xxx.py`

---

## 常见错误

**L06：不要把后续阶段依赖并入核心依赖**
- 规则：语音、视觉、外部向量库等后续阶段依赖不得进入核心 `dependencies`；开发者 API 这类已实现能力必须放在 optional group
- 原因：避免依赖膨胀，同时允许已落地的本地开发工具独立安装
- 如何应用：新增依赖先判断是否属于核心运行路径；非核心能力放入对应 optional dependency group，并在 README 写清安装方式

**L12：API 入口必须保持瘦身**
- 规则：`interfaces/api.py` 只保留 ASGI app 入口与兼容导出；请求模型、runtime helper、路由处理分文件维护
- 原因：API 端点增长很快，单文件堆叠会让测试、配置切换、记忆管理和会话管理互相牵连
- 如何应用：新增 API 能力时先放入 `api_models.py`、`api_runtime.py` 或 `api_routes.py` 中的对应层，不把新 helper 直接塞回 `api.py`

**L13：TTS 不能成为绕过宪法的输出后门**
- 规则：访客侧和身体节点只能播放由合法 `ExpressionOutput` 创建的 `tts_stream_id`；raw text TTS 只能作为显式 debug preview，不能视为 Stranger speech
- 原因：如果外部节点能直接提交任意文本给 TTS，实体声音就会绕过 Perception、Policy、Expression 和 Constitution
- 如何应用：新增语音、身体或远程播放入口时，先确认它消费的是 stream id 或已过滤输出，而不是未治理文本

**L14：开发者界面不能吞掉可恢复的协议生命周期**
- 规则：STT/TTS 这类 streaming provider 的 recoverable close、server end、reconnect 等事件不能伪装成成功或直接隐藏；应作为 lifecycle event 返回给开发者界面
- 原因：现场调试需要知道服务端何时主动结束流、客户端何时重连；把 `RST_STREAM NO_ERROR` 静默处理会让真正的链路状态不可诊断
- 如何应用：区分 fatal error 与 recoverable lifecycle，前者进入 error，后者进入明确的 stream status / last event / reconnect detail

**L15：语音播放期间的 suppress 不能阻断 barge-in**
- 规则：TTS 播放期间可以给 STT 发送静音来防回声，但必须保留本地用户人声检测；检测到用户插话时应立即停止播放并恢复真实麦克风音频
- 原因：展陈对话需要允许观众打断实体发声；无条件 suppress 麦克风会让系统看似“听不见”
- 如何应用：播放期间用本地音量门限检测 barge-in，未触发时静音，触发后停止 `<audio>` 并发送真实 PCM

**L16：语音 transcript 必须带通道上下文进入 prompt**
- 规则：`/audio/dialog` 不能只把 STT final transcript 当普通文字输入；必须用 metadata 告诉 expression prompt 最新用户消息来自实时语音转录
- 原因：否则实体会把转录文本当成书面输入来解释，错误声称自己区分了文字层面的语言、标点或拼写，而不知道它没有接收原始声音
- 如何应用：保持 `raw_text` 干净，只在 short-term metadata / prompt context 中注入 `voice_transcript` 说明

**L17：跨 session 记忆必须有 visitor scope**
- 规则：不能依赖 `session_type` 或全局池去模拟“同一个访客”的连续性；跨 session 的个人事实、关系线索和回返感必须经过显式 `visitor_id` 绑定
- 原因：否则一个访客说过的事实会在另一个访客处泄漏，或者像“K 是谁”这类旧会话事实在新 session 中无法稳定召回
- 如何应用：session 可为空 visitor；一旦设置 `visitor_id`，interaction / episodic / reflective / managed memory 路径都要记录该 scope，检索时优先同一 visitor 的旧 session

**L18：SQLite 旧库迁移不能在 ALTER 前创建新列索引**
- 规则：`SCHEMA_SQL` 可以描述新库表结构，但涉及新增列的索引必须放在 ensure/migration 阶段，等旧表 `ALTER TABLE ADD COLUMN` 后再创建
- 原因：`CREATE TABLE IF NOT EXISTS` 不会更新旧表结构，若随后直接 `CREATE INDEX ... (new_column)`，旧库会在启动时失败
- 如何应用：新增持久化列时必须添加旧库回归测试，覆盖“已有表缺少新列”的迁移路径

**L07：不要跳过 `clamp_all()`**
- 规则：每次状态更新调用链末尾必须调用 `clamp_all()`
- 原因：连续事件的累积增量可能使状态值越出 `[0.0, 1.0]`
- 如何应用：`StateEngine.apply_event()` 的最后一行永远是 `return new_state.clamp_all()`

**L08：ExpressionOutput.raw_prompt 必须存储**
- 规则：LLM 生成的每个回应都要保存完整的 prompt 输入
- 原因：展览期间无法 attach debugger，`raw_prompt` 是唯一的事后诊断途径
- 如何应用：`ExpressionEngine.generate()` 必须在 `ExpressionOutput` 中填入 `raw_prompt`

**L09：可选增强服务失败必须降级，不得中断对话**
- 规则：embedding、preview、统计等增强能力失败时，只记录日志并回退到基础路径
- 原因：Stranger 的现场对话不能因为语义召回供应商、网络或向量缺失而崩溃
- 如何应用：`MemoryRetriever` 的 embedding 分支捕获异常后必须退回确定性检索

**L10：`.env` 里同一 key 不能重复出现**
- 规则：同一 `.env` 文件中重复 key 必须产生 warning；修改配置时只保留一个有效定义
- 原因：加载器默认不覆盖已有变量，重复 key 会让第一处值生效，后面的值看起来写了但实际无效
- 如何应用：切换 LLM / Embedding 供应商时，先检查重复 key，再看运行时配置面板的 `source` 与脱敏值

**L11：服务拒绝必须处理上下文续问**
- 规则：服务请求不能只按当前输入单句判断；上一轮已触发服务需求后，下一轮短补充仍应按服务需求处理，除非用户明确退出该请求框架
- 原因：访客可以先提出服务任务，再用“历史背景”等字段片段绕过直接服务词
- 如何应用：服务需求检测应保留 YAML 可调的 followup 规则；策略仍拒绝任务交付，但表达层可以在有兴趣时转入非服务讨论

---

## 待观察（尚未验证）

- Embedding 模型 `all-MiniLM-L6-v2` 对中文关机/删除语义的召回效果是否足够 — 需要在 v0.2 实测
- 10 轮短期记忆窗口是否足够支撑上下文连贯性 — 需要在 v0.1 对话测试中验证
- `salience >= 0.5` 的阈值是否会遗漏重要事件 — 需要在 Phase 6 的 replay 工具中分析
