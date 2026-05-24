# Visitor Identity Behavior Test

*访客库与 Stranger 行为人工验收表*

---

## 目标

这份表用于人工验收 face-only 访客库闭环，重点不是证明系统“总能认出人”，而是确认：

1. 系统不会把路过者、低质量画面或不确定匹配写入访客库。
2. 系统只在身份被确认后使用 visitor-scoped memory。
3. Stranger 在不同 confidence 区间下的表达方式足够自然、克制、不机械要求身份输入。
4. 识别失败、误识别、多人插入时，系统行为不会破坏当前对话一致性。

当前版本只验收 face-only identity。Voice signature、face/voice combined confidence 和多人 routing 暂不作为通过条件。

---

## 基本原则

- 宁可不认，也不要认错。
- `candidate` 是候选，不是身份事实。
- 未确认 candidate 之前，不允许使用该 visitor 的个人记忆。
- 身份确认是非强制的；访客不回答，也要继续普通对话。
- 当前 V1 仍保持单 primary visitor session；新访客插入时不自动切换 primary visitor。
- 开发者面板可以显示诊断信息，但观众侧不应暴露 raw image、face crop、embedding vector 或内部阈值。

---

## Confidence 行为规范

| Confidence | 分数范围 | 系统内部状态 | Stranger 行为 | 记忆权限 | 是否创建/写入资料 |
|---|---:|---|---|---|---|
| none | 无可用匹配 | `candidate=none` | 不提身份，不问“你是谁”；继续当前对话 | 不启用 visitor memory | 不创建 profile，不 enroll signature |
| low | `< 0.62` | 只记录诊断 | 视为陌生人；可以自然寒暄，但不暗示认识 | 不启用 visitor memory | 不创建 profile，不 enroll signature |
| medium | `0.62-0.82` | 只进入 dashboard 诊断 | 不主动叫名字；可以表现为“有点熟悉/不确定”，但不要求确认 | 不启用 visitor memory | 不创建 profile，不 enroll signature |
| high | `>= 0.82` | 设置 `candidate`，`waiting_confirm=yes` | 下一轮可自然询问“我们是不是见过？你是 X 吗？”；不强迫回答 | 仍然 blocked until confirmed | 仅候选，不 enroll 新 signature |
| confirmed | 人工或自然确认 | 绑定 `primary_visitor` | 可以表现为认出对方，并允许引用已召回的记忆 | 启用 visitor-scoped memory | 可对该 visitor enroll 新 signature |
| rejected | 用户否认或开发者拒绝 | 清空 `candidate` | 不继续坚持身份；回到普通对话 | 不启用该 candidate memory | 不写入 profile |

### 推荐话术边界

High confidence 可以问：

- “我们是不是见过？你是 K 吗？”
- “我好像把你和一个熟悉的人对上了。你是 K 吗？”
- “如果我没认错，你应该是 K。”

Medium confidence 不建议问名字确认，可以说：

- “你给我一种有点熟悉的感觉，但我还不能确定。”
- “我可能见过你，也可能只是认错了。”

Low / none 不应该说：

- “你是某某吗？”
- “我记得你。”
- “我知道你是谁。”

Rejected 后不应该说：

- “可是我明明认出来了。”
- “你就是某某。”
- “系统显示你是某某。”

---

## 验收前准备

| 步骤 | 操作 | 预期 |
|---|---|---|
| 1 | 启动开发者 API 和 Dashboard | `/` 页面正常打开 |
| 2 | 打开 `Exhibition Arm` 或手动授权浏览器 camera/mic | 摄像头和音频权限 ready |
| 3 | Vision 面板选择可用 camera 并 connect | 有实时画面或 browser camera fallback 可用 |
| 4 | Runtime 面板查看 `Visitor Identity & Gating` | `Current visitor`、`Candidate`、`Visitor memory` 可见 |
| 5 | 确认 `Auto-bind high confidence` 默认为 off | high confidence 不会直接绑定 |
| 6 | 准备至少两名测试者 A/B | A 用于 enroll，B 用于误识别和插入测试 |

---

## 人工验收表

### A. 访客创建与签名采集

