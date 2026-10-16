# SO101 机器人资源与硬件工具

## 来源与版本选择

直接来源：[TheRobotStudio/SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100)，目录 [Simulation/SO101](https://github.com/TheRobotStudio/SO-ARM100/tree/main/Simulation/SO101)。本目录没有使用 MuJoCo Menagerie 文件。

选用 [so101_new_calib.xml](https://github.com/TheRobotStudio/SO-ARM100/blob/main/Simulation/SO101/so101_new_calib.xml)：上游 [README](https://github.com/TheRobotStudio/SO-ARM100/blob/main/Simulation/SO101/README.md) 明确标注它为默认校准版本，默认 `scene.xml` 也引用它。当前需求是从臂本体，后续先使用场景固定相机，因此不引入腕部相机实体版本。该选择依据上游说明和 XML，并不表示已经确认真实主臂的校准与模型一致。

| 上游文件 | 对象与差异 | 外部资源 |
| --- | --- | --- |
| `so101_new_calib.xml` | 从臂；上游将新校准描述为关节范围中部虚拟零点，实际限位以 XML 为准 | 13 个 STL，无 include |
| `so101_old_calib.xml` | 从臂；水平完全伸展姿态为虚拟零点；连杆变换、部分限位及执行器增益也不同，不只是改文件名 | 同一组 13 个 STL，无 include |
| `so101_new_calib_camera.xml` | 新校准从臂，增加腕部相机支架和相机实体及其惯性；没有渲染用的 `<camera>` | 上述 13 个 STL，加 `wrist_camera_mount_so101_v1.stl`、`wrist_camera_so101_v1.stl`，无 include |
| `scene.xml` | 示例场景，不是另一套机器人；包括地面、灯光和程序生成纹理 | include `so101_new_calib.xml` |
| `joints_properties.xml` | 默认参数片段，不是独立机器人；其参数与新模型内联参数不同 | 本次模型不引用它，不下载或套用 |

主臂只有 `so101_leader_new_calib.urdf`，当前没有对应 MJCF。它使用手柄和扳机替代从臂夹爪；上游明确指出扳机零点、暂定行程和打印件惯性未经过实物测量。本轮不下载 URDF 或进行转换。

## 许可证与文件布局

适用上游仓库的 [Apache-2.0 许可证](https://github.com/TheRobotStudio/SO-ARM100/blob/main/LICENSE)，原文保存在 `model/LICENSE`。本次检查的仓库根目录、Simulation、SO101 和 assets 目录未发现另附 NOTICE 或子目录许可证。保留 XML 原有生成器、Onshape CAD 来源和执行器参数出处注释；后续分发时保留许可证和相关声明。

上游模型由 onshape-to-robot 从 CAD 生成；上游说明已移除底座碰撞网格。电机属性说明引用 [Open Duck Mini](https://github.com/apirrone/Open_Duck_Mini)，当前 XML 的位置增益注释另引用 [RBE501-RL-arm-project](https://github.com/Gregory119/RBE501-RL-arm-project/blob/main/gymnasium_env/README.md)。这些参数不是实际舵机固件增益的一对一映射。

```text
robots/so101/
  README.md
  scripts/
    teleoperate.py         # 交互软件对齐与只读主臂遥操作仿真
    check_connection.py    # 只读检查指定舵机 ID
    calibrate.py           # 现场交互确认的主臂校准
  model/
    LICENSE
    so101_new_calib.xml
    assets/                 # XML 实际引用的 13 个 STL，保留原文件名
```

本次没有路径调整，也没有修改 XML、网格、关节、惯性、碰撞、摩擦或执行器参数。`meshdir="assets"` 直接引用本地相对目录；材料均内联，无外部纹理、include 或其他加载依赖。未复制上游示例场景、其他校准版本、URDF、打印源文件或媒体。

## 关节与执行器约定

下表按 XML 关节遍历顺序排列，也是本次加载得到的关节和执行器顺序。全部关节为 `hinge`，轴为各自所属 body 的局部 `(0, 0, 1)`，正向遵循该轴的右手规则；不是六个相同的世界坐标轴。`compiler angle="radian"`，关节位置和位置目标均以弧度表示，包括夹爪。

执行器均为 `<position>`，名称及绑定关节与表中关节同名，一对一驱动。关节限位按 XML 原始精度记录，控制范围保留上游的舍入值，两者不应混同。

| 顺序 | 关节 / 执行器名称 | 关节限位（rad） | 控制范围（rad） |
| --- | --- | --- | --- |
| 0 | `shoulder_pan` | `-1.9198621771937616 1.9198621771937634` | `-1.91986 1.91986` |
| 1 | `shoulder_lift` | `-1.7453292519943224 1.7453292519943366` | `-1.74533 1.74533` |
| 2 | `elbow_flex` | `-1.69 1.69` | `-1.69 1.69` |
| 3 | `wrist_flex` | `-1.6580628494556928 1.6580627293335335` | `-1.65806 1.65806` |
| 4 | `wrist_roll` | `-2.7438472969992493 2.841206309382605` | `-2.74385 2.84121` |
| 5 | `gripper` | `-0.17453297762778586 1.7453291995659765` | `-0.17453 1.74533` |

- 五个机械臂转动关节加一个夹爪转动关节，共六个自由度。夹爪是一侧固定指体与一侧活动爪，`gripper` 执行器直接驱动活动爪铰链；没有 tendon 或 equality 联动。XML 中虽定义 backlash 默认类，但没有使用该类的额外关节。
- 六个执行器继承 `kp=998.22`、`kv=2.731`；每个执行器显式设置 `forcerange="-3.35 3.35"`，覆盖默认力范围。关节继承 `damping=0.60`、`frictionloss=0.052`、`armature=0.028`，本轮原样保留。
- `base` 直接挂在 worldbody 下，没有自由关节，底座固定；模型包含连杆惯性与碰撞网格，但没有底座碰撞几何。
- 模型不自带渲染相机、桌面、物体或任务场景。本轮没有创建环境、控制器封装或 GUI 入口。
- 上游所谓新校准是模型坐标约定，不是实物校准结果；例如腕转与夹爪范围并非严格以零对称，肘关节还有上游的偏移说明，必须保留实际 XML 数值。真实主臂的方向、零点、单位、限位和夹爪映射仍待实物确认。
- 上游说明 LeRobot 的夹爪 0～100 开合表示尚未反映在此模型中，不能将其直接当作这里的弧度目标，也不能用仿真限位替代设备校准。

## 本次最小检查

上游上述说明没有指定 MuJoCo 最低版本。使用现有虚拟环境 MuJoCo 3.3.2 加载成功：`nq=6`、`nv=6`、`nu=6`、`nmesh=13`、`ncam=0`，没有缺失资源。一次 `mj_forward` 后，位置、速度、加速度、连杆变换、质量矩阵、驱动力及约束结果均为有限数值，MuJoCo 警告计数全为零。

XML 未显式设置物理时间步；此次加载得到 MuJoCo 默认值 0.002 秒，未改写模型。这只是加载与前向计算检查，不代表已经验证动态稳定性、接触、关节控制、实物一致性或图形显示；本轮未执行 `mj_step` 或渲染。

## 主臂只读连接检查

从项目根目录使用项目虚拟环境运行：

```bash
.venv/bin/python robots/so101/scripts/check_connection.py --help
.venv/bin/python robots/so101/scripts/check_connection.py --port /dev/ttyACM0
# 只检查显式指定的 ID，波特率由调用方指定，不自动扫描。
.venv/bin/python robots/so101/scripts/check_connection.py --port /dev/ttyACM0 --baudrate 1000000 --ids 1 2 3
```

入口使用 pyserial 3.5、feetech-servo-sdk 1.0.0，不导入完整 LeRobot。默认值依据同级 LeRobot 的 `src/lerobot/teleoperators/so_leader/so_leader.py`、`src/lerobot/motors/feetech/feetech.py` 和 `tables.py`：SO101 配置使用 STS3215、1000000 波特率、ID 1～6；SDK `PacketHandler(0)` 选择 STS/SMS 的小端字序。这些参考文件仅用于核对，脚本运行时不依赖同级仓库。

| 读取内容 | 寄存器地址 | 字节数 |
| --- | --- | --- |
| 型号编号 | 3 | 2 |
| ID | 5 | 1 |
| Torque_Enable | 40 | 1 |
| Present_Position | 56 | 2 |

仅发送 PING 和 READ。SDK 自带 `ping()` 会附带型号读取并覆盖通信结果，因此入口通过 SDK 的 `txRxPacket` 单独发送 PING，再逐项读取，明确区分 ping 无响应、其他通信错误和 ping 成功但寄存器读取失败。每次响应等待限制为 100 ms，使用单调时钟；串口发送也设置有限超时。每个指定 ID 仅检查一次，不重试、不扫描其他波特率，无响应后继续下一指定 ID。完整读取成功时退出码为 0，否则为 1；原始通信错误文本、状态错误位均保留输出。

所有型号仅输出原始编号；位置显示未经符号解码或校准的两字节原始字，可能含符号位，不限定为 0～4095，也不转换角度。默认 ID 顺序不能证明实际关节对应关系，仍需后续手动逐关节确认。

配置主机串口波特率不是修改舵机 Baud_Rate 寄存器。入口不调用 LeRobot 高级连接初始化，不写 ID、模式、零点、限位、扭矩或目标位置；读到扭矩已开启也只报告。结束及异常时通过 finally 关闭已打开的串口，硬件读数只打印到终端，不保存到仓库。

本节工具只执行连接检查，不执行运动或校准。主臂校准使用下面的独立交互入口；端口发现仍未实现；实物到仿真映射和遥操作见下方专节，需要现场对齐和验收。

## 主臂交互式校准

只针对用户已确认的主臂 ID：1 shoulder_pan、2 shoulder_lift、3 elbow_flex、4 wrist_flex、5 wrist_roll、6 gripper。使用现有 pyserial 和 Feetech SDK，不安装或导入 LeRobot，不连接仿真。此次只做语法、帮助和纯函数检查，尚未替用户执行硬件校准。

参考的实际本地调用链（同级 `../lerobot/`）：

- `src/lerobot/scripts/lerobot_calibrate.py`：连接设备、调用校准、退出。
- `src/lerobot/teleoperators/so_leader/so_leader.py`：`SOLeader.calibrate`、参考姿态图、wrist_roll 特殊处理；SO101Leader 是该实现的别名。
- `src/lerobot/motors/motors_bus.py`：`reset_calibration`、`set_half_turn_homings`、`record_ranges_of_motion`、归一化。
- `src/lerobot/motors/feetech/feetech.py` 与 `tables.py`：偏置公式、寄存器地址、符号位、校准读写和配置步骤。
- `src/lerobot/motors/encoding_utils.py`、`src/lerobot/teleoperators/teleoperator.py`：符号幅值编码、JSON 保存与加载。

本项目将寄存器访问和纯函数放在 `src/my_act/hardware/so101/calibration.py`，交互流程放在 `robots/so101/scripts/calibrate.py`，正常包导入，无 sys.path 修改。改编的算法、示意图保留 Hugging Face Apache-2.0 声明，许可证原文在 `src/my_act/hardware/so101/LICENSE`；新增了备份、显式确认、范围有效性检查和受限写入。

### 现场运行

先阅读 [SO101 官方校准说明与视频](https://huggingface.co/docs/lerobot/main/en/so101#calibration-video)。本地 SOLeader 还提供主臂参考姿态示意，入口会原样打印；[官方视频](https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/lerobot/calibrate_so101_2.mp4) 来自同一文档。按图示摆到各关节行程中部，不能自行用仿真 qpos=0 或旧校准的水平伸展零位替代。

在 WSL 的交互终端执行下面一条完整命令。`leader01` 是给这条实物主臂指定的稳定名称示例，若改名，应同步修改文件目录，不能用于另一台设备。

```bash
cd /home/lzh/projects/my-act && .venv/bin/python robots/so101/scripts/calibrate.py --port /dev/ttyACM0 --baudrate 1000000 --device-name leader01 --calibration-file robots/so101/calibration/leader/leader01/calibration.json
```

`--calibration-file` 可指定该设备目录内的 JSON 路径；省略时使用上述默认结构。名称和路径区分 leader 角色及设备身份，不能与 follower 校准共用。路径、串口和设备名称不是自动发现的硬件身份，运行前须现场确认。

1. 若已有文件，输入 `reuse` 将旧文件偏置及限位写回舵机，或输入 `new` 重新采集；其他输入取消。复用也要经过备份和写入确认，不静默应用。
2. 只读核对六个 ID、型号编号 777，并读取所有可能修改的寄存器原始字。先在 `calibration/leader/<设备名>/backups/<时间戳>/` 保存 `registers_before.json`；已有文件原样备份为 `previous_calibration.json`，不覆盖旧备份。
3. 查看原值与写入计划。若发现任何扭矩非零，先托住臂体，再输入 `DISABLE` 明确允许关闭；随后输入 `WRITE` 才会执行准备写入。不会开启扭矩或发送运动目标。
4. 新校准时按官方图示摆参考姿态并保持不动，按回车清除旧偏置、恢复 0～4095 限位并读取当前位置。由 `当前位置 - 2047` 计算新偏置，显示后再输入 `WRITE` 写入。先清零并读回旧偏置，避免把旧偏置当成零或重复累加。
5. 按提示开始只读范围采样。逐个手动缓慢移动 shoulder_pan、shoulder_lift、elbow_flex、wrist_flex 和 gripper，覆盖完整安全行程；不要用力顶止挡。`wrist_roll` 不采范围，也不要求绕转一圈，沿用上游范围 0～4095。采样最多约 20 Hz，终端最多 1 Hz 覆盖刷新，按回车结束。
6. 范围必须在 0～4095 内且非退化；本工具另要求五个采集关节覆盖中心计数 2047 的两侧，以拒绝只采到半边的情况。若读数越界、发生跳变或范围不满足，不自动裁剪或修正。数值变化不证明完整行程，因此必须现场检查显示的范围，再输入 `SAVE` 确认写限位。
7. 每次写入检查 SDK 状态并立即读回；所有写入完成后恢复原 Lock 值、确认扭矩仍为 0，才保存新校准文件。重校准通过临时完整文件替换，旧文件已备份；复用不重写原校准文件。

### 寄存器变更与失败行为

| 寄存器 | 地址 / 字节 | 处理 |
| --- | --- | --- |
| Torque_Enable | 40 / 1 | 明确确认后设 0；绝不写 1，也不恢复此前开启状态 |
| Lock | 55 / 1 | 设 0 以写配置；流程成功后恢复各电机原值 |
| Operating_Mode | 33 / 1 | 沿用上游校准，设为位置模式 0；不发送位置目标 |
| Phase | 18 / 1 | 只在原 bit 4 为 1 时清除它，保留其他位，沿用上游 STS3215 角度反馈配置 |
| Homing_Offset | 31 / 2 | 新校准先清零再写参考姿态偏置；复用时直接写文件值 |
| Min_Position_Limit / Max_Position_Limit | 9 / 2、11 / 2 | 新校准先恢复 0/4095，采样完成后写范围；复用时写文件值 |

上游 `connect(calibrate=False)` 仍会调用 `configure()`，其中还会配置返回延迟、加速度等。本工具不调用该高级流程，也不带入这些无关写入；仅明确保留影响本次位置反馈的 Phase bit 4 处理。串口波特率只在主机设置，不写舵机 Baud_Rate，不改 ID。

通信等待每次最多 100 ms，不自动重试。取消、Ctrl+C、输入关闭、通信失败或无效范围均终止；finally 只关闭串口。开始写入后中断可能留下部分配置，**不会自动回滚、重试或恢复扭矩**，终端会报告原始错误和备份路径。原成功文件保持不变；它在失败后不一定仍与舵机内部配置相符，不能直接当作当前有效校准。应先根据备份与现场状态核对，不继续遥操作。

### 输出字段与单位

JSON 沿用 LeRobot 的关节名到五字段字典，不包含设备包装层，设备身份由角色目录、设备名称及备份元信息记录。

| 字段 | 含义 |
| --- | --- |
| id | 用户确认的舵机总线 ID |
| drive_mode | 本流程固定 0，LeRobot 归一化的方向标记；不是 Operating_Mode 寄存器 |
| homing_offset | 有符号偏置计数，Homing_Offset 的符号位为 bit 11 |
| range_min / range_max | 写入新偏置后采集的位置计数范围，wrist_roll 固定 0/4095 |

Present_Position 的符号位为 bit 15，是符号加幅值，不是普通 int16 补码；Homing_Offset 则用 bit 11。舵机返回位置已应用内部偏置，上游公式为 `Present_Position = Actual_Position - Homing_Offset`，后续不能再次减文件里的偏置。

本工具保存计数，不输出角度或归一化动作。LeRobot 默认对五个臂关节将范围内计数映射到 [-100,100]，夹爪映射到 [0,100]，范围模式会先限幅；可选 degrees 模式是按范围中点及 4095 分辨率换算。本轮不实现这些读数输出接口，更不把它们直接映射到 MuJoCo 弧度。实物方向、零点、夹爪与 `so101_new_calib.xml` 的对应关系留到下一轮。


## 校准后只读核验

沿用 `check_connection.py`，增加 `--calibration-file` 和 `--register-backup`。两项一起提供时，复用校准模块的寄存器定义、符号解码及关节 ID 检查，逐关节比较偏置和限位；不提供时保留普通连接检查。必须指定与本次校准对应的备份，不自动选择最近时间戳；有多份备份时先根据现场校准记录确认归属。设备目录、角色、设备名、串口、波特率和 ID 映射不符时，在打开串口前报错。

从项目根目录执行（将备份路径替换为本次校准的实际路径）：

```bash
.venv/bin/python robots/so101/scripts/check_connection.py --port /dev/ttyACM0 --baudrate 1000000 --calibration-file robots/so101/calibration/leader/leader01/calibration.json --register-backup robots/so101/calibration/leader/leader01/backups/<本次校准时间戳>/registers_before.json
```

每个 ID 仅 PING 一次，随后逐项读取 ID、型号编号、偏置、最小/最大限位、扭矩、工作模式、Phase、Lock 和当前位置，不重试。对照本项目校准流程，要求 Torque_Enable=0、Operating_Mode=0、Phase 为备份值清除 bit 4 后的结果（其余位保持）、Lock 恢复备份值；不把文件的 drive_mode 当作工作模式或扭矩状态。

表格区分读取失败、读取成功但值不一致、全部一致，并输出具体字段差异。位置同时显示原始字和按 bit 15 符号幅值规则解码后的计数；它已包含内部偏置，不重复补偿。当前位置无需等于参考姿态，暂时超出采集范围只单独提示，不计为校准写入失败，也不转换为仿真角度。

全部核验一致时退出码为 0，否则为 1。只读 PING/READ，不修复差异、不切换扭矩、不发送目标、不修改校准文件；finally 关闭串口。读数仅打印，不保存到受 Git 管理的文件。

## 主臂遥操作仿真

真实设备只读，仿真从臂接收绝对关节目标。硬件校准与软件映射分开：本工具不写任何舵机寄存器、不改变原 `calibration.json`，也不把模型限位当作实物校准值。通信复用 `calibration.py` 的寄存器、符号幅值解码及有限超时；不调用包含配置写入的 LeRobot `connect/configure`。

### 换算依据与尚待确认的部分

- [上游 new_calib 说明](https://github.com/TheRobotStudio/SO-ARM100/blob/main/Simulation/SO101/README.md) 将零位描述为行程中部；主臂 URDF 复用五轴约定，但手柄行程只是 CAD 估计，且上游明确未实现 LeRobot 夹爪 0～100 到 MJCF 的映射。XML 肘关节注释提到限位的 5° 偏移，不能据此给实物读数再加一个未经验证的 5°。
- 本地 `../lerobot/src/lerobot/teleoperators/so_leader/so_leader.py` 的 `get_action` 读取 Present_Position；`motors/motors_bus.py::_normalize` 默认将臂关节变为 [-100,100]、夹爪变为 [0,100]。这些是范围百分比，不是角度。其可选 degrees 模式使用范围中点和 `360/4095` 边界刻度；本项目不调用这两套归一化。
- 本地 `motors/feetech/tables.py::MODEL_RESOLUTION` 给 STS3215 4096 计数/圈。本工具采用物理编码器比例 `k = 2π/4096 ≈ 0.00153398 rad/count`（0.087890625°/count）。[飞特控制表](https://ftservo.github.io/ftservo-wiki/reference/parameter/memory-sts/) 定义位置反馈和 Phase bit 4。默认单圈反馈；比例不是采集范围到仿真限位的拉伸。
- 原始两字节位置先按 bit 15 符号幅值解码，得到计数 c。该计数已经受内部 Homing_Offset 影响，后续不再次减去偏置；约定 2047 是硬件校准参考计数，也不代表已自动精确匹配 MJCF 零位。

五轴统一公式：`q = q_ref + s × (c_continuous - c_ref) × k`。首次交互对齐显示模型零位，由用户记录对应主臂计数 `c_ref`；再观察仿真小幅正向运动，手动同向移动主臂，通过计数差确定 `s=+1/-1`。因此软件角度偏置是 `q_ref - s*c_ref*k`，来自现场参考姿态，不用采集范围中点猜测。

| 关节 | 比例 | 方向与角度偏置来源 |
| --- | --- | --- |
| shoulder_pan | 2π/4096 rad/count | 现场参考点 + 正向小幅确认 |
| shoulder_lift | 2π/4096 rad/count | 现场参考点 + 正向小幅确认 |
| elbow_flex | 2π/4096 rad/count | 同上，不额外猜加 5° |
| wrist_flex | 2π/4096 rad/count | 现场参考点 + 正向小幅确认 |
| wrist_roll | 2π/4096 rad/count | 同上，并连续处理单圈跨界 |

腕转首样本取相对参考点的最近单圈差，随后累积相邻样本的最短计数差，例如 4094→2 是 +4 计数。跨界不会跳一整圈，也不会把累积多圈运动重新绕回合法限位；最终仍受模型有限关节行程约束。启动参考有整圈歧义时，必须回到参考姿态，不支持无限旋转。

夹爪单独采用 `u=(c-c_closed)/(c_open-c_closed)`、`q=q_closed+u*(q_open-q_closed)`。两端计数由用户实际闭合/张开手柄时记录，允许读数方向相反；仿真开口候选为 0 和 0.7 rad，需要目视认可后才保存，不能声称它们是夹爪的机械极限。未确认时不能运行完整跟随，也不会自动生成一套方向全为 +1 的设备配置。

### 首次现场对齐

从 WSL 项目根目录运行，保持真实舵机扭矩关闭。若 shell 残留 OSMesa 的 PyOpenGL 配置，可在这次命令前用 `env -u PYOPENGL_PLATFORM`；无需改 shell 配置。

```bash
cd /home/lzh/projects/my-act
env -u PYOPENGL_PLATFORM MUJOCO_GL=glfw .venv/bin/python robots/so101/scripts/teleoperate.py \
  --align --device-name leader01 --port /dev/ttyACM0 --baudrate 1000000 \
  --calibration-file robots/so101/calibration/leader/leader01/calibration.json \
  --scene assets/scenes/so101_pick_place.xml \
  --mapping-config robots/so101/configs/mapping.yaml \
  --alignment-file robots/so101/configs/local/leader01.yaml
```

1. 逐轴按窗口零位匹配主臂相对连杆姿态，输入 `MATCH` 记录计数。底座朝向需对应，不能只按屏幕左右判断；必要时拖动视角，看不清就取消。
2. 该仿真关节缓慢增加 0.12 rad（约 6.9°）。观察局部正方向后，将实物同一关节小幅同向移动，再输入 `MATCH`。工具按计数变化确定方向，然后提示回到参考姿态。允许 10～300 计数的确认位移，不要求扫极限。
3. 分别查看夹爪候选闭合/张开姿态，手柄放到对应端点后 `MATCH`。若候选开口不合适，取消，明确修改通用配置中的候选角度后重新对齐；工具不会猜测端点。
4. 查看完整对齐内容，输入 `SAVE` 才生成本机 YAML 并退出。已有文件不会覆盖；重新对齐需显式使用另一个本机文件名。此次只写本机映射文件，不改硬件校准或任何寄存器。

本机 YAML 保存角色、设备名、串口、波特率、校准文件路径、各轴参考计数/参考 rad/方向，以及夹爪两端点。不要提交该文件。换设备、重新硬件校准、改变反馈方向或参考姿态后，需要重新现场对齐；文件路径不构成设备身份自动认证。`calibration.json` 不混入这些映射参数。

### 单关节与完整跟随

对齐完成后执行。未指定端口、波特率和校准路径时从本机文件读取；也可用命令行显式覆盖。

```bash
# 底座单关节，其余五个仿真关节保持明确初始目标。
env -u PYOPENGL_PLATFORM MUJOCO_GL=glfw .venv/bin/python robots/so101/scripts/teleoperate.py \
  --alignment-file robots/so101/configs/local/leader01.yaml --joint shoulder_pan

# 全部六轴跟随，不限制为固定时长；关闭窗口或 Ctrl+C 结束。
env -u PYOPENGL_PLATFORM MUJOCO_GL=glfw .venv/bin/python robots/so101/scripts/teleoperate.py \
  --alignment-file robots/so101/configs/local/leader01.yaml
```

按以下顺序逐次替换 `--joint`：① shoulder_pan 底座，② shoulder_lift 肩部，③ elbow_flex 肘部，④ wrist_flex 腕俯仰，⑤ wrist_roll 腕转，⑥ gripper 夹爪，最后去掉 `--joint` 做⑦全轴协同。每项小幅缓慢移动，检查方向、静止姿态与连续性；暂不扫机械极限、不尝试抓取。首次对齐不是最终验收，未经目视确认不能宣称主从完全一致。

启动先打印映射原目标与模型范围，等待 `START`。请在确认与启动过渡期间保持主臂不动；确认后仍读取新样本，不重放确认前的旧样本。初始目标沿用查看入口的五轴 0 rad、夹爪 0.7 rad；仅启动阶段以最多 0.5 rad/s 过渡，至少 3 秒，过渡超时未稳定则退出。正常阶段每次完整新样本直接映射，没有隐藏滤波。`--steps N` 可限制总控制周期数（包含启动过渡），默认运行到窗口关闭。

### 门限与失败处理

通用配置集中记录单位与初值：采集边界余量 32 计数（约 2.8°，包含此前肘部超出 8 计数）；仿真限位小幅容忍 0.08 rad（约 4.6°）；相邻有效跟随目标变化上限 0.25 rad/样本（约 14.3°）。这些是本次人工小幅演示的异常门限，不是硬件安全额定值，也不是经实验优化的滤波参数。

采集范围只用于位置异常检查，小幅超出不修改校准、不直接限幅计数；模型可执行范围取 joint range 与 actuator ctrlrange 的交集。原映射目标保留用于显示，小幅越界才裁剪；明显越界和跳变直接退出。单关节模式只对被跟随关节应用目标限位/跳变检查，其余 ctrl 保持初始值，但仍要求六个硬件读数完整、有限且没有明显超采集范围。每秒显示计数、原目标、当前 ctrl、实际 qpos 和裁剪状态，并合并该间隔内的短暂越界提示。

每次顺序读取六个舵机，不声称硬件同时采样；单次响应超时 100 ms，整批超过 0.2 秒拒收。失败不填零、不复用旧样本，不推进下一仿真周期，直接报告原始错误并通过 finally 关闭串口/窗口。不自动重连、不切换扭矩、不发送真实运动目标；启动发现任何扭矩非零就退出。此工具不采集数据、不启动训练、不实现抓取成功判定。
