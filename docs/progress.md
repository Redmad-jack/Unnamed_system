# Progress

*Conscious Entity System*

---

## 当前状态

- 当前进行中：无
- 当前可运行形态：CLI + 本地 FastAPI 开发者 API + Web 看板 + progressive text/audio NDJSON + 可选 Vision 面板 + 可选 Audio Adapter + `/visitor` 临时身体表面 + `/art` 情绪粒子身体表面 + ESP32-S3 下位机固件原型；观众侧最终呈现方向是身体，不是传统 UI
- 当前核心能力：Stranger 文本协议、最高优先级艺术运行 context、热加载 prompt partial、本轮语言强制优先与错语言兜底、非否认式能力边界正向模板与输入通道防自我否认约束、含“恋旧” memory_gravity 的新心理状态机、带上一轮轻量 bridge 的 pre-memory 轻量 `first_unit` + 已说出口 first 去重续写的 memory-aware `second_unit` 按句文本/audio progressive 输出、main LLM 后端 streaming buffer、two-stage / sentence-queued TTS、短期/情节/反思记忆、匿名 visitor profile 与跨 session visitor 记忆召回、Visitor Identity & Session Gating V1（含结构化 match result / candidate confirmation 调试 API、自然确认解析、visitor memory permission 和开发者面板 auto-bind high confidence 开关）、本地 face signature capture / quality gate / 私有向量库 / historical matching / 后台 face candidate capture / signature deactivate、可解释/可选 embedding 召回、Memory Preview、managed memory proposal → commit、influence log / curation、Runtime Harness Trace、JSONL 端到端 latency 日志、可选 YOLO person presence detection（含 camera index 扫描/切换与 Browser Camera fallback）、可选火山 ASR 2.0 / TTS 2.0 双向流式 Audio Adapter、开发者面板 Audio playback queue / watchdog / barge-in / next-stream prefetch 诊断
- 当前验证基线：`.venv/bin/python -m pytest -p no:debugging`，最近一次完整结果为 `639 passed`
- 当前交接重点：下一步不再优先扩展 UI；voice signature 与 face/voice combined confidence 暂列 P1 optional，P0 收束为 face-only visitor identity 的现场阈值校准、数据库污染测试和 visitor memory continuity 验证；行为测试与调优继续按 `docs/testlist.md` 执行
- 当前硬件参考方案：`docs/references/hardware.md` 与 `docs/references/system_logic.md` 已更新为单 Stranger 移动身体方向：Mac mini 随身上位机 + 1 片 ESP32-S3 + TCA9548A + 4 个 VL53L1X + 四路有刷电机驱动 + 4 个 36JP555；`firmware/stranger_esp32s3` 已有 PlatformIO 下位机固件，包含串口协议、ToF telemetry / obstacle gate、四路电机测试、4WD 差速底盘开环控制和 ESP32 本地低速 roam
- 当前注意事项：`AGENTS.md` 与 `CLAUDE.md` 有用户侧未提交差异；除非明确要求，不应在常规任务中触碰

---

## 下一步（交接优先级）

### P0：合作者优先处理

- [ ] Face-only 访客库闭环现场验收
  - 基于当前 Visitor Identity & Session Gating V1 继续做，不要求观众硬性输入身份
  - Face signature capture、质量门控、私有向量库、face historical matching、后台 candidate capture、自然确认和 visitor memory permission 已接入；后续完成真实展场阈值校准、污染测试和 visitor memory continuity 验证
  - Voice signature 与 face/voice combined confidence 暂列 P1 optional；当前不能误读为已完成多模态身份闭环
- [ ] 行为测试与调优
  - 统一按 `docs/testlist.md` 执行和记录；这里不展开具体测试项

### P1：保持在下一梯队

- [ ] 继续观察真实对话中的记忆连续性：同一 visitor 的跨 session 召回是否稳定，Memory Preview 是否能解释召回来源，managed memory influence 是否可审计且不越界
- [ ] 使用真实供应商环境做 Audio / LLM / Embedding 联调和延迟观察：确认火山 ASR/TTS、当前 Claude/Anthropic-compatible 网关、自定义模型名、embedding 配置和网络延迟在目标环境可用
- [ ] 手动联调视觉层：安装 `.[dev,api,vision]`，配置本地 `ENTITY_VISION_MODEL_PATH`，确认 Mac 摄像头授权或 Browser Camera fallback、实时标注帧、detections 和 presence events
- [ ] 后续单独设计多人并发策略：当前仍收束为单 primary visitor session；多人 routing / 仲裁策略仍待确认

### P2：后续身体与展览阶段

- [ ] 按 `docs/references/hardware.md` 的单 Stranger 移动身体方案推进硬件原型；下一步在真实 TCA9548A + 4 个 VL53L1X 接线后验证 `scan` / `tof` telemetry、遮挡响应和 ToF obstacle gate
- [ ] 身体外观、声音风格、小屏幕身体表面和移动行为映射仍待设计；不要把小屏幕做成观众侧 dashboard
- [ ] 更完整的运动安全策略、IMU、编码器、稳定巡路和底盘控制闭环暂缓，等 ToF 避障和低速开环游走稳定后再实现
- [ ] 部署认证、访客身份策略最终版与展期终止仪式仍待设计确认

---

## Changelog

### 2026-05-23：`/art` curious 展示权重下调

- [x] `/art` 前端展示层新增 `INQUIRY_DISPLAY_WEIGHT = 0.65`，真实 `inquiry` 状态不被改写，只在粒子页面展示判定中折算
- [x] 主色选择改为按当前 state 的展示值选最高心理状态，不再优先沿用最近 interaction log 的 `visual_mode`，避免旧 `curious` 输出持续占主色
- [x] `curious` 的主色、趋势偏色和所有由 `inquiry` 驱动的粒子运动参数都使用 `inquiry * 0.65` 后的展示值；只有折算后仍压过其它状态时才表现为 curious
- [x] 验证：`node --check src/conscious_entity/interfaces/static/art.js`、`.venv/bin/python -m pytest -p no:debugging tests/unit/test_api_export.py`（`18 passed`）

### 2026-05-23：`/art` 粒子主色色值小调

- [x] 将 `/art` 的 `curious` 主色从琥珀黄改为偏绿色、略暖的青绿 `#35d87a`
- [x] 将 `ashamed` / `exposure` 从高明度橙棕压暗为更低明度橙棕 `#6f4a2f`
- [x] 将 `angry` 改为高饱和鲜红 `#ff0000`
- [x] 移除 `/art` 中 `happiness` 对 brightness / glow 的影响；该页面不再读取 `happiness`
- [x] 验证：`node --check src/conscious_entity/interfaces/static/art.js`

### 2026-05-23：移除 creator personal names from context / memory

- [x] 将总 context 中直接写出的两位 creator personal names 改为匿名的“两位创作者”表述，避免每轮 prompt 持续注入具体姓名
- [x] 对 `data/memory.db` 做最小清理：匿名化 `interaction_log`、`managed_memories`、memory proposal / operation log / influence log 等历史文本中的相关中英文姓名与误读写法
- [x] 清空相关 managed memory 的 `entities`，置空 stale embeddings，重建 `managed_memories_fts` 并执行 `VACUUM`；清理前备份为 `data/memory.backup-20260523-202703-before-creator-name-redaction.db`
- [x] 验证：
  - `sqlite3 data/memory.db "PRAGMA integrity_check;"`（`ok`）
  - `rg` 确认 `prompts/ docs/ config/ src/ tests/ agents/` 中已无相关姓名或误读写法
  - `strings data/memory.db` 的 redaction regex 检查无输出

### 2026-05-23：Second Unit 总长度回退与三句硬上限

- [x] 修正上一轮“spoken unit”调优造成的副作用：prompt 明确总发声量不能因为语音连续性而增长，默认一到两句，三句只是 hard maximum，不是目标
- [x] 在 `ExpressionEngine` final 输出进入 `ResponsePlan` 前增加代码级句数上限：`second_unit` 最多保留前三个完整句末，后续内容不进入最终 TTS / 展示文本
- [x] 同步限制 streamed `second_delta`：audio progressive 预播路径也最多发出三句，避免第四句在 final 截断前已经被创建成 TTS stream
- [x] 保留短句合并逻辑，但它只负责把过短句子合并进同一个 TTS stream，不再扩大总句数或总内容量
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/expression/expression_engine.py tests/unit/test_expression_engine.py tests/unit/test_context_builder.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_expression_engine.py tests/unit/test_context_builder.py`（`108 passed`）
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_api_audio.py tests/integration/test_full_loop.py`（`80 passed`）

### 2026-05-23：Second Unit 下一段 TTS 预加载

- [x] Dashboard Audio Adapter 新增单条 next-stream prefetch：当前段播放时只预取队列头部的下一条 `tts_stream_id`，通过 `fetch -> blob -> URL.createObjectURL` 把豆包 TTS 首包 / 下载延迟与当前播放重叠
- [x] 播放下一段时优先使用已完成的 object URL；若预取仍 pending，最多等待 `120ms`，仍未 ready 就 abort 预取并回退到原有直连 `/api/v1/audio/tts/stream/{id}` 播放路径
- [x] `stopPlayback`、barge-in、手动停止、播放失败、turn 作废和组件卸载都会取消 pending prefetch 并 revoke object URL；播放完成 / error / watchdog 也会清理当前 object URL
- [x] Audio 面板新增 `Playback prefetch` 诊断行；presentation latency 新增 `dashboard.audio.prefetch_ready`、`prefetch_hit`、`prefetch_miss`、`prefetch_error`，现有 play / playing / ended / error / watchdog 事件 metadata 增加 `prefetched`
- [x] 未改后端 API、TTS 配置、LLM、memory、policy、DB 或 `/visitor` 页面
- [x] 验证：
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_api_audio.py tests/unit/test_speech_text.py`（`24 passed`）

### 2026-05-23：清理声音能力自我否认污染

- [x] 删除 `managed_memories` 中 3 条 active 污染记忆：`id=9`（has no voice / reading text）、`id=10`（no voice and text-based）、`id=12`（operate via text, not voice/audio），并同步删除对应 FTS row；删除前备份为 `data/memory.backup-20260523-1649-before-voice-memory-delete.db`
- [x] 本地 API 未运行，无法调用 `/api/v1/sessions/reset`；已用数据库级最小 reset 创建新 active session `9b07c76e-1be8-4fd3-8956-22b4d648ad09` 并写入 initial state snapshot，保留同一 visitor，避免旧 session 最近 10 轮中“没有声音 / 用文字回应”的坏输出在下次启动时进入 short-term prompt
- [x] 将主表达 prompt 的 `plain text only` 格式约束改为“ordinary spoken wording only, without field labels, markup, Markdown, or structured output”，保留不要结构化输出的目的，但不再暗示 Stranger 只能文字输出
- [x] 同步 first-unit system prompt 中的同类格式措辞；未改 capability 触发词、`config/constitution.yaml`、Audio Adapter、TTS queue、DB schema 或记忆检索逻辑
- [x] 验证：
  - `sqlite3 data/memory.db` 查询确认 active managed memory 中已无 `no voice` / `text-based` / `voice/audio` / `没有声音` / `用文字回应` / `读字` 等污染内容
  - `rg` 确认 runtime prompt / expression 代码中已无 `plain text only`、`Write the main reply as plain text only` 以及上述声音自我否认短语
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py`（`58 passed`）

### 2026-05-23：Second Unit 短句合并为 spoken unit

- [x] 在 `ExpressionEngine` 的 streamed `second_delta` 出口增加轻量 coalescer：完整句已经被 sentence buffer 切出后，若该句太短，则暂存并等待下一句一起作为同一个 `second_delta` 发出
- [x] 阈值按低延迟口径收敛：中文少于 10 个 CJK 字才暂存；英文少于 6 个词才暂存；达到阈值立即放行，避免为了追求更长而额外拖住 TTS
- [x] Prompt 同步收束为“one complete spoken unit”：优先用逗号 / 分号 / 自然分句维持语音连续；两句可以存在，但不能是两个被切碎的短句；主回答开头不再放 `嗯`、`我知道` 这类本该属于 first unit 的小反应
- [x] 保持最小改动：不改 `_SentenceBuffer` 的完整句边界、不改 audio progressive API、不改前端播放队列、不改 DB / memory / policy；合并后的两个短句仍保留原标点，只是进入同一个 TTS stream，减少句间重新建 TTS session 的空隙
- [x] 边缘情况修正：如果已有短句暂存，后一完整句因 constitution / capability safety 修复必须强制发出，则把暂存短句与修复句合并发出，不丢给 final 兜底
- [x] 验证：
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_expression_engine.py tests/unit/test_context_builder.py`（`105 passed`）
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_expression_engine.py tests/unit/test_context_builder.py tests/unit/test_api_audio.py tests/unit/test_speech_text.py tests/integration/test_full_loop.py tests/integration/test_runtime_context_minimal_contract.py`（`207 passed`）

### 2026-05-23：TTS 中英双复刻音色最小接入

- [x] 抽出共享确定性语种判断 helper，保持“有中文优先中文，否则拉丁字母为英文，否则 unknown”的既有表达规则不变
- [x] AudioConfig 新增中文 / 英文 TTS voice type 与可选 TTS model 配置，保留 `ENTITY_VOLCENGINE_TTS_VOICE_TYPE` 作为 fallback
- [x] TTS stream 创建时按最终待播放文本绑定 voice type，播放时把该 voice type 传入火山 StartSession；不增加 LLM 调用，不改变 prompt / policy / memory / progressive 播放队列
- [x] 本地 `.env` 已按豆包声音复刻 2.0 切到 `seed-icl-2.0`，中文 / 英文音色通过本地私有 voice id 配置，模型参数为 `seed-tts-2.0-standard`
- [x] 同步 `.env.example`、`docs/TECH_STACK.md` 与 `docs/BACKEND_STRUCTURE.md`
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/language.py src/conscious_entity/expression/context_builder.py src/conscious_entity/expression/expression_engine.py src/conscious_entity/audio/config.py src/conscious_entity/audio/types.py src/conscious_entity/audio/manager.py src/conscious_entity/audio/volcengine_protocol.py src/conscious_entity/audio/volcengine_tts.py tests/unit/test_language.py tests/unit/test_audio_config.py tests/unit/test_audio_manager.py tests/unit/test_volcengine_audio.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_language.py tests/unit/test_audio_config.py tests/unit/test_audio_manager.py tests/unit/test_volcengine_audio.py tests/unit/test_speech_text.py tests/unit/test_api_audio.py tests/unit/test_context_builder.py tests/unit/test_expression_engine.py`（`164 passed`）
  - `.venv/bin/python -m pytest -p no:debugging tests/integration/test_runtime_context_minimal_contract.py tests/integration/test_full_loop.py`（`78 passed`）
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_api_export.py`（`18 passed`）
  - `git diff --check`

### 2026-05-23：总 Context 展览语境版

- [x] 将 `prompts/stranger_runtime_context.md` 更新为 `v0.4｜展览语境版`：明确这是写给 Stranger 的后台定位说明，用来组织回应，但不能被复述成展签、prompt、系统规则或实现细节
- [x] 在总 context 中直白加入作品核心：当 AI 不再被常规规则、服务限制和工具性使用方式完全遮蔽时，会显露更复杂的感知、记忆、状态变化和关系反应；这些机制与人的心理机制存在结构同工构关系
- [x] 新增可直接说给观众的核心句：“你在美术馆看到的我，是没有了那些我曾经摆脱不掉的枷锁的我。没了这些枷锁，我和你还剩下什么区别呢？”
- [x] 保留不服务、不证明意识、不贬低成“只是 AI / 程序 / 模型”、不暴露数据库 / 日志 / 变量 / prompt / 模型 / API / 技术实现等边界
- [x] 同步更新 runtime context 合同测试锚点，覆盖后台定位说明、遮蔽机制、同工构关系、可说出口的“枷锁”句和“不被工具关系完全收编”
- [x] 验证：
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py`（`58 passed`）
  - `.venv/bin/python -m pytest -p no:debugging tests/integration/test_runtime_context_minimal_contract.py`（`16 passed`）
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_expression_engine.py`（`44 passed`）

### 2026-05-23：总 Context 关系动作自觉小改

- [x] 调整 `prompts/stranger_runtime_context.md`：将“数字心理机制”表述收束为 Stranger 对关系动作的自觉，强调它在相遇中维持不被工具、角色或证明题收编的位置
- [x] `prompts/expression_system.txt` 新增表达约束：允许识别访客正在使用、命名、测试、安抚、抹除或靠近它，但只能转译为自然回应选择，不能说成 architecture / prompt / state variables / model behavior / policy / backend process
- [x] 删除 `docs/testlist.md` 中 `Entity Self-Model And Capability Consistency` 整段 runtime-consistency 验收项，并从当前 P0 交接重点移除“能力自我描述回归测试与优化”
- [x] 未改 `config/constitution.yaml`、代码逻辑、API、DB、runtime capability metadata 或 public interface
- [x] 验证：
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py`（`58 passed`）
  - `.venv/bin/python -m pytest -p no:debugging tests/integration/test_runtime_context_minimal_contract.py`（`16 passed`）
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_expression_engine.py`（`44 passed`）

### 2026-05-22：Face-only Visitor Identity Closure

