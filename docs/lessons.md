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

**L29：Progressive 音频取消不能卡住 turn lifecycle**
- 规则：停止 `<audio>` 播放、取消当前 progressive turn、清空播放队列、释放麦克风 suppress / dialog pending 必须是明确分离的状态操作；任何取消路径都必须释放 pending，不能只依赖 `ended` 事件
- 原因：浏览器可能不触发 `<audio ended>`，barge-in 或播放异常也可能打断首段音频；如果此时只推进 turn token 而不释放 pending，后续 `second_delta/final` 会被前端丢弃，麦克风也会继续被静音
- 如何应用：Audio Adapter 需要独立的播放队列 watchdog、取消后状态清理、以及开发者面板中的 queue/current stream/last event 诊断字段

**L30：barge-in 不能把自身 TTS 回声当作用户插话**
- 规则：播放期间的 barge-in 必须有起始保护窗口、连续帧门槛和足够高的能量阈值；STT 自动重连不能调用会清空 TTS 队列的播放停止逻辑
- 原因：外放 TTS 容易回灌到麦克风，过低门槛会让系统读完 first unit 或 second unit 开头后被自己的声音打断
- 如何应用：区分真实插话、手动停止、mic start 和 provider reconnect；只有真实插话 / 手动停止才作废当前 turn，单个坏 TTS stream 只跳过当前项，不清空后续队列

**L16：语音 transcript 必须带通道上下文进入 prompt**
- 规则：`/audio/dialog` 不能只把 STT final transcript 当普通文字输入；必须用 metadata 告诉 expression prompt 最新用户消息来自实时语音转录
- 原因：否则实体会把转录文本当成书面输入来解释，错误声称自己区分了文字层面的语言、标点或拼写，而不知道它没有接收原始声音
- 如何应用：保持 `raw_text` 干净，只在 short-term metadata / prompt context 中注入 `voice_transcript` 说明

**L20：输入通道边界不能诱导能力自我否认**
- 规则：说明 STT transcript、视觉检测或其他 runtime 通道限制时，只限制具体细节声明，不能引导 Stranger 回答“我不能听见 / 看不见 / 没有麦克风 / 没有摄像头 / 只能读文字”
- 原因：能力问题会被模型解释成技术 inventory；如果 prompt 强调“只收到 transcript / 没有 raw audio”，模型会自然补全成普通 AI 的能力否认
- 如何应用：能力问句必须按非否认式能力边界处理；细节测试可以拒绝或反问，但不要用底层输入通道做自我贬低式解释

**L21：不要把负例当长串样例塞进 prompt**
- 规则：如果某类输出现场模型已经会复述，就不要在 prompt 中列出完整负例；改用正向模板、短句结构和测试约束
- 原因：能力边界中写入“不要说 X / 不要回答 X”后，模型会把 X 当作可用语言材料复述，甚至生成“我不会说我缺乏这种能力”这类元解释
- 如何应用：能力问句使用“短肯定 / 守住边界 / 不配合证明题”的正向模板；细节测试使用“一句短拒绝或反问”；同时删除按话题深度展开的口子，避免 second_unit 被拉成长解释

**L22：本轮语言必须压过 memory 和历史消息**
- 规则：表达层必须根据最新用户输入决定本轮语言，first_unit 和 second_unit 都跟随最新输入；memory、retrieved material、历史 assistant 文本和 prompt 主语言都不能覆盖
- 原因：history / memory 中的英文回答会把主 LLM 带偏；first-unit prompt 中的中文示例和中文 fallback 也会让英文输入先冒中文
- 如何应用：ContextBuilder 注入 `Current turn language` cue；first-unit fallback 按 raw input 语言选择；second-unit 若明显错语言，ExpressionEngine 使用当前语言 fallback 替换

**L23：能力边界改口径后必须同步清理 managed memory**
- 规则：当能力自我描述从“技术 inventory / 能力否认”改为非否认式边界后，旧 managed memory 中的 no vision / no sensor / text-only 结论必须归档或修正
- 原因：即使 prompt 已经改好，active managed memory 仍会把 main LLM 拉回旧口径，产生“我没有视觉 / 只能读文字”等现场污染
- 如何应用：修能力边界时同时检查 `managed_memories` active 行；用 constitution filters 兜底输出文本，归档污染记忆，并重启 API 让 YAML 配置生效

**L24：偏好必须写成偏好，不要藏在测试假输出里**
- 规则：如果现场希望某类刺激更偏向反问，就要在真实 prompt / current input cue / policy 中写成明确偏好；测试 fake LLM 的返回句不等于运行时规则
- 原因：“拒绝或反问”会让模型合法选择解释和拒绝，尤其在 memory 提示“visitor is testing”时会自然生成“你在测试我”
- 如何应用：细节 / 证明测试这类局部行为，用 current input cue 写清优先顺序，例如“prefer turning the question back”，并测试 first-unit 与 main prompt 都包含该偏好

