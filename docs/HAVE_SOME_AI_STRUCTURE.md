# Have Some "Ai" System Structure

本文档记录 Have Some "Ai" 当前结构。它和 `conscious_entity` 并列存在：原系统继续作为 The "Stranger" 的技术基础；本系统专门负责观众流程、问卷、语音理解、评分、食物分配与工作人员队列。

## 当前边界

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
    ├── voice.py               # Claude 将语音转写映射到 A/B
    ├── voice_provider.py      # 语音 provider / STT mode 配置
    ├── voice_realtime.py      # 豆包 realtime dialogue 后端 WebSocket 适配器
    └── interfaces/
        ├── api.py             # FastAPI app
        └── static/index.html  # 单文件观众/工作人员界面
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
2. Food Gate 先问“想来点吃的吗？”
3. `NO_FOOD` 进入普通闲聊，不抽正式题、不分配食物
4. `WANT_FOOD` 后从两个正式模块各随机抽一题
5. 屏幕显示 A / B / C；C 表示 Other / 其他
6. AIHubMix/OpenAI-compatible TTS 或豆包 realtime 只读题，答案 accepted 后致谢
7. 浏览器麦克风采集语音，AIHubMix file STT 或豆包 realtime dialogue 生成 transcript
8. Claude 只在正式题阶段将 transcript 映射到隐藏 A/B rubric，并保存置信度和理由
9. 低置信度、无效选项、打岔或 Claude JSON repair 失败时要求回到当前题
10. 根据两道正式题映射到四种食物：
   - `soup`
   - `salad`
   - `aimiao_soup`
   - `aimiao_salad`
11. 将分配结果写入工作人员队列
12. 工作人员将队列项更新为 `preparing` 或 `served`
13. 导出所有 Have Some "Ai" 数据

## 运行

```bash
python scripts/start_have_some_ai.py
```

默认地址：

```text
http://127.0.0.1:8010/
```

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
HAVE_SOME_AI_STT_MODEL=gpt-4o-mini-transcribe
HAVE_SOME_AI_TTS_MODEL=gpt-4o-mini-tts
HAVE_SOME_AI_TTS_VOICE=alloy

# Doubao realtime dialogue
HAVE_SOME_AI_VOICE_PROVIDER=doubao
HAVE_SOME_AI_STT_MODE=realtime_dialogue
HAVE_SOME_AI_DOUBAO_APP_ID=your_volcengine_app_id_here
HAVE_SOME_AI_DOUBAO_APP_KEY=PlgvMymc7f3tQnJ6
HAVE_SOME_AI_DOUBAO_ACCESS_TOKEN=your_volcengine_access_token_here
HAVE_SOME_AI_DOUBAO_RESOURCE_ID=volc.speech.dialog
HAVE_SOME_AI_DOUBAO_WS_URL=wss://openspeech.bytedance.com/api/v3/realtime/dialogue
HAVE_SOME_AI_DOUBAO_MODEL=1.2.1.1
HAVE_SOME_AI_DOUBAO_SPEAKER=zh_female_vv_jupiter_bigtts
HAVE_SOME_AI_DOUBAO_BOT_NAME=Have Some Ai
HAVE_SOME_AI_DOUBAO_SPEAKING_STYLE=用简短、温和、带一点展览店主感的中文或英文回答。
```

## 当前语音链路状态

- `aihubmix + file`：使用 MediaRecorder 录音并上传真实 MIME，默认 `whisper-large-v3`，适合作为稳定 fallback。
- `doubao + realtime_dialogue`：浏览器通过本地 `/conversation-realtime` WebSocket 发送 PCM16 16k mono 音频块，后端转发豆包 `TaskRequest=200`；豆包返回 PCM16 24k `TTSResponse=352` 给浏览器播放。
- 豆包 StartSession 使用 server VAD/default 麦克风模式，不再默认 `push_to_talk`；新建观众开场和主语音按钮进入同一个长连接通话，active capture 时不再按单轮播放自动释放麦克风；手动停止按钮仍会发送 `audio.end`，由后端映射为 `EndASR=400`。
- 店主开场和独立播报使用 `SayHello=300`；用户说完后的本地回复等待 provider `ASREnded=459` 后再发送 `ChatTTSText=500`。
- 电话式打断 v1 已接入：播放中前端默认上传静音帧抑制扬声器回声，只有检测到较明显真人说话才恢复真实麦克风流；本地 RMS 不再直接打断播放，收到 `ASRInfo=450` 后前端停止 WebAudio 队列，并通过本地 WebSocket 请求后端发送 `ClientInterrupt=515`。
- 真实诊断已通过：豆包握手、TTS-only 桥接、interrupt 通道冒烟。仍需现场浏览器麦克风验收 ASR 稳定性、回声门限、真实插话手感和完整答题流程。

## API

主要端点：

```text
GET  /health
GET  /api/v1/config
POST /api/v1/participants
GET  /api/v1/participants
GET  /api/v1/participants/{id}
POST /api/v1/participants/{id}/questionnaire/start
POST /api/v1/participants/{id}/questions/{question_id}/speech
POST /api/v1/participants/{id}/answers
POST /api/v1/participants/{id}/voice-answers
POST /api/v1/participants/{id}/observations
POST /api/v1/participants/{id}/assign
WS   /api/v1/participants/{id}/conversation-realtime
GET  /api/v1/staff-queue
PATCH /api/v1/staff-queue/{queue_item_id}
GET  /api/v1/export
```

## 后续扩展顺序

建议按这个顺序继续做：

1. 细化 `questions.yaml` 与 `scoring.yaml`，确定最终分配机制
2. 用真实豆包 / AIHubMix 凭证做浏览器端到端联调
3. 打磨低置信度重新录音机制
4. 给观众端和工作人员端拆成两个页面
5. 增加安全/忌口覆盖逻辑，确保发餐前由工作人员确认
6. 接入摄像头或传感器，把识别结果写入 `/observations`
7. 在 `hardware.py` 中实现打印、小票、灯光、厨房信号或 Arduino/ESP32 适配器
8. 增加 CSV 导出和展后统计面板

## 设计原则

- 食物分配由规则引擎决定；豆包只负责实时听说与 transcript，Claude 只负责把 transcript 映射到隐藏 A/B rubric，两者都不直接决定食物。
- 摄像头/动作识别只生成抽象观察事件，不直接决定食物。
- 安全与忌口必须优先于艺术算法。
- Have Some "Ai" 与 Stranger 可以共享代码仓库，但不共享状态、记忆、题库、评分和分配结果。
