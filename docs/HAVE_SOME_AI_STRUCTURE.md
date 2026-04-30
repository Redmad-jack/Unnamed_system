# Have Some "Ai" System Structure

本文档记录当前文件夹中新增的 Have Some "Ai" 项目骨架。它和原有 `conscious_entity` 并列存在：原系统可以继续作为 The "Stranger" 的技术基础；本系统专门负责观众流程、问卷、评分、食物分配与工作人员队列。

## 当前边界

```text
src/
├── conscious_entity/          # 保留：Stranger / 原 Conscious Entity
└── have_some_ai/              # 新增：Have Some "Ai"
    ├── config.py              # 加载题库与评分配置
    ├── db.py                  # Have Some "Ai" 专属 SQLite 表
    ├── hardware.py            # 未来硬件边界：打印、灯、传感器、厨房信号
    ├── models.py              # 参与者、题目、答案、观察事件、分配结果
    ├── questionnaire.py       # 三模块随机抽题
    ├── repository.py          # 数据库读写
    ├── scoring.py             # 双轴评分与四种食物映射
    ├── service.py             # 观众流程应用服务
    └── interfaces/
        ├── api.py             # FastAPI app
        └── static/index.html  # 最小观众/工作人员界面
```

## 配置文件

```text
config/have_some_ai/
├── questions.yaml   # 三个模块的题库、选项、分数
└── scoring.yaml     # 阈值、食物映射、观察事件权重、安全备注
```

后续细化分配机制时，优先改这两个 YAML，而不是直接改代码。

## 最小闭环

当前系统已经支持：

1. 新建匿名观众，生成 `A001` 形式的 public code
2. 从三个模块各随机抽一题
3. 提交三题答案
4. 根据 `ai_trace` 与 `relational` 两条轴计算结果
5. 映射到四种食物：
   - `soup`
   - `salad`
   - `ai_sprout_soup`
   - `ai_sprout_salad`
6. 将分配结果写入工作人员队列
7. 工作人员将队列项更新为 `preparing` 或 `served`
8. 导出所有 Have Some "Ai" 数据

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
```

## API

主要端点：

```text
GET  /health
GET  /api/v1/config
POST /api/v1/participants
GET  /api/v1/participants
GET  /api/v1/participants/{id}
POST /api/v1/participants/{id}/questionnaire/start
POST /api/v1/participants/{id}/answers
POST /api/v1/participants/{id}/observations
POST /api/v1/participants/{id}/assign
GET  /api/v1/staff-queue
PATCH /api/v1/staff-queue/{queue_item_id}
GET  /api/v1/export
```

## 后续扩展顺序

建议按这个顺序继续做：

1. 细化 `questions.yaml` 与 `scoring.yaml`，确定最终分配机制
2. 给观众端和工作人员端拆成两个页面
3. 增加安全/忌口覆盖逻辑，确保发餐前由工作人员确认
4. 接入摄像头或传感器，把识别结果写入 `/observations`
5. 在 `hardware.py` 中实现打印、小票、灯光、厨房信号或 Arduino/ESP32 适配器
6. 加入 LLM 话术层，但保持规则引擎决定最终食物
7. 增加 CSV 导出和展后统计面板

## 设计原则

- 食物分配由规则引擎决定，LLM 以后只负责语气和文本。
- 摄像头/动作识别只生成抽象观察事件，不直接决定食物。
- 安全与忌口必须优先于艺术算法。
- Have Some "Ai" 与 Stranger 可以共享代码仓库，但不共享状态、记忆、题库、评分和分配结果。