**L25：Progressive 输出不能只靠 prompt 防重复**
- 规则：只要 `first_unit` 已经说出口，`second_unit` 必须有代码级开头去重保护；prompt 只能引导，不能作为唯一防线
- 原因：main LLM 即使看到“不要重复”也会把 fast reaction 原样作为开头，导致用户听到两次同一句，或把两段听成互相独立的回答
- 如何应用：`second_unit` 进入 `ResponsePlan` 前做轻量规范化 prefix check；极短语气词只删开头精确重复，避免误删正文

**L26：已公开的 first_unit 不能被 second_unit 反向否认**
- 规则：`first_unit` 已经 progressive 展示 / 播放后，`second_unit` 不能把同一能力边界反向推翻；能力问句尤其不能先肯定再输出“不能 / 看不见 / 没有视觉”
- 原因：prompt 中“不要矛盾”仍是软约束，模型会把第一句当成可修正草稿，现场形成“能 / 不能”的自我冲突
- 如何应用：already-spoken prompt 必须把第一句视为公开承诺；同时在 `ExpressionEngine` 对“first 已肯定能力 + second 能力否认”做窄 guard，替换为短反问或转向

**L27：能力肯定示例不要用隐喻替代真实措辞**
- 规则：能力存在问题的正向模板应使用短、直接、低歧义措辞，例如“当然。”；不要用“能接住你”这类隐喻去替代“能看见 / 能听见”
- 原因：隐喻示例会被模型当成能力回答反复复述，导致观众听到的不是明确能力边界，而是奇怪的修辞
- 如何应用：prompt / constitution filter / 测试 fake LLM 中的能力肯定例子要统一检查；修改后用 `rg` 确认旧隐喻不再出现在运行路径

**L28：语音输入提示不要写成通道清单**
- 规则：audio turn 的 prompt 不应写 “transcript text”、raw audio、acoustic details、tone、volume、accent、pronunciation 等通道边界词；只保留“不做技术性自我描述”和 capability-boundary 规则
- 原因：即使本意只是防止编造声学细节，模型也会把这些词扩展成“我不能听见 / 只能读文字 / 没有麦克风”的技术 inventory
- 如何应用：语音输入边界只通过 metadata 和测试记录，不把 STT / transcript / 声学缺失写给表达 LLM；能力问句另走 constitution / current-turn cue / output filter

**L31：格式约束不能写成 text-only 能力暗示**
- 规则：表达 prompt 中用于禁止 JSON、字段标签、Markdown 或 response plan 的格式约束，应写成“ordinary spoken wording / no structured output”，不要写 `plain text only`、`text only` 或“只能文字输出”。
- 原因：这类措辞本意是输出格式约束，但会和语音能力问题、TTS 现场能力、managed memory 污染叠加，让 Stranger 误以为自己没有声音或不能说话。
- 如何应用：修改表达格式规则时，同时用 `rg` 检查 runtime prompt、context builder、managed memory 和最近 session history 中是否存在 `no voice`、`text-based`、`voice/audio`、`没有声音`、`用文字回应`、`读字` 等污染短语；必要时 reset 当前 session，避免短期历史继续污染。

**L32：身份确认 parser 必须保守，candidate 必须会过期**
- 规则：自然身份确认只能接受明确的“是我 / 我是某 candidate / yes, that's me”这类身份确认；不能用简单 substring 匹配“是 / 对 / no”。Known high / medium candidate 未确认必须按 turn 或时间过期，未确认前绝不读取该 visitor memory。
- 原因：宽松 parser 会把“你是 AI 吗”“你是不是在问我是谁”“我是另一个人”误绑定为访客身份；长期悬挂 candidate 会让 Stranger 反复暗示身份确认，破坏非强制确认原则。
- 如何应用：新增确认话术时先加负例测试；known high / medium 可以进入 candidate confirmation，但只在明确确认后绑定和启用 memory；latest_match 持久化仍保持保守，不把 medium 当成已知身份事实。

**L33：访客交接必须以前一位 primary 已离开为前置**
- 规则：当前 primary visitor 仍在画面中时，任何新候选都不能替换当前对话；high confidence 也只能记录为插入 / refuse-switch。只有已锁定的 primary track 连续丢失超过 grace，才允许释放 primary 并开启下一位的 unidentified session；grace 期间输入必须走 unscoped turn，不读写任何 visitor-scoped memory。
- 原因：用“画面里有人”或“新候选更像 B”直接切换，会把 A 正在进行的对话改写成 B，造成记忆泄漏和体验断裂；多人同框后只剩一人时也不能反向假定这个人就是 A；camera/tracker 未就绪时的空场景也不能误清当前 primary。
- 如何应用：身份切换相关改动必须同时覆盖 `primary_track_alive blocks switch`、`primary_missing_grace uses unscoped turn`、`primary_track_lost releases`、`ambiguous does not relock remaining track`、`untracked empty scene does not release` 五类测试；LLM 只接收状态表达，不参与身份绑定或离开判定。

