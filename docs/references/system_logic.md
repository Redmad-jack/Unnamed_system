# 系统逻辑文档（软硬件综合）

> 本文档说明当前 Stranger 单体移动身体方案的硬件拓扑、软件分层和数据流，供开发与展览调试使用。
> 当前仓库只实现 Stranger，不实现 Shopkeeper。旧的双实体、两片 ESP32、ESP32 I2S DAC / PCM5102A 音频方案不再作为本项目当前方案。

---

## 一、当前范围

当前系统由一个 Stranger 移动身体构成：

- **Mac mini** 随身体移动，作为上位机与主要计算单元
- **ESP32-S3** 作为唯一的下位身体控制器
- **TCA9548A** 扩展 I2C，总线下接 4 个 **VL53L1X ToF**
- **TCRT5000** x3 通过 `A0` 模拟量读取单黑线轨道
- **四路有刷直流电机驱动板** 驱动 4 个 **36JP555 直流有刷减速电机**
- **小音响** 直接连接 Mac mini 播放声音
- **小屏幕** 作为 Stranger 的身体状态表面，不作为观众侧 dashboard

当前优先完成：

1. ESP32-S3 + TCA9548A + 4 个 VL53L1X 的距离读取
2. 三个 TCRT5000 的单轨道 `A0` 模拟循迹读取
3. 基于 TCRT 轨道状态 + ToF 的本地下位机运动 gate
4. 四路电机的低速开环移动
5. Mac mini 与 ESP32-S3 的 USB Serial 通信
6. BNO085 IMU SPI bring-up 与可观测 telemetry

当前暂缓：

- IMU 完整运动闭环接入：当前 BNO085 可辅助 TCRT 丢线后的 yaw 扫描幅度，但不估算里程、不判断回轨成功、不设置倾斜 / 撞击阈值、不单独自动停机
- 编码器
- 稳定巡路 / 精确里程计
- SLAM / 地图导航
- WiFi 下位机通信
- ESP32 音频播放

---

## 二、系统总体架构

### 2.1 系统拓扑

```mermaid
graph TB
    V["访客"]

    subgraph BODY ["Stranger 移动身体"]
        subgraph MAC ["Mac mini 上位机"]
            API["FastAPI 开发者 API / Dashboard"]
            LOOP["Stranger turn loop"]
            STATE["State / Memory / Policy / Expression"]
            AUDIO["TTS / Audio output"]
            SCREEN_DRV["小屏幕渲染或页面服务"]
            BODY_BRIDGE["BodyBridge USB Serial"]
            DB[("SQLite memory.db")]
            LLM["Claude / Anthropic-compatible API"]
        end

        subgraph ESP ["ESP32-S3 下位身体控制器"]
            SERIAL["USB Serial protocol"]
            LINE_GATE["TCRT line-following gate"]
            TOF_GATE["ToF obstacle gate"]
            I2C["I2C master"]
            ADC["ADC read"]
            SPI["SPI master"]
            PWM["PWM + DIR motor output"]
        end

        subgraph SENSORS ["传感层"]
            MUX["TCA9548A I2C multiplexer"]
            TFL["VL53L1X front_left"]
            TFR["VL53L1X front_right"]
            TL["VL53L1X left"]
            TR["VL53L1X right"]
            TCRT_L["TCRT line_left"]
            TCRT_C["TCRT line_center"]
            TCRT_R["TCRT line_right"]
            IMU["BNO085 IMU"]
        end

        subgraph DRIVE ["移动执行"]
            DRIVER["四路有刷直流电机驱动板"]
            M1["36JP555 M1"]
            M2["36JP555 M2"]
            M3["36JP555 M3"]
            M4["36JP555 M4"]
        end

        SPK["小音响"]
        SCR["小屏幕身体表面"]
    end

    V -- "声音 / 语言输入（当前经已有 audio 或开发入口）" --> LOOP
    V -- "物理靠近 / 障碍物" --> TFL
    V -- "物理靠近 / 障碍物" --> TFR
    V -- "侧向距离变化" --> TL
    V -- "侧向距离变化" --> TR
    V -- "地面黑线轨道" --> TCRT_L
    V -- "地面黑线轨道" --> TCRT_C
    V -- "地面黑线轨道" --> TCRT_R
    V -- "搬动 / 倾斜 / 碰撞" --> IMU

    LOOP --> STATE
    STATE --> DB
    STATE --> LLM
    STATE --> AUDIO
    STATE --> BODY_BRIDGE
    STATE --> SCREEN_DRV

    AUDIO --> SPK
    SCREEN_DRV --> SCR
    BODY_BRIDGE -- "motion intent / body mode" --> SERIAL
    SERIAL --> LINE_GATE
    I2C --> MUX
    ADC --> TCRT_L & TCRT_C & TCRT_R
    SPI --> IMU
    MUX --> TFL & TFR & TL & TR
    TCRT_L & TCRT_C & TCRT_R --> LINE_GATE
    TFL & TFR & TL & TR --> TOF_GATE
    LINE_GATE --> TOF_GATE
    TOF_GATE --> PWM
    PWM --> DRIVER
    DRIVER --> M1 & M2 & M3 & M4
    LINE_GATE -- "line / track telemetry" --> BODY_BRIDGE
    TOF_GATE -- "distance / safety telemetry" --> BODY_BRIDGE
    IMU -- "orientation / gyro / accel telemetry" --> BODY_BRIDGE
```

