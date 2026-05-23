# Have Some "Ai" System Structure

本文档记录 Have Some "Ai" 当前结构。它和 `conscious_entity` 并列存在：原系统继续作为 The "Stranger" 的技术基础；本系统专门负责观众流程、问卷、语音理解、评分、食物分配与工作人员队列。

## 当前边界

当前发布版本：`v1.2.1-EC`

```text
src/
├── conscious_entity/          # 保留：Stranger / 原 Conscious Entity
└── have_some_ai/              # 新增：Have Some "Ai"
    ├── config.py              # 加载题库与评分配置
    ├── db.py                  # Have Some "Ai" 专属 SQLite 表
    ├── hardware.py            # 未来硬件边界：打印、灯、传感器、厨房信号
    ├── models.py              # 参与者、题目、答案、观察事件、分配结果、语音理解记录
    ├── openai_tts.py          # OpenAI-compatible TTS 读题
    ├── questionnaire.py       # 两道正式题随机抽题 + Food Gate 开头轮换
    ├── repository.py          # 数据库读写
    ├── scoring.py             # 两轴正式答案到四种食物的规则映射
    ├── service.py             # 观众流程应用服务
    ├── chat.py                # 店主话术层；闲聊可用配置的文本 LLM provider 生成 reply_text，模板兜底
    ├── prompt_context.py      # 读取 AI 店主运行语境，仅注入闲聊话术 prompt
    ├── voice.py               # 文本 LLM 判断 Food Gate 歧义入口；正式题 answer/chitchat + A/B/unclear
    ├── voice_provider.py      # 语音 provider / STT mode 配置
    ├── doubao/                # 豆包 ASR/TTS 二进制 WebSocket 协议与客户端
    └── interfaces/
        ├── api.py             # FastAPI app
        └── static/
            ├── index.html     # 控制页：真实录音、状态推进、工作人员队列
            ├── display.html   # 只读观众展示页
            └── assets/        # 展示页薄膜/装饰图片
```

## 配置文件

```text
config/have_some_ai/
├── questions.yaml   # Food Gate 开头、两道正式题库、选项、分数
└── scoring.yaml     # 四种食物映射、观察事件权重备注、安全备注
```

后续细化分配机制时，优先改这两个 YAML，而不是直接改代码。

## 当前闭环

当前系统已经支持：

1. 新建匿名观众，生成 `A001` 形式的 public code
2. Language Gate 先问 `Hi. 你好～ Do you want to talk in 中文 or English?`；English / en / 英文 或明显英文输入固定本次会话 `response_language=en`，中文 / Chinese / zh 或明显中文输入使用中文默认逻辑
3. Food Gate 使用 `questions.yaml` 的 13 条开场轮换；中文问“想吃点什么，还是说说话？”，English 模式问 “Do you want something to eat, or do you want to talk?”
4. `WANT_CHAT` 进入 `talk_only_chat`，最多闲聊 3 回合后送客并删除 transient participant，不抽正式题、不分配食物；Food Gate 先看本地食物意图、拒绝食物、聊天/提问和语气词证据，强证据直接路由，弱证据或本地不确定的实质输入再由文本 LLM 判断 `want_food / want_chat / no_food / unclear_speech`
5. `NO_FOOD` 进入 `not_eating_chat`，最多闲聊 3 回合后送客并删除 transient participant，不抽正式题、不分配食物
6. `WANT_FOOD` 后从两个正式模块各随机抽一题
7. 屏幕显示 A / B 两个正式选项
8. AIHubMix/OpenAI-compatible TTS 或豆包 TTS V3 只读 Orchestrator 生成的话术
9. 浏览器麦克风采集语音，AIHubMix file STT 或豆包 ASR `bigmodel_async` 生成 transcript
10. 正式题 ASR final 先经过 `FormalTurnRouter` 处理空音频、重复、取消和极短回应；其余正式题输入进入同一次 LLM judge
11. LLM judge 先判断 `answer` / `chitchat`；`answer` 再映射 A / B / unclear。`chitchat` 不写正式答案、不写 voice interpretation、不评分、不推进；前 1-2 回合可由 `ShopkeeperReplyService` 调配置的文本 LLM provider 生成自由 `reply_text`，失败则模板兜底
12. 两道正式题完成后分配食物并写入工作人员队列；出餐话术会读出观众 public code（中文如 `A零零一号顾客`，英文如 `customer A001`）；出餐后还允许最多 2 回合 `post_assignment_chat`，第 3 次追问结束会话，且不改变 assignment
13. 整个语音会话只在控制页等待观众说话时计算静默；连续 15 秒没有可检测观众语音时，控制页停止当前语音链路并让 `/display` / `/particle-display` 回到“按按钮叫醒我 / Press the button to wake me”；`/particle-display` 的待机 wake 按钮会通知控制页创建下一位观众
14. 根据两道正式题映射到四种食物：
   - `soup`
   - `salad`
   - `aimiao_soup`
   - `aimiao_salad`
