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
- 规则：语音 provider 必须显式区分 `file` 与 `realtime` STT mode；AIHubMix 当前走 `/audio/transcriptions`
- 原因：AIHubMix 对 `/realtime/transcription_sessions` 返回 404，说明 OpenAI-compatible 不等于 Realtime-compatible
- 如何应用：前端先读 `/api/v1/voice-config` 决定录音上传或 Realtime，后端保留两个入口但不混用

**L12：音频上传必须保留真实 MIME**
- 规则：浏览器上传音频时传真实 `mime_type`，后端按 MIME 推断扩展名，不把所有文件伪装成 wav
- 原因：不同浏览器的 `MediaRecorder` 输出不同，错误扩展名会降低 STT 网关兼容性
- 如何应用：`audio/webm`、`audio/mp4`、`audio/mpeg`、`audio/wav` 分别映射到对应文件名，不支持的 MIME 直接返回 400

**L13：VAD 失败不能取消录音**
- 规则：`MediaRecorder.start()` 成功后，VAD 只能作为自动停止辅助；VAD 初始化或运行失败不得调用用户取消路径
- 原因：把 VAD 失败当作取消会导致麦克风短暂开启后直接关闭，且不会上传音频
- 如何应用：用户取消走 discard；静音、超时、VAD fallback 等自然停止必须先 `requestData()` 再 `stop()` 并尝试上传

**L14：题目 TTS 不朗读答案选项**
- 规则：Have Some "Ai" 的语音播放只读题干和流程提示，A/B/C 选项留在屏幕上，不由模型朗读
- 原因：朗读选项会拉长题目前置音频，也会让录音开启时间更难预测
- 如何应用：`question_speech_text()` 不拼接选项；题目音频结束后使用明确 cooldown 再开启录音

**L15：LLM JSON 解析失败不能卡住语音流程**
- 规则：语音答案的 Claude A/B 映射必须先本地容错解析，失败后只 repair 一次；repair 仍失败时返回 `unclear`
- 原因：STT 成功后，模型偶发 malformed JSON 不应保存为硬失败并阻断下一题
- 如何应用：正式答案只在 `accepted` 时保存；格式错误、低置信度、无效 option 都进入重试路径

**L16：Realtime 语音模型不能绕过正式判题链路**
- 规则：豆包 realtime v1 只负责听、说和 transcript；正式 A/B 保存只能走 `ConversationOrchestrator.conversation_turn()` 与 Claude rubric interpreter
- 原因：实时语音模型自然对话稳定性和结构化 JSON 稳定性不是同一个问题，直接落库会污染评分链路
- 如何应用：收到豆包 `ASRResponse=451` transcript 后再进入现有服务层；正常麦克风轮次依赖 provider server VAD，手动停止时才把本地 `audio.end` 映射为 `EndASR=400`；不从豆包 JSON 直接写 `meal_answers`

**L17：实验性 provider 判题路径不能留在主代码**
- 规则：如果当前版本不允许某 provider 直接写正式答案，就不要保留可调用的 direct submit 方法或前端入口
- 原因：未接线但可调用的实验代码会让后续维护者误以为它是支持路径，增加落库污染风险
- 如何应用：保留 fallback 只保留实际使用的入口；实验路径进入文档待办或独立分支，不留在主服务层

**L18：Realtime provider 事件号必须以官方协议为准**
- 规则：接入豆包 realtime 时，客户端上传音频必须使用 `TaskRequest=200`；开场/独立播报使用 `SayHello=300`；用户一轮语音后的本地回复使用 `ChatTTSText=500`；手动 `audio.end` 使用 `EndASR=400`；播放打断使用 `ClientInterrupt=515`
- 原因：相邻事件号含义差异很大，误把 `300`/`350` 当作 TTS/音频上传会让链路看似可导入但真实联调失败
- 如何应用：协议常量要有单元测试覆盖；StartSession payload 与音频格式以官方文档为准，不凭名称猜测

**L19：Food Gate 与正式题的落库边界必须分开**
- 规则：Food Gate、普通闲聊和 food-chat detour 不能写入 `meal_answers`；只有两道正式题的 accepted A/B 结果可以进入 assignment
- 原因：观众是否想吃、是否打岔、是否继续聊，都是对话状态，不是食物分配答案
- 如何应用：新增 chat mode 或流程分支时先写测试确认 `meal_answers` 不变，再处理 reply wording

**L20：语音 provider 一旦接管发声，所有可听见回复必须同源**
- 规则：`provider=doubao` 时，店主发声只能走本地 `/conversation-realtime` 桥接豆包 TTS；HTTP fallback 不能偷偷调用 OpenAI-compatible TTS
- 原因：同一角色混用两个 TTS 会让现场听感和调试判断都失真，尤其新建观众开场与手动 transcript 容易绕开 realtime 主链路
- 如何应用：HTTP 对话接口只返回文字和 provider 标记；前端需要播放时打开后端 WebSocket 触发当前 provider 的 TTS