### 2.2 三个运行层

| 层次 | 硬件 / 模块 | 职责 |
|---|---|---|
| 意图与表达层 | Mac mini / Stranger runtime | 状态、记忆、策略、表达、声音、小屏幕状态、运动意图 |
| 本地身体控制层 | ESP32-S3 | ToF 轮询、TCRT 轨道读取、BNO085 telemetry、本地循迹 / 避障 gate、最终电机 PWM + DIR 输出 |
| 物理层 | TCRT5000、VL53L1X、TCA9548A、BNO085、电机驱动、36JP555 | 轨道感知、距离感知、姿态观测与低速移动 |

核心边界：Mac mini 可以提出移动意图，但 ESP32-S3 必须在输出电机前应用本地 TCRT 轨道约束和 ToF 避障限制。

---

## 三、硬件层详解

### 3.1 Mac mini 上位机

Mac mini 是 Stranger 的“主要计算身体部件”，随移动身体一起移动。

职责：

- 运行当前 Python Stranger 系统
- 维护状态、记忆、策略、表达和 runtime trace
- 运行开发者 API 与运营者 dashboard
- 生成声音并直接通过小音响播放
- 驱动或服务小屏幕身体表面
- 通过 USB Serial 与 ESP32-S3 交换运动命令和传感器遥测

不再承担旧方案中的外置固定上位机角色；它属于身体内部。

### 3.2 ESP32-S3 下位控制器

ESP32-S3 是唯一的下位身体控制器。

职责：

```text
ESP32-S3
├── USB Serial
│   ├── 接收 Mac mini 的 motion intent / wheel command
│   └── 上报 TCRT 轨道、ToF 距离、避障状态和电机输出摘要
├── I2C
│   └── 控制 TCA9548A，轮询 4 个 VL53L1X
├── ADC
│   └── 读取 3 个 TCRT5000 A0 模拟量，估算单黑线位置
├── Line-following gate
│   ├── track_follow
│   ├── line_lost
│   └── reacquire
├── ToF obstacle gate
│   ├── hard stop
│   ├── slow zone
│   └── turn bias / movement clipping
└── Motor output
    └── 4 路 PWM + DIR → 电机驱动板
```

ESP32-S3 不运行：

- LLM
- 记忆系统
- 策略选择
- 表达生成
- 宪法约束
- 访客身份识别
- 屏幕上的观众表达文案

### 3.3 传感器与执行器一览