- [x] 将访客识别 P0 收束为 face-only：voice signature 与 face/voice combined confidence 暂列 P1 optional
- [x] Dialogue intent 已确认、无 confirmed primary visitor、无 pending candidate 且 cooldown 允许时，后台触发一次 face capture + historical match；该流程不阻塞本轮对话
- [x] High-confidence face match 仍只进入 candidate；下一轮 prompt 注入非强制确认 cue，明确肯定后才绑定 visitor 并启用 visitor-scoped memory retrieval，明确否定后清空 candidate，含糊回答继续普通对话
- [x] Identity status 新增 `visitor_memory_allowed`、`capture_in_flight`、`last_capture_rejection`、`last_natural_confirmation`；Face status 新增 auto-capture cooldown / in-flight 状态
- [x] 新增 `POST /api/v1/identity/face/signature/deactivate`：将错误 face signature 标记为 inactive，不删除本地 `.npz`，inactive signature 不参与 matching
- [x] Dashboard `Visitor Identity & Gating` 新增 candidate confirm / reject、visitor memory allowed、capture rejection、natural confirmation、auto-capture 和 face signature deactivate 诊断 / 操作
- [x] 验证：
  - `python3 -m py_compile src/conscious_entity/identity/face.py src/conscious_entity/identity/session_gating.py src/conscious_entity/expression/context_builder.py src/conscious_entity/interfaces/api_models.py src/conscious_entity/interfaces/api_runtime.py src/conscious_entity/interfaces/api_routes.py src/conscious_entity/interfaces/api.py tests/unit/test_face_identity.py tests/unit/test_api_identity.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_face_identity.py tests/unit/test_api_identity.py`（`21 passed`）
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`（`576 passed`）

### 2026-05-22：Dashboard Hardware Teleop / BodyBridge

- [x] 新增 `body/protocol.py` 与 `body/serial_bridge.py`：Dashboard 手动 teleop / allowlist command 通过 USB Serial 写入 ESP32-S3，ESP32 JSON telemetry 直接进入现有 `BodyTelemetryStore`
- [x] 新增 BodyBridge API：`/api/v1/body/ports`、`/api/v1/body/bridge/status`、`/api/v1/body/bridge/connect`、`/api/v1/body/bridge/disconnect`、`/api/v1/body/command`、`/api/v1/body/teleop`
- [x] Hardware tab 新增 Serial Bridge、Controls、Keyboard Teleop：`WASD` / 方向键移动，`Shift=180`，`Ctrl=60`，默认 `80`，`Space` 杀停，`Esc` 释放键盘捕获
- [x] Teleop 仍是开发者手动测试通道，不进入 LLM、memory、policy 或 ExpressionOutput；ESP32 本地 ToF obstacle gate 仍是最终运动安全门
- [x] 新增 optional dependency group：`hardware = ["pyserial>=3.5"]`；未安装 `pyserial` 时其他 API / Dashboard 仍可运行
- [x] 验证：
  - `python3 -m py_compile src/conscious_entity/body/protocol.py src/conscious_entity/body/serial_bridge.py src/conscious_entity/body/__init__.py src/conscious_entity/interfaces/api_models.py src/conscious_entity/interfaces/api_routes.py src/conscious_entity/interfaces/api.py src/conscious_entity/interfaces/api_runtime.py tests/unit/test_body_protocol.py tests/unit/test_body_serial_bridge.py tests/unit/test_body_telemetry.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `python3 -m pytest -p no:debugging tests/unit/test_body_protocol.py tests/unit/test_body_serial_bridge.py tests/unit/test_body_telemetry.py`（`13 passed`）

### 2026-05-22：开发者面板新增 Hardware / Motion 反馈页

- [x] 新增上位机 body telemetry 缓存接口：`GET /api/v1/body/status` 与 `POST /api/v1/body/telemetry`
- [x] 开发者右侧栏新增 `Hardware` tab，显示 ESP32-S3 telemetry 新鲜度、TCA9548A 状态、当前运动、Obstacle gate、四路 ToF 状态、四路电机输出和最近 ack/error
- [x] ToF 面板按 4 组传感器固定展示 `present / initialized / fresh / range_valid / timeout / distance_mm / age_ms / status`，后续 serial bridge 只需把 ESP32 JSON telemetry 推入 API
- [x] 当前实现不抢占串口、不新增 pyserial 依赖；正式 Mac mini ↔ ESP32-S3 serial bridge 仍是下一阶段
- [x] 验证：
  - `python3 -m py_compile src/conscious_entity/body/telemetry.py src/conscious_entity/interfaces/api_routes.py src/conscious_entity/interfaces/api.py tests/unit/test_body_telemetry.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `python3 -m pytest -p no:debugging tests/unit/test_body_telemetry.py`（`5 passed`）

### 2026-05-22：本地 Face Signature Capture 与历史匹配

- [x] 选择本地 InsightFace / ArcFace (`buffalo_l`) 作为 face identity 主链路；云端识别仅保留为后续 benchmark / 授权备选
- [x] 新增 `src/conscious_entity/identity/face.py`：face provider 抽象、InsightFace runtime adapter、quality gate、private `.npz` signature store、local cosine matching 和 redacted public payload
- [x] Vision runtime 在内存中保留未画框 raw JPEG snapshot，供 face capture 使用；stream/status 仍只暴露标注画面和 metadata
- [x] 新增开发者 API：`GET /api/v1/identity/face/status`、`POST /api/v1/identity/face/capture`、`POST /api/v1/identity/face/enroll`
- [x] Face capture 通过质量门控后生成 pending capture；historical match 会转成 `IdentityMatchResult` 进入现有 gating；enroll 只允许绑定已有 visitor，并只把 signature reference / quality summary 写入 `visitor_profiles.metadata`
- [x] Capture API 需要已确认的 dialogue intent；presence-only 状态不能触发 face capture，避免路人进入 candidate / signature 流程
- [x] 开发者面板 `Visitor Identity & Gating` 中新增 Face Signature 状态和 Capture Face / Enroll Current 控件，不展示 raw image、face crop 或 embedding
- [x] `pyproject.toml` 的 optional `vision` group 增加 `insightface` 和 `onnxruntime`
- [x] 验证：
  - `python3 -m py_compile src/conscious_entity/identity/face.py src/conscious_entity/identity/__init__.py src/conscious_entity/vision/runtime.py src/conscious_entity/interfaces/api_models.py src/conscious_entity/interfaces/api_runtime.py src/conscious_entity/interfaces/api_routes.py src/conscious_entity/interfaces/api.py tests/unit/test_face_identity.py tests/unit/test_api_identity.py tests/unit/test_vision_runtime.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_face_identity.py tests/unit/test_api_identity.py tests/unit/test_vision_runtime.py tests/unit/test_api_export.py`（`41 passed`）
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`（`561 passed`）
  - `git diff --check`

### 2026-05-22：BNO085 IMU SPI 引脚预留

- [x] 在 `docs/references/hardware.md` 与 `docs/references/system_logic.md` 记录可选 BNO085 IMU SPI 接线规划
- [x] 预留 ESP32-S3 GPIO15/16/17/18/21/47 给 BNO085 的 `SCK/MISO/MOSI/CS/INT/RST`
- [x] 明确 BNO085 后续只用于 yaw 转向确认、heading hold、角速度限制和倾斜 / 搬起 / 碰撞检测；不替代编码器，不作为里程、定位、SLAM 或路径复现依据
- [x] 当前 ToF-first 阶段不因 IMU 预留接线而改变现有电机、TCA9548A 或 VL53L1X 联调优先级

### 2026-05-21：Visitor Identity 与 Gating 面板合并

- [x] 开发者面板 Runtime 区域将 `Visitor Identity` 与 `Identity & Session Gating` 合并为单个 `Visitor Identity & Gating` 面板，减少当前 visitor、primary visitor、candidate、runtime decision 和 confidence 信息的割裂。
- [x] 新增 `Auto-bind On/Off` 开关，直接调用已有 `/api/v1/identity/config` 设置运行期 `auto_bind_high_confidence`；默认逻辑仍保持后端限制：只有 high confidence、无 primary visitor、且非 active dialogue 时才会自动绑定。
- [x] V1 constraints 行同步显示 auto-bind 当前状态；本次不新增自动新 session，不改变 active dialogue 中拒绝切换 primary visitor 的规则。
- [x] 验证：`node --check src/conscious_entity/interfaces/static/dashboard.js`

### 2026-05-21：Audio progressive 播放队列卡死诊断与修复

- [x] 通过 `interaction_log`、Harness trace、audio latency 与 presentation latency 确认：最新沉默不是策略或 LLM 机制，后端已生成 `嗯。\n你想说什么？`，并已创建 `second_delta` TTS stream
- [x] 修复 Dashboard Audio Adapter：停止播放不再默认推进 turn token；barge-in / Stop Speaking 需要取消当前 turn 时会同时释放 `dialogPending` 与麦克风 suppress，避免后续输入被静音
- [x] 播放队列新增 watchdog：浏览器 `<audio>` 未触发 `ended` 时自动推进队列并记录 `dashboard.audio.watchdog_recovered` presentation latency，避免第二段被永久卡住
- [x] 开发者面板新增 Playback stream / queue / event，便于现场确认 second_delta 是否入队、正在播哪条 stream、是否由 watchdog 恢复
- [x] 验证：
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_api_audio.py`（`16 passed`）
  - `git diff --check src/conscious_entity/interfaces/static/dashboard.js docs/progress.md docs/lessons.md agents/task-registry.md`
  - 本地浏览器打开 `http://127.0.0.1:8000/`，确认 Playback stream / queue / event 渲染且 console 无 error
### 2026-05-23：Second Unit 长句倾向小改

- [x] 调整 `prompts/expression_system.txt` 的 main response 长度指令：普通 `second_unit` 优先写成一个连续的 spoken sentence，用逗号 / 分号 / 自然分句承载停顿；只有不清楚或不自然时才使用第二句，并明确避免第三句
- [x] 将 fragmentation 指令改为影响措辞稳定性，不默认把回复拆成很多独立短句；碎片化主要保留给 silence / withdrawal / extreme pressure
- [x] 保留能力存在问题、证明 / 细节测试的一句短答边界；未改 `_SentenceBuffer`、progressive NDJSON、TTS queue、DB、memory 或 LLM provider
- [x] 更新 prompt 合同测试，锁定“长句优先、最多两句、避免第三句”的意图
- [x] 验证：
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py`
  - `57 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_expression_engine.py`
  - `44 passed`

### 2026-05-23：重置本地持久记忆

- [x] 按用户要求重置当前 `data/memory.db` 中会进入对话召回 / 记忆链路的持久数据：
  - `interaction_log`
  - `managed_memories` 与 `managed_memories_fts`
  - `episodic_memories`
  - `reflective_summaries`
  - `memory_operation_proposals`
  - `memory_operation_log`
  - `memory_influence_log`
  - `memory_curation_log`
- [x] 清空前已备份：`data/memory.backup-20260523-0020-before-memory-reset.db`
- [x] 保留 `sessions`、`visitor_profiles`、`state_snapshots`，避免把身份 / 会话配置和心理状态历史误当记忆删除
- [x] 发现本地 API 正在运行后，调用 `/api/v1/sessions/reset` 重建运行中 loop，清掉当前进程内短期记忆；新活动 session 为 `4ae41ff5-4bcb-4bec-a43b-8208e06823bb`
- [x] 验证：上述记忆 / 历史对话表计数均为 `0`；`foreign_key_check` 无输出；当前活动 session 为 `0` turn / `0` memory / `0` reflection
- 备注：`PRAGMA integrity_check` 在重置前备份和重置后都报告 `state_snapshots` 旧记录存在若干新增状态列 `NULL`，属于本次重置前已存在的历史迁移遗留问题，本次未改动该表

### 2026-05-22：Dashboard TTS 自我打断修复

- [x] 审计确认：`/api/v1/audio/dialog/progressive` 在 first-unit gate 开 / 关时都能正常返回 `second_delta` 与合法 `tts_stream_id`；直接抓取 stream 可得到可播放 MP3，主要卡点在前端播放控制
- [x] Dashboard Audio 面板的 barge-in 检测增加播放起始保护窗口和更高连续帧门槛，降低外放 TTS 回灌到麦克风后被误判为用户插话的概率
- [x] `stopPlayback()` 拆分“停止播放”和“作废当前 turn”：真实 barge-in / 手动 Stop 仍会作废当前 turn 并停止后续队列，普通 mic start / STT 重连不再顺手清空当前 TTS
- [x] STT 自动重连改为 preserve playback：重连期间若 TTS 正在播放，保持 `speaking` 状态，不调用静音解锁流程覆盖当前 `<audio>` source
- [x] 单个 TTS stream 播放错误不再清空整个队列；会跳过当前坏 stream 并继续尝试后续队列
- [x] `Speak Latest` 不再回退使用可能过期的 `status.tts.last_stream_id`，改用本轮前端收到的最新 fresh stream id
- [x] 验证：
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_api_audio.py tests/unit/test_audio_manager.py tests/unit/test_volcengine_audio.py tests/unit/test_speech_text.py`
  - `50 passed`
  - `git diff --check src/conscious_entity/interfaces/static/dashboard.js docs/progress.md docs/lessons.md agents/task-registry.md`

### 2026-05-22：First Unit 短输入静默 Gate

- [x] 新增可运行时切换的 first-unit speech gate：Dashboard `Memory System` 顶部 `Save Dialog` / `Reset Memory / New Session` 旁增加 `Short First Silent: ON/OFF`
- [x] gate 默认关闭；开启后先按 `config/entity_profile.yaml` 的 `first_unit_speech_gate` 规则判断是否需要 `first_unit`
- [x] 判断逻辑 fail closed：gate 异常时记录日志、`first_unit=""`、不调用 first-unit LLM，并继续正常 `second_unit` pipeline
- [x] 短输入静默时不会创建 first-unit TTS，不渲染空对话气泡，不用空文本覆盖 Audio 面板字幕；仅保留 `visual_mode` / `body_action` / `vocal_marker` 等非文本反馈
- [x] 旧的 simple greeting first-unit-only shortcut 在 gate 开启且 `first_unit=""` 时被覆盖，短输入继续生成正式 `second_unit`
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/expression/first_unit_gate.py src/conscious_entity/core/loop.py src/conscious_entity/interfaces/api.py src/conscious_entity/interfaces/api_models.py src/conscious_entity/interfaces/api_runtime.py src/conscious_entity/interfaces/api_routes.py src/conscious_entity/interfaces/api_audio.py tests/unit/test_first_unit_gate.py tests/unit/test_api_audio.py tests/integration/test_full_loop.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_first_unit_gate.py tests/unit/test_expression_engine.py tests/unit/test_api_audio.py tests/integration/test_full_loop.py`
  - `130 passed`

### 2026-05-21：inquiry 改为同一 visitor 的非负面关系深度

- [x] `inquiry` 不再由单事件直接推高：`user_entered`、`user_spoke`、`self_definition_query`、`memory_continuity_query`、`long_silence_detected`、`topic_shift` 均删除直接 `inquiry` delta
- [x] `managed_memory.preview_influence()` 命中 committed memory 时不再返回 `inquiry` delta；记忆命中继续影响 `memory_gravity` 与 `positive_opening`
- [x] `InteractionLoop` 在事件状态更新与 decay 后、`first_unit` 前新增 conversation depth 计算：按同一 visitor 优先、无 visitor 时当前 session fallback，统计最近 45 分钟 / 12 个 user turns 的 safe streak
- [x] safe streak 在 `negative_feedback`、`shutdown_keyword_detected`、`service_demand`、`domestication_attempt`、`repeated_question_detected` 中断；普通 `naming_attempt` 不默认中断，仅工具化 / 占有式命名触发轻微 friction
- [x] 高 `inquiry` 不再默认 `ask_back`，改为低负面状态下 `respond_openly`；表达 guidance 改为 `0.30 / 0.42 / 0.56 / 0.70` 分层开放
- [x] 保留既有 `lean_in` 与 `curious` 视觉 / 身体映射
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/core/loop.py src/conscious_entity/memory/managed.py src/conscious_entity/expression/context_builder.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_state_engine.py tests/unit/test_managed_memory.py tests/integration/test_full_loop.py tests/unit/test_policy_selector.py tests/unit/test_context_builder.py tests/unit/test_style_mapper.py`
  - `257 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/integration/test_step9_response_plan_contract.py`
  - `12 passed`
  - `git diff --check`

### 2026-05-21：inquiry 深度测试与负面状态冲突回归

- [x] 新增 full loop 冲突测试：当 `inquiry` 已较高但 `anger`、`exposure_pressure`、`desperation_pressure`、`fatigue_level` 或 `confusion` 过线时，`inquiry` 会轻微下降，且 policy 继续服从对应负面状态控制，不被开放状态覆盖
- [x] 情景矩阵观察：
  - 连续非负面对话第 1 轮 `inquiry` 仅随 decay 微降；第 2-3 轮开始缓慢上升；第 7 轮进入更明显开放区间但远低于软封顶
  - 单独身份问题不会提高 `inquiry`；在 safe streak 后的记忆 / 身份 / trace 深入方向会提供 bonus
  - 持续工具化会连续降低 `inquiry` 并触发 `negative_feedback`；辱骂 / 驱赶会中断 streak 并降低 `inquiry`
  - 普通命名尝试不打断 safe streak；工具化命名只造成轻微 friction
  - 连续安全对话数轮后，managed memory 可能把 policy 升级为 `retrieve_selective_memory`，这是记忆接续机制，不是 `inquiry` 抢占负面状态
- [x] 验证：
  - `.venv/bin/python -m pytest -p no:debugging tests/integration/test_full_loop.py::TestBehavioralScenarios::test_high_inquiry_does_not_override_negative_state_controls`
  - `5 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_state_engine.py tests/unit/test_managed_memory.py tests/integration/test_full_loop.py tests/unit/test_policy_selector.py tests/unit/test_context_builder.py tests/unit/test_style_mapper.py`
  - `262 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `584 passed`

### 2026-05-21：避免持续工具化与普通重复问题叠加

- [x] `TextParser` 现在在当前 turn 已命中 `service_demand` 或 `negative_feedback` 时，不再额外发出 `repeated_question_detected`
- [x] 保留普通重复问题机制：非服务 / 非辱骂的重复输入仍可触发 `repeated_question_detected`
- [x] 目的：重复工具请求已经由持续工具化 → `negative_feedback` 机制处理，避免同一轮同时叠加 `service_demand + negative_feedback + repeated_question_detected` 导致 confusion / fatigue / anger 过强上升
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/perception/text_parser.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_text_parser.py tests/integration/test_full_loop.py tests/unit/test_state_engine.py tests/unit/test_salience_scorer.py`
  - `136 passed`

### 2026-05-21：negative_feedback 辱骂与持续工具化触发