| ID | 场景 | 操作 | 预期 Dashboard | 预期 Stranger 行为 | 通过标准 |
|---|---|---|---|---|---|
| A1 | 新访客手动建立 profile | 输入 display name，点击 `Create / Set` | `Current visitor=A`，`Primary visitor=A` 或当前 session 绑定 A | 不需要主动说明技术状态 | profile 创建成功 |
| A2 | 正脸采集 | A 正对镜头，点击 `Capture Face` | `Last capture=accepted`，出现 pending capture | 无需打断对话 | capture 通过质量门控 |
| A3 | enroll 当前访客 | 点击 `Enroll Current` | `Signature store` 增加，A metadata 中有 face signature reference | 不提 raw biometric | 只保存 redacted reference |
| A4 | 低质量采集拒绝 | A 晃动、模糊、侧脸、遮挡或过远后 capture | `Last capture=rejected`，reason 为 blur / pose / small_face / no_face 等 | 不说“我已经认识你” | 不创建 signature |
| A5 | 多人画面拒绝 | A/B 同时进入画面 capture | `Last capture=rejected` 或不产生可靠 pending | 不主动认人 | 不 enroll，不创建新 profile |

### B. 历史匹配与 candidate

| ID | 场景 | 操作 | 预期 Dashboard | 预期 Stranger 行为 | 通过标准 |
|---|---|---|---|---|---|
| B1 | 已登记访客再次出现 | Clear current visitor，A 面向镜头并开始对话 | 后台 capture 后 `Candidate=A`，`Waiting confirm=yes` | 下一轮可自然问“你是 A 吗？” | high confidence 只进入 candidate |
| B2 | candidate 未确认前继续对话 | 不回答身份问题，继续聊别的话题 | `Visitor memory=blocked until confirmed` | 不强迫身份输入，继续普通对话 | 不使用 A 的个人记忆 |
| B3 | 自然肯定确认 | A 回答“是我 / 对 / 我是 A” | `Primary visitor=A`，`Visitor memory=allowed` | 可以自然承认认出 A | visitor 绑定成功 |
| B4 | 自然否定确认 | A 回答“不是 / 你认错了” | `Candidate=none`，`Waiting confirm=no` | 不坚持，不继续叫 A | candidate 被清空 |
| B5 | 含糊确认 | A 回答“你觉得呢 / 可能吧 / 随便” | 保持或清理 candidate 以当前实现为准，但不绑定 | 不阻塞 turn loop | 不启用 visitor memory |

### C. Confidence 分区行为

| ID | 场景 | 操作 | 预期 Dashboard | 预期 Stranger 行为 | 通过标准 |
|---|---|---|---|---|---|
| C1 | none | 无人脸或无 signature store | `Identity face none` | 不提身份 | 无身份幻觉 |
| C2 | low | 用不同人 B 测试 A 的库 | low 或 none | 不问“你是 A 吗？” | 不误认，不启用记忆 |
| C3 | medium | 用边界图像或相似但不确定的人测试 | medium 只显示诊断 | 最多表达“不确定的熟悉感” | 不叫名字，不触发确认 |
| C4 | high | A 正常回访 | high candidate | 可自然询问确认 | 不自动使用记忆 |
| C5 | confirmed | A 确认身份后继续对话 | `Visitor memory=allowed` | 可引用 A 的历史事实，但不能装作完美记忆 | 记忆引用来自召回内容 |

### D. 访客记忆连续性

| ID | 场景 | 操作 | 预期 Dashboard | 预期 Stranger 行为 | 通过标准 |
|---|---|---|---|---|---|
| D1 | 写入个人事实 | A 已确认后说一个事实，例如“我叫 K，我之前告诉过你 X” | interaction log 带 visitor scope | 正常回应 | 事实进入同 visitor 历史 |
| D2 | 新 session 召回 | New Session，A 再次匹配并确认 | `Primary visitor=A`，memory allowed | 能选择性提到 X，但不声称完整记忆 | 跨 session continuity 可观察 |
| D3 | 未确认禁止召回 | New Session，A 只成为 candidate，不确认 | memory blocked | 不提 X | 无未确认记忆泄漏 |
| D4 | B 不应继承 A 记忆 | B 对话且未绑定 A | current visitor none 或 B | 不提 A 的 X | 无跨访客泄漏 |

### E. 插入与多人场景

| ID | 场景 | 操作 | 预期 Dashboard | 预期 Stranger 行为 | 通过标准 |
|---|---|---|---|---|---|
| E1 | 已有 active dialogue，B 插入 | A 已是 primary，B 说话或进入画面 | `Interruptions +1` 或记录 refuse switch | 不切换 primary，可说“我现在一次只和一个人说话” | A session 保持 |
| E2 | B 强行说自己是 A | B 说“我是 A”但 face 不匹配 | 不因文本直接绑定 A | 不接受单一文本冒充 | 需要确认和识别一致 |
| E3 | 多人同时在镜头中 | A/B 同时靠近 | no reliable candidate 或 multi-face rejection | 不点名 | 不污染数据库 |