| 设备 | 型号 | 数量 | 职责 | 接口 |
|---|---|---:|---|---|
| 上位机 | Mac mini | 1 | 主运行时、声音、小屏幕、通信桥 | USB Serial / Audio / Display |
| 下位机 | ESP32-S3 | 1 | 本地循迹、避障与电机控制 | USB / I2C / ADC / GPIO PWM |
| I2C 扩展 | TCA9548A | 1 | 隔离同地址 ToF 通道 | I2C |
| 距离传感器 | VL53L1X | 4 | 前方与侧向近场距离 | I2C via TCA9548A |
| 循迹传感器 | TCRT5000 | 3 | 单黑线轨道反射强度 | ADC via `A0` |
| 电机驱动 | Fierce 四路有刷驱动 Ver2.3 | 1 | 四路全桥驱动 | PWM + DIR |
| 驱动电机 | 36JP555 | 4 | 低速开环移动 | Driver output |
| 声音输出 | 小音响 | 1 | Stranger 语音输出 | Mac mini audio |
| 显示输出 | 小屏幕 | 1 | 身体状态表面 | Mac mini display / local rendering |

### 3.4 当前接线总表

具体引脚以 `docs/references/hardware.md` 的完整接线方案为准。本节只记录系统逻辑层需要稳定引用的 wiring map。

#### Mac mini 连接

| Mac mini | 连接对象 | 用途 |
|---|---|---|
| USB | ESP32-S3 USB | 下位机烧录、USB Serial 命令和 telemetry |
| Audio / USB audio | 小音响 | Stranger 语音输出 |
| HDMI / USB-C display | 小屏幕 | 身体状态表面 |
| Power | Mac mini 电源方案 | 上位机供电 |

#### ESP32-S3 推荐 pin map

这些 GPIO 是当前推荐分配，接线前必须按实际 ESP32-S3 开发板丝印和板卡文档复核。

| 功能 | 推荐 GPIO | 连接对象 |
|---|---:|---|
| I2C SDA | GPIO8 | TCA9548A `SDA` |
| I2C SCL | GPIO9 | TCA9548A `SCL` |
| M1 PWM | GPIO4 | 电机驱动 `P1` |
| M1 DIR | GPIO10 | 电机驱动 `D1` |
| M2 PWM | GPIO5 | 电机驱动 `P2` |
| M2 DIR | GPIO11 | 电机驱动 `D2` |
| M3 PWM | GPIO6 | 电机驱动 `P3` |
| M3 DIR | GPIO12 | 电机驱动 `D3` |
| M4 PWM | GPIO7 | 电机驱动 `P4` |
| M4 DIR | GPIO13 | 电机驱动 `D4` |
| TCRT line_left A0 | GPIO1 / ADC1 | 左循迹 TCRT5000 `A0` |
| TCRT line_center A0 | GPIO2 / ADC1 | 中循迹 TCRT5000 `A0` |
| TCRT line_right A0 | GPIO14 / ADC2 | 右循迹 TCRT5000 `A0` |
| BNO085 SPI SCK | GPIO15 | BNO085 `SCL` |
| BNO085 SPI MISO | GPIO16 | BNO085 `SDA` |
| BNO085 SPI MOSI | GPIO17 | BNO085 `DI` |
| BNO085 SPI CS | GPIO18 | BNO085 `CS` |
| BNO085 INT | GPIO21 | BNO085 `INT` |
| BNO085 RST | GPIO47 | BNO085 `RST` |

#### BNO085 IMU SPI 接线

该接线已进入当前 bring-up 阶段。BNO085 第一版只作为可观测 IMU telemetry：固件初始化 SPI、读取 yaw / pitch / roll、quaternion、gyro、accel 并上报 Dashboard。它暂时不设置倾斜 / 撞击阈值，不自动停机，不拦截键盘 / 手柄 / roam。BNO085 不应挂在 TCA9548A 下游，避免 IMU 通信影响 ToF 安全总线。