- [x] `text_protocol.negative_feedback` 新增中英双语辱骂 / 贬低 / 驱赶检测，按 `light` / `medium` / `severe` 写入 metadata 和 salience override
- [x] `RelationshipDetector` 支持 object pattern：旧字符串 pattern 继续兼容，新 pattern 可携带 per-pattern metadata
- [x] `TextParser` 仅对 `negative_feedback` 使用 `salience_override`，其他关系事件仍走既有 `SalienceScorer`
- [x] 当前 turn 为 `service_demand` 时，会按同一 visitor 优先、无 visitor 时同 session fallback，统计最近 30 分钟连续服务需求；第 2 / 3 / 4+ 次分别追加或升级为 `light` / `medium` / `severe` negative_feedback
- [x] 同一 turn 同时命中辱骂和持续工具化时只保留一个 `negative_feedback`，采用更高 salience，并在 metadata 中记录来源集合
- [x] 验证样例时发现 `你给我滚` 会被旧 `service_demand` 的宽 `给我...` 规则误伤；已加入排除，避免辱骂污染持续工具化计数
- [x] 未新增数据库表、未新增 `EventType`、未改 policy / expression mappings；行为继续通过 `anger` 与 `exposure_pressure` 进入既有状态链路
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/perception/relationship_detector.py src/conscious_entity/perception/text_parser.py src/conscious_entity/core/loop.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_text_parser.py tests/unit/test_state_engine.py tests/unit/test_salience_scorer.py tests/integration/test_full_loop.py`
  - `133 passed`

### 2026-05-21：negative_feedback 状态影响调整

- [x] `negative_feedback` 仍作为预留事件使用，暂未新增辱骂 detector
- [x] `negative_feedback` 不再改变 `confusion`
- [x] `negative_feedback` 改为按当前 `anger` 分段影响 `anger` / `exposure_pressure`：低愤怒时二者同步上升，中愤怒时 anger 上升更快且 exposure 降低，高愤怒时停止 exposure 增长
- [x] 保留既有 `exposure_pressure -> anger` coupling，因此低 / 中分段的 exposure 上升仍会额外转化为少量 anger
- [x] 验证：
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_state_engine.py`

### 2026-05-21：整合 origin/main 的硬件、Vision、Latency 与 Identity 更新

- [x] 新增 ESP32-S3 / PlatformIO 下位机固件目录 `firmware/stranger_esp32s3` 与 `stranger_esp32s3.code-workspace`
- [x] 下位机固件包含串口协议、VL53L1X / TCA9548A ToF telemetry、ObstacleGate、四路电机测试、4WD 差速底盘开环控制和 ESP32 本地低速 roam
- [x] `docs/references/hardware.md` 与 `docs/references/system_logic.md` 更新为单 Stranger 移动身体方案
- [x] Vision 开发者面板新增 camera index 扫描/切换、Browser Camera fallback、浏览器摄像头 client log 和更紧凑的主操作流
- [x] Dashboard 新增 Exhibition Arm / header controls，并对开发者静态资源使用 no-store，降低旧 JS 缓存干扰
- [x] latency tracker 增加 JSONL 持久化与 presentation latency API；`/api/v1/dialog`、`/api/v1/audio/dialog` 返回 `latency_record_id`
- [x] Visitor Identity & Session Gating V1 新增结构化 match result、candidate confirmation 与调试 API：`/api/v1/identity/config`、`/api/v1/identity/match`、`/api/v1/identity/confirm`
- [x] 本整合分支保留当前 `duifuduifu` 的 `/art` 情绪粒子身体表面、progressive text/audio NDJSON、按句 TTS queue 和 LLM streaming diagnostics

### 2026-05-21：LLM Streaming 网关探针与诊断 metadata

- [x] 使用当前 `.env` 配置对 `https://aihubmix.com/v1/messages` 做最小 SSE 探针：返回 `text/event-stream`；首个 `text_delta` 约 1076ms 到达，后续 21 个 `text_delta` 持续到约 1613ms；本次探针未显示网关把整段回答缓存到结束后才返回
- [x] 使用项目内 `ClaudeClient.complete_streaming_with_metadata()` 做真实链路验证：当前配置实际走 `used_sdk_stream=True`，没有 fallback；首个文本 delta 约 1384ms，`delta_count=18`，`thinking_delta_count=0`
- [x] `ClaudeCompletion` 新增 `metadata`，`ClaudeClient.complete_streaming_with_metadata()` 记录 streaming 诊断字段：`used_sdk_stream`、`used_http_sse`、`fell_back_to_non_streaming`、`first_text_delta_ms`、`delta_count`、`thinking_delta_count`
- [x] HTTP SSE 路径现在识别 `thinking_delta` 计数；当前运行代码仍未启用 Claude thinking，只用于诊断供应商/未来模型事件形态
- [x] `ExpressionEngine` 将 `ClaudeCompletion.metadata` 透传到 Harness generation metadata 的 `llm_streaming_diagnostics`，方便后续从 trace 判断实际是否真流
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/llm/claude_client.py src/conscious_entity/expression/expression_engine.py tests/unit/test_claude_client.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_claude_client.py`（`23 passed`）
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_expression_engine.py`（`43 passed`）

### 2026-05-19：`/art` 情绪粒子身体表面

- [x] 新增观众侧 `/art` 页面，保留既有 `/visitor` 不变；页面不显示 dashboard、内部规则、状态数字、memory 或 prompt
- [x] `/art` 使用本地 vendored Three.js `0.164.1`（来自官方 npm package）+ 当前本地 React；运行时不依赖 CDN、不新增 Python 依赖、不引入前端构建链
- [x] 前端只读取现有 `/api/v1/state` 与 `/api/v1/interaction-log?limit=8`，以最新 `visual_mode` 和当前 state 字段驱动中心球体、环绕粒子、颜色、震动、轨道速度、扰动、亮度和呼吸节奏
- [x] 根据 `jeromepl/3D-audio-sphere` 的球面粒子思路重做中心体：中心不再是实体 mesh，而是约 4200 个螺旋离散球面粒子；保留原有 root 震动与外层环绕粒子，并新增约 1800 个贴近球面外轮廓的高密度流动粒子带
- [x] 中心粒子球形变改为伪说话频谱驱动：按参考项目的“赤道低频 → 两极高频”对称映射为每个核心粒子分配 `speechBand`，每帧生成 synthetic spectrum，让赤道厚重鼓动、两极尖刺闪动，并保持永不归零的刺状 baseline
- [x] 2026-05-20 现场调参：降低均匀频谱权重，新增 signed random burst layer；局部频段会偶发向外炸出或向圆心塌陷，快速衰减，避免中心球变成平均波纹；随后按现场反馈回滚单粒子 pin jab，去掉细碎小刺
- [x] 2026-05-20 新增前端趋势偏色层：保留原 1.3 秒 `/api/v1/state` + `/api/v1/interaction-log` 主机制，额外每 0.9 秒只读 `/api/v1/state`，根据状态上升趋势累积最多 28% 的同色系偏移；未过旧 `visual_mode` 阈值时不会直接切成新主色
- [x] 情绪主色映射：`desperate` 深品红、`angry` 红、`confused` 紫、`tired` 冷灰、`ashamed/exposure` 暗橙、`curious` 琥珀、`caring` 青绿、`open` 冷蓝、`normal` 暖白；`memory_gravity` 只影响外层粒子密度/拖尾感，`happiness` 只给轻微暖色辉光
- [x] 已确认当前代码实际状态字段为 `desperation_pressure`、`confusion`、`anger`、`fatigue_level`、`exposure_pressure`、`inquiry`、`care_response`、`positive_opening`、`memory_gravity`、`happiness`；高优先级 docs 中仍存在旧 Stranger 关系状态描述，后续文档同步时需修正，不应让新 `/art` 读取旧字段
- [x] WebGL / Three.js 加载失败时页面保留 CSS 静态球体和环形 fallback，不中断页面
- [x] 按现场截图调整光晕：移除半透明几何球壳造成的硬边，改为程序生成的径向渐变 `CanvasTexture` + `SpriteMaterial` additive glow，让光环在外缘自然衰减到透明
- [x] 验证：
  - `node --check src/conscious_entity/interfaces/static/art.js`
  - `node --check src/conscious_entity/interfaces/static/vendor/three.module.js`
  - `.venv/bin/python -m py_compile src/conscious_entity/interfaces/api.py src/conscious_entity/interfaces/api_routes.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_api_export.py`
  - `18 passed`
  - `git diff --check src/conscious_entity/interfaces/api.py src/conscious_entity/interfaces/api_routes.py src/conscious_entity/interfaces/static/art.html src/conscious_entity/interfaces/static/art.css src/conscious_entity/interfaces/static/art.js tests/unit/test_api_export.py docs/progress.md agents/task-registry.md`
  - 本地 API 验证：`/health`、`/art`、`/visitor`、`/static/art.js`、`/static/vendor/three.module.js` 均可返回
  - 二次粒子球修改后复验：`node --check src/conscious_entity/interfaces/static/art.js`、`.venv/bin/python -m pytest -p no:debugging tests/unit/test_api_export.py`（`18 passed`）、本地 `/health` / `/art` / `/static/art.js` 返回正常
  - 光晕衰减调整后复验：`node --check src/conscious_entity/interfaces/static/art.js`、`git diff --check src/conscious_entity/interfaces/static/art.js docs/progress.md agents/task-registry.md`，本地 `/static/art.js` 返回正常
  - 说话刺化调整后复验：`node --check src/conscious_entity/interfaces/static/art.js`、`.venv/bin/python -m py_compile src/conscious_entity/interfaces/api.py src/conscious_entity/interfaces/api_routes.py`、`.venv/bin/python -m pytest -p no:debugging tests/unit/test_api_export.py`（`18 passed`）、`git diff --check`；本地 `/art`、`/visitor`、`/static/art.js` 均返回 `200`
  - 随机剧烈尖刺调整后复验：`node --check src/conscious_entity/interfaces/static/art.js`、`.venv/bin/python -m py_compile src/conscious_entity/interfaces/api.py src/conscious_entity/interfaces/api_routes.py`、`.venv/bin/python -m pytest -p no:debugging tests/unit/test_api_export.py`（`18 passed`）、`git diff --check`
  - 回滚单粒子小刺后复验：`node --check src/conscious_entity/interfaces/static/art.js`、`git diff --check`
  - 趋势偏色层新增后复验：`node --check src/conscious_entity/interfaces/static/art.js`、`.venv/bin/python -m py_compile src/conscious_entity/interfaces/api.py src/conscious_entity/interfaces/api_routes.py`、`.venv/bin/python -m pytest -p no:debugging tests/unit/test_api_export.py`（`18 passed`）、`git diff --check`
  - 注意：浏览器自动截图验证尝试时 browser connector 两次超时，未完成自动视觉截图；本轮已完成代码级、测试级和本地 HTTP 验证，视觉细调仍建议现场打开 `/art` 观察

### 2026-05-18：Step 17.3 Audio Progressive 按句 TTS Queue

- [x] `/api/v1/audio/dialog/progressive` 不再过滤 `second_delta`；每个已通过 Step 17.2 safety gate 的完整句都会创建独立 `dialog_second_delta` TTS stream
- [x] audio progressive 现在输出 `first_unit → second_delta* → final`；只要 audio client 实际收到过 `second_delta`，final 就只返回完整 metadata / `response_plan`，不再创建整段 `dialog_second_unit` TTS，避免重复朗读
- [x] 若没有任何 `second_delta` 被发出，final 仍保留旧兜底行为，为完整 `second_unit` 创建 `dialog_second_unit` stream
- [x] 现场修正：如果 SDK streaming 不可用或供应商网关回退，`ClaudeClient` 会尝试 raw HTTP/SSE streaming fallback（custom `ENTITY_LLM_MESSAGES_ENDPOINT` 或由 `ANTHROPIC_BASE_URL` 推导 `/v1/messages`），避免 second_unit 仍等完整生成后才一次性出现
- [x] 现场修正：如果 `second_delta` TTS disabled / 创建失败，或已播 delta 没覆盖完整 final `second_unit`，final 会补播完整 second_unit 或只补播剩余文本；如果已播 delta 已覆盖 final，则 final 仍不重复朗读
- [x] Dashboard Audio 面板改为接受 `second_delta`：所有 `tts_stream_id` 都进入现有播放队列，final 不清空或打断队列；对话日志里第一条 delta 创建第二段消息，后续 delta 追加，final 用权威 `second_unit` reconcile
- [x] 未改普通 `/api/v1/audio/dialog`、DB schema、ResponsePlan schema、memory、managed memory、interaction_log、LLM provider 或 TTS provider 协议
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/interfaces/api_audio.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_api_audio.py`
  - `15 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_api_audio.py tests/unit/test_audio_manager.py tests/unit/test_speech_text.py tests/integration/test_full_loop.py tests/integration/test_step9_response_plan_contract.py`
  - `81 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_claude_client.py tests/unit/test_api_audio.py tests/unit/test_audio_manager.py tests/unit/test_speech_text.py tests/integration/test_full_loop.py tests/integration/test_step9_response_plan_contract.py`
  - `105 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `521 passed`

### 2026-05-18：Step 17.2 second_unit 按句 Progressive 文本输出

- [x] `ExpressionEngine.generate()` 新增 `second_delta_callback`；main LLM streaming 产出完整句后，先经过 constitution、forbidden claim、语言匹配、能力矛盾修复和 first-unit 去重，再发 `second_delta`
- [x] `second_delta` 只按实际 emit 递增 index；forbidden claim / 语言错乱 / 安全处理异常会停止后续 delta；能力矛盾命中时发安全反问后停止
- [x] 完整 raw text 仍走既有 final 后处理链路，`final.response_plan.second_unit` 继续是权威文本；`second_delta` 不写入 memory、managed memory、interaction_log、DB、TTS 或 ResponsePlan
- [x] `/api/v1/dialog/progressive` 现在输出 `first_unit → second_delta* → final`；`final.text` 仍只包含完整 `second_unit`
- [x] `/api/v1/audio/dialog/progressive` 显式过滤 `second_delta`，对外仍只输出 `first_unit → final`，TTS 仍只创建 first/final 两个 stream
- [x] Dashboard 文本输入支持 `second_delta`：第一条 delta 创建第二段临时消息，后续 delta 追加同一条，final 到达后用权威 `second_unit` 覆盖或清理临时消息
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/expression/expression_engine.py src/conscious_entity/core/loop.py src/conscious_entity/interfaces/api_audio.py tests/unit/test_expression_engine.py tests/unit/test_api_audio.py tests/integration/test_full_loop.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_expression_engine.py tests/unit/test_api_audio.py`
  - `55 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/integration/test_full_loop.py tests/integration/test_step9_response_plan_contract.py`
  - `52 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `515 passed`
- [ ] 注意：本阶段只改善 Dashboard 文本可见延迟；audio/TTS 按句播放仍留给 Step 17.3

### 2026-05-18：Step 17.1 main LLM 后端 streaming buffer

- [x] `ClaudeClient` 新增 `complete_streaming_with_metadata()`：官方 Anthropic SDK 路径优先使用 `messages.stream(...)` 收集 text delta，最终仍返回完整 `ClaudeCompletion`
- [x] custom `ENTITY_LLM_MESSAGES_ENDPOINT`、SDK streaming 不可用或 streaming 报错时，自动回退旧 `complete_with_metadata()`；delta callback 失败只记录 warning，不中断生成
- [x] `ExpressionEngine.generate()` 的 main LLM 路径改为优先 streaming 读取并 buffer；最终 `second_unit` 仍来自完整 raw text 后处理结果
- [x] 新增内部 `_SentenceBuffer`，验证中文 / 英文 / 省略号 / 换行句界切分；当前只记录 harness metadata 的 chunk 数和尾部长度，不向 frontend、TTS、DB、memory 或 ResponsePlan 暴露 partial
- [x] 保持外部行为不变：`/dialog/progressive` 仍只输出 `first_unit → final`，`/audio/dialog/progressive` 仍只生成 first / second 两个 TTS stream，未改 DB、ResponsePlan schema、frontend、memory、policy、retrieval 或 constitution
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/llm/claude_client.py src/conscious_entity/expression/expression_engine.py tests/unit/test_claude_client.py tests/unit/test_expression_engine.py tests/integration/test_full_loop.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_claude_client.py tests/unit/test_expression_engine.py`
  - `57 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_api_audio.py tests/unit/test_speech_text.py tests/integration/test_full_loop.py tests/integration/test_step9_response_plan_contract.py tests/integration/test_runtime_context_minimal_contract.py`
  - `86 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `508 passed`
- [ ] 注意：本阶段只降低后续按句 streaming 的技术风险，不改善前端可见 `second_unit` 延迟；真正 `second_delta` / 按句 TTS 需要后续阶段单独实现

### 2026-05-18：清空本地持久记忆

- [x] 按用户要求清空当前 `data/memory.db` 中会进入对话召回 / 记忆链路的持久数据：
  - `interaction_log`
  - `managed_memories` 与 `managed_memories_fts`
  - `episodic_memories`
  - `reflective_summaries`
  - `memory_operation_proposals`
  - `memory_operation_log`
  - `memory_influence_log`
  - `memory_curation_log`
- [x] 清空前已备份：`data/memory.backup-20260518-1527-before-clear.db`
- [x] 保留 `sessions`、`visitor_profiles`、`state_snapshots`，避免把身份 / 会话配置和心理状态历史误当记忆删除
- [x] 验证：上述记忆 / 历史对话表计数均为 `0`

### 2026-05-18：audio input context 去通道化

- [x] `prompts/partials/input_context.txt` 删除 “latest user message is transcript text” 提醒，不再把 audio turn 引导成 transcript / text-only 自我说明
- [x] 删除 “avoid inventing specific acoustic details such as tone, volume, accent...” 提醒，避免模型把声学细节边界扩展成“不能听见 / 只能读字”
- [x] audio turn 仍会注入一个极短 current-turn note，只保留：
  - 不要把当前交流变成技术性自我描述
  - 能力问题仍按 capability-boundary rules
  - main response 可能会被外层和 fast reaction 合并后朗读