15. 店主说出固定出餐话术；中文食物名只说中文，English food names stay English.
16. 将分配结果写入工作人员队列
17. 工作人员将队列项更新为 `preparing` 或 `served`
18. 导出所有 Have Some "Ai" 数据

## 双屏展览模式

现场运行方式是 iMac 双屏：

- `/` 控制页负责所有真实操作：开始会话、麦克风、`conversation-stream`、ASR/TTS、状态推进、食物分配、数据库写入和工作人员队列。
- `/display` 展示页只读，只负责观众可见呈现：膜后存在、AI 字幕、当前题目和最终食物结果。
- `/particle-display` 展示页在待机文案旁提供一个小型粒子 wake 按钮；按钮只通过 `BroadcastChannel` 通知已打开的控制页复用现有 `newParticipant()`，自身不直接调用参与者创建、会话、麦克风或数据库写入端点。
- `GET /api/v1/display-state` 返回内存级展示状态；`POST /api/v1/display-state` 只更新内存状态，不写 SQLite，不调用业务服务。
- `/display-assets/{filename}` 只返回展示页白名单图片资产：`avatar-film-texture.png`、`avatar-film-overlay.png`、`amhand.png`。

`/display` 不得请求麦克风、调用 `getUserMedia`、创建 WebSocket、启动 `conversation-stream`、提交答案、操作工作人员队列、调用 `MealService`、推进 `ConversationOrchestrator` 或触发 ASR/TTS。

### 拯救者主控 + iMac 展示拓扑

展场也可以使用拯救者 Windows 作为唯一主控：拯救者运行 FastAPI、打开 `/` 控制页、负责收音和发音；iMac 只通过局域网打开 `/particle-display`。此时服务必须以 `--host 0.0.0.0 --port 8010` 启动，iMac 使用 `http://<拯救者局域网IP>:8010/particle-display` 访问。

跨电脑时，`/particle-display` 的 wake 按钮无法通过 `BroadcastChannel` 通知拯救者控制页；启动观众应使用拯救者控制页按钮或接在拯救者上的实体按钮。部署步骤见 `docs/windows_lenovo_deployment.md`。

## 现场主链路

当前现场语音主链路只有一条：

```text
Browser PCM s16le 16k mono
  → FastAPI WebSocket /api/v1/participants/{participant_id}/conversation-stream
  → Doubao ASR 2.0 bigmodel_async
  → ConversationOrchestrator
  → [food gate ambiguity: FoodGateIntentInterpreter routes want_food/want_chat/no_food/unclear_speech]
  → [formal turn: RubricInterpreter routes answer/chitchat; accepted A/B → ScoringEngine]
  → ShopkeeperReplyService（chitchat reply_text 可走配置的文本 LLM provider，流程不交给 LLM）
  → Doubao TTS 2.0 tts/bidirection
  → Browser PCM s16le 24k mono
```

豆包在本项目中只负责 ASR 和 TTS，不生成店主回复、不判断 A/B、不推进题目、不打分、不分配食物。旧的端到端 realtime dialogue 主链路已移出运行时代码，不应恢复为 fallback。

兼容端点仍用于调试或非豆包 fallback：

- `/conversation-turn`：文本 transcript 进入同一个 `ConversationOrchestrator`。
- `/conversation-audio`：AIHubMix/OpenAI-compatible file STT fallback，之后仍进入同一个 `ConversationOrchestrator`。
- `/voice-answers` / `/questions/{question_id}/voice-audio`：旧式正式答案提交兼容入口，不是现场豆包语音主链路。

## 职责边界