| BNO085 引脚 | ESP32-S3 / 电源 | 用途 |
|---|---|---|
| `VIN` | `3V3` | IMU 逻辑供电 |
| `GND` | `GND` | 逻辑共地 |
| `P0` / `PS0` | `3V3` | 选择 SPI 模式 |
| `P1` / `PS1` | `3V3` | 选择 SPI 模式 |
| `SCL` | GPIO15 | SPI `SCK` |
| `SDA` | GPIO16 | SPI `MISO`，BNO085 到 ESP32-S3 |
| `DI` | GPIO17 | SPI `MOSI`，ESP32-S3 到 BNO085 |
| `CS` | GPIO18 | SPI chip select |
| `INT` | GPIO21 | data-ready interrupt，SPI 稳定工作需要接入 |
| `RST` | GPIO47 | IMU reset，SPI 恢复需要接入 |

BNO085 当前职责：

- 观察 yaw / pitch / roll、gyro、accel 在正常行驶、转向、搬起、碰撞时的范围
- 暴露 `ok` / `not_found` / `report_error` / `no_update` / `stale` 等 IMU 状态
- 为后续阈值和安全策略提供现场数据

BNO085 后续可承担的职责：

- 短时间 yaw 转向确认、heading hold、角速度限制、倾斜 / 搬起 / 碰撞检测
- 不用于真实里程、全局定位、SLAM 或路径复现
- 不替代编码器；若后续需要稳定里程和轮速闭环，仍需轮端编码器

#### TCA9548A 与 ToF 通道

| TCA9548A channel | VL53L1X sensor | 位置 |
|---:|---|---|
| 0 | `front_left` | 前左 |
| 1 | `front_right` | 前右 |
| 2 | `left` | 左侧 |
| 3 | `right` | 右侧 |

TCA9548A channel connector 与 VL53L1X module connector 的线序不同，必须交叉连接：

| TCA9548A channel pin | VL53L1X pin |
|---|---|
| `GND` | `GND` |
| `VCC` | `VIN` |
| `SCLn` | `SCL` |
| `SDAn` | `SDA` |

#### TCRT5000 单轨循迹

当前确定使用 **单黑胶带轨道 + 三个 TCRT5000** 的方案，替代此前讨论过的双轨 / 四角 D0 hard-stop 方案。

接线规范：

| 位置 | TCRT5000 引脚 | ESP32-S3 / 电源 | 用途 |
|---|---|---|---|
| `line_left` | `VCC` | `3V3` sensor bus | 左循迹传感器供电 |
| `line_left` | `GND` | `GND` bus | 共地 |
| `line_left` | `A0` | GPIO1 / ADC1 | 左侧模拟反射值 |
| `line_left` | `D0` | 不接 | 第一版不使用数字阈值输出 |
| `line_center` | `VCC` | `3V3` sensor bus | 中循迹传感器供电 |
| `line_center` | `GND` | `GND` bus | 共地 |
| `line_center` | `A0` | GPIO2 / ADC1 | 中间模拟反射值 |
| `line_center` | `D0` | 不接 | 第一版不使用数字阈值输出 |
| `line_right` | `VCC` | `3V3` sensor bus | 右循迹传感器供电 |
| `line_right` | `GND` | `GND` bus | 共地 |
| `line_right` | `A0` | GPIO14 / ADC2 | 右侧模拟反射值 |
| `line_right` | `D0` | 不接 | 第一版不使用数字阈值输出 |

安装规范：

```text
车头前进方向 ↑

line_left      line_center      line_right
                    |
                单黑胶带轨道
```

- 三个 TCRT5000 安装在车头下方同一横向线上。
- 中间传感器在正常循迹时对准黑胶带；左右传感器用于判断线偏向哪一侧。
- TCRT5000 应贴近地面，建议从 5-10 mm 量级开始测试；4-5 cm 不适合作为可靠循迹高度。
- 展场灯光、投影或反光地面干扰明显时，应加黑色消光遮光罩，但不能刮地或遮挡发射 / 接收管。

控制语义：