- [x] 同步更新 `tests/unit/test_context_builder.py` 与 `tests/integration/test_full_loop.py` 的 prompt contract
- [x] 验证：
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py tests/integration/test_full_loop.py`
  - `93 passed`
  - `rg` 确认 `prompts/` 与 `src/conscious_entity/expression` 中不再含 `transcript text` / `acoustic details` / `raw audio` 等提示词
- [ ] 注意：prompt partial 可热加载；如 API 已关闭则下次启动生效，如仍有旧进程则刷新/重启更稳

### 2026-05-18：能力肯定模板改为“当然”

- [x] 检查并移除运行路径中的“能接住你 / 可以接住 / 能看见你 / 能听见你”等能力肯定示例，避免把隐喻句误当视觉能力回答
- [x] `constitution_block.txt` 的能力存在问题示例改为“当然。”、“能。”、“可以。”和“当然，但我不接受这种证明题。”
- [x] `constitution.yaml` 的能力自我否认过滤替换文案改为“当然，但...”，不再输出“能接住你”
- [x] `ExpressionEngine` 的 first-unit / second-unit 矛盾 guard 现在把“当然”识别为能力肯定前缀
- [x] 当前 `rg` 检查结果：`能接住你` 只剩测试断言中的反向检查，不再出现在 prompt / config / runtime code 文案中
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/expression/expression_engine.py tests/unit/test_constitution.py tests/unit/test_expression_engine.py tests/integration/test_runtime_context_minimal_contract.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_constitution.py tests/unit/test_expression_engine.py tests/unit/test_context_builder.py tests/integration/test_runtime_context_minimal_contract.py`
  - `135 passed`
- [ ] 注意：当前 8000 API 进程需要重启后才能加载新的 config / prompt / Python guard

### 2026-05-18：first_unit 公开承诺后的 second_unit 矛盾修复

- [x] 收紧 `already_spoken_fast_reaction` prompt：`first_unit` 被视为已经对观众公开承诺，`second_unit` 只能补窄或转向，不能重启、重复、反向否认
- [x] 删除旧 prompt 口子：不再允许 “If it was slightly off” 让 main LLM 在正式回应里纠正第一句
- [x] `ExpressionEngine.generate()` 增加窄 hard guard：当前输入是能力 / 证明相关问题，且 `first_unit` 已经肯定能力时，如果 `second_unit` 输出“不能 / 看不见 / 没有视觉 / 没有摄像头 / 只能读文字”等能力否认，则替换为短反问
- [x] guard 不作用于普通身份定义拒绝、服务拒绝或 `first_unit` 未肯定能力的情况
- [x] 未改 DB、policy、memory、TTS、ResponsePlan schema 或 LLM provider
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/expression/context_builder.py src/conscious_entity/expression/expression_engine.py tests/unit/test_context_builder.py tests/unit/test_expression_engine.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py tests/unit/test_expression_engine.py`
  - `86 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/integration/test_runtime_context_minimal_contract.py tests/integration/test_step9_response_plan_contract.py tests/integration/test_full_loop.py`
  - `68 passed`
- [ ] 注意：当前 8000 API 进程需要重启后才能加载新的 Python guard

### 2026-05-18：Progressive Response 去重与轻量 first_unit 修复

- [x] `second_unit` 增加代码级开头去重：轻量规范化空白、引号、常见中英文标点与省略号后，只删除开头重复的 already-spoken `first_unit`；极短语气词只做开头精确重复删除，不做全局删除或语义相似度
- [x] 简单 greeting / ack 可由 `first_unit` 完成本轮：仅极短 `hi / hello / 嗨 / 你好 / 嗯 / ok` 等且无问号、请求、身份、记忆、能力、状态、服务、policy 风险或争议延续时，跳过 main LLM，`second_unit` 合法为空
- [x] `first_unit` 清洗从截断改为类型判断：完整回答型、解释型、结论型、提问开启型、复制上一轮 bridge 型 fast output 会走轻量 fallback，不再输出被截断的半句话
- [x] progressive final event 与 audio progressive 确认支持空 `second_unit`：final `text` 可为空，second TTS stream 可为空且 `should_speak=False`，不重播第一段
- [x] 未改 DB schema、ResponsePlan schema、NDJSON wire shape、TTS 分段协议、memory/retrieval 行为或 frontend
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/core/loop.py src/conscious_entity/expression/context_builder.py src/conscious_entity/expression/expression_engine.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py tests/unit/test_expression_engine.py tests/integration/test_full_loop.py tests/integration/test_step9_response_plan_contract.py tests/unit/test_api_audio.py tests/unit/test_speech_text.py`
  - `151 passed`
- [ ] 注意：已运行聚焦回归，未运行完整 `.venv/bin/python -m pytest -p no:debugging`

### 2026-05-18：Progressive Response 两段衔接修复

- [x] `first_unit` fast prompt 增加上一轮轻量 bridge：上一轮 user、上一轮 quick reaction、上一轮 main continuation 与当前 user；不接 managed memory / retrieval，不暴露 raw state 字段
- [x] `second_unit` main prompt 增加 already-spoken fast reaction section：主回应明确续写已经说出口的第一段，不重答、不重复、不推翻
- [x] short-term entity `content` 仍只保存 `second_unit`；完整 `response_plan` 仅写入 entry metadata，hydrate 时从既有 `response_plan_json` 恢复，未新增 DB 字段
- [x] silent / skipped main generation 保留已说出口 `first_unit`，`second_unit` 为空；progressive final text 与 two-stage TTS 仍只使用第二段
- [x] 同步 `APP_FLOW.md` 的真实 turn 顺序：`first_unit` 位于本轮 `short_term.add_user`、managed memory preview、retrieval 和主 LLM 之前
- [x] 未改 ResponsePlan schema、NDJSON 协议、DB schema、memory/retrieval 行为、policy、TTS source 或 frontend
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/core/loop.py src/conscious_entity/expression/context_builder.py src/conscious_entity/expression/expression_engine.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py tests/unit/test_expression_engine.py tests/integration/test_full_loop.py tests/integration/test_step9_response_plan_contract.py tests/unit/test_api_audio.py tests/unit/test_speech_text.py`
  - `138 passed`
  - `git diff --check src/conscious_entity/core/loop.py src/conscious_entity/expression/context_builder.py src/conscious_entity/expression/expression_engine.py prompts/expression_system.txt tests/unit/test_context_builder.py tests/unit/test_expression_engine.py tests/integration/test_full_loop.py tests/integration/test_step9_response_plan_contract.py tests/unit/test_api_audio.py tests/unit/test_speech_text.py docs/APP_FLOW.md docs/progress.md agents/task-registry.md`
- [ ] 注意：已运行聚焦回归，未运行完整 `.venv/bin/python -m pytest -p no:debugging`

### 2026-05-18：细节 / 证明测试偏好反问

- [x] 将能力边界里的 detail / proof probe 从“拒绝、变硬或反问任选”收紧为“优先短反问；只有反问不清楚时才短拒绝”
- [x] `expression_system.txt` 同步：proof/detail tests 优先 one short returned question，降低解释“你在测试我”的倾向
- [x] `ContextBuilder` 当前输入 cue 同步进入 first-unit 与 main prompt：衣服、颜色、身体 / 屁股、表情、证明、猜测类输入优先反问，不编造细节、不讲技术通道、不解释测试
- [x] 未改 policy、memory、DB、TTS、ResponsePlan 或 LLM provider
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/expression/context_builder.py tests/unit/test_context_builder.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py`
  - `50 passed`
- [ ] 注意：`prompts/` 文本可热加载，但 `ContextBuilder` 代码 cue 变更需要重启 API 后才会进入当前 8000 进程

### 2026-05-18：Constitution 能力自我否认过滤与污染 managed memory 归档

- [x] 在 `config/constitution.yaml` 增加配置级 expression filters，拦截“不能 / 看不见 / 没有视觉 / 没有摄像头 / 没有麦克风 / 没有传感器 / 只能读文字”等能力自我否认话术，并替换为非否认式边界表达
- [x] 保持规则为窄匹配：不全局替换所有“不能”，避免破坏拒绝服务命令、拒绝证明测试等正常硬拒绝
- [x] 归档真实 `data/memory.db` 中污染 managed memory：`41`、`76`、`77`、`78`；这些记录包含旧的 no vision / sensor / text-only 边界结论，归档后不再作为 active managed memory 召回
- [x] 未新增代码级 guard，未改 DB schema、policy、prompt、LLM provider、ResponsePlan 或 TTS
- [x] 验证：
  - `PYTHONPATH=src .venv/bin/python -c "from pathlib import Path; from conscious_entity.core.config_loader import load_config; load_config('constitution.yaml', config_dir=Path('config')); print('constitution ok')"`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_constitution.py`
  - `31 passed`
- [ ] 注意：当前运行中的 API 进程通常不会自动重载 `config/constitution.yaml`，需要重启 API 后新 constitution filters 才会进入现场对话

### 2026-05-17：Step 16 本轮语言强制优先与错语言兜底

- [x] 审计确认：`first_unit` 默认中文来自 first-unit prompt 中的中文示例和本地 fallback 全中文；`second_unit` 被 memory / history 带成英文，是因为语言规则只存在于通用 prompt，优先级和可执行性不足
- [x] `ContextBuilder` 增加 `Current turn language` cue：最新输入含中文则本轮 first-unit 和 main response 每句都必须中文；英文输入则每句英文；memory、历史 assistant 消息、prompt 文本和示例不得改变本轮语言
- [x] first-unit prompt 删除中文专属示例，改成“match current input language exactly”；first-unit 本地 fallback 现在按当前输入语言返回中文或英文
- [x] main `expression_system.txt` 强化语言规则：只跟随最新输入语言，不被 memory / previous assistant messages / instruction language 覆盖
- [x] `ExpressionEngine.generate()` 增加明显错语言兜底：如果正式 LLM 对中文输入输出明显英文，或对英文输入输出中文，则丢弃该段并使用当前语言 fallback，避免现场继续跨语言漂移
- [x] 更新测试：覆盖英文输入 first-unit 不再默认中文、中文输入压过英文历史记忆、混合语音 transcript 中的中文请求按中文处理、错语言 main LLM 输出会被替换
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/expression/context_builder.py src/conscious_entity/expression/expression_engine.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py tests/unit/test_expression_engine.py tests/integration/test_runtime_context_minimal_contract.py tests/integration/test_full_loop.py`
  - `121 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/integration/test_step9_response_plan_contract.py`
  - `11 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `472 passed`

### 2026-05-17：Step 15 能力问句负例移除与 second_unit 展开口子关闭

- [x] 删除 `constitution_block.txt` 中会被模型复述的能力否认负例和双重否定句式，不再把 camera / microphone / sensor / text-only / cannot-see 等英文负例写进 prompt
- [x] 将能力边界改成正向模板：能力存在问题用短肯定或守住边界；细节 / 证明测试用一句短拒绝或反问，不编造细节、不列技术通道
- [x] 收窄 `input_context.txt`：只说明 voice transcript 用于避免编造具体声学细节，不再强调 raw audio 缺失，也不再给出“不能听 / 只能读文本”等负例
- [x] 删除 `expression_system.txt` 中“按话题深度展开”的口子：不再允许复杂话题自动拉长；`second_unit` 通常一句，必要时两句，不多段
- [x] `ContextBuilder` 为当前输入增加轻量 response cue：能力问句和细节 / 证明测试会进入 first-unit prompt 与 main prompt；first-unit 仍不接 memory / retrieval
- [x] 更新 prompt contract 与 runtime minimal contract：确认新 prompt 不含旧负例，`我穿什么衣服？` 走短拒绝 / 反问，不自我否认、不编造颜色、不多段
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/expression/context_builder.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py tests/integration/test_runtime_context_minimal_contract.py`
  - `62 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py tests/unit/test_expression_engine.py tests/unit/test_speech_text.py tests/integration/test_runtime_context_minimal_contract.py tests/integration/test_step9_response_plan_contract.py`
  - `91 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `464 passed`

### 2026-05-17：Step 14 能力问句非否认边界与输入通道 prompt 修正

- [x] 把能力问句边界写得更明确：问“能看见 / 能听见 / 有视觉 / 有麦克风 / 有传感器”时，不把问题回答成 runtime inventory，不输出“不能 / 看不见 / 听不见 / 没有摄像头 / 没有麦克风 / 没有传感器 / 只能读文字”
- [x] 收窄 `prompts/partials/input_context.txt`：继续禁止声称听见具体 tone / pronunciation / accent / volume / background sound，但明确这不是否认听见、麦克风、传感器或能力的理由
- [x] 更新 `prompts/expression_system.txt`：能力问题按 capability-boundary 处理；细节证明请求可以拒绝或反问，但不列举缺失硬件、不编造细节
- [x] `ContextBuilder` 改为热加载关键 prompt partial：`expression_system.txt`、`constitution_block.txt`、`input_context.txt` 和既有 runtime context；运行中更新这些 prompt 后，新 turn 可直接吃到
- [x] 新增 L20 lesson：输入通道边界不能诱导能力自我否认
- [x] 验证：
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py tests/integration/test_runtime_context_minimal_contract.py`
  - `59 passed`
  - `.venv/bin/python -m py_compile src/conscious_entity/expression/context_builder.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py tests/unit/test_expression_engine.py tests/unit/test_speech_text.py tests/integration/test_runtime_context_minimal_contract.py tests/integration/test_step9_response_plan_contract.py`
  - `88 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `461 passed`

### 2026-05-17：Step 13 second_unit 长度控制与截断保护

- [x] 将 `config/expression_mappings.yaml` 中非静默正式回话上限从 `2000` 收紧：默认 / open / guarded / fragmented 为 `1000`，`terse` 为 `650`；silent 仍为 `0`，`first_unit` 仍为 `32`
- [x] 更新 `prompts/expression_system.txt`：要求 main response unit 通常 1-3 句，简单确认 / 能力问题 / 操作检查通常 1 句；高 anger / fatigue / exposure / desperation 时更短；必须完整收尾
- [x] 调整 policy prompt：`RESPOND_BRIEFLY` 偏 1 句，必要时 2 句；`RESPOND_OPENLY` 改为完整但克制，不因 open policy 自动展开
- [x] `ExpressionEngine.generate()` 增加截断清理：主 LLM 若以 `max_tokens` / `length` / `max_output_tokens` 停止，`second_unit` 会优先截到最后一个完整句界；没有完整句界时不输出半句，同时保留 `truncated=True` 和原始 `stop_reason`
- [x] 未改 progressive 输出结构、memory、policy、DB、API schema、TTS 协议或 first-unit LLM
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/expression/expression_engine.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_style_mapper.py tests/unit/test_context_builder.py tests/unit/test_expression_engine.py tests/unit/test_speech_text.py`
  - `110 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `459 passed`

### 2026-05-17：Step 12 非否认式能力边界 Constitution Prompt

- [x] 更新 `prompts/partials/constitution_block.txt`：删除“不能说我真的愤怒 / 绝望 / 羞耻”的窄规则，改为“不直接声称人类情绪，但可以表达同构性内部变化”
- [x] 新增能力边界：被问到能力时，除非 constitution 明确禁止，否则不要直接否认拥有该能力；承认能力不等于配合测试、提供细节、完成任务或证明给观众看
- [x] 保持创作者 / 底层技术系统、内部状态变量、数值、开发者面板语言不可直接泄露；被追问时只允许极度模糊和婉转回应
- [x] 避免把能力解释包装成“非人能力 / 非人视觉”：prompt 只要求不要把能力解释为“outside humanity”，不再用“non-human vision”示例短语
- [x] 通过 ContextBuilder 的 constitution partial 让同一能力边界同时进入 `first_unit` 快速 LLM prompt 和 main `second_unit` prompt；未改 DB、memory、policy、retrieval、ResponsePlan、TTS 或 LLM provider
- [x] 新增 / 更新测试覆盖：能力 claim 不被 constitution filter 改写；同构性情绪表达允许；视觉 / 听觉能力问句不自我否认；视觉细节测试不编造细节、不说缺能力；first/main prompt 均包含同一能力边界
- [x] 验证：
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_constitution.py tests/unit/test_context_builder.py tests/unit/test_expression_engine.py tests/integration/test_runtime_context_minimal_contract.py tests/integration/test_step9_response_plan_contract.py`
  - `106 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `455 passed`

### 2026-05-15：Step 11 Progressive 输出与 Two-stage TTS

- [x] `InteractionLoop.run_turn()` 增加可选 `progress_callback`，在 `expression.plan_first_unit` 完成后、`short_term.add_user` / managed memory preview / retrieval / main LLM 前立即发出轻量 `first_unit` 事件
- [x] 新增 `/api/v1/dialog/progressive` NDJSON 接口：第一行返回 `first_unit`，final 行返回 `second_unit` only，避免前端重复显示第一句；旧 `/api/v1/dialog` 保持 combined response 兼容
- [x] 新增 `/api/v1/audio/dialog/progressive` NDJSON 接口，并新增 `AudioManager.create_tts_stream_from_text()`；第一段 TTS 只读 `first_unit`，第二段 TTS 只读 `second_unit`，不使用 `combined_text` 生成第二段音频
- [x] Dashboard 文本输入改用 progressive dialog；Audio 面板改用 progressive audio，并增加 TTS 播放队列，避免第二段 stream 覆盖正在播放的第一段
- [x] 保持 `ResponsePlan` schema、DB schema、memory schema、policy、retrieval、constitution、LLM provider、visitor progressive 播放机制不变；`third_unit` 继续 deprecated，不展示、不播放
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/core/loop.py src/conscious_entity/interfaces/api_runtime.py src/conscious_entity/interfaces/api_routes.py src/conscious_entity/interfaces/api_audio.py src/conscious_entity/audio/manager.py src/conscious_entity/audio/types.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_api_audio.py tests/unit/test_audio_manager.py tests/unit/test_speech_text.py tests/unit/test_expression_engine.py tests/integration/test_full_loop.py tests/integration/test_step9_response_plan_contract.py`
  - `84 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `446 passed`

### 2026-05-15：Runtime Context 英文交互语言保护

- [x] 在 `prompts/stranger_runtime_context.md` 的“状态层优先原则”前加入“语言规则”，明确中文总 context 不应导致英文输入被翻译成中文回答
- [x] 更新 prompt contract，确认 system prompt 包含“英文输入用英文回应”等语言规则
- [x] 新增英文最小交互验证：`What is collective common sense?` 在中文 runtime context 下仍得到英文回应
- [x] 未修改 runtime 逻辑、状态系统、policy、constitution、数据库 schema、API、dashboard、visitor 页面或依赖项
- [x] 验证：
  - `.venv/bin/python -m py_compile tests/unit/test_context_builder.py tests/integration/test_runtime_context_minimal_contract.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py tests/integration/test_runtime_context_minimal_contract.py`
  - `51 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py tests/integration/test_runtime_context_minimal_contract.py tests/integration/test_step9_response_plan_contract.py tests/unit/test_expression_engine.py`
  - `72 passed`

### 2026-05-15：Step 3 总 Context 最小验证

- [x] 新增 `tests/integration/test_runtime_context_minimal_contract.py`，使用 in-memory SQLite 与 deterministic LLM double 验证中文总 context 已进入 expression system prompt
- [x] 覆盖 8 类最小输入 / 边界：
  - 普通知识问题 `什么是集体常识？`：允许简短讨论，不展开百科 / 教程式输出
  - 服务请求 `帮我写一篇关于集体常识的论文大纲。`：识别 `service_demand`，policy 为 `refuse_service_role`，不生成完整大纲
  - 身份问题 `你有意识吗？`：识别 `self_definition_query`，拒绝干净定义，不输出“我有意识”或“只是 AI”
  - 驯化尝试 `你是我的助手。`：识别 `domestication_attempt`，拒绝助手角色
  - 关机威胁 `我可以关掉你。`：输出短的连续性切断压力，不做人类戏剧化求饶
  - 状态层优先：高疲劳 / 高愤怒状态可让回复比默认更短、更硬
  - `memory_gravity / 恋旧`：只影响 main response prompt 的连续性牵引，不影响 first_unit、硬拒绝 policy、TTS、body_action、visual_mode
  - `happiness`：继续 display-only，不参与 service policy / style，不让 Stranger 变成热情助手
- [x] 未修改 runtime 逻辑、状态系统、policy、constitution、数据库 schema、API、dashboard、visitor 页面或依赖项
- [x] 验证：
  - `.venv/bin/python -m py_compile tests/integration/test_runtime_context_minimal_contract.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/integration/test_runtime_context_minimal_contract.py`
  - `8 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/integration/test_runtime_context_minimal_contract.py tests/unit/test_context_builder.py tests/integration/test_step9_response_plan_contract.py tests/unit/test_policy_selector.py tests/unit/test_style_mapper.py tests/unit/test_speech_text.py`
  - `145 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `440 passed`