| 组件 | 职责 |
| --- | --- |
| `LanguageGateRouter` | 只判断 English / 中文 语言选择；不抽题、不写答案、不参与评分 |
| `FoodGateRouter` | 用本地语义证据判断 Food Gate 中的强食物、不吃、明确聊天/提问、听不懂、取消等入口意图；“不吃但想聊”优先进入聊天线 |
| `FoodGateIntentInterpreter` | 只在 Food Gate 本地弱证据或不确定实质输入时调用文本 LLM，输出 `want_food / want_chat / no_food / unclear_speech`；失败时按本地规则兜底，不写正式答案、不评分、不分配食物 |
| `FormalTurnRouter` | 在正式题阶段先处理 noise、repeat、cancel、极短非答案；其余输入交给正式题 judge |
| `ConversationOrchestrator` | 唯一主状态机，维护 Food Gate、talk_only_chat、not_eating_chat、两道正式题、post_assignment_chat 和 session cleanup |
| `ShopkeeperReplyService` / ConversationHost | 只根据 Orchestrator 已决定的 context 生成店主话术；闲聊前 1-2 回合可调用配置的文本 LLM provider 自由回应，但不改变流程、不写答案、不分配食物 |
| `RubricInterpreter` | 正式题阶段用一次 LLM 调用输出 `answer` / `chitchat`；`answer` 才继续输出 A / B / unclear |
| `ScoringEngine` | 只接收两道正式题 accepted A/B，输出四种食物之一 |

`chitchat` 不是 `unclear`。Food Gate 的 LLM 入口分类只决定是否进入想吃、聊天、不吃或重问分支，不产生 A/B、不写 `meal_answers` 或 `meal_voice_answer_interpretations`，也不触发 `ScoringEngine`。正式题里的 `unclear` 只表示“像是在回答当前题，但无法映射到唯一 A/B”；闲聊、侧问、评论由正式题 judge 返回 `chitchat` 或由本地规则接住。文本 LLM 可以在话术层生成 `reply_text`，但返回值只被当作可听见文本，不能决定题目、A/B 或食物。

AI 店主运行语境放在 `backend/prompts/shopkeeper_runtime_context.md`，由 `prompt_context.py` 缓存读取，只注入 `ShopkeeperReplyService` 的自由闲聊 system prompt。该语境不得影响 Food Gate 入口分类、LLM rubric、`ScoringEngine`、food assignment 或任何 `meal_*` 落库逻辑。

## 运行

```bash
python scripts/start_have_some_ai.py
```

默认地址：

```text
http://127.0.0.1:8010/
```

本地语音联调先确认服务真的在跑：

```bash
lsof -nP -iTCP:8010 -sTCP:LISTEN
curl -s http://127.0.0.1:8010/health
curl -s http://127.0.0.1:8010/api/v1/voice-config
```

如果 8010 未监听，网页不会有声音，麦克风音频也不会进入后端。

默认数据库：

```text
data/have_some_ai.db
```

可在 `.env` 覆盖：

```env
HAVE_SOME_AI_DB_PATH=data/have_some_ai.db
HAVE_SOME_AI_CONFIG_DIR=config/have_some_ai
HAVE_SOME_AI_VOICE_API_KEY=your_voice_provider_key_here
HAVE_SOME_AI_VOICE_BASE_URL=https://your-voice-provider.example/v1
HAVE_SOME_AI_STT_MODEL=whisper-large-v3
HAVE_SOME_AI_STT_LANGUAGE=zh
HAVE_SOME_AI_TTS_MODEL=gpt-4o-mini-tts
HAVE_SOME_AI_TTS_VOICE=alloy
HAVE_SOME_AI_RUBRIC_CONFIDENCE_THRESHOLD=0.55

# Doubao ASR/TTS split streaming
HAVE_SOME_AI_VOICE_PROVIDER=doubao
HAVE_SOME_AI_STT_MODE=asr_tts_stream
DOUBAO_API_KEY=your_volcengine_api_key_here
DOUBAO_ASR_ENDPOINT=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async
DOUBAO_ASR_RESOURCE_ID=volc.seedasr.sauc.duration
DOUBAO_ASR_ENABLE_NONSTREAM=true
DOUBAO_ASR_RESULT_TYPE=single
DOUBAO_TTS_ENDPOINT=wss://openspeech.bytedance.com/api/v3/tts/bidirection
DOUBAO_TTS_RESOURCE_ID=seed-icl-2.0
DOUBAO_TTS_SPEAKER_ZH=S_sd9II0522
DOUBAO_TTS_SPEAKER_EN=S_r98II0522
DOUBAO_TTS_AUDIO_FORMAT=pcm
DOUBAO_TTS_SAMPLE_RATE=24000
```