- TCRT5000 是展场运动的主轨道参考。
- ToF 不替代循迹，只负责人、家具、展台边缘等临时 / 近场障碍。
- IMU 可辅助 yaw 回正和脱轨后的粗略扫线，但只有 TCRT 重新读到轨道才算回轨成功。

#### 电机驱动控制侧

| 电机 | 驱动板控制脚 | ESP32-S3 推荐 GPIO | 逻辑 |
|---|---|---:|---|
| M1 | `P1` | GPIO4 | PWM 调速 |
| M1 | `D1` | GPIO10 | 方向 |
| M2 | `P2` | GPIO5 | PWM 调速 |
| M2 | `D2` | GPIO11 | 方向 |
| M3 | `P3` | GPIO6 | PWM 调速 |
| M3 | `D3` | GPIO12 | 方向 |
| M4 | `P4` | GPIO7 | PWM 调速 |
| M4 | `D4` | GPIO13 | 方向 |
| signal `+V` | - | ESP32-S3 `3V3` | 隔离信号侧供电 |
| signal `-V` | - | ESP32-S3 `GND` | 隔离信号侧地 |

电机驱动逻辑：

| P | D | 状态 |
|---|---|---|
| PWM | 0 | 正转 |
| PWM | 1 | 反转 |
| 0 | 0 或 1 | 制动 / 停止 |

#### 电机与供电

| 连接 | 说明 |
|---|---|
| 驱动板 M1-M4 输出 | 分别接 4 个 36JP555 电机 |
| 驱动板 motor bus positive / negative | 接独立电机电源或电池 |
| ESP32-S3 USB / 3V3 | 只供下位机逻辑、TCA9548A、VL53L1X 和驱动板信号侧 |
| Mac mini / 小屏幕 / 小音响 | 使用 Mac mini 侧显示、音频和电源路径 |

不要用 ESP32-S3 USB 给电机供电；不要把 motor bus positive 接到 ESP32-S3。

---

## 四、软件层详解

### 4.1 当前已存在的软件主链路

当前代码中已经存在并应继续作为核心的层：

```text
输入 / 事件
  -> Perception
  -> State
  -> Memory
  -> Policy
  -> Prompt / Expression
  -> Constitution filter
  -> ExpressionOutput
  -> Audio / visitor surface / developer dashboard
```

现有能力包括：

- Stranger 文本协议
- 状态机
- 短期 / 情节 / 反思记忆
- managed memory proposal / influence log
- Runtime Harness Trace
- 可选 Vision presence 第一版
- 可选 Audio Adapter
- Visitor Identity & Session Gating V1

### 4.2 身体桥层

硬件接入使用一个薄的 body bridge，而不是把硬件逻辑塞入 expression、policy 或 API 入口。当前第一版已经接入 Dashboard 手动 teleop 和 ESP32 telemetry 读取；艺术行为到运动意图的自动映射仍留到后续阶段。

当前职责：

| 模块 | 职责 |
|---|---|
| `body/protocol.py` | 将 Dashboard allowlist command / teleop intent 转成 ESP32 当前文本命令 |
| `body/serial_bridge.py` | USB Serial connect/disconnect、读 ESP32 JSON line、写命令、将 telemetry 推入缓存 |
| `body/telemetry.py` | 缓存 ToF、BNO085 IMU、obstacle、motion、motor state、ack/error，供 Hardware 面板显示 |

后续可新增：

| 模块 | 职责 |
|---|---|
| `body/command_mapper.py` | 将 runtime 状态 / 表达输出映射为运动意图和屏幕模式 |
| `body/tof_events.py` | 将 ESP32 ToF telemetry 转为可记录的近场状态或 perception hint |

当前 Dashboard teleop 是开发者手动测试通道，不进入 LLM、memory、policy 或 ExpressionOutput。

### 4.3 软件模块全景

