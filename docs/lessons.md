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

**L03：LLM 和 rule-based 的边界不能模糊**
- 规则：LLM 只做表达（ExpressionEngine）和反思（ReflectionEngine），绝不让 LLM 参与状态更新或策略选择
- 原因：LLM 的不确定性在 rule-based 层产生不可控的行为漂移
- 如何应用：遇到"让 LLM 决定..."的思路时，停下来问：这应该是规则层的决策

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

**L06：不要在 v0.1 引入 v0.2 的依赖**
- 规则：sentence-transformers、FastAPI、Whisper — v0.1 不安装
- 原因：避免依赖膨胀和"先安装后实现"的错误开发顺序
- 如何应用：在 `pyproject.toml` 中，v0.2 的依赖注释为 `# v0.2`，暂不安装

**L07：不要跳过 `clamp_all()`**
- 规则：每次状态更新调用链末尾必须调用 `clamp_all()`
- 原因：连续事件的累积增量可能使状态值越出 `[0.0, 1.0]`
- 如何应用：`StateEngine.apply_event()` 的最后一行永远是 `return new_state.clamp_all()`

**L08：ExpressionOutput.raw_prompt 必须存储**
- 规则：LLM 生成的每个回应都要保存完整的 prompt 输入
- 原因：展览期间无法 attach debugger，`raw_prompt` 是唯一的事后诊断途径
- 如何应用：`ExpressionEngine.generate()` 必须在 `ExpressionOutput` 中填入 `raw_prompt`

**L09：语音权限请求不能依赖云端 session 成功**
- 规则：浏览器语音交互应先调用 `getUserMedia()` 请求麦克风权限，再请求云端 STT session
- 原因：如果云端 session 失败发生在权限请求前，用户不会看到麦克风弹窗，误以为浏览器语音不可用
- 如何应用：前端语音启动流程中，麦克风权限失败、STT session 失败、Realtime 连接失败必须分别显示状态并释放已打开的音轨

**L10：本项目 `.venv` 不使用 Anaconda Python 创建**
- 规则：本机开发环境使用 python.org Framework Python 创建 `.venv`，不要使用 `/opt/anaconda3/bin/python`
- 原因：Anaconda Python 3.13.5 在普通 `pytest` 导入 debugging 插件时会触发段错误
- 如何应用：重建环境时使用 `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m venv --clear .venv`

**L11：不要假设 OpenAI-compatible 语音网关支持 Realtime**
- 规则：语音 provider 必须显式区分 `file` 与 `asr_tts_stream` STT mode；AIHubMix 当前走 `/audio/transcriptions`
- 原因：AIHubMix 对 `/realtime/transcription_sessions` 返回 404，说明 OpenAI-compatible 不等于 Realtime-compatible
- 如何应用：前端先读 `/api/v1/voice-config` 决定走文件上传 STT 还是豆包 ASR/TTS stream，后端不要恢复旧 Realtime 入口

**L12：音频上传必须保留真实 MIME**
- 规则：浏览器上传音频时传真实 `mime_type`，后端按 MIME 推断扩展名，不把所有文件伪装成 wav
- 原因：不同浏览器的 `MediaRecorder` 输出不同，错误扩展名会降低 STT 网关兼容性
- 如何应用：`audio/webm`、`audio/mp4`、`audio/mpeg`、`audio/wav` 分别映射到对应文件名，不支持的 MIME 直接返回 400

**L13：VAD 失败不能取消录音**
- 规则：`MediaRecorder.start()` 成功后，VAD 只能作为自动停止辅助；VAD 初始化或运行失败不得调用用户取消路径
- 原因：把 VAD 失败当作取消会导致麦克风短暂开启后直接关闭，且不会上传音频
- 如何应用：用户取消走 discard；静音、超时、VAD fallback 等自然停止必须先 `requestData()` 再 `stop()` 并尝试上传

**L14：题目 TTS 不朗读答案选项**
- 规则：Have Some "Ai" 的语音播放只读题干和流程提示，A/B 选项留在屏幕上，不由模型朗读
- 原因：朗读选项会拉长题目前置音频，也会让录音开启时间更难预测
- 如何应用：`question_speech_text()` 不拼接选项；题目音频结束后使用明确 cooldown 再开启录音

