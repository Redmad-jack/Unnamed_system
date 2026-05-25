# Visitor Identity Behavior Test

*访客库与 Stranger 行为人工验收表*

---

## 目标

这份表用于人工验收 face-only 访客库闭环，重点不是证明系统“总能认出人”，而是确认：

1. 系统不会把路过者、低质量画面、多人脸或相似旧访客的模糊匹配写入访客库。
2. 系统只在 visitor 已绑定后使用 visitor-scoped memory；known candidate 未确认前不读取旧 visitor memory。
3. Stranger 在不同 confidence 区间下的表达方式足够自然、克制、不机械要求身份输入。
4. 识别失败、误识别、多人插入时，系统行为不会破坏当前对话一致性。

当前版本只验收 face-only identity、“主访客离开后再交接”和新陌生访客自动建档的第一版保守逻辑。Voice signature、face/voice combined confidence 和多人同时对话 routing 暂不作为通过条件。

---

## 基本原则

- 宁可不认，也不要认错。
- `candidate` 是候选，不是身份事实。
- 未确认 candidate 之前，不允许使用该 visitor 的个人记忆。
- 已知访客 candidate 的身份确认是非强制的；访客不回答，也要继续普通对话。
- 新陌生访客不是 consent / onboarding flow：A 已 release 且当前是 unidentified ready 时，accepted single face 没有 medium/high known match、没有 ambiguous known cluster，就直接创建匿名 `visitor-*` profile 并绑定本轮。
- 当前 V1 仍保持单 primary visitor session；新访客插入时不自动切换 primary visitor。
- primary visitor 在画面中时，对话窗口被锁住；B 进入画面只算插入，不替换 A。
- 只有已锁定的 primary track 连续丢失超过 35 秒，才允许释放 A 并开启新的 unidentified session；grace 内的输入必须走 unscoped turn，不归属 A 或 B。
- 如果 primary 从未成功锁定 track，不能因为画面为空直接释放 A，避免 camera / tracker 未就绪时误清当前对话窗口。
- 多人同框导致 track 不可靠时，默认保守：不自动把剩下的某个人当成 A，也不自动切换。
- 开发者面板可以显示诊断信息，但观众侧不应暴露 raw image、face crop、embedding vector 或内部阈值。

---

## Confidence 行为规范

| Confidence | 分数范围 | 系统内部状态 | Stranger 行为 | 记忆权限 | 是否创建/写入资料 |
|---|---:|---|---|---|---|
| no frame / rejected | 无 frame、多人脸、低质量、质量门控失败 | `candidate=none` | 不提身份，不问“你是谁”；继续当前对话 | 不启用 visitor memory | 不创建 profile，不 enroll signature |
| unknown accepted | 单人脸通过质量门控，且没有 medium/high known match、没有 ambiguous known cluster | 自动创建并绑定新 `visitor-*` | 作为新访客自然开场，不暗示旧记忆 | 本轮可写入新 visitor scope；无旧 memory 可召回 | 创建 profile，enroll 当前 face signature |
| known low | `< 0.62` 且不 ambiguous | 视作陌生新人路径 | 不问“你是旧访客吗？” | 同 unknown accepted | 创建新 profile，而不是绑定低置信旧访客 |
| known low ambiguous | 两个以上旧访客 near-medium 且分差很小 | `candidate=none` | 不点名，不建新人 | 不启用 visitor memory | 不创建 profile，不 enroll signature |
| known medium | `0.62-0.82` | 设置 `candidate`，`waiting_confirm=yes` | 可自然询问“我们是不是见过？你是 X 吗？”；不强迫回答 | blocked until confirmed | 仅候选，不 enroll 新 signature |
| known high | `>= 0.82` | 设置 `candidate`，`waiting_confirm=yes` | 可自然询问确认；不强迫回答 | blocked until confirmed | 仅候选，不 enroll 新 signature |
| confirmed | 人工或自然确认 | 绑定 `primary_visitor` | 可以表现为认出对方，并允许引用已召回的记忆 | 启用 visitor-scoped memory | 可对该 visitor enroll 新 signature |
| rejected | 用户否认或开发者拒绝 | 清空 `candidate` | 不继续坚持身份；回到普通对话 | 不启用该 candidate memory | 不写入 profile |

### 推荐话术边界

High confidence 可以问：

- “我们是不是见过？你是 K 吗？”
- “我好像把你和一个熟悉的人对上了。你是 K 吗？”
- “如果我没认错，你应该是 K。”