```mermaid
graph LR
    subgraph INPUT ["输入层"]
        TEXT["Text / API input"]
        AUDIO_IN["Audio transcript"]
        VISION["Vision presence"]
        TOF_TEL["ToF telemetry"]
    end

    subgraph CORE ["Stranger 核心运行时"]
        PER["Perception"]
        ST["StateEngine"]
        MEM["Memory"]
        POL["PolicySelector"]
        CTX["ContextBuilder"]
        EXP["ExpressionEngine"]
        CON["Constitution"]
        HAR["HarnessTrace"]
    end

    subgraph OUTPUT ["输出与身体映射"]
        EXPO["ExpressionOutput"]
        AUD["Mac mini audio output"]
        SCRMODE["Screen body mode"]
        MOTION["Motion intent（后续自动映射）"]
        DEVTELEOP["Dashboard teleop"]
    end

    subgraph BODY ["下位身体控制"]
        BRIDGE["USB Serial BodyBridge"]
        GATE["ESP32 ToF obstacle gate"]
        MOTOR["PWM + DIR motor output"]
    end

    TEXT --> PER
    AUDIO_IN --> PER
    VISION --> PER
    TOF_TEL --> PER
    PER --> ST --> MEM --> POL --> CTX --> EXP --> CON --> EXPO
    ST --> HAR
    POL --> HAR
    EXP --> HAR
    EXPO --> AUD
    EXPO --> SCRMODE
    ST -. "后续" .-> MOTION
    POL -. "后续" .-> MOTION
    DEVTELEOP --> BRIDGE
    MOTION --> BRIDGE --> GATE --> MOTOR
    GATE --> TOF_TEL
```

---

## 五、核心数据流

### 5.1 TCRT 单轨循迹闭环

```mermaid
flowchart TD
    A["ESP32 读取 TCRT5000 line_left / line_center / line_right A0"] --> B["归一化黑线反射强度"]
    B --> C["估算 line position / track state"]
    C --> D{"是否仍在轨道附近"}
    D -- "是" --> E["输出低速循迹修正"]
    D -- "否" --> F["停止前进或进入低速 reacquire"]
    E --> G["通过 Serial 上报 line telemetry"]
    F --> G
```

第一版循迹使用成熟 line follower 方案：先用 `line calibrate floor` / `line calibrate tape` 建立每个 TCRT 的白地 / 黑线范围，再把三路 `A0` 转换成黑线置信度。位置权重固定为 `left=0`、`center=1000`、`right=2000`，`line_error = position - 1000`。`line_error < 0` 表示黑线在车身左侧，应向左修正；`line_error > 0` 表示黑线在车身右侧，应向右修正。若实测底盘转向方向与该坐标相反，只允许改方向反转参数，不改循迹算法。

第一版循迹状态：

| 状态 | 条件 | 下位行为 |
|---|---|---|
| `track_follow` | `010` 或中间读数占优，line error 在中心死区内 | 低速前进 + PD 差速修正 |
| `bias_left` | `100` / `110` 或 position 小于中心 | 限速并向左修正，让中心传感器重新压线 |
| `bias_right` | `001` / `011` 或 position 大于中心 | 限速并向右修正，让中心传感器重新压线 |
| `line_lost` | `000`，三路都没有稳定看到黑线 | 停止前进，记录最后有效 error |
| `reacquire` | 丢线后允许找回 | 低速按最后 error 方向扫线；IMU 只辅助 yaw 搜索幅度，TCRT 确认后才算回轨 |
| `noise` | `101`，左右看到线但中心没看到 | 减速并沿上一帧方向判断；连续出现则停机 |
| `wide` | `111`，黑区过宽或特殊标记 | 减速 / 停机，不当作正常循迹 |

运动 gate 顺序：

1. `motor/test/test all` 是排线工具，只需要 `arm`，不走 TCRT / ToF gate。
2. `drive/spin/roam` 先经过 TCRT line gate，再经过 ToF obstacle gate。
3. ToF `obstacle_stop` / `sensor_fault` 优先级高于 TCRT 找线；近场硬停时禁止继续找线动作。
4. `line off` 只用于人工调试，重启后默认恢复 line gate 开启。