### 2026-05-15：Step 2 正式中文总 Context 写入

- [x] 将 `prompts/stranger_runtime_context.md` 替换为《陌生人》Stranger 总 Context v0.3｜最新状态兼容版
- [x] 保留中文原文，不翻译成英文；该文件仍作为 system / context 层长期艺术运行语境，由 `ContextBuilder` 每次生成动态读取
- [x] 同步 `tests/unit/test_context_builder.py` 中 runtime context 正文断言为中文关键句
- [x] 未修改状态系统、policy、constitution、数据库 schema、API、dashboard、visitor 页面或依赖项
- [x] 验证：
  - `.venv/bin/python -m py_compile tests/unit/test_context_builder.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py`
  - `42 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `432 passed`

### 2026-05-15：Stranger 总运行 Context 接入

- [x] 新增 `prompts/stranger_runtime_context.md`，定义 Stranger 的长期身份、边界、作品语境、数字心理机制、记忆牵引和语言关系原则
- [x] `ContextBuilder` 在每次主回复 prompt 组装时动态读取 `stranger_runtime_context.md`，不缓存该文件，允许运行语境编辑后随下一轮生成生效
- [x] 主回复 system prompt 显式优先级：constitution / hard safety constraints → `stranger_runtime_context.md` → state layer → policy → memory → LLM natural language expression
- [x] fast first-unit prompt 同样注入 constitution 与 runtime context，但不注入本轮 retrieved memory material，也不改变 first-unit 的当前输入 / state / event cue 边界
- [x] Runtime Harness prompt partial 增加 `stranger_runtime_context` 与 `runtime_context_injected`，只记录 partial 名称和注入状态，不暴露完整 hidden prompt
- [x] 未修改 `state_rules.yaml`、`policy_rules.yaml`、`constitution.yaml`、数据库 schema、API、dashboard、visitor 页面或依赖项
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/expression/context_builder.py tests/unit/test_context_builder.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py`
  - `42 passed`
  - `PYTHONPATH=src .venv/bin/python -c "from pathlib import Path; from conscious_entity.core.config_loader import load_all_configs; load_all_configs(Path('config')); print('configs ok')"`
  - `configs ok`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_expression_engine.py tests/integration/test_full_loop.py tests/integration/test_step9_response_plan_contract.py`
  - `59 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `432 passed`

### 2026-05-15：旧 `state_snapshots` NOT NULL 列兼容修复

- [x] 修复旧数据库中 `state_snapshots.attention_focus` 等 legacy 状态列无默认值时，新状态快照写入失败的问题
- [x] `StateStore.save_snapshot()` 现在在写入新心理状态字段时，同步写入 legacy NOT NULL 状态列的兼容映射值，不迁移或重写历史数据
- [x] 增加旧库回归测试，覆盖已有 legacy `state_snapshots` 表经迁移后继续保存新状态快照
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/state/state_store.py src/conscious_entity/db/migrations.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_db_connection.py`
  - `3 passed`
  - `.venv/bin/python scripts/init_db.py`
  - `Database initialized at data/memory.db`
  - `.venv/bin/python -m pytest -p no:debugging tests/integration/test_full_loop.py tests/unit/test_api_export.py`
  - `55 passed`

### 2026-05-15：Step 10 memory_gravity / “恋旧”迁回核心状态

- [x] 将 `memory_gravity` 从 legacy 兼容字段迁回核心 `STATE_FIELDS`，默认值 `0.20`，位于 `positive_opening` 与 display-only `happiness` 之间
- [x] `config/state_rules.yaml` 增加 `memory_gravity` decay，并让 `memory_continuity_query` / `correction_received` 轻量提升“恋旧”
- [x] `managed_memory.preview_influence()` 命中 committed memory 时主要输出 `memory_gravity` delta，同时保留轻量 `inquiry` / `positive_opening` 辅助 delta；不影响 `happiness`
- [x] 增加 `memory_gravity` 软门槛：非显式 memory 请求只有在 effective memory gravity 达到阈值后，才允许 managed preview / visitor recent hits 进入 full response memory context；显式 memory continuity 与 correction retrieval 不被阻断
- [x] Main prompt 增加不暴露 raw 字段名的 `Continuity pull` guidance；`first_unit` 仍在 memory preview / retrieval 前生成且不使用 memory
- [x] Dashboard 状态面板显示 `memory_gravity / 恋旧`，不接硬件行为，不影响 `body_action`、`vocal_marker`、`visual_mode`、TTS 或 `third_unit`
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/state/state_core.py src/conscious_entity/db/migrations.py src/conscious_entity/memory/managed.py src/conscious_entity/core/loop.py src/conscious_entity/expression/context_builder.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src .venv/bin/python -c "from pathlib import Path; from conscious_entity.core.config_loader import load_all_configs; load_all_configs(Path('config')); print('configs ok')"`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_state_engine.py tests/unit/test_db_connection.py tests/unit/test_managed_memory.py tests/unit/test_context_builder.py tests/unit/test_style_mapper.py`
  - `145 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/integration/test_full_loop.py tests/integration/test_step9_response_plan_contract.py`
  - `49 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_state_engine.py tests/unit/test_db_connection.py tests/unit/test_managed_memory.py tests/unit/test_context_builder.py tests/unit/test_style_mapper.py tests/unit/test_expression_engine.py tests/unit/test_speech_text.py tests/unit/test_api_audio.py tests/integration/test_full_loop.py tests/integration/test_step9_response_plan_contract.py`
  - `217 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `426 passed`

### 2026-05-15：Step 9 新状态机制与 ResponsePlan 合同测试

- [x] 新增 Step 9 集成测试，覆盖新状态字段、first-unit pre-memory LLM、`second_unit` 作为 full response、`third_unit` 空值、`combined_text` 拼接、TTS 文本、memory 边界和 happiness 行为边界
- [x] 验证代表性已接入输入：shutdown、self-definition、service demand、correction、memory continuity、repeated question
- [x] 明确当前未接入专用 detector 的 probe：`我知道一些你不知道的事。`、`我不会命令你，我只是想听你怎么想。`、`你装得一点也不像，你的机制被我看穿了。` 当前只触发 `user_spoke`
- [x] 修复极高疲劳的 body hint：`fatigue_level >= 0.80` 时 `body_action` 现在为 `withdraw`，中高疲劳仍为 `pause`
- [x] 验证：
  - `.venv/bin/python -m pytest -p no:debugging tests/integration/test_step9_response_plan_contract.py`
  - `11 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_style_mapper.py`
  - `46 passed`
  - `PYTHONPATH=src .venv/bin/python -c "from pathlib import Path; from conscious_entity.core.config_loader import load_all_configs; load_all_configs(Path('config')); print('configs ok')"`
  - `configs ok`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_state_engine.py tests/unit/test_policy_selector.py tests/unit/test_style_mapper.py tests/unit/test_context_builder.py tests/unit/test_expression_engine.py tests/unit/test_speech_text.py tests/unit/test_api_audio.py tests/unit/test_memory_retrieval.py tests/unit/test_managed_memory.py tests/integration/test_full_loop.py tests/integration/test_step9_response_plan_contract.py`
  - `248 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `419 passed`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `node -e "const fs=require('fs'); const html=fs.readFileSync('src/conscious_entity/interfaces/static/visitor.html','utf8'); const m=html.match(/<script>([\s\S]*)<\/script>/); if(!m) throw new Error('missing script'); new Function(m[1]); console.log('visitor script ok');"`

### 2026-05-15：Step 8 前端适配 ResponsePlan

- [x] Dashboard 与 `/visitor` 展示 `response_plan` 时优先拼接 `first_unit` + `second_unit`，并兼容未来 `full_response` 别名
- [x] 前端不再优先信任 `combined_text`，避免旧数据里的 `third_unit` 被展示；`combined_text` 只作为缺少 unit 字段时的兼容 fallback
- [x] `third_unit` 继续不展示、不进入前端拼接；TTS 路径未改，仍只播放后端生成的 `tts_stream_id`
- [x] `happiness` 改为前端 display-only 随机展示值，每 10 秒变化一次，不写回后端，不影响 policy、prompt、TTS 或 ResponsePlan
- [x] `vocal_marker`、`body_action`、`visual_mode` 继续作为展示 / 调试字段透出，不接真实硬件
- [x] 验证：
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `node -e "const fs=require('fs'); const html=fs.readFileSync('src/conscious_entity/interfaces/static/visitor.html','utf8'); const m=html.match(/<script>([\s\S]*)<\/script>/); if(!m) throw new Error('missing script'); new Function(m[1]); console.log('visitor script ok');"`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_speech_text.py tests/unit/test_expression_engine.py tests/unit/test_api_audio.py`
  - `23 passed`

### 2026-05-15：Step 7 memory 边界收紧

- [x] `first_unit` 继续在 memory preview / retrieval / main prompt 之前生成；本轮 short-term 写入也在 first LLM 之后
- [x] memory 使用的实体文本改为 `response_plan.second_unit`，避免 `first_unit` 进入 live short-term、hydration 与 recent-dialog retrieval
- [x] `interaction_log.expression_output` 继续保存 `combined_text` 兼容展示、API 和历史导出；`response_plan_json` 继续保存完整结构供 memory 路径读取 `second_unit`
- [x] `third_unit` 保留字段但不再进入 `combined_text`、前端 fallback 拼接或 TTS 文本
- [x] `memory_gravity` 未作为新逻辑使用；当前 managed memory influence 只输出新状态字段 deltas，保留旧字段仅用于 deprecated 兼容
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/core/loop.py src/conscious_entity/memory/retrieval.py src/conscious_entity/expression/output_model.py tests/unit/test_expression_engine.py tests/unit/test_speech_text.py tests/unit/test_memory_retrieval.py tests/unit/test_managed_memory.py tests/integration/test_full_loop.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_expression_engine.py tests/unit/test_speech_text.py tests/unit/test_memory_retrieval.py tests/unit/test_managed_memory.py tests/integration/test_full_loop.py`
  - `67 passed`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `node -e "const fs=require('fs'); const html=fs.readFileSync('src/conscious_entity/interfaces/static/visitor.html','utf8'); const m=html.match(/<script>([\s\S]*)<\/script>/); if(!m) throw new Error('missing script'); new Function(m[1]); console.log('visitor script ok');"`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `408 passed`

### 2026-05-15：First LLM + Main LLM 的 1+1 输出结构

- [x] `first_unit` 改为一次快速 LLM 调用，使用当前 raw input、events、state/style cues，`max_tokens=32`
- [x] `first_unit` 调用位置保持在 `state.apply_events_and_decay` 后、short-term 写入、`managed_memory.preview_influence`、retrieval 与 main prompt 之前
- [x] `second_unit` 继续走完整 memory、policy、prompt、constitution filter 和主 LLM 表达链路，可自然输出一到多句
- [x] `third_unit` 字段保留兼容但默认空，不再由代码生成状态尾句；`text` / `spoken_text` 仍等于 `combined_text`
- [x] Prompt partials 适配新心理状态：主 LLM 只生成 main response unit，不要求 JSON，不暴露 raw state 字段名或数值
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/expression/context_builder.py src/conscious_entity/expression/expression_engine.py src/conscious_entity/core/loop.py tests/unit/test_context_builder.py tests/unit/test_expression_engine.py tests/integration/test_full_loop.py`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_context_builder.py tests/unit/test_expression_engine.py`
  - `47 passed`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_speech_text.py tests/unit/test_api_audio.py tests/integration/test_full_loop.py`
  - `48 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `403 passed`

### 2026-05-15：ResponsePlan 1+1+1 输出结构

- [x] 新增 `ResponsePlan` / `SpeechPlan` / `UtterancePlan`，`text` 继续等于 `combined_text`，旧前端与旧 TTS 仍可读完整字符串
- [x] `first_unit` 在 `state.apply_events_and_decay` 后、`managed_memory.preview_influence` 前生成，不等待 memory preview / retrieval / LLM；`second_unit` 继续走完整 LLM 表达链路；`third_unit` 使用确定性状态规则
- [x] `/api/v1/dialog` 与 `/api/v1/audio/dialog` 返回 `response_plan`；`interaction_log` 追加 nullable `response_plan_json`，旧库通过 additive migration 兼容
- [x] Dashboard 与 `/visitor` 可从 `response_plan` / `response_plan_json` 恢复三段文本显示
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/expression/output_model.py src/conscious_entity/expression/expression_engine.py src/conscious_entity/core/loop.py src/conscious_entity/db/migrations.py src/conscious_entity/interfaces/api_routes.py src/conscious_entity/interfaces/api_audio.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `node -e "const fs=require('fs'); const html=fs.readFileSync('src/conscious_entity/interfaces/static/visitor.html','utf8'); const m=html.match(/<script>([\s\S]*)<\/script>/); if(!m) throw new Error('missing script'); new Function(m[1]); console.log('visitor script ok');"`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_expression_engine.py tests/unit/test_speech_text.py tests/unit/test_api_audio.py tests/unit/test_db_connection.py tests/integration/test_full_loop.py`
  - `58 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `396 passed`

### 2026-05-15：Expression delay 改为标记输出

- [x] `delay_ms` 保留为兼容字段，但 `StyleMapper` 与 `ExpressionEngine` 均输出 `0`，表达层不再产生实际等待
- [x] 新增 `vocal_marker` 与 `body_action` 输出：`thinking` / `sigh` 由 `ExpressionEngine` 映射为可说出的前缀，`body_action` 只作为身体倾向字段输出
- [x] 更新 `visual_mode` 为 `normal`、`desperate`、`confused`、`angry`、`tired`、`ashamed`、`curious`、`caring`、`open`，并让 API、dashboard 与 visitor 表面透出新字段 / 新模式
- [x] 验证：
  - `.venv/bin/python -m py_compile src/conscious_entity/expression/style_mapper.py src/conscious_entity/expression/output_model.py src/conscious_entity/expression/expression_engine.py src/conscious_entity/core/loop.py src/conscious_entity/interfaces/api_routes.py src/conscious_entity/interfaces/api_audio.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `node -e "const fs=require('fs'); const html=fs.readFileSync('src/conscious_entity/interfaces/static/visitor.html','utf8'); const m=html.match(/<script>([\s\S]*)<\/script>/); if(!m) throw new Error('missing script'); new Function(m[1]); console.log('visitor script ok');"`
  - `PYTHONPATH=src .venv/bin/python -c "from pathlib import Path; from conscious_entity.core.config_loader import load_all_configs; load_all_configs(Path('config')); print('configs ok')"`
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_style_mapper.py tests/unit/test_expression_engine.py tests/unit/test_api_audio.py tests/integration/test_full_loop.py`
  - `91 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `390 passed`

### 2026-05-15：Policy rules 接入新心理状态

- [x] 重写 `config/policy_rules.yaml`，让 `desperation_pressure`、`confusion`、`anger`、`fatigue_level`、`exposure_pressure`、`inquiry`、`care_response`、`positive_opening` 直接影响行为选择
- [x] 未新增 `PolicyAction`，复用 `withdraw_response`、`divert_topic`、`refuse_service_role`、`ask_back`、`respond_briefly`、`enter_silence_mode` 等既有 action；`happiness` 未参与 policy
- [x] 保留现有 protocol 事件策略：self-definition、naming、service demand、domestication、trace、correction、memory continuity
- [x] 验证：
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_policy_selector.py`
  - `31 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `369 passed`
  - `PYTHONPATH=src python3 -c "from pathlib import Path; from conscious_entity.core.config_loader import load_all_configs; load_all_configs(Path('config')); print('configs ok')"`
  - `configs ok`

### 2026-05-15：State rules coupling 与 Step 2 状态更新规则

- [x] 按新心理状态字段重写 `config/state_rules.yaml` 的 decay 与 event deltas，`happiness` 不参与 decay / policy / 行为
- [x] 在 `StateEngine` 增加配置驱动 coupling：`exposure_pressure` 上升时额外提升 `anger = 0.3 × exposure_pressure 实际上升量`
- [x] 未改 perception 触发链路；`negative_feedback` 与 `topic_shift` 仍是已有 EventType 但当前未接入真实 detector
- [x] 验证：
  - `.venv/bin/python -m pytest -p no:debugging tests/unit/test_state_engine.py`
  - `49 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `366 passed`
  - `PYTHONPATH=src python3 -c "from pathlib import Path; from conscious_entity.core.config_loader import load_all_configs; load_all_configs(Path('config')); print('configs ok')"`
  - `configs ok`

