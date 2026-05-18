# Progress

*Conscious Entity System*

---

## 当前状态

- 当前进行中：无
- 当前可运行形态：CLI + 本地 FastAPI 开发者 API + Web 看板 + progressive text/audio NDJSON + 可选 Vision 面板 + 可选 Audio Adapter + `/visitor` 临时身体表面；观众侧最终呈现方向是身体，不是传统 UI
- 当前核心能力：Stranger 文本协议、最高优先级艺术运行 context、热加载 prompt partial、本轮语言强制优先与错语言兜底、非否认式能力边界正向模板与输入通道防自我否认约束、含“恋旧” memory_gravity 的新心理状态机、带上一轮轻量 bridge 的 pre-memory 轻量 `first_unit` + 已说出口 first 去重续写的 memory-aware `second_unit` 按句文本/audio progressive 输出、main LLM 后端 streaming buffer、two-stage / sentence-queued TTS、短期/情节/反思记忆、匿名 visitor profile 与跨 session visitor 记忆召回、Visitor Identity & Session Gating V1、可解释/可选 embedding 召回、Memory Preview、managed memory proposal → commit、influence log / curation、Runtime Harness Trace、可选 YOLO person presence detection、可选火山 ASR 2.0 / TTS 2.0 双向流式 Audio Adapter
- 当前验证基线：`.venv/bin/python -m pytest -p no:debugging`，最近一次完整结果为 `521 passed`
- 当前交接重点：下一步不再优先扩展 UI，而是先补齐完整声纹识别、视觉识别和访客库；能力自我描述已改为非否认式边界，后续按该口径继续做行为测试调优
- 当前注意事项：`AGENTS.md` 与 `CLAUDE.md` 有用户侧未提交差异；除非明确要求，不应在常规任务中触碰

---

## 下一步（交接优先级）

### P0：合作者优先处理

- [ ] 完整声纹识别、视觉识别与访客库
  - 基于当前 Visitor Identity & Session Gating V1 继续做，不要求观众硬性输入身份
  - 完成 voice signature / face signature 的采集、质量门控、历史匹配、combined confidence、自然确认和 visitor profile metadata
  - 当前 V1 只支持开发者手动绑定匿名 `visitor_id`；不能把它误读为已完成自动识别
- [ ] 能力自我描述回归测试与优化
  - 重点检查 Stranger 对“看见、听见、记得、识别、移动、身体、声音、记忆”的自我描述是否符合非否认式能力边界：不直接说“没有 / 不能 / 做不到”，但也不编造未进入 runtime 的细节、不服从证明测试
  - `docs/testlist.md` 的 capability consistency 条目仍需后续按 Step 12 新口径同步细化
- [ ] 行为测试与调优
  - 统一按 `docs/testlist.md` 执行和记录；这里不展开具体测试项

### P1：保持在下一梯队

- [ ] 继续观察真实对话中的记忆连续性：同一 visitor 的跨 session 召回是否稳定，Memory Preview 是否能解释召回来源，managed memory influence 是否可审计且不越界
- [ ] 使用真实供应商环境做 Audio / LLM / Embedding 联调和延迟观察：确认火山 ASR/TTS、当前 Claude/Anthropic-compatible 网关、自定义模型名、embedding 配置和网络延迟在目标环境可用
- [ ] 手动联调视觉层：安装 `.[dev,api,vision]`，配置本地 `ENTITY_VISION_MODEL_PATH`，确认 Mac 摄像头授权、实时标注帧、detections 和 presence events
- [ ] 后续单独设计多人并发策略：当前仍收束为单 primary visitor session；多人 routing / 仲裁策略仍待确认

### P2：后续身体与展览阶段

- [ ] 继续规划非移动身体阶段：身体外观、声音风格、显示/投影/光的呈现映射；更完整空间感知仍待设计
- [ ] 物理移动、循路、避障、底盘控制和安全边界放到更后阶段，等非物理身体通道稳定后再实现
- [ ] 部署认证、访客身份策略最终版与展期终止仪式仍待设计确认

---

## Changelog

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