**L21：Realtime TTS 不能在首个音频事件前按短 idle 超时退出**
- 规则：后端向 provider 发出 `speak_text()` 后，drain loop 必须至少等待到首个 `audio.delta` 或总超时，再使用短 idle timeout 收尾
- 原因：真实豆包 TTS 首包可能慢于 0.5s；过早退出会让浏览器永远收不到 PCM 音频，看起来像网页没声音
- 如何应用：测试中覆盖 provider 先返回 state、延迟返回 audio 的场景；前端点击入口要提前解锁 Web Audio context

**L22：豆包 Realtime 的 App-Key 是固定网关值**
- 规则：`X-Api-App-Key` 使用官方固定值 `PlgvMymc7f3tQnJ6`；控制台凭证只填 AppID 与 Access Token
- 原因：错误 App-Key 仍可能收到 `ConnectionStarted=50`，但 `StartSession` 会失败，看起来像 payload、音频格式或模型不可用
- 如何应用：代码默认固定 App-Key，诊断脚本打印 `X-Tt-Logid` 与错误码；真实联调先跑 `scripts/diagnose_doubao_realtime.py`

**L23：豆包 ChatTTSText 必须对齐 ASR 生命周期**
- 规则：开场/独立播报走 `SayHello=300`；用户一轮语音后的本地回复必须等 provider 返回 `ASREnded=459` 后再发 `ChatTTSText=500`
- 原因：会话刚开始直接发 `ChatTTSText` 可以不报错但不返回音频，网页表现为无声
- 如何应用：后端把 transcript 产生的回复先暂存，收到 provider ASR end 后再 flush；TTS-only WebSocket 测试使用 `SayHello`

**L24：电话式打断需要边发音频边读 provider 事件**
- 规则：不能只在 `audio.end` 后 drain provider；持续麦克风流期间也要小步读取 `ASRInfo=450`、`ASRResponse=451` 和 `ASREnded=459`
- 原因：如果后端等待用户手动结束才读取事件，本地播放永远无法被用户说话实时打断
- 如何应用：`audio.append` 后进行短 timeout drain；前端收到 provider ASR start 或本地检测到说话时停止 WebAudio 队列，并发送 `ClientInterrupt=515`

**L25：本地插话检测必须有误触发恢复**
- 规则：本地 RMS 判断用户插话后，不能无限期丢弃豆包后续音频；必须在 provider ASR 事件缺席时自动恢复播放接收状态
- 原因：扬声器回声、环境噪声或阈值过低可能触发本地打断，但豆包未必会确认 `ASRInfo/ASREnded`
- 如何应用：本地打断后设置短恢复计时器；收到 `ASRInfo=450` 或 `ASREnded=459` 时清理计时器并按 provider 状态继续

**L26：电话式 realtime 不能把播放回声原样上传**
- 规则：豆包播放中保持麦克风长开时，默认上传静音帧保活；只有检测到较明显真人说话时才恢复真实麦克风流；active capture 期间不能按单轮播放自动释放资源
- 原因：扬声器回声会让 provider VAD/ASR 把豆包自己的声音当作用户输入，表现为说话约数秒后自我打断或乱码 transcript
- 如何应用：开场和主语音按钮共用 `/conversation-realtime` 长连接；本地 RMS 只做回声门控，不直接打断播放，真正停止 WebAudio 以 provider `ASRInfo=450` 为主

**L27：豆包自主音频不能当成店主回复**
- 规则：`/conversation-realtime` 只能向前端转发后端本地 `SayHello` / `ChatTTSText` 授权后的 TTS 音频；provider 自主 `chat.delta` 和未授权 `audio.delta` 必须忽略或打断
- 原因：豆包 realtime dialogue 即使有 system prompt，仍可能自主回答、追问或发明菜单；这会绕过 `ConversationOrchestrator`，破坏两题流程和四种食物约束
- 如何应用：收到 transcript 后先关闭 TTS 音频门并发送 `ClientInterrupt`；只有后端根据状态机产出的 `reply_text` 才能打开音频门；最终话术必须引用系统 assignment 的四种合法食物之一

---

## 待观察（尚未验证）

- Embedding 模型 `all-MiniLM-L6-v2` 对中文关机/删除语义的召回效果是否足够 — 需要在 v0.2 实测
- 10 轮短期记忆窗口是否足够支撑上下文连贯性 — 需要在 v0.1 对话测试中验证
- `salience >= 0.5` 的阈值是否会遗漏重要事件 — 需要在 Phase 6 的 replay 工具中分析