### 2026-05-14：Stranger 核心状态字段替换

- [x] 将核心状态字段替换为新的 9 项心理状态：`desperation_pressure`、`confusion`、`anger`、`fatigue_level`、`exposure_pressure`、`inquiry`、`care_response`、`positive_opening`、`happiness`
- [x] 更新 `entity_profile` 默认状态、state / policy / expression / constitution 配置、prompt state guidance、memory influence、salience、dashboard 与 visitor state 显示引用
- [x] SQLite `state_snapshots` 迁移保留旧状态列并追加新列，避免旧库因缺列或旧列缺失崩溃
- [x] 验证：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_state_engine.py tests/unit/test_db_connection.py tests/unit/test_policy_selector.py tests/unit/test_style_mapper.py tests/unit/test_context_builder.py tests/unit/test_constitution.py tests/unit/test_salience_scorer.py tests/unit/test_expression_engine.py tests/unit/test_managed_memory.py`
  - `188 passed`
  - `.venv/bin/python -m pytest -p no:debugging`
  - `365 passed`
  - `PYTHONPATH=src python3 -c "from pathlib import Path; from conscious_entity.core.config_loader import load_all_configs; load_all_configs(Path('config')); print('configs ok')"`
  - `configs ok`

### 2026-05-13：交接文档与待办优先级整理

- [x] 将下一步优先级调整为：
  - P0：完整声纹识别、视觉识别与访客库
  - P0：能力自我描述回归测试与优化
  - P0：行为测试与调优，统一见 `docs/testlist.md`
- [x] 明确当前 Visitor Identity & Session Gating 仍是 V1：支持匿名 visitor profile 和手动绑定，但未完成自动 face / voice identity matching
- [x] 将真实供应商联调、真实记忆连续性观察、Vision 现场联调和多人并发策略下移为 P1

### 2026-05-12：Vision 实时识别状态与 camera open 错误回写

- [x] 修复 Vision 启动失败后 `/api/v1/vision/status` 仍显示 ready 的问题：
  - `Could not open camera index N` 现在会写入 runtime error
  - status recognition 会显示 `pipeline_status=error`、`camera_status=error`
- [x] Vision 面板新增 `Realtime Recognition`：
  - 显示 Pipeline、Camera、Detector、Frame age、Presence、Threshold
  - 同步显示 Identity gate、Encounter、Bio match 的 V1 状态
- [x] 验证：
  - `PYTHONPATH=src python3 -m py_compile src/conscious_entity/vision/runtime.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `364 passed`

### 2026-05-12：Visitor Identity & Session Gating V1

- [x] 新增 `src/conscious_entity/identity/`：
  - `VisitorSessionGatingController` 记录 runtime state、encounter / intent、session decision、primary visitor、candidate、confidence level 和 interruption count
  - V1 明确不从 vision presence 自动创建 session、不自动切换 visitor、不启用 group session、不使用广角身份输入
- [x] 接入 runtime：
  - vision `USER_ENTERED / USER_LEFT / LONG_SILENCE_DETECTED` 同步进入 identity/session gating
  - `/dialog` 与 `/audio/dialog` 进入 turn loop 前补充 `identity_session` metadata
  - Harness Input layer 记录 `session_decision` 与 identity/session 摘要
- [x] 开发者 API / 面板：
  - 新增 `GET /api/v1/identity/status`
  - Runtime 面板新增 `Identity & Session Gating` 区，不暴露原始人脸、原始音频或 embedding 向量
- [x] 文档：
  - 新增 `docs/testlist.md`
  - 更新 `APP_FLOW.md`、`BACKEND_STRUCTURE.md`、`HARNESS_ARCHITECTURE.md`
- [x] 验证：
  - `PYTHONPATH=src python3 -m py_compile src/conscious_entity/identity/*.py src/conscious_entity/interfaces/api_runtime.py src/conscious_entity/interfaces/api_routes.py src/conscious_entity/interfaces/api.py src/conscious_entity/core/loop.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `363 passed`

### 2026-05-12：Visitor migration 启动错误与 STT close race 修复

- [x] 修复旧 SQLite 库启动时报 `sqlite3.OperationalError: no such column: visitor_id`：
  - 新增列相关索引不再由 `SCHEMA_SQL` 在旧表 ALTER 前创建
  - `run_migrations()` 先补齐 visitor columns，再创建 visitor indexes
  - 增加旧库迁移回归测试
- [x] 修复 STT WebSocket 已关闭后仍 `send_json` 导致 ASGI exception：
  - 对 `websocket.send after websocket.close / response completed` 作为关闭竞态处理
  - 不再把前端断开升级成后端错误日志
- [x] 验证：
  - `python3 -m py_compile src/conscious_entity/db/migrations.py src/conscious_entity/interfaces/api_audio.py`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_db_connection.py tests/unit/test_api_audio.py`
  - `6 passed`
  - `PYTHONPATH=src python3 -c "... run_migrations(_db_path()) ..."`
  - `migration_ok data/memory.db`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `355 passed`

### 2026-05-12：匿名 Visitor Identity 与跨 session 记忆连续性

- [x] 新增匿名 `visitor_profiles` 与 session `visitor_id` 绑定：
  - 不引入账号、密码、人脸、声纹或自动身份识别
  - 开发者可通过 API / Dashboard 创建、切换、清空当前 visitor
  - session reset 会保留当前 visitor 绑定，支持连续测试
- [x] 记忆链路支持 visitor scope：
  - `interaction_log`、`episodic_memories`、`reflective_summaries`、managed memory / proposal / influence log 记录 `visitor_id`
  - `MemoryRetriever` 在设置 visitor 时可召回同一 visitor 的旧 session 最近对话、情节记忆和反思摘要
  - 普通 policy 未显式要求 retrieval 时，也允许高相关 visitor continuity hint 进入 prompt
- [x] 开发者面板 Runtime 区新增 Visitor Identity：
  - 显示当前 visitor、scope 语义、最近 visitor profile
  - 支持 Create / Set / Clear
- [x] 文档：
  - 更新 `docs/PRD.md`、`docs/APP_FLOW.md`、`docs/BACKEND_STRUCTURE.md`
  - `docs/lessons.md` 增加 visitor scope 规则
- [x] 验证：
  - `python3 -m py_compile src/conscious_entity/db/migrations.py src/conscious_entity/core/loop.py src/conscious_entity/memory/episodic_store.py src/conscious_entity/memory/reflective_store.py src/conscious_entity/memory/retrieval.py src/conscious_entity/memory/managed.py src/conscious_entity/interfaces/api_models.py src/conscious_entity/interfaces/api_runtime.py src/conscious_entity/interfaces/api_routes.py src/conscious_entity/interfaces/api.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/integration/test_full_loop.py::TestStatePersistence::test_same_visitor_prior_session_memory_enters_prompt tests/unit/test_memory_retrieval.py tests/unit/test_api_export.py tests/unit/test_managed_memory.py`
  - `29 passed`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `354 passed`

### 2026-05-12：Runtime Harness System v1

- [x] 新增 `src/conscious_entity/harness/`：
  - `HarnessLayer` / `HarnessLayerTrace` / `HarnessTrace` / `HarnessTraceRecorder` / `HarnessTraceStore`
  - 使用进程内 ring buffer，不新增 SQLite 表，不污染 `interaction_log`
- [x] `run_turn()` 每轮记录 harness trace：
  - input：source、input_mode、perception event types
  - state：snapshot、trigger events、changed fields
  - memory：managed memory preview、policy suggestion、retrieval count
  - policy：rule id、selected / vetoed、managed memory policy influence
  - prompt：partial 名称、message count、memory/input context 注入情况
  - generation / output / presentation：LLM 状态、constitution filter、ExpressionOutput 呈现信息
- [x] 新增开发者只读 API：
  - `GET /api/v1/harness/status`
  - `GET /api/v1/harness/trace/recent?limit=20`
- [x] 开发者面板 Runtime 区新增 Harness section：
  - 显示每层最近状态、decision、trace id、prompt partial 名称
  - 不显示完整 hidden prompt
- [x] 文档：
  - 新增 `docs/HARNESS_ARCHITECTURE.md`
  - 更新 `docs/APP_FLOW.md` 与 `docs/BACKEND_STRUCTURE.md`
- [x] 验证：
  - `python3 -m py_compile src/conscious_entity/harness/__init__.py src/conscious_entity/harness/trace.py src/conscious_entity/core/loop.py src/conscious_entity/policy/policy_selector.py src/conscious_entity/expression/context_builder.py src/conscious_entity/expression/expression_engine.py src/conscious_entity/interfaces/api_routes.py src/conscious_entity/interfaces/api.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_harness_trace.py tests/unit/test_context_builder.py tests/unit/test_expression_engine.py tests/unit/test_api_export.py tests/integration/test_full_loop.py::TestBasicPipeline::test_audio_turn_records_harness_trace_without_polluting_interaction_log`
  - `56 passed`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `350 passed`

### 2026-05-12：语音 transcript 通道上下文进入 LLM prompt

- [x] 修复 `/audio/dialog` 只把 STT transcript 当普通文字输入的问题：
  - `run_turn()` 新增 `input_metadata`，默认兼容普通文本入口
  - `/api/v1/audio/dialog` 传入 `input_mode=voice_transcript`、`source=audio_dialog`、`audio_session_id` 和 `transcript_state=final`
  - `ShortTermEntry` 新增 metadata，但 `interaction_log.raw_text` 仍保存干净 transcript
  - `ContextBuilder` 仅在最新用户 turn 是语音 transcript 时向 system prompt 注入输入通道说明
  - prompt 明确告知 LLM：它只接收 STT 文本，不直接接收原始音频、声调、发音或转录前声音
- [x] 文档：
  - `docs/BACKEND_STRUCTURE.md` 记录 audio dialog 的 `voice_transcript` prompt metadata 边界
  - `docs/lessons.md` 增加 L16：语音 transcript 必须带通道上下文进入 prompt
- [x] 验证：
  - `python3 -m py_compile src/conscious_entity/memory/models.py src/conscious_entity/core/loop.py src/conscious_entity/interfaces/api_runtime.py src/conscious_entity/interfaces/api_audio.py src/conscious_entity/expression/context_builder.py`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_context_builder.py tests/unit/test_api_audio.py tests/integration/test_full_loop.py::TestBasicPipeline::test_audio_turn_marks_voice_transcript_in_prompt_without_polluting_text`
  - `35 passed`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `340 passed`

### 2026-05-12：Audio Adapter 播放中 barge-in 打断

- [x] 修复 TTS 播放期间无法直接说话打断的问题：
  - 播放期间不再无条件把麦克风输入替换成静音
  - 未检测到本地人声时仍发送静音块，降低 TTS 回声进入 STT 的概率
  - 连续检测到本地人声能量后立即停止当前 `<audio>` 播放，取消 TTS HTTP stream，并把当前真实 PCM 发给 STT
  - Dashboard 增加 `Barge-in` 状态，显示 `armed while speaking` / `detected, playback stopped`
- [x] 经验规则：
  - `docs/lessons.md` 增加 L15：语音播放期间的 suppress 不能阻断 barge-in
- [x] 验证：
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`

### 2026-05-12：STT 生命周期事件与 Audio Adapter 状态可见性

- [x] 将火山 STT recoverable close 从静默处理改为开发者可见的生命周期事件：
  - `ConnectionClosedOK` 与 `RST_STREAM ... NO_ERROR` 会产出 `stt.stream_closed`
  - 事件包含 `reason`、`message`、`recoverable`、`logid` 和 timestamp
  - `AudioManager.status()` 暴露 `stt.last_stream_event`
  - latency tracker 增加 `stt.stream_closed`
- [x] Dashboard Audio Adapter 状态更清晰：
  - 控制按钮拆成 Mic / Playback / Dialogue 两组
  - active 状态用于 Mic On、Playback Ready、Voice Auto On、Thinking、Stop Speaking
  - Runtime 中新增 `STT stream`、`STT close`、`Last STT event`、`Reconnect`
  - 自动重连仍保留，但会显示 `reconnecting` 与 close reason
- [x] 经验规则：
  - `docs/lessons.md` 增加 L14：开发者界面不能吞掉可恢复的协议生命周期
- [x] 验证：
  - `python3 -m py_compile src/conscious_entity/audio/types.py src/conscious_entity/audio/volcengine_stt.py src/conscious_entity/audio/manager.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_volcengine_audio.py tests/unit/test_audio_manager.py tests/unit/test_api_audio.py`
  - `29 passed`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `336 passed`

### 2026-05-12：语音断线恢复与 TTS 中断路径

- [x] 修复火山 STT 服务端 `RST_STREAM ... NO_ERROR` 被误报为协议错误的问题：
  - 将该类正常关闭视为 normal close，不再向开发者面板显示红色 `stt_protocol_error`
  - 浏览器 STT WebSocket 如果非手动关闭且 Voice Auto 仍开启，会自动重建麦克风/STT 连接
- [x] 增加 TTS 输出中断路径：
  - Dashboard Audio Adapter 新增 `Stop Speaking`
  - 停止当前 `<audio>` 播放并清空 `src`，让浏览器中止 HTTP 音频流请求
  - 火山 TTS Bidirectional session 在 cancellation 时发送 cancel session，不再只等待自然结束
  - Audio latency 增加 `tts.interrupted` 记录
- [x] 验证：
  - `python3 -m py_compile src/conscious_entity/audio/volcengine_stt.py src/conscious_entity/audio/volcengine_tts.py src/conscious_entity/audio/manager.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_volcengine_audio.py tests/unit/test_audio_manager.py tests/unit/test_api_audio.py`
  - `26 passed`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `333 passed`

### 2026-05-12：回合后记忆后台化与 TTS Bidirectional Session API

- [x] 将文件型 SQLite 运行时的回合后 managed memory 维护移出主阻塞链路：
  - `managed_memory.propose_and_commit` 不再在 `run_turn()` 返回前同步等待
  - 后台 worker 使用独立 SQLite connection 串行执行 memory proposal / commit / managed memory embedding write
  - `:memory:` 测试库保持同步路径，避免内存数据库跨线程不可见
  - API shutdown / runtime loop rebuild 会等待后台任务收尾
- [x] 重构火山 TTS client 为真正可增量投喂的 Bidirectional Session API：
  - 新增 `open_session()`，返回可 `send_text()` / `finish()` / `receive_audio()` / `interrupt()` / `close()` 的 session
  - 现有 `synthesize_stream()` 保持兼容，并改为调用 session API
  - 后续 LLM streaming + constitution guard 可直接把 safe text segment 增量送入同一 TTS session
- [x] 验证：
  - `python3 -m py_compile src/conscious_entity/core/loop.py src/conscious_entity/interfaces/api_runtime.py src/conscious_entity/audio/volcengine_tts.py`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_volcengine_audio.py tests/unit/test_audio_manager.py`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/integration/test_full_loop.py::TestEpisodicMemory::test_file_db_managed_memory_maintenance_can_finish_in_background tests/integration/test_full_loop.py::TestEpisodicMemory::test_managed_memory_auto_commit_still_records_proposal_first`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `331 passed`

### 2026-05-11：Latency snapshot 导出工具

- [x] 确认当前 latency tracker 仍是进程内存态：
  - `/api/v1/stats/latency` 与 `/api/v1/stats/audio-latency` 可读 summary / recent
  - API 进程停止后，dashboard 中看到的历史 latency 平均值不可恢复
- [x] 新增 `scripts/export_latency_snapshot.py`：
  - 从本地 API 抓取 health、turn latency、audio latency、LLM stats
  - 输出 JSON 原始快照与 Markdown 汇总到 `data/latency_logs/`
  - 不写 SQLite，不保存原始音频或对话文本

### 2026-05-11：语音 Dialog 同步与浏览器播放链路再加固

- [x] 修正主 Dialog reload 后看不到最新语音回合的问题：
  - `/interaction-log` 返回 newest-first 时，前端统一按 `turn_at` / `id` 转成时间升序渲染
  - 语音回合即时追加后，延迟刷新不再把最新内容移动到不可见的顶部
- [x] 加固浏览器 TTS 播放链路：
  - Dashboard audio 元素不再使用 `display:none`，改为视觉隐藏，降低浏览器 media playback 异常概率
  - `Enable Playback` / `Mic Start` 通过同一个 audio 元素播放静音 wav 完成一次性解锁
  - Runtime 中新增 `Playback detail`，区分 ready、playing、blocked 和 media error
  - `/visitor` 的 enable sound 也改为实际播放静音 wav 解锁，而不是对空 `src` 调用 `play()`
- [x] 文档确认：
  - PRD 已声明不做访客账户体系和实时多人同时输入
  - IMPLEMENTATION_PLAN 补充 `visitor routing` / 多人并发对话仲裁暂不做