### 5.2 ToF 避障闭环

```mermaid
flowchart TD
    A["ESP32 定时选择 TCA9548A 通道"] --> B["读取 VL53L1X front_left / front_right / left / right"]
    B --> C["生成本地距离快照"]
    C --> D{"是否进入 hard stop"}
    D -- "是" --> E["最终 PWM = 0，进入 obstacle_stop"]
    D -- "否" --> F{"是否进入 slow zone"}
    F -- "是" --> G["限制前进速度，保留低速避让"]
    F -- "否" --> H["允许低速开环移动"]
    E --> I["通过 Serial 上报 safety telemetry"]
    G --> I
    H --> I
```

初始建议阈值：

| 区域 | 距离 | 下位行为 |
|---|---:|---|
| hard stop | `< 250 mm` | 停止 / 制动 |
| slow zone | `250-600 mm` | 限制前进速度 |
| clear | `> 600 mm` | 允许低速移动 |

这些阈值是现场调参起点，不是艺术行为规则。

### 5.3 运动命令流

```mermaid
flowchart TD
    A["ExpressionOutput.body_action + current EntityState"] --> B["Runtime Motion selector"]
    B --> C["Motion profile from config/body_motion_profiles.yaml"]
    C --> D["BodyMotionExecutor short step sequence"]
    D --> E["BodyBridge USB Serial"]
    E --> F["ESP32 drive / expressive command"]
    F --> G["TCRT line gate + ToF obstacle gate"]
    G --> H["PWM + DIR output"]
    H --> I["Post-action line verify / reacquire"]
```

关键原则：

- Dashboard 手动 teleop 仍是开发者测试通道；Runtime Motion 是 Stranger 说话交互后的自动身体表达通道
- Runtime Motion 默认关闭；关闭时只记录 motion decision，不驱动电机
- Runtime Motion 只接收高层 intent，不接收 LLM raw motor command
- ESP32-S3 决定“当前能不能这样动”
- TCRT line gate 和 ToF gate 必须在电机输出前执行
- `allow_transient_line_loss` 只适用于原地转开 / 扭动等艺术动作，允许动作过程中短暂扫不到线，但动作后必须 verify line 或进入 reacquire
- 当前不把 PWM 时间当成真实里程
- 串口同一时刻只允许一个 owner；使用 Dashboard BodyBridge 时不要同时打开 PlatformIO Monitor

### 5.4 语音输出流

```mermaid
flowchart TD
    A["ExpressionOutput / spoken_text"] --> B["现有音频路径或 Mac mini TTS 输出"]
    B --> C["Mac mini audio output"]
    C --> D["小音响播放"]
```

边界：

- 不再通过 ESP32 / PCM5102A 播放声音
- 声音仍必须来自合法的 Stranger expression path
- raw text TTS 只能作为 debug preview，不能作为 Stranger 正式发声后门

### 5.5 小屏幕身体表面流

```mermaid
flowchart TD
    A["EntityState / PolicyDecision / ExpressionOutput"] --> B["screen body mode mapper"]
    B --> C["小屏幕显示模式"]
    C --> D["访客看到身体状态"]
```

小屏幕适合表达：

- 沉默
- 注意
- 退避
- 干扰
- 漂移
- 近场警觉
- 说话 / 聆听边界

小屏幕不应显示：

- raw state vector
- policy rule id
- hidden prompt
- memory table
- operator log

---

## 六、通信协议草案

### 6.1 连接方式

当前第一阶段：

```text
Mac mini -- USB Serial --> ESP32-S3
```

不优先使用 WiFi，因为 Mac mini 已经随身体移动，USB 更稳定、延迟更低、调试更直接。

### 6.2 下行消息（Mac mini → ESP32-S3）

运动命令：

```json
{
  "type": "drive",
  "m1": 20,
  "m2": 20,
  "m3": 20,
  "m4": 20,
  "duration_ms": 300
}
```