Known medium confidence 可以进入 candidate confirmation，但在确认前不能读取该 visitor 的 memory，也不能当作已经认出。表达上应保持不强迫、不登录化。

Rejected、ambiguous 或未建档前不应该说：

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
| 6 | 确认 `主访客离开后允许下一位接管` 默认为开启 | A 离开后才允许 B 进入新 unidentified session |
| 7 | 准备至少两名测试者 A/B，或一人 + 一张清晰照片/屏幕显示的人脸 | A 用于 enroll，B 用于误识别、插入和交接测试 |

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
| A6 | 新陌生访客自动建档 | A 已 release 后，unknown B 首轮说话且单人脸质量通过 | 新 `visitor-*` profile，session `visitor_id=B`，signature store +1 | 作为新访客自然开场 | 本轮写入新 visitor scope，不召回旧 visitor memory |

### B. 历史匹配与 candidate

| ID | 场景 | 操作 | 预期 Dashboard | 预期 Stranger 行为 | 通过标准 |
|---|---|---|---|---|---|
| B1 | 已登记访客再次出现 | Clear current visitor，A 面向镜头并开始对话 | 后台 capture 后 `Candidate=A`，`Waiting confirm=yes` | 下一轮可自然问“你是 A 吗？” | known high / medium 只进入 candidate |
| B2 | candidate 未确认前继续对话 | 不回答身份问题，继续聊别的话题 | `Visitor memory=blocked until confirmed` | 不强迫身份输入，继续普通对话 | 不使用 A 的个人记忆 |
| B3 | 自然肯定确认 | A 回答“是我 / 对，是我 / 我是 A” | `Primary visitor=A`，`Visitor memory=allowed` | 可以自然承认认出 A | visitor 绑定成功 |
| B4 | 自然否定确认 | A 回答“不是 / 你认错了” | `Candidate=none`，`Waiting confirm=no` | 不坚持，不继续叫 A | candidate 被清空 |
| B5 | 含糊确认 | A 回答“你觉得呢 / 可能吧 / 随便 / 我是另一个人” | `last_natural_confirmation=unclear`，candidate 未被绑定，之后按 2 轮或 90 秒过期 | 不阻塞 turn loop | 不启用 visitor memory |

### C. Confidence 分区行为

| ID | 场景 | 操作 | 预期 Dashboard | 预期 Stranger 行为 | 通过标准 |
|---|---|---|---|---|---|
| C1 | no frame / rejected | 无人脸、多人脸、模糊或过远 | no candidate | 不提身份 | 无身份幻觉，不建档 |
| C2 | known low / unknown accepted | 用不同人 B 测试 A 的库，且画面质量通过、无 ambiguous cluster | 新 `visitor-*` 被创建，当前 session 绑定 B | 作为新访客继续，不问“你是 A 吗？” | 不误绑 A；只写入新 B scope |
| C3 | known medium | 用边界图像或相似但达到 medium 的人测试 | `Candidate=旧 visitor`，`Waiting confirm=yes` | 可自然确认，但不使用旧 visitor memory | 不绑定、不读取 memory、不 enroll 新 signature |
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
| E1 | A 仍在画面中，B 插入 | A 已是 primary 且 `Primary presence=present`，B 说话或进入画面 | `Interruptions +1` 或 `refuse_switch`，`Primary visitor=A` | 不切换 primary，可说“我现在一次只和一个人说话” | A session 保持 |
| E2 | A 短暂离开，B 还在画面中 | A 的 track 丢失但未超过 35 秒，B 说话 | `Primary presence=missing_grace`，turn decision 为 `continue_unscoped` | 不把 B 当作 A 的延续，也不要求 B 确认身份 | 不写入 A / B visitor scope，不启用 visitor memory |
| E3 | A 离开超过 grace | A 的 track 连续丢失超过 35 秒，B 留在镜头内 | `Last primary release=primary_track_lost`，新 session `Current visitor=none` | 不把 B 当作 A 的延续 | 先释放 A，再允许 B 后续 candidate |
| E4 | A 离开后 unknown B 开始互动 | E3 之后 B 开始说话，画面为单人 accepted face，且无 known medium/high/ambiguity | 创建新 `visitor-*`，当前 session 绑定 B | 作为新访客开场，不继承 A 记忆 | 不泄漏 A 的 visitor memory，本轮写入 B scope |
| E5 | A 离开后 known B 开始互动 | E3 之后 B 开始说话，face match 为 medium/high known B | `Candidate=B`，`Waiting confirm=yes` | 可自然询问是否是 B | B 未确认前不使用 B memory |
| E6 | B 强行说自己是 A | B 说“我是 A”但 face 不匹配 | 不因文本直接绑定 A | 不接受单一文本冒充 | 需要确认和识别一致 |
| E7 | 多人同时在镜头中 | A/B 同时靠近 | `Primary presence=ambiguous` 或 multi-face rejection | 不点名 | 不污染数据库，不把剩下的人反向锁成 A |