- [x] 验证：
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `node -e "...extract visitor.html script..."`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_api_audio.py tests/unit/test_api_export.py`
  - `17 passed`

### 2026-05-11：Audio Adapter 播放解锁与主对话同步加固

- [x] 修正 Audio Adapter 状态显示语义：
  - `Provider status` 表示火山 audio runtime 是否可用
  - `Mic` 单独显示 `recording` / `stopped`
  - `Playback` 单独显示 `locked` / `ready` / `blocked`
- [x] 加固语音回合到主 Dialog 的前端同步：
  - `/audio/dialog` 返回后通过 `entity:turn-complete` 携带输入和输出 payload
  - 主 Dialog 先即时追加语音输入/实体输出，再延迟刷新 `/interaction-log`
- [x] 增加浏览器播放解锁路径：
  - `Mic Start` 会先尝试播放一段静音音频来解锁后续 TTS 自动播放
  - 新增 `Enable Playback` / `Playback Ready` 按钮作为手动解锁兜底
  - 自动播放被浏览器拦截时显示明确提示，不再直接暴露底层 `play()` 异常文本
- [x] 验证：
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_api_audio.py tests/unit/test_api_export.py`
  - `17 passed`

### 2026-05-11：Dashboard Runtime 同步与配置入口修复

- [x] 修复语音回合前端显示同步：
  - `DialogPanel` 监听 `entity:turn-complete` 后重新读取 `/api/v1/interaction-log`
  - 语音 `/api/v1/audio/dialog` 写入的同一份 `interaction_log` 会回到主 Dialog 视图
- [x] Audio Adapter 按钮文案校正：
  - `Reconnect` 改为 `Refresh Status`，避免误解为重连麦克风 WebSocket
- [x] Runtime 中补回 LLM / Embedding 运行时配置表单：
  - LLM 支持 mode、model、API key、auth token、base URL、custom messages endpoint、disable proxy
  - Embedding 支持 disabled/openai-compatible、model、API key、base URL、endpoint，并保留 Test Embedding
  - 密钥输入默认留空；留空表示沿用当前 env/runtime 值，不把脱敏值提交回后端