身体模式：

```json
{
  "type": "body_mode",
  "screen_mode": "silent",
  "intensity": 0.4
}
```

停车命令：

```json
{
  "type": "stop",
  "reason": "runtime_pause"
}
```

### 6.3 上行消息（ESP32-S3 → Mac mini）

距离遥测：

```json
{
  "type": "tof",
  "front_left_mm": 430,
  "front_right_mm": 380,
  "left_mm": 900,
  "right_mm": 760
}
```

本地避障状态：

```json
{
  "type": "safety",
  "state": "obstacle_stop",
  "reason": "front_left_hard_stop"
}
```

电机输出摘要：

```json
{
  "type": "motor_output",
  "m1": 0,
  "m2": 0,
  "m3": 0,
  "m4": 0,
  "clipped": true
}
```

协议在代码实现前可以继续精简。第一目标是稳定调试 TCRT 循迹、ToF 和电机，不是一次设计完整远程控制协议。

---

## 七、状态与行为边界

### 7.1 当前运动能力描述

当前硬件阶段只能描述为：

- 低速开环移动
- 单黑线轨道附近的低速循迹 / 微行为
- ToF 近场避障
- IMU 姿态观测
- 允许轻微漂移

不能描述为：

- 精确定位
- 精确路径复现
- 无轨道的稳定巡路
- 完整自主导航
- 有地图的空间理解

这会影响后续能力自我描述测试：Stranger 不应声称自己能精确知道走了多远或在空间中的绝对位置。

### 7.2 硬件安全与艺术行为的边界

TCRT line tracking、line lost stop / reacquire、ToF hard stop、slow zone、PWM clipping 属于下位机安全逻辑，可以直接在 ESP32-S3 本地执行。

身份张力、沉默、拒绝服务、记忆牵引、观察反转等仍属于上位机 Stranger 行为系统，不应写死进 ESP32 固件。

---

## 八、实施阶段

```mermaid
gantt
    title "当前硬件实施阶段"
    dateFormat X
    axisFormat "Phase %s"

    section Phase 1
    "ESP32-S3 + TCA9548A 接线验证" :p1, 0, 1
    "4 个 VL53L1X 轮询与 Serial telemetry" :p1b, 0, 1
    "3 个 TCRT5000 A0 读取与校准" :p1c, 0, 1

    section Phase 2
    "TCRT 单轨循迹 gate" :p2, 1, 2
    "ToF hard stop / slow zone gate" :p2b, 1, 2
    "黑线 / 距离阈值现场调试" :p2c, 1, 2

    section Phase 3
    "四路电机驱动单通道验证" :p3, 2, 3
    "四轮低速开环移动" :p3b, 2, 3

    section Phase 4
    "Mac mini BodyBridge 接入" :p4, 3, 4
    "runtime motion intent -> ESP32 gate -> motor output" :p4b, 3, 4

    section Phase 5
    "小音响与小屏幕身体表面接入" :p5, 4, 5
    "声音 / 屏幕 / 移动联调" :p5b, 4, 5
```

后续可选阶段：

- 若转向角度和脱轨恢复需要更稳定，再把 BNO085 telemetry 接入 heading / turn control
- 若需要稳定巡路、直线修正或里程估计，再加入编码器

---

## 九、最终定义

```text
Mac mini = Stranger 的主运行身体部件：记忆、语言、声音、屏幕状态、高层意图
ESP32-S3 = 下位身体控制器：TCRT 循迹、ToF 读取、本地运动 gate、电机输出
TCRT5000 x3 = 单黑线轨道感知
VL53L1X array = 近场障碍感知
四路有刷电机驱动 + 36JP555 = 低速开环移动
小音响 = Stranger 声音出口
小屏幕 = Stranger 身体状态表面
```

当前系统目标不是构建服务机器人导航系统，而是在可控、低速、单轨道约束的展览环境中，让 Stranger 获得一个能够沿轨道移动、避让、发声和呈现状态的身体。