## 当前语音链路状态

- `aihubmix + file`：使用 MediaRecorder 录音并上传真实 MIME，默认 `whisper-large-v3`，适合作为稳定 fallback。
- `doubao + asr_tts_stream`：浏览器通过本地 `/conversation-stream` WebSocket 发送 binary PCM s16le 16k mono 音频块；后端保持一个 ASR `bigmodel_async` session，只消费新增 `utterances[].definite=true` 分句。
- TTS 使用豆包 V3 双向流式 `/tts/bidirection`，使用声音复刻资源 `seed-icl-2.0`，按 `response_language` 选择复刻音色：中文 `S_sd9II0522`，英文 `S_r98II0522`，未确定语言时 fallback 中文，默认输出 PCM s16le 24k mono。
- 新版控制台鉴权只使用 `X-Api-Key` 和 `X-Api-Resource-Id`；本项目读取共享 `DOUBAO_API_KEY`，或分别读取 `DOUBAO_ASR_API_KEY` / `DOUBAO_TTS_API_KEY` 作为 `X-Api-Key`。
- TTS session 串行复用连接：每段 Orchestrator 文本 StartSession → TaskRequest → FinishSession，必须等 `SessionFinished=152` 后才开下一段。
- 播放 TTS 时启用 half-duplex：后端发送 `mic.muted_for_tts` / `mic.resumed_after_tts`，TTS 期间不把麦克风音频继续上行到 ASR，避免店主声音被识别成用户回答。
- 前端语音会话有 15 秒观众静默超时：AI TTS 期间暂停计时；`mic.resumed_after_tts` 后等待浏览器已排队 PCM 播放完成再重新计时；超时只清理控制页语音资源和展示状态，不写业务数据库。
- `barge_in` 会取消当前 TTS session；被取消的播报不算完整播放完成。

## API

主要端点：

```text
GET  /display
GET  /display-assets/{filename}
GET  /health
GET  /api/v1/config
GET  /api/v1/voice-config
GET  /api/v1/display-state
POST /api/v1/display-state
POST /api/v1/participants
GET  /api/v1/participants
GET  /api/v1/participants/{id}
POST /api/v1/participants/{id}/questionnaire/start
POST /api/v1/participants/{id}/conversation-turn
POST /api/v1/participants/{id}/conversation-audio
POST /api/v1/participants/{id}/questions/{question_id}/speech
POST /api/v1/speech/thanks
POST /api/v1/participants/{id}/answers
POST /api/v1/participants/{id}/voice-answers
POST /api/v1/participants/{id}/questions/{question_id}/voice-audio
POST /api/v1/participants/{id}/observations
POST /api/v1/participants/{id}/assign
WS   /api/v1/participants/{id}/conversation-stream
GET  /api/v1/staff-queue
PATCH /api/v1/staff-queue/{queue_item_id}
GET  /api/v1/export
```

## 后续扩展顺序

建议按这个顺序继续做：

1. 细化 `questions.yaml` 与 `scoring.yaml`，确定最终分配机制
2. 用真实豆包 ASR/TTS / AIHubMix 凭证做浏览器端到端联调
3. 打磨低置信度重新录音机制
4. 给观众端和工作人员端拆成两个页面
5. 增加安全/忌口覆盖逻辑，确保发餐前由工作人员确认
6. 接入摄像头或传感器，把识别结果写入 `/observations`
7. 在 `hardware.py` 中实现打印、小票、灯光、厨房信号或 Arduino/ESP32 适配器
8. 增加 CSV 导出和展后统计面板

## 设计原则

- 食物分配由规则引擎决定；豆包语音只负责 ASR 和 TTS；文本 LLM provider（Anthropic 或 Ark）只用于 Food Gate 歧义入口分类、正式题 answer/chitchat + A/B/unclear judge 与受限闲聊话术生成，都不直接决定食物。
- 摄像头/动作识别只生成抽象观察事件，不直接决定食物。
- 安全与忌口必须优先于艺术算法。
- Have Some "Ai" 与 Stranger 可以共享代码仓库，但不共享状态、记忆、题库、评分和分配结果。