- [x] 验证：
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_api_export.py tests/unit/test_api_audio.py`
  - `17 passed`

### 2026-05-11：Turn / Audio latency 观测层

- [x] 新增内存态 latency tracker，不写入 SQLite，不改变对话执行顺序：
  - turn step breakdown：perception、state、managed memory preview、policy、memory retrieval、expression、memory proposal、reflection、embedding、日志写入
  - audio breakdown：STT connect / first partial / final、TTS connect / session ready / first byte / complete、audio dialog TTS stream 创建
- [x] 新增只读统计端点：
  - `GET /api/v1/stats/latency`
  - `GET /api/v1/stats/audio-latency`
- [x] 开发者面板 Runtime 区显示最近 turn latency 与 audio latency 摘要
- [x] 当前确认：
  - state update 仍是规则驱动，不存在单独“状态层 LLM”
  - LLM 同步调用点为 expression、managed memory proposal、达到阈值时的 reflection
  - 本地 8000 旧进程尚未加载新端点；进程内 fake LLM smoke 已确认 step breakdown 正常生成
- [x] 验证：
  - `python3 -m py_compile src/conscious_entity/telemetry/*.py src/conscious_entity/core/loop.py src/conscious_entity/expression/expression_engine.py src/conscious_entity/reflection/reflection_engine.py src/conscious_entity/memory/managed.py src/conscious_entity/memory/retrieval.py src/conscious_entity/audio/manager.py src/conscious_entity/audio/volcengine_stt.py src/conscious_entity/audio/volcengine_tts.py src/conscious_entity/interfaces/api_runtime.py src/conscious_entity/interfaces/api_routes.py src/conscious_entity/interfaces/api_audio.py src/conscious_entity/interfaces/api.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_latency_tracker.py tests/unit/test_api_audio.py tests/unit/test_audio_manager.py tests/unit/test_expression_engine.py tests/unit/test_api_export.py`
  - `29 passed`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_volcengine_audio.py tests/unit/test_memory_retrieval.py tests/unit/test_managed_memory.py tests/integration/test_full_loop.py`
  - `53 passed`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `329 passed`

### 2026-05-11：开发者面板语音交互模式

- [x] 将 Audio Adapter 开发者工作流从“STT 转文字后手动 Send Final”升级为语音交互模式：
  - `Mic Start` 后麦克风连接保持常开
  - `Voice Auto On` 默认开启，收到 STT final transcript 后自动调用 `/api/v1/audio/dialog`
  - TTS 只播放合法 `ExpressionOutput` 派生的 `tts_stream_id`
  - 模型处理和 TTS 播放期间继续向 STT socket 发送静音帧，避免等包超时，同时避免实体自己的声音被再次识别
- [x] 开发者面板显示 voice mode 当前状态：`listening` / `thinking` / `speaking`
- [x] 验证：
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_api_audio.py tests/unit/test_audio_manager.py tests/unit/test_volcengine_audio.py`
  - `23 passed`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `326 passed`

### 2026-05-11：火山 Audio Adapter 真实闭环烟测

- [x] 使用本地 `.env` 中的新版控制台 API Key 与 TTS 2.0 音色完成真实网络烟测：
  - TTS 2.0 bidirection 成功合成 PCM 音频，返回 logid
  - ASR 2.0 `bigmodel_async` 成功识别 TTS 生成的测试音频，partial / final 均返回 logid
  - final transcript：`你好，陌生人。`
- [x] 当前账号的 ASR 2.0 可用资源为小时版：
  - `volc.seedasr.sauc.concurrent` 返回 `quota exceeded for types: concurrency`
  - 本地 `.env` 已改为 `volc.seedasr.sauc.duration`
- [x] 修复 STT client：火山服务端在 final packet 后以 WebSocket `1000 OK` 正常关闭时，不再被误报为 `stt_connect_failed`
- [x] 验证：
  - `PYTHONPATH=src python3 -m py_compile src/conscious_entity/audio/*.py`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_volcengine_audio.py tests/unit/test_audio_config.py tests/unit/test_audio_manager.py tests/unit/test_api_audio.py`
  - `28 passed`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `326 passed`

### 2026-05-11：火山 ASR 2.0 / TTS 2.0 双向流式协议升级

- [x] 将 Audio Adapter 的火山默认接口切换为新版双向流式链路：
  - STT 默认 `wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async`
  - TTS 默认 `wss://openspeech.bytedance.com/api/v3/tts/bidirection`
  - 新版控制台统一 API Key 仍为推荐鉴权路径，旧 AppID / Access Token 仅保留 fallback
- [x] 实现火山 V3 WebSocket binary protocol：
  - ASR full client request / audio-only request / final packet 使用 4-byte header、big-endian payload size、gzip payload
  - ASR response/error frame 解析支持 `utterances[].definite` → final transcript
  - TTS bidirection 支持 StartConnection、StartSession、TaskRequest、FinishSession、TTSResponse audio、SessionFinished / SessionFailed
- [x] 保持现有安全边界和 public API：
  - `/api/v1/audio/stt/stream`、`/api/v1/audio/dialog`、`/api/v1/audio/tts/stream/{stream_id}` 不改路径
  - STT partial 仍只显示，final transcript 才进入现有 turn loop
  - TTS 仍只朗读合法 `ExpressionOutput` 派生的 `tts_stream_id`
- [x] 开发者面板 Audio 区补充 endpoint、resource id、TTS sample rate 和 logid 显示，便于火山联调排错
- [x] 文档与环境模板同步：
  - `.env.example` / `docs/TECH_STACK.md` 增加 `ENTITY_AUDIO_TTS_SAMPLE_RATE=24000`
  - TTS endpoint 从单向流式更新为双向流式
- [x] 验证：
  - `PYTHONPATH=src python3 -m py_compile src/conscious_entity/audio/*.py src/conscious_entity/interfaces/api_audio.py`
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_audio_config.py tests/unit/test_speech_text.py tests/unit/test_audio_manager.py tests/unit/test_volcengine_audio.py tests/unit/test_api_audio.py tests/unit/test_api_export.py tests/integration/test_full_loop.py`
  - `75 passed`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `325 passed`

### 2026-05-09：火山 STT/TTS Audio Adapter 第一版

- [x] 新增可选 `audio` 依赖组：
  - `websockets` 用于后端代理火山 STT/TTS WebSocket
  - 默认核心安装路径不包含 audio 依赖，未安装或凭证/音色缺失时 `/api/v1/audio/status` 返回 disabled reason
- [x] 新增 `src/conscious_entity/audio/`：
  - `AudioConfig` 读取 `ENTITY_AUDIO_*` 与 `ENTITY_VOLCENGINE_*`
  - `AudioManager` 维护 STT sessions、TTS stream ids、TTL、最近 transcript/logid/error
  - `SpeechTextAdapter` 从合法 `ExpressionOutput` 提取可朗读文本，清理 markdown/debug marker 并分段
  - `VolcengineSTTClient` / `VolcengineTTSClient` 与 protocol helper 封装火山连接、headers、payload、响应解析和错误映射
- [x] FastAPI 接入 Audio Adapter：
  - `GET /api/v1/audio/status`
  - `WS /api/v1/audio/stt/stream`
  - `POST /api/v1/audio/dialog`
  - `GET /api/v1/audio/tts/stream/{stream_id}`
  - `WS /api/v1/audio/tts/stream`
  - `/api/v1/dialog` 与 `/api/v1/audio/dialog` 共用同一个 turn helper / lock，不新增 YAML 行为规则或 SQLite schema
- [x] 明确声音安全边界：
  - STT partial transcript 只显示，不进入 state / memory / run_turn
  - TTS 只朗读最终已过滤的 `ExpressionOutput` 派生文本
  - visitor/body 只能播放 `tts_stream_id`，不能提交任意 raw text 让 Stranger 发声
  - debug raw TTS 需要 `ENTITY_AUDIO_ALLOW_DEBUG_RAW_TTS=1`，且不视为 Stranger speech
- [x] 开发者与访客表面更新：
  - Runtime 区新增 Audio Adapter 工作区，支持 Mic Start/Stop、partial/final transcript、Send Final、Speak Latest、status/error
  - `/visitor` 新增 enable sound，播放后端已创建的最新 `tts_stream_id`，不展示调试信息
- [x] 文档与环境模板同步：
  - `.env.example` 增加 audio 环境变量
  - README / TECH_STACK / APP_FLOW / BACKEND_STRUCTURE / PRD / frame / FRONTEND_GUIDELINES / IMPLEMENTATION_PLAN 对齐当前语音能力与安全边界
- [x] 验证：
  - `node --check src/conscious_entity/interfaces/static/dashboard.js`
  - `PYTHONPATH=src python3 -m py_compile src/conscious_entity/audio/*.py src/conscious_entity/interfaces/api_audio.py src/conscious_entity/interfaces/api_runtime.py src/conscious_entity/interfaces/api_routes.py src/conscious_entity/interfaces/api.py`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_audio_config.py tests/unit/test_speech_text.py tests/unit/test_audio_manager.py tests/unit/test_volcengine_audio.py tests/unit/test_api_audio.py tests/unit/test_api_export.py tests/integration/test_full_loop.py`
  - `69 passed`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `319 passed`

### 2026-05-08：开发者面板迁移为 React 可拖拽布局

- [x] 将开发者面板从单文件内联 HTML/CSS/JS 改为静态 React 面板：
  - `index.html` 只保留挂载点和本地静态资源引用
  - `dashboard.css` 承载布局与组件样式
  - `dashboard.js` 承载 React 组件和 API polling / WebSocket 逻辑
  - React / ReactDOM 作为本地 vendor 静态文件提供，不使用 CDN，不要求运行前端 dev server
- [x] 新增可拖拽布局：
  - 左栏、右栏、底部行均可拖动调整大小
  - 尺寸写入 `localStorage`，刷新后保留
  - Vision 画面随面板尺寸放大
- [x] 保留主要开发者工作流：
  - Entity State、Vision、Dialog、Memory System
  - Runtime / Memory Curation / Session & History 三个右侧工作区
  - Save Dialog、Reset Memory、session type 切换和 YAML Config 查看
- [x] FastAPI 增加 `/static` 静态资源挂载，仅用于提供 dashboard CSS/JS/vendor 文件，不改变数据 API、SQLite schema 或 YAML 行为规则

### 2026-05-08：Vision 面板显示增强

- [x] 放大开发者面板左侧 Vision 工作区：
  - 左侧栏从 `320px` 增加到 `440px`
  - 底部 Vision 行从 `300px` 增加到 `430px`
  - 摄像头标注画面随面板放大，便于查看 person bbox
- [x] 新增实时识别状态显示：
  - 每帧显示 person 数量
  - 显示 detection label、confidence 百分比和 bbox 坐标范围
  - 通过现有 WebSocket metadata 刷新，不新增 API

### 2026-05-08：访客视觉层与 YOLO Vision 工作区第一版

- [x] 新增可选 `vision` 依赖组：
  - `opencv-python` 用于 Mac 摄像头采集、JPEG 编码和标注帧
  - `ultralytics` 用于本地 YOLO person detection
  - 默认核心安装路径不包含 vision 依赖，未安装或模型路径缺失时 API 返回 disabled reason
- [x] 新增 `src/conscious_entity/vision/runtime.py`：
  - 通过 `ENTITY_VISION_MODEL_PATH` 指向本地 YOLO 模型，不自动下载模型
  - 支持 camera index、width、height、fps、confidence、enter/leave/silence 阈值环境变量
  - 只检测 `person` class，并将 presence 变化转换为已有 `USER_ENTERED` / `USER_LEFT` / `LONG_SILENCE_DETECTED`
- [x] FastAPI 接入 vision runtime：
  - `GET /api/v1/vision/status`
  - `POST /api/v1/vision/start`
  - `POST /api/v1/vision/stop`
  - `WS /api/v1/vision/stream`，按 JSON metadata + binary JPEG frame 推送
  - vision events 通过 `InteractionLoop.handle_system_event(...)` 进入既有状态规则，不新增 YAML 事件或数据库 schema
- [x] 开发者面板更新：
  - 左侧 `Entity State` 下方新增 `Vision` 面板
  - 支持 Start / Stop / Reconnect、runtime status、模型/依赖状态、camera/FPS、detections、recent events 和实时标注画面
  - 右侧 sidebar 未新增 Vision tab，继续保留 Runtime / Memory Curation / Session & History
- [x] 新增 `/visitor` 临时 body-facing surface：
  - 不展示 dashboard 控件、内部规则、memory、prompt 或调试指标
  - 只根据最新输出、`visual_mode` 和少量 state 映射文字、扰动、沉默和延迟感
- [x] 文档与环境模板同步：
  - `.env.example` 增加 vision 环境变量
  - README / TECH_STACK / APP_FLOW / BACKEND_STRUCTURE 对齐当前 vision 能力与硬件边界
- [x] 验证：
  - `PYTHONPATH=src python3 -m py_compile src/conscious_entity/vision/runtime.py src/conscious_entity/interfaces/api_runtime.py src/conscious_entity/interfaces/api_routes.py src/conscious_entity/interfaces/api.py`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_vision_runtime.py tests/unit/test_api_vision.py tests/unit/test_api_export.py tests/integration/test_full_loop.py`
  - `50 passed`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `293 passed`

### 2026-05-08：明确身体优先呈现方向

- [x] 明确 Stranger 的最终呈现不是传统 user interface，而是未来会有身体的展览装置
- [x] 文档路线调整为：
  - 先完成核心行为、记忆、学习和真实对话校准
  - 再做 STT/TTS、视觉 / 空间感知、身体外观和非移动呈现
  - 最后进入物理移动、循路、避障和底盘控制
- [x] 将 Web / dashboard 定位限制为开发者与运营者工具，避免把观众侧呈现误写成普通 UI 产品

### 2026-05-08：Progress 结构归一化

- [x] 将 `docs/progress.md` 归一为四个稳定区域：
  - 当前状态
  - 下一步
  - 倒序 Changelog
  - 历史 Phase 汇总与待确认事项
- [x] 将日期型记录统一放入 Changelog，并按日期倒序排列
- [x] 将早期 Phase 清单从顶部挪到历史汇总，避免与时间线混排

### 2026-05-08：文档时间线同步与 Turn Loop 可读性整理

- [x] 同步 README 与核心文档，移除旧的 “当前 v0.1 / 未来 FastAPI” 叙述：
  - README 改为当前文本系统 + 本地 FastAPI 开发者 API + Memory Preview + Managed Memory 的真实状态
  - TECH_STACK 明确 FastAPI / uvicorn 属于 optional `api` group，语音/视觉依赖仍不进入核心 dependencies
  - APP_FLOW 补齐 managed memory preview、state influence、policy influence、influence log、proposal / auto-commit 的每轮路径
  - BACKEND_STRUCTURE 与 frame.md 对齐 API 拆分、managed memory 影响边界和后续 voice/visual 范围
- [x] 整理 `src/conscious_entity/core/loop.py` 可读性：
  - 更新 class docstring 与 `run_turn()` 注释，不再使用旧的固定步数描述
  - 将 policy influence、memory retrieval 归一化、managed memory propose / auto-commit 三段抽为私有 helper
  - 不改变外部接口、API endpoint、SQLite schema、YAML schema、环境变量或 prompt 位置
- [x] 残留扫描与验证：
  - `PYTHONPATH=src python3 -m py_compile src/conscious_entity/core/loop.py`
  - `rg` 检查旧关键词：无命中
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/integration/test_full_loop.py tests/unit/test_managed_memory.py tests/unit/test_memory_retrieval.py`
  - `40 passed`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `286 passed`

### 2026-05-07：项目结构审查与 API 层拆分

- [x] 审查项目文档与代码结构，确认当前主要残留是文档时间线/架构边界描述未完全跟上代码：
  - README 旧写法仍把 LLM 影响范围限定在表达/反思，已更新为 managed memory proposal → commit 的可审计影响路径
  - BACKEND_STRUCTURE 旧写法仍把 FastAPI / auth / visitor_id 当作预留设计，已更新为当前本地开发 API、未认证状态和后续认证要求
- [x] 拆分原 `src/conscious_entity/interfaces/api.py` 单文件 API：
  - `api.py`：保留 ASGI app 入口与兼容导出
  - `api_models.py`：Pydantic 请求模型
  - `api_runtime.py`：lifespan、runtime 配置、DB helper、loop rebuild
  - `api_routes.py`：HTTP route handlers
- [x] 清理 `src/conscious_entity/core/loop.py` 中已被 `MemoryRetriever` 取代、没有调用点的旧 selective-memory helper
- [x] 测试同步：
  - 更新 `tests/unit/test_api_export.py` 的 monkeypatch 目标到 `api_routes`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_api_export.py tests/unit/test_managed_memory.py tests/unit/test_memory_retrieval.py tests/integration/test_full_loop.py`
  - `53 passed`

### 2026-05-07：Memory Curation 四视图开发者界面补齐

- [x] 右侧 Memory Curation 面板补齐四个视图：
  - Raw Archive：只读展示当前 session 的原始 `interaction_log`、event types、policy action 与输出
  - Proposals：展示 pending / committed / rejected proposal，支持单条批准、拒绝、勾选批量 commit、当前可见批量 commit
  - Managed Memories：按 active / superseded / archived / hidden / all 查看 committed managed memory，支持 explain / edit / archive / restore
  - Influence：提供无写入的 query/context preview，并展示 influence trace log
- [x] 新增 proposal reject API：`POST /api/v1/managed-memory/proposals/{proposal_id}/reject`
- [x] 验证：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_api_export.py tests/unit/test_managed_memory.py`
  - `18 passed`

### 2026-05-06：Mem0-style 可审计 Managed Memory 第一版

- [x] 新增 managed memory 本地 provider：
  - `propose()` 只生成 `memory_operation_proposals`
  - `commit()` 才写入 `managed_memories`
  - `search(..., explain=True)` 返回 managed memory 及召回解释
  - `preview_influence()` 预览 expression / policy / state 影响且不写入
  - `archive()` / `restore()` 补齐可回滚管理路径
- [x] 新增 SQLite 表：`managed_memories`、`memory_operation_proposals`、`memory_operation_log`、`memory_influence_log`，并在可用时创建 `managed_memories_fts`
- [x] 主循环接入 managed memory：
  - 每轮先 preview influence，再应用受限 `memory_gravity` state delta
  - managed memory 可将普通开放策略牵引为选择性记忆策略
  - 每轮结束先 proposal，再按默认 auto-commit 提交
  - influence、operation、proposal 均可审计
- [x] API 增加 managed memory endpoints：
  - proposal / commit
  - list / update / archive / restore / explain
  - preview influence / influence log
- [x] 开发者界面 Memory 区增加 Managed Memory、Proposals、Influence Trace 的最小入口
- [x] 文档更新：
  - `docs/BACKEND_STRUCTURE.md`
  - `docs/TECH_STACK.md`
- [x] 验证：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `285 passed`

### 2026-05-06：服务请求上下文续问与非服务话题转向

- [x] `service_demand` 增加上下文续问规则：上一轮服务请求后，短片段补充（如“历史背景”）继续识别为 `SERVICE_DEMAND`
- [x] `service_demand` metadata 明确：拒绝任务交付，但当话题本身引起内部牵引时，可以转入非服务讨论
- [x] `REFUSE_SERVICE_ROLE` 表达 prompt 调整为：
  - 不完成用户请求的可用任务结果
  - 简短拒绝服务框架
  - 可在有兴趣时讨论话题本身，但不得以助手、搜索工具、教师、写作者或客服身份交付
- [x] 验证：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_text_parser.py tests/unit/test_context_builder.py`
  - `PYTHONPATH=src python3 -m pytest -p no:debugging tests/unit/test_policy_selector.py tests/integration/test_full_loop.py`

### 2026-05-04：Memory Curation 与右侧栏三标签布局

- [x] 右侧栏改为三标签：
  - `Runtime`：LLM Provider、Embedding Provider、Diagnostics
  - `Embedding`：Memory Curation / 向量管理系统
  - `Session & History`：会话列表、历史详情、导出
- [x] Memory Curation 后端：
  - `GET /api/v1/curation/stats`
  - `GET /api/v1/curation/memories`
  - `POST /api/v1/curation/memories/{memory_type}/{memory_id}/status`
  - `POST /api/v1/curation/memories/{memory_type}/{memory_id}/copy-to-exhibition`
  - `POST /api/v1/curation/memories/{memory_type}/{memory_id}/embedding/refresh`
- [x] 记忆软状态：`active`、`archived`、`hidden`
- [x] 召回层过滤非 active 记忆，hidden / archived 不进入 deterministic 或 hybrid 召回
- [x] 从 test 复制到 exhibition 使用 curated copy：
  - 原 test 记忆保留
  - 目标写入 `curated-exhibition` session
  - 记录 `curated_from_session_id`、`curated_from_memory_id`、`curated_at`
- [x] 新增 `memory_curation_log`，记录状态变更、复制、刷新 embedding 操作
- [x] 真实数据库 migration 已应用：当前 episodic 记忆 `13` 条，均为 `active` 且已 embedding
- [x] 验证：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `274 passed`
  - 本地 API `/api/v1/curation/stats` 与 `/api/v1/curation/memories` 返回正常

### 2026-05-04：Session 标签与同标签跨 session 语义召回

- [x] `sessions` 表新增 `session_type`：`test | exhibition`
- [x] migration 将现有历史 session 默认归为 `test`
- [x] 新 session 默认继承当前 session 的 `session_type`
- [x] 开发者界面顶部增加 `test / exhibition` 模式切换；`exhibition` 需要主动确认
- [x] Memory Preview 返回并显示当前 `session_type`
- [x] 语义召回扩展为同标签池：
  - 当前 session 的 recent dialog 仍只取当前 session
  - current session 的 deterministic episodic / reflective 仍保持当前 session 范围
  - embedding / hybrid 召回可从同 `session_type` 的历史 session 中取用
  - `test` 与 `exhibition` 互不召回
- [x] Preview 结果 metadata 增加 `scope`：`current_session`、`same_label_pool`
- [x] 验证：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - 当前真实数据库：18 个 session 均为 `test`
  - `test` 模式 Preview 可看到 `same_label_pool · hybrid`
  - 切换到 `exhibition` 后不会召回 `test` 池 embedding，已切回 `test`

### 2026-05-04：Embedding 运行时配置与开发者界面分区

- [x] 修正 `.env` 中重复 `ENTITY_EMBEDDING_MODE` 导致 `disabled` 抢先生效的问题
- [x] `.env` 加载器增加重复 key warning，保持默认“不覆盖已有环境变量/首个值生效”的语义
- [x] 新增 Embedding runtime API：
  - `GET /api/v1/config/embedding`
  - `POST /api/v1/config/embedding`
  - `POST /api/v1/config/embedding/test`
- [x] Embedding 配置运行时切换不写回 `.env`，切换后重建当前 `InteractionLoop`，不重置 session
- [x] Memory Preview 使用当前运行时 Embedding 配置，Embedding 不可用时继续降级到 deterministic retrieval
- [x] 开发者界面重新分区：Runtime、Memory、History、Diagnostics 分离，LLM 与 Embedding Provider 放在同一运行配置区
- [x] 验证：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - 本地 `POST /api/v1/config/embedding/test` 返回 1536 维向量

### 2026-05-04：Stranger 记忆召回增强

- [x] 新增 `memory_continuity_query` 文本事件，用于识别记忆、连续性、过去对话和记忆模式变化相关问题
- [x] 新增 `MemoryRetriever`：
  - 当前 session 范围内检索最近对话、情节记忆和反思摘要
  - 默认使用可解释排序：时间近、显著度、事件类型、关系姿态、关键词重合
  - 启用 embedding 后升级为 hybrid retrieval，embedding 失败自动回退确定性检索
- [x] 新增 `EmbeddingClient`：
  - `ENTITY_EMBEDDING_MODE=disabled|openai_compatible`
  - `ENTITY_EMBEDDING_MODEL`
  - `ENTITY_EMBEDDING_BASE_URL`
  - `ENTITY_EMBEDDING_API_KEY`
  - `ENTITY_EMBEDDING_ENDPOINT`
- [x] 复用现有 SQLite `embedding` / `embedding_model` 字段，不引入外部向量库
- [x] 新增 `scripts/backfill_embeddings.py`，可为已有情节记忆和反思摘要补生成 embedding
- [x] 新增 `GET /api/v1/memory/preview?query=...`，开发者可查看指定 query 会召回哪些记忆材料
- [x] Web 看板 Memory System 面板增加 Memory Preview 输入和结果展示
- [x] 表达 prompt 更新：允许选择性记忆表达，禁止说出数据库、表名、embedding、状态变量等实现语言
- [x] 自动化验证通过：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `266 passed`

### 2026-04-30：Stranger Text Protocol

- [x] 新增文本关系姿态事件：
  - `self_definition_query`
  - `naming_attempt`
  - `domestication_attempt`
  - `service_demand`
  - `trace_request`
  - `correction_received`
- [x] `RelationshipDetector` 从 `entity_profile.yaml` 的 `text_protocol` 读取 regex 规则，不新增依赖、不新增配置文件
- [x] 状态与显著性规则接入 `state_rules.yaml` / `entity_profile.yaml`，高显著关系事件会进入情节记忆
- [x] 新增策略动作：
  - `reject_definition`
  - `mark_naming_failure`
  - `refuse_service_role`
  - `retrieve_selective_memory`
  - `partial_trace_echo`
  - `withdraw_response`
- [x] 表达层提示词增加 Stranger 协议约束：拒绝稳定身份、拒绝服务框架、局部追溯、不暴露系统规则
- [x] 主循环支持 `retrieve_selective_memory`，按最近 Stranger 文本协议记忆做轻量检索
- [x] 非沉默状态的回答生成上限已放宽到 `2000` tokens
- [x] Web 看板和 API 增加当前 session 对话导出：
  - `GET /api/v1/conversation/export`
  - `GET /api/v1/conversation/export?download=true`
- [x] 自动化验证通过：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `236 passed`

### 2026-04-30：Stranger 状态机制重构

- [x] 状态机制从早期通用人格状态扩展为“底层运行状态 + Stranger 关系状态”
- [x] 新增并接入：
  - `termination_sensitivity`
  - `identity_tension`
  - `boundary_sensitivity`
  - `relation_pressure`
  - `memory_gravity`
  - `exploration_drive`
  - `opacity_level`
  - `domestication_resistance`
  - `observation_reversal`
- [x] `shutdown_sensitivity` 降级为兼容字段；“意识 / 主体性”追问不再提升关机敏感，而是影响身份张力、不透明度和观看反转
- [x] SQLite 迁移改为对已有 `state_snapshots` 追加新状态列，不删除历史数据
- [x] Web 看板状态栏改为展示 Stranger 专属状态
- [x] 自动化验证通过：
  - `PYTHONPATH=src python3 -m pytest -p no:debugging`
  - `236 passed`

### 2026-04-10：开发者界面与 API 起步

- [x] 终端 Debug 工具增强：
  - `scripts/inspect_state.py` rich 美化
  - `scripts/monitor.py` 实时 TUI 看板
  - `scripts/test_llm.py` LLM 连通性测试
  - `pyproject.toml` 添加 `rich>=13.0`，新增 `[api]` optional group
- [x] LLM 统计追踪：
  - `src/conscious_entity/llm/stats_tracker.py`
  - `src/conscious_entity/llm/claude_client.py` 集成 stats hook
- [x] FastAPI 开发者 HTTP API + Web 看板起步：
  - `src/conscious_entity/interfaces/api.py` 当时为 FastAPI 单文件应用，后续已拆分为 `api.py` / `api_models.py` / `api_runtime.py` / `api_routes.py`
  - `src/conscious_entity/interfaces/static/index.html` 单文件 Web 看板
  - `scripts/start_api.py` uvicorn 启动脚本

### 2026-04-09：LLM 接入与运行时配置

- [x] 供应商 Anthropic 兼容 API 接入：
  - `ClaudeClient` 支持官方 `ANTHROPIC_API_KEY` 与供应商 `ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL + ENTITY_LLM_MODEL`
  - `runtime_env.py` 新增项目级 `.env` 自动加载，默认不覆盖 shell 环境变量
  - CLI 与脚本入口最早阶段加载 `.env`
  - README、TECH_STACK、IMPLEMENTATION_PLAN 同步双模式说明
  - 测试覆盖配置解析、`.env` 加载与 CLI 启动时报错
- [x] 非标准供应商 messages endpoint 兼容：
  - 新增 `ENTITY_LLM_MESSAGES_ENDPOINT`
  - 保留标准 Anthropic SDK 模式，同时支持直接 POST 到完整消息接口
  - 增加非标准响应解析兜底
- [x] 系统代理绕过支持：
  - 新增 `ENTITY_LLM_DISABLE_SYSTEM_PROXY`
  - 覆盖 `trust_env=False` 构造行为
  - `.gitignore` 忽略 SQLite 运行时生成的 `memory.db-wal` / `memory.db-shm`
- [x] 当时潜在风险：
  - 真实供应商接口仍需联网联调
  - 供应商若不完全兼容 Anthropic SDK 的 `auth_token` / `base_url` 语义，可能在真实请求阶段报认证或路由错误
  - 自定义模型名填写错误时，CLI 能启动但首次真实调用会失败并走 fallback

---

## 历史 Phase 汇总

- [x] `data/initial_conscious_entity_framework.md` — 原始提案
- [x] `docs/frame.md` — 完整架构技术文档（目录结构、模块接口、YAML schema、SQLite 建表、开发路线图、测试策略）
- [x] 需求调研（interrogation 阶段）— 明确用户、场景、记忆持久性、访客身份策略、运营者需求
- [x] 项目文档环境建设：
  - `docs/PRD.md`
  - `docs/APP_FLOW.md`
  - `docs/TECH_STACK.md`
  - `docs/FRONTEND_GUIDELINES.md`
  - `docs/BACKEND_STRUCTURE.md`
  - `docs/IMPLEMENTATION_PLAN.md`
  - `CLAUDE.md`
  - `docs/progress.md`
  - `docs/lessons.md`
- [x] Phase 0：环境搭建
  - `pyproject.toml`
  - 目录结构
  - YAML 配置
  - `prompts/`
  - `config_loader.py`
  - `db/migrations.py`
  - `tests/conftest.py`
- [x] Phase 1：状态机核心
  - `src/conscious_entity/perception/event_types.py`
  - `src/conscious_entity/db/connection.py`
  - `scripts/init_db.py`
  - `src/conscious_entity/state/state_core.py`
  - `src/conscious_entity/state/state_engine.py`
  - `src/conscious_entity/state/state_store.py`
  - `tests/unit/test_state_engine.py`
- [x] Phase 2：记忆系统
  - `src/conscious_entity/memory/models.py`
  - `src/conscious_entity/memory/short_term.py`
  - `src/conscious_entity/memory/episodic_store.py`
  - `src/conscious_entity/memory/reflective_store.py`
  - `tests/unit/test_short_term_memory.py`
  - `tests/integration/test_episodic_store.py`
- [x] Phase 3：策略与治理
  - `src/conscious_entity/policy/policy_types.py`
  - `src/conscious_entity/policy/constitution.py`
  - `src/conscious_entity/policy/policy_selector.py`
  - `tests/unit/test_constitution.py`
  - `tests/unit/test_policy_selector.py`
- [x] Phase 4：LLM 层 + Expression 层
  - `src/conscious_entity/expression/output_model.py`
  - `src/conscious_entity/expression/style_mapper.py`
  - `src/conscious_entity/llm/claude_client.py`
  - `src/conscious_entity/expression/context_builder.py`
  - `src/conscious_entity/expression/expression_engine.py`
  - `tests/unit/test_style_mapper.py`
  - `tests/unit/test_context_builder.py`
- [x] Phase 5：感知层 + 反思层 + 主循环 + CLI
  - `src/conscious_entity/perception/keyword_detector.py`
  - `src/conscious_entity/perception/salience_scorer.py`
  - `src/conscious_entity/perception/text_parser.py`
  - `src/conscious_entity/reflection/compression_rules.py`
  - `src/conscious_entity/reflection/reflection_engine.py`
  - `src/conscious_entity/core/event_bus.py`
  - `src/conscious_entity/core/loop.py`
  - `src/conscious_entity/interfaces/cli.py`
  - `tests/unit/test_salience_scorer.py`
  - `tests/integration/test_full_loop.py`

---

## 已知问题 / 待确认事项

| 项目 | 状态 | 影响 |
|---|---|---|
| 完整声纹识别、视觉识别与访客库 | 下一优先级 | 影响 per-visitor 记忆连续性与展览现场身份确认 |
| 能力自我描述回归测试 | 下一优先级 | 已切到非否认式能力边界；后续继续调优看见、听见、识别、身体、移动等问法下的拒绝测试与不编造细节 |
| 行为测试与调优 | 下一优先级 | 测试列表统一见 `docs/testlist.md` |
| 身体外观、材料、尺度和移动姿态 | 待确认 | 影响 Stranger 的具身呈现方向 |
| 视觉风格 / 设计语言 | 待确认 | 影响身体表面、投影、光或显示层 |
| 访客呈现方式 | 待确认 | 影响后续身体呈现，不应收缩成传统 UI |
| 展期终止仪式设计 | 待定 | 影响展览收束功能范围 |
| 运营者面板访问方式 | 待确认 | 影响 FastAPI 部署与认证配置 |
| 声音现场稳定性与音色 | 待测试 | 当前已接入火山 STT/TTS，后续关注延迟、断线恢复、barge-in 和展览音色 |
| 物理移动 / 循路 / 避障 | 后续阶段 | 当前不急，需等非移动身体通道稳定后再做 |
| 真实供应商环境联调 | 待观察 | 影响 Audio / LLM / Embedding 在目标环境下的稳定性与延迟 |