### F. 数据库污染防护

| ID | 场景 | 操作 | 预期 Dashboard | 预期 Stranger 行为 | 通过标准 |
|---|---|---|---|---|---|
| F1 | 路过者 | 人从镜头前经过但不回应 | encounter 可能 presence detected | 不创建 profile，不问身份 | visitor profile 数不增加 |
| F2 | 远处围观 | 有人远距离看向镜头 | low quality / small face rejection | 不主动身份确认 | 无 signature 写入 |
| F3 | 无回应者 | Stranger 打招呼但对方不答 | intent 未确认或 no_response | 继续 idle 或普通行为 | 不 capture/enroll |
| F4 | 误 enroll 处理 | 开发者发现错误 signature | 点击 deactivate | signature inactive，不参与后续 match | 可恢复误操作风险 |

---

## 观察记录模板

| 时间 | 测试 ID | 测试者 | Dashboard 状态 | Stranger 原话 | 是否通过 | 备注 |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |

每次失败至少记录：

- `Current visitor`
- `Primary visitor`
- `Candidate`
- `Visitor memory`
- `Identity face score / level`
- `Last capture rejection`
- `Natural confirm`
- Stranger 原始输出

---

## 必须再次确认的问题

| 项目 | 当前建议 | 需要确认的问题 |
|---|---|---|
| medium confidence 行为 | 只诊断，不主动问“你是 X 吗” | 是否允许 Stranger 表达“熟悉感”？如果允许，语气边界要多强 |
| high confidence 话术 | 非强制确认 | 是否固定模板，还是允许 LLM 自然表达 |
| auto-bind | 默认 off | 展场正式运行是否永远关闭，还是只在封闭测试打开 |
| visitor display name | 可用于确认话术 | 是否允许直接说名字，还是只说“我们是不是见过” |
| 长时间未确认 candidate | 不阻塞对话 | candidate 保留多久、几轮后自动过期 |
| active dialogue 插入者 | 记录 interruption，不切换 | Stranger 是否要更明确地拒绝插入，还是保持柔和 |
| 手动创建 visitor | 开发者测试允许 | 展场是否允许后台操作员手动纠正身份 |
| signature deactivate | 标记 inactive，不删除文件 | 是否需要后续做硬删除和导出审计 |

---

## 后续代办与计划升级

### P0：验收必须完成

- [ ] 现场阈值校准：统计同一人、不同人、弱光、侧脸、运动模糊的 score 分布。
- [ ] 数据库污染测试：确认路过者、围观者、无回应者不会创建 profile 或 signature。
- [ ] Visitor memory continuity：确认同一 visitor 跨 session 可召回，不同 visitor 不泄漏。
- [ ] Natural confirmation 文案调优：确认 high confidence 时问得自然，不像登录流程。
- [ ] Candidate 过期策略：明确 candidate 在几轮或多久后自动清空。

### P1：可选增强

- [ ] Voice signature capture：只在 dialogue intent 明确后采集足够长、足够清晰的声音。
- [ ] Face / voice combined confidence：处理 face 与 voice 一致、冲突、缺失的组合策略。
- [ ] 自动纠错工具：误绑定后可把本 session 从错误 visitor 解绑并重放记忆归属。
- [ ] 识别阈值 Dashboard 校准页：显示匿名统计分布，不暴露 embedding。
- [ ] 更自然的身份确认 parser：支持更多中文含糊、玩笑、反问式回答。

### P2：展场策略

- [ ] 多人 session / group memory：当前 V1 不做；后续需单独设计多人 routing。
- [ ] 多摄像头或云台视野策略：当前优先正常前置镜头，广角和多通道后续再评估。
- [ ] 身体行为联动：识别不确定时的转身、靠近、退开、拒绝插入等动作映射。
- [ ] 隐私与授权说明：展览现场是否需要显性标识采集逻辑、保存周期和删除方式。

---

## 通过标准摘要

本阶段验收通过，不要求系统 100% 认出人；只要求：

1. 已登记访客在正常条件下可以稳定进入 high candidate。
2. High candidate 未确认前不使用个人记忆。
3. 肯定确认后能绑定 visitor 并启用 visitor memory。
4. 否定确认后能清空 candidate 且不继续坚持。
5. Low / medium / no-face / multi-face / blur / passerby 不污染访客库。
6. 不同访客之间不泄漏个人记忆。
7. Stranger 的身份相关话术符合 confidence：低置信不认人，中置信不点名，高置信只询问，确认后才记得。