### F. 数据库污染防护

| ID | 场景 | 操作 | 预期 Dashboard | 预期 Stranger 行为 | 通过标准 |
|---|---|---|---|---|---|
| F1 | 路过者 | 人从镜头前经过但不回应 | encounter 可能 presence detected | 不创建 profile，不问身份 | visitor profile 数不增加 |
| F2 | 远处围观 | 有人远距离看向镜头 | low quality / small face rejection | 不主动身份确认 | 无 signature 写入 |
| F3 | 无回应者 | Stranger 打招呼但对方不答 | intent 未确认或 no_response | 继续 idle 或普通行为 | 不 capture/enroll |
| F4 | 相似旧访客 ambiguous | 两个旧访客的低于 medium 但接近 medium 的分数很接近 | no candidate / no new profile | 不点名 | 不把相似旧访客拆成新人 |
| F5 | 误 enroll 处理 | 开发者发现错误 signature | 点击 deactivate | signature inactive，不参与后续 match | 可恢复误操作风险 |

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
| medium confidence 行为 | 当前无 primary 且非 grace 时进入 candidate confirmation | 是否需要调整 medium 阈值或确认话术强度 |
| high confidence 话术 | 非强制确认 | 是否固定模板，还是允许 LLM 自然表达 |
| unknown accepted 自动建档 | A release 后 unidentified ready 中直接创建匿名 `visitor-*` | 现场阈值是否足够保守，是否需要增加质量门槛 |
| auto-bind | 默认 off | 展场正式运行是否永远关闭，还是只在封闭测试打开 |
| visitor display name | 可用于确认话术 | 是否允许直接说名字，还是只说“我们是不是见过” |
| 长时间未确认 candidate | 2 个未确认 turn 或 90 秒后过期 | 现场是否需要调短或调长 |
| active dialogue 插入者 | 记录 interruption，不切换 | Stranger 是否要更明确地拒绝插入，还是保持柔和 |
| 主访客离开后交接 | 默认开启，只在 primary left 后接管 | 展场正式运行是否保留自动开启，还是由操作员手动控制 |
| 手动创建 visitor | 开发者测试允许 | 展场是否允许后台操作员手动纠正身份 |
| signature deactivate | 标记 inactive，不删除文件 | 是否需要后续做硬删除和导出审计 |

---

## 后续代办与计划升级

### P0：验收必须完成

- [ ] 现场阈值校准：统计同一人、不同人、弱光、侧脸、运动模糊的 score 分布。
- [ ] 数据库污染测试：确认路过者、围观者、无回应者、multi-face、low quality 和 ambiguous known cluster 不会创建 profile 或 signature；清晰 unknown B 在 handoff 后会创建新 profile。
- [ ] Visitor memory continuity：确认同一 visitor 跨 session 可召回，不同 visitor 不泄漏。
- [ ] Natural confirmation 文案调优：确认 high confidence 时问得自然，不像登录流程。
- [x] Candidate 过期策略：当前默认 2 个未确认 turn 或 90 秒后自动清空。

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

1. 已登记访客在正常条件下可以稳定进入 high / medium candidate。
2. Known candidate 未确认前不使用个人记忆。
3. 肯定确认后能绑定 visitor 并启用 visitor memory。
4. 否定确认后能清空 candidate 且不继续坚持。
5. No-face / multi-face / blur / passerby / ambiguous known cluster 不污染访客库；accepted unknown / non-ambiguous low known 会新建匿名 visitor，而不是误绑旧 visitor。
6. 不同访客之间不泄漏个人记忆。
7. Stranger 的身份相关话术符合 confidence：known candidate 只询问，unknown accepted 按新访客处理，确认或新建绑定后才有 visitor scope。
8. A 没离开镜头时，B 不会替换 A；只有 A 被确认离开后，B 才能进入新对话窗口。