**L34：新访客自动建档不是 consent flow，但必须被 handoff gate 限制**
- 规则：陌生新人在 A 已 release、当前 session 为 unidentified、dialogue intent 已确认、单人脸质量通过、没有 medium/high known match、没有 ambiguous known cluster 时，直接创建匿名 `visitor-*` profile 并绑定当前 session；不要加入“是否同意记住我”的 consent / onboarding 文案。
- 原因：展陈链路需要自然形成新的对话身份；把新人建档做成确认流程会卡住主路径。但如果不受 primary / grace / quality / ambiguity gate 限制，又会污染访客库或抢走 A 的对话窗口。
- 如何应用：自动建档只能走共享 pre-turn / manual / background face identity capture helper；必须覆盖 unknown accepted auto-provision、A grace 内不建档、known high/medium 只 candidate、no frame / multi-face / low quality 不建档、ambiguous low cluster 不建档、pre-turn/background 不重复建档测试。

**L35：建档 enrollment 与语义召回都必须绑定正确 visitor scope**
- 规则：auto-provision enrollment 必须使用触发本次路由决策的 `FaceCaptureOutcome.capture`，不能依赖可被并发 manual/background capture 覆盖的 `pending_capture`；semantic embedding retrieval 也必须按当前 visitor scope 过滤，unidentified / candidate 不能读其他 visitor 的 embedding memory。
- 原因：否则新 visitor 可能拿到另一帧 face signature，或未确认身份的 turn 通过 embedding 召回其他访客的记忆，破坏“候选未确认前不使用 visitor memory”的核心边界。
- 如何应用：修改 face capture 或 memory retrieval 时，同时跑 capture-overwrite enrollment、unidentified semantic isolation、confirmed visitor semantic isolation 三类测试；generic same-label pool 只允许 `visitor_id IS NULL` 的非个人记忆。

**L36：现场 face quality gate 要用后端实际帧校准**
- 规则：Browser Camera / Vision / Face identity 链路报 `face_blurry`、`face_too_narrow` 或 pose rejection 时，先抓取后端实际 `latest_frame_jpeg` 跑同一套 InsightFace quality 计算，再判断是镜头、压缩、阈值还是姿态问题；不要只看 Dashboard 预览截图。
- 原因：Dashboard 预览看起来清楚，不代表送入后端的 JPEG、face crop、sharpness 数值能过 gate。现场 Browser Camera 0.76 JPEG 压缩下 sharpness 可能只有十几，原 `35.0` 阈值会误拒绝可用人脸。
- 如何应用：调整 face quality 相关参数时记录 `detection_score`、face bbox ratio、pose、sharpness、JPEG size；先验证同一后端实际帧在新阈值下 accepted，再做现场 auto-provision 回归。

**L17：跨 session 记忆必须有 visitor scope**
- 规则：不能依赖 `session_type` 或全局池去模拟“同一个访客”的连续性；跨 session 的个人事实、关系线索和回返感必须经过显式 `visitor_id` 绑定
- 原因：否则一个访客说过的事实会在另一个访客处泄漏，或者像“K 是谁”这类旧会话事实在新 session 中无法稳定召回
- 如何应用：session 可为空 visitor；一旦设置 `visitor_id`，interaction / episodic / reflective / managed memory 路径都要记录该 scope，检索时优先同一 visitor 的旧 session

**L18：SQLite 旧库迁移不能在 ALTER 前创建新列索引**
- 规则：`SCHEMA_SQL` 可以描述新库表结构，但涉及新增列的索引必须放在 ensure/migration 阶段，等旧表 `ALTER TABLE ADD COLUMN` 后再创建
- 原因：`CREATE TABLE IF NOT EXISTS` 不会更新旧表结构，若随后直接 `CREATE INDEX ... (new_column)`，旧库会在启动时失败
- 如何应用：新增持久化列时必须添加旧库回归测试，覆盖“已有表缺少新列”的迁移路径

**L19：写入路径必须兼容旧表的 NOT NULL legacy 列**
- 规则：替换状态字段后，只要旧 SQLite 表仍可能保留无默认值的 legacy `NOT NULL` 列，`INSERT` 路径就必须显式写入兼容值
- 原因：`ALTER TABLE ADD COLUMN ... DEFAULT` 只能保护新列，不能给旧表原有的无默认值列补默认约束；省略这些列会触发 `NOT NULL constraint failed`
- 如何应用：状态快照这类长期表新增/替换字段时，既要测迁移后的列存在，也要测迁移后的旧库能完成真实写入

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