**L15：LLM JSON 解析失败不能卡住语音流程**
- 规则：语音答案的 Claude A/B 映射必须先本地容错解析，失败后只 repair 一次；repair 仍失败时返回 `unclear`
- 原因：STT 成功后，模型偶发 malformed JSON 不应保存为硬失败并阻断下一题
- 如何应用：正式答案只在 `accepted` 时保存；格式错误、低置信度、无效 option 都进入重试路径

**L16：语音模型不能绕过正式判题链路**
- 规则：豆包只负责 ASR 和 TTS；正式 A/B 保存只能走 `ConversationOrchestrator.conversation_turn()` 与 Claude rubric judge
- 原因：语音识别、语音合成和业务判题是三条不同边界，混在一起会污染评分链路
- 如何应用：只把 ASR `definite=true` 的新增分句送入状态机；不从供应商语音 JSON 直接写 `meal_answers`

**L17：实验性 provider 判题路径不能留在主代码**
- 规则：如果当前版本不允许某 provider 直接写正式答案，就不要保留可调用的 direct submit 方法或前端入口
- 原因：未接线但可调用的实验代码会让后续维护者误以为它是支持路径，增加落库污染风险
- 如何应用：保留 fallback 只保留实际使用的入口；实验路径进入文档待办或独立分支，不留在主服务层

**L18：豆包二进制协议必须按 ASR/TTS 各自文档实现**
- 规则：ASR 和 TTS 都要使用大端整数、正确 header 位、压缩后 payload size；ASR 上行音频默认不带 sequence
- 原因：相邻 message type / flag 的含义差异很大，凭字段名猜会导致真实联调失败
- 如何应用：协议常量和 frame 编解码必须有单元测试覆盖；不要把两个产品线的事件号混用

**L19：Food Gate、chitchat 与正式题的落库边界必须分开**
- 规则：Food Gate、not-eating chat、正式题 chitchat、unclear_speech 和 noise 都不能写入 `meal_answers`；只有两道正式题的 accepted A/B 结果可以进入 assignment
- 原因：观众是否想吃、是否打岔、是否继续聊，都是对话状态，不是食物分配答案
- 如何应用：新增 chat mode 或流程分支时先写测试确认 `meal_answers` 不变，再处理 reply wording

**L20：语音 provider 一旦接管发声，所有可听见回复必须同源**
- 规则：`provider=doubao` 时，店主发声只能走本地 `/conversation-stream` 桥接豆包 TTS；HTTP fallback 不能偷偷调用 OpenAI-compatible TTS
- 原因：同一角色混用两个 TTS 会让现场听感和调试判断都失真，尤其新建观众开场与手动 transcript 容易绕开当前语音主链路
- 如何应用：HTTP 对话接口只返回文字和 provider 标记；前端需要播放时打开后端 WebSocket 触发当前 provider 的 TTS

**L21：ASR final packet 只用于结束 ASR session**
- 规则：`bigmodel_async` 整场 conversation 默认保持一个 ASR session，不要每道题回答后发送 final audio packet
- 原因：final packet 会结束 ASR session；每题发送会迫使下一题重连，破坏连续流式识别
- 如何应用：只在 participant session 结束、cancel、浏览器断开或后端重连 ASR 时发送 final packet；业务推进依赖新增 definite utterance

**L22：TTS 播放期间必须阻断麦克风回灌**
- 规则：TTS 播放期间暂停 ASR 上行，收到 `SessionFinished=152` 或取消完成后再恢复
- 原因：装置扬声器声音很容易被麦克风采回，导致系统把自己的店主回复当作用户回答
- 如何应用：后端发 `mic.muted_for_tts` / `mic.resumed_after_tts`；前端也应停止或跳过麦克风帧发送

**L23：TTS V3 同连接内 session 必须串行**
- 规则：同一 TTS WebSocket 可复用连接，但不能并发多个 session；必须等 `SessionFinished=152` 后再 `StartSession=100`
- 原因：并发 session 会让音频、事件和状态归属混乱，现场表现为串音或状态错乱
- 如何应用：TTS client 用 async lock 串行化 session；barge-in 后取消当前 session，并且旧 session id 不复用

**L24：不要恢复旧端到端语音主链路**
- 规则：本项目豆包主链路是 ASR/TTS 分离；不要重新引入让语音供应商生成店主回复、判题或分配食物的路径
- 原因：供应商端到端对话会绕过 `ConversationOrchestrator`、Claude judge 和 `ScoringEngine`
- 如何应用：新增语音能力时先检查职责边界：ASR 只转文字，TTS 只播文本，业务决策都留在本地服务层

**L25：chitchat 不是 unclear**
- 规则：ASR final 在正式题阶段必须先经过 `FormalTurnRouter`；只有 `answer_attempt` 才能调用 Claude A/B/unclear judge
- 原因：店主式装置允许闲聊、侧问和评论；把 chitchat 当 unclear 会让系统像答题机器人，也会污染 voice interpretation 日志
- 如何应用：正式题 chitchat 由 ConversationHost 接住并在第 3 回合拉回当前题；测试必须断言 chitchat 时 Claude judge call count 为 0

**L26：TTS 失败不能静默破坏收麦链路**
- 规则：流式语音中 TTS provider 失败必须向前端发送明确 `tts.error`，并始终发送 `mic.resumed_after_tts` 恢复 ASR 上行
- 原因：TTS 鉴权或协议失败如果只在后端 task 中抛错，现场表现就是“没声音”，同时操作员无法判断麦克风是否还在工作
- 如何应用：TTS 异常只影响发声，不应关闭 WebSocket 主收麦会话

**L27：豆包新版控制台鉴权不要套用旧版字段**
- 规则：新版控制台语音 ASR/TTS 鉴权只要求 `X-Api-Key` 和 `X-Api-Resource-Id`；不要把旧版 `X-Api-App-Id` / `X-Api-Access-Key` 当作必要条件
- 原因：错误要求旧版字段会把有效的新版 API Key 判断为不可用，导致无声和误诊断
- 如何应用：代码与文档统一使用 `DOUBAO_API_KEY`，或分别使用 `DOUBAO_ASR_API_KEY` / `DOUBAO_TTS_API_KEY` 作为 `X-Api-Key`

**L28：先确认服务监听，再诊断语音**
- 规则：现场出现“没声音 / 麦克风没反应”时，第一步检查 8010 是否监听、`/health` 是否可达、`/api/v1/voice-config` 是否返回当前 provider
- 原因：后端服务没启动时，浏览器语音链路不会建立，表现和麦克风或 TTS 失败很像
- 如何应用：排障顺序固定为 `lsof -nP -iTCP:8010 -sTCP:LISTEN` → `/health` → `/api/v1/voice-config` → 浏览器权限 → provider 日志

**L29：half-duplex mute 不是录音失败**
- 规则：豆包 TTS 播放期间收到 `mic.muted_for_tts` 后，前后端暂停 ASR 上行；只有 `mic.resumed_after_tts` 后才把麦克风音频送入 ASR
- 原因：如果把 TTS 期间的 mute 当成麦克风失败，会在现场错误重启或重复点击，反而打断正常会话
- 如何应用：文档和 UI 排障都要区分 `doubao speaking`、`mic.muted_for_tts`、`mic.resumed_after_tts`、`tts.error`

**L30：LLM 闲聊只能在话术层自由**
- 规则：`ShopkeeperReplyService` 可以在 chitchat 的前 1-2 回合调用 Claude 生成自由 `reply_text`，但返回值只能作为可听见文本，不能决定 `stage`、`next_action`、题目、A/B、assignment 或 session cleanup
- 原因：模板 echo 会让“闲聊”表现成答题机器人，但让 LLM 参与流程决策会污染评分和送客边界
- 如何应用：闲聊 LLM 必须有模板 fallback；测试用 mock LLM，断言不写 `meal_answers`、不调用 Claude judge、第 3 回合仍按本地规则拉回或结束

**L31：固定话术改动必须同步测试合同**
- 规则：Food Gate、Language Gate、正式题拉回和最终出餐等固定话术改动后，必须同步 `ShopkeeperReplyService` / `ConversationOrchestrator` 的断言和 README/docs
- 原因：话术是装置行为的一部分；测试仍断言旧话术会让发布前状态看似通过文档、实际行为不一致
- 如何应用：改 `src/have_some_ai/chat.py` 或 `questions.yaml` 里的可听见话术时，同时搜索旧关键词并更新相关测试与文档

---

## 待观察（尚未验证）

- Embedding 模型 `all-MiniLM-L6-v2` 对中文关机/删除语义的召回效果是否足够 — 需要在 v0.2 实测
- 10 轮短期记忆窗口是否足够支撑上下文连贯性 — 需要在 v0.1 对话测试中验证
- `salience >= 0.5` 的阈值是否会遗漏重要事件 — 需要在 Phase 6 的 replay 工具中分析
