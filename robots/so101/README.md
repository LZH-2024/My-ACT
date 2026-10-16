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
    check_connection.py    # 只读检查指定舵机 ID
    calibrate.py           # 按角色隔离的主从臂交互式校准
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

## 主从臂只读连接检查

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

本节工具只执行连接检查，不执行运动或校准。主从臂校准使用下面的独立交互入口；现有主臂仿真跟随见文末，本轮不修改。

## 主从臂交互式校准

只针对用户已确认的主臂或从臂 ID：1 shoulder_pan、2 shoulder_lift、3 elbow_flex、4 wrist_flex、5 wrist_roll、6 gripper。使用现有 pyserial 和 Feetech SDK，不安装或导入 LeRobot，不连接仿真。此次只做语法、帮助和离线替身检查，尚未替用户执行硬件校准。

参考的实际本地调用链（同级 `../lerobot/`）：

- `src/lerobot/scripts/lerobot_calibrate.py`：连接设备、调用校准、退出。
- `src/lerobot/teleoperators/so_leader/so_leader.py`：`SOLeader.calibrate`、主臂手柄参考姿态图、wrist_roll 特殊处理；SO101Leader 是该实现的别名。
- `src/lerobot/robots/so_follower/so_follower.py`：`SOFollower.calibrate`、从臂夹爪参考姿态图、wrist_roll 特殊处理；SO101Follower 是该实现的别名。
- `src/lerobot/motors/motors_bus.py`：`reset_calibration`、`set_half_turn_homings`、`record_ranges_of_motion`、归一化。
- `src/lerobot/motors/feetech/feetech.py` 与 `tables.py`：偏置公式、寄存器地址、符号位、校准读写和配置步骤。
- `src/lerobot/motors/encoding_utils.py`、`src/lerobot/teleoperators/teleoperator.py`：符号幅值编码、JSON 保存与加载。

本项目将寄存器访问和纯函数放在 `src/my_act/hardware/so101/calibration.py`，交互流程放在 `robots/so101/scripts/calibrate.py`，正常包导入，无 sys.path 修改。改编的算法、示意图保留 Hugging Face Apache-2.0 声明，许可证原文在 `src/my_act/hardware/so101/LICENSE`；新增了备份、显式确认、范围有效性检查和受限写入。

### 主臂现场运行（兼容已有命令）

先阅读 [SO101 官方校准说明与视频](https://huggingface.co/docs/lerobot/main/en/so101#calibration-video)。本地 SOLeader 还提供主臂参考姿态示意，入口会原样打印；[官方视频](https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/lerobot/calibrate_so101_2.mp4) 来自同一文档。按图示摆到各关节行程中部，不能自行用仿真 qpos=0 或旧校准的水平伸展零位替代。

在 WSL 的交互终端执行下面一条完整命令。`leader01` 是给这条实物主臂指定的稳定名称示例，若改名，应同步修改文件目录，不能用于另一台设备。

```bash
cd /home/lzh/projects/my-act && .venv/bin/python robots/so101/scripts/calibrate.py --port /dev/ttyACM0 --baudrate 1000000 --device-name leader01 --calibration-file robots/so101/calibration/leader/leader01/calibration.json
```

`--role` 支持 leader / follower，默认 leader（主臂），帮助和启动输出均明确说明；旧主臂命令无需改写，也可显式加 `--role leader`。
`--calibration-file` 可指定对应角色及设备目录内的 JSON 路径；省略时使用 `robots/so101/calibration/<role>/<设备名>/calibration.json`。主从校准不能共用。路径、串口和设备名称不是自动发现的硬件身份，运行前须现场确认。

1. 若已有文件，输入 `reuse` 将旧文件偏置及限位写回舵机，或输入 `new` 重新采集；其他输入取消。复用也要经过备份和写入确认，不静默应用。
2. 只读核对六个 ID、型号编号 777，并读取所有可能修改的寄存器原始字。先在校准目录下的 `<role>/<设备名>/backups/<时间戳>/` 保存 `registers_before.json`；已有文件原样备份为 `previous_calibration.json`，不覆盖旧备份。
3. 查看原值与写入计划。若发现任何扭矩非零，先托住臂体，再输入 `DISABLE` 明确允许关闭；随后输入 `WRITE` 才会执行准备写入。不会开启扭矩或发送运动目标。
4. 新校准时按官方图示摆参考姿态并保持不动，按回车清除旧偏置、恢复 0～4095 限位并读取当前位置。由 `当前位置 - 2047` 计算新偏置，显示后再输入 `WRITE` 写入。先清零并读回旧偏置，避免把旧偏置当成零或重复累加。
5. 按提示开始只读范围采样。逐个手动缓慢移动 shoulder_pan、shoulder_lift、elbow_flex、wrist_flex 和 gripper，覆盖完整安全行程；不要用力顶止挡。`wrist_roll` 不采范围，也不要求绕转一圈，沿用上游范围 0～4095。采样最多约 20 Hz，终端最多 1 Hz 覆盖刷新，按回车结束。
6. 范围必须在 0～4095 内且非退化；本工具另要求五个采集关节覆盖中心计数 2047 的两侧，以拒绝只采到半边的情况。若读数越界、发生跳变或范围不满足，不自动裁剪或修正。数值变化不证明完整行程，因此必须现场检查显示的范围，再输入 `SAVE` 确认写限位。
7. 每次写入检查 SDK 状态并立即读回；所有写入完成后恢复原 Lock 值、确认扭矩仍为 0，才保存新校准文件。重校准通过临时完整文件替换，旧文件已备份；复用不重写原校准文件。

### 从臂 follower01 的现场命令

从臂已确认连接在 `/dev/ttyACM1`，设备名为 `follower01`，使用相同的关节 ID 映射。
本轮只扩展工具并做离线验证，下面的交互式命令由用户在本机执行：

```bash
cd /home/lzh/projects/my-act
.venv/bin/python robots/so101/scripts/calibrate.py \
  --role follower \
  --port /dev/ttyACM1 \
  --baudrate 1000000 \
  --device-name follower01 \
  --calibration-file robots/so101/calibration/follower/follower01/calibration.json
```

运行前阅读 [SO101 官方 Calibrate → Follower 说明与参考姿态视频](https://huggingface.co/docs/lerobot/main/en/so101#calibrate)。
入口按角色打印本地上游 `SOFollower` 的**夹爪参考姿态图**，不打印主臂手柄图。
按从臂参考图将关节放到行程中部，保持不动后记录偏置；不能以仿真 qpos=0、
主臂手柄姿态或旧模型的水平伸展姿态代替。

源码核对结果如下，通用部分共用现有代码，不另复制从臂校准脚本：

| 项目 | 主臂 SOLeader | 从臂 SOFollower |
| --- | --- | --- |
| 参考姿态 | 主臂手柄图 | 从臂固定爪/活动爪图 |
| 偏置 | 清零旧偏置及限位后，当前位置减 2047 | 同一 Feetech 公式 |
| 范围采集 | 手动采集前四个臂关节及 gripper | 同样五个关节；gripper 是从臂夹爪 |
| wrist_roll | 不采范围，固定 0～4095 | 同样处理，不要求转一整圈 |
| 完成保存 | leader/<设备名>/ | follower/<设备名>/ |

从臂在每次准备关闭扭矩前会提示**先托住从臂**，确认后才写入。
成功后会逐项回读并保存独立文件，六个关节扭矩保持关闭；**请继续托住或妥善放置从臂，再松手**。
若中途取消或通信失败，按现有流程退出并显示备份位置，不自动恢复扭矩或回滚部分写入。

本次校准保留已有写入白名单，不调用官方 follower 的高级 `configure()`：
其中 PID 增益、夹爪电流/力矩保护等设置不属于本轮校准，不会带入。
不写舵机 ID、波特率、目标位置，不自动开启扭矩。

校准结果与备份分别位于：

```text
robots/so101/calibration/
  leader/leader01/
    calibration.json
    backups/<时间戳>/
  follower/follower01/
    calibration.json
    backups/<时间戳>/
      registers_before.json
      previous_calibration.json  # 仅在此前已有该从臂校准文件时保存
```

角色/设备路径校验在读取校准文件、打开串口之前完成。
跨角色、跨设备以及通过符号链接跨目录的校准或备份路径会被拒绝。
现有主臂文件及备份不会作为从臂输入或输出。JSON 保持原来的六关节字典格式；
角色身份由目录及备份元信息表达，不自动迁移、复制或改写主臂文件。
校准目录已被 Git 忽略；不要提交校准结果、备份或本机设备配置。

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

从臂校准成功后，先托住或妥善放置从臂，再用同一工具只读核验。
将下方引号内的 `<本次校准时间戳>` 替换为刚才终端显示的实际备份目录，不自动选择最新备份：

```bash
cd /home/lzh/projects/my-act
.venv/bin/python robots/so101/scripts/check_connection.py \
  --role follower \
  --port /dev/ttyACM1 \
  --baudrate 1000000 \
  --device-name follower01 \
  --calibration-file robots/so101/calibration/follower/follower01/calibration.json \
  --register-backup 'robots/so101/calibration/follower/follower01/backups/<本次校准时间戳>/registers_before.json'
```

核验也默认 `--role leader`。旧主臂命令不带 `--role`、`--device-name` 仍可使用；
省略设备名时从校准路径的设备目录推断。显式指定设备名时必须与路径及备份一致。
从臂必须指定 `--role follower`，否则其路径会在打开串口前被默认 leader 角色检查拒绝。

### 本轮离线验证

使用项目 `.venv`，未新增依赖或安装完整 LeRobot。检查语法和两个入口的 `--help`，
并使用标准库 unittest 检查角色路径、设备名、跨角色备份拒绝、符号链接隔离、
旧主臂命令、从臂参考图，以及替身总线下的从臂独立备份/保存流程：

```bash
.venv/bin/python -m unittest discover -s tests -p test_so101_calibration_roles.py -v
```

测试只使用临时目录和替身总线，真实串口被拦截；未执行真实校准或寄存器写入。
不启动主从遥操作、不接摄像头、不采集数据，现有 `follow.py` 和仿真跟随逻辑保持不变。

## 六关节跟随检查

`follow.py` 由原底座检查入口扩展并改名，默认读取六个关节并驱动仿真。真实主臂始终只读，启动核对六个 ID、偏置、限位、工作模式、Phase bit 4 和关闭的扭矩；不会重新校准或写寄存器。

五个臂关节统一采用 `角度(rad) = direction × (解码计数 - 行程中点) × 2π / 4095`，行程中点从各自校准记录计算。沿用本地 LeRobot `motors_bus.py` degrees 分支，不再次减内部 Homing_Offset，不把实物行程拉伸到模型限位。

| 关节 | 当前零点计数 / 开度范围 | 跟随约定 |
| --- | --- | --- |
| shoulder_pan | 2088.5 | 中点对应 0 rad，用户已验证底座效果 |
| shoulder_lift | 2040.5 | 中点对应 0 rad，方向和姿态待人工确认 |
| elbow_flex | 1944 | 中点对应 0 rad，方向和姿态待人工确认 |
| wrist_flex | 2033.5 | 中点对应 0 rad，方向和姿态待人工确认 |
| wrist_roll | 2047.5 | 校准约定范围 0～4095 的中点；不表示模型允许无限转动 |
| gripper | 1546～2724 | 单独按 0～100% 开度映射到模型 0～约 1.74533 rad |

夹爪沿用 LeRobot 的开度比例，当前测试约定为最小计数闭合、最大计数张开；仿真以 0 rad 为闭合参考、模型最大正角度为最大开口，不使用负角度余量强压闭合。这是主臂手柄开度到从臂夹指的控制约定，不是两者角度相等的证明，开合方向和端点效果仍需用户观察。

在 WSL 项目根目录执行全部跟随：

```bash
cd /home/lzh/projects/my-act
env -u PYOPENGL_PLATFORM MUJOCO_GL=glfw .venv/bin/python robots/so101/scripts/follow.py
```

点击窗口后按空格开始。先保持实物不动，等待“启动同步完成”，再逐个小幅、缓慢移动。首次目标同步每个关节限速 0.5 rad/s，完成后直接跟随；没有持续滤波。关闭窗口或 Ctrl+C 退出。

单独核对肩部时，在命令末尾加 `--joint shoulder_lift`；未选关节保持初始目标（五个臂关节 0 rad，夹爪 0.7 rad）。仍然读取并检查完整六关节，其他关节异常也会停止。

如果肩部方向相反，关闭后加 `--reverse-joints shoulder_lift` 重新运行；多个关节可写为 `--reverse-joints shoulder_lift wrist_flex`。夹爪加入此列表会交换开合方向。旧的 `--direction` 已改为按关节指定，底座单独反向可用 `--joint shoulder_pan --reverse-joints shoulder_pan`。

建议人工观察顺序：底座 → 肩部 → 肘部 → 腕俯仰 → 腕旋转 → 夹爪 → 协同。底座之外的映射尚未经过用户目视确认；先小幅移动，不扫机械极限或尝试抓取。

每周期 0.05 秒，当前物理步长 0.002 秒，因此每周期推进 25 步。目标按关节与执行器范围交集限幅，夹爪另限制为非负目标。腕俯仰 `wrist_flex` 的有效读数超过模型行程时，仅限幅并显示裁剪，不因模型限位退出；它超出采集范围时只显示“超采集范围=True”，仍要求计数有限且在当前单圈反馈约定 0～4095 内，并保留突变检查；校准文件不变。其他关节最多允许 0.10 rad 的轻微越界并显示裁剪，更多则停止。其他关节的采集边界允许 32 个计数的小偏差并提示。相邻采样角度跳变超过 0.35 rad 则停止，腕旋转跨越计数边界时不会把目标绕回另一端，通常在到达模型限位时已停止。这些是小幅跟随检查的保护阈值，不是实物性能标定结果。

通信失败立即停止目标更新和物理推进，关闭串口与窗口，不补零、不使用旧读数、不自动重连。终端约每秒输出一次六关节信息。有限无窗口检查使用 `--headless --steps 40`，会直接开始；默认窗口模式等待空格才推进物理仿真。该入口不采集数据、不训练、不执行抓取任务评测。

## 真实主臂跟随真实从臂

入口为 `robots/so101/scripts/teleoperate_real.py`，可复用实现为 `src/my_act/hardware/so101/real_teleop.py`。原 `follow.py` 仍用于仿真，命令与行为不变。**真实运动尚未验证**；工具开发与离线检查通过不代表从臂已经校准。本次开发时 `follower/follower01/calibration.json` 不存在。

### 先完成从臂校准与只读核验

由用户现场确认连接的是从臂、托住臂体后执行已有校准工具；不要把主臂校准复制为从臂校准：

```bash
cd /home/lzh/projects/my-act
.venv/bin/python robots/so101/scripts/calibrate.py --role follower --port /dev/ttyACM1 --baudrate 1000000 --device-name follower01 --calibration-file robots/so101/calibration/follower/follower01/calibration.json
```

按工具的参考图与确认提示完成校准，校准完成后扭矩保持关闭。需要核对原 Phase 全部位及 Lock 恢复情况时，使用前述 `check_connection.py --role follower` 并显式提供本次实际备份；不要随意选旧备份。

随后执行双臂一次只读预览。此入口不要求历史备份，逐关节读取 ID、型号、工作模式、扭矩、Homing_Offset、最小/最大限位以及 Phase 必要反馈位。两份文件须分别位于正确角色和设备目录，偏置和范围须与各自硬件一致，主从扭矩都须关闭；缺失或不一致立即退出，不自动写回。这里的路径角色不是硬件唯一身份，用户仍须确认串口实际对应哪条臂。

```bash
.venv/bin/python robots/so101/scripts/teleoperate_real.py --leader-port /dev/ttyACM0 --follower-port /dev/ttyACM1 --leader-name leader01 --follower-name follower01 --leader-calibration-file robots/so101/calibration/leader/leader01/calibration.json --follower-calibration-file robots/so101/calibration/follower/follower01/calibration.json --baudrate 1000000 --preview
```

预览展示主臂映射目标、从臂当前姿态、差值及限制后的目标计数，然后关闭串口；不预写目标、不启用或关闭扭矩。文件检查在打开串口前完成，两个端口的真实设备号不能相同。

### 动作转换与限制

依据同级 LeRobot 的 `teleoperators/so_leader/so_leader.py`、`robots/so_follower/so_follower.py`、`motors/motors_bus.py`、`motors/feetech/tables.py` 和 `robots/utils.py`。主从统一使用 `use_degrees=True` 的约定：

- 五个臂关节：`度 = (主臂反馈计数 - 主臂范围中点) × 360 / 4095`；`从臂目标计数 = int(度 × 4095 / 360 + 从臂范围中点)`。
- 夹爪：主臂采集范围映射为 0～100% 开度，再用从臂自己的夹爪范围反归一化；超出主臂采集开度的部分按 LeRobot 规则限幅。
- 两臂都使用现有校准字段验证，当前只接受 `drive_mode=0`；不是 Operating_Mode，也不引入额外反向开关。反馈已包含内部偏置，不再次减 homing_offset。不使用 MuJoCo 弧度、模型限位或直接复制主臂原始计数。
- 从臂目标先限制到其校准且回读一致的范围，再限制到当前从臂反馈附近。`--max-relative-target-deg 2` 表示五个臂关节每次目标离当前反馈最多 2 度；`--max-gripper-target-percent 2` 表示夹爪最多 2 个百分点。最终计数向允许区间内部取整。相同反馈下重复规划不会继续积累目标。
- 这些参数是反馈相对位置限制，不是上一条命令的变化量、保证的速度、力矩限制或碰撞规避。20 Hz 是期望频率；逐 ID 响应与回读有开销，终端显示实际频率。
- 单圈读数必须完整、有限、为 0～4095 的整数；相邻采样跳变超过 512 计数（约 45° 编码器角）时停止。主臂超过采集边界单独提示；从臂当前反馈若已超出自身限位则拒绝继续。腕旋转跨圈不会绕回发送整圈跳变。

改编算法保留 Hugging Face Apache-2.0 声明，许可证见 `src/my_act/hardware/so101/LICENSE`。只复用现有 SDK，不导入完整 LeRobot，也不调用其会写 PID、加速度、电流保护等参数的 `configure()`；已有舵机参数不被此工具修改。通信写入仅限从臂 Goal_Position（42，2 字节）与 Torque_Enable（40，1 字节），不写配置锁、偏置或限位。

### 现场启动与停止

完成校准及预览后，由用户在交互终端现场执行：

```bash
.venv/bin/python robots/so101/scripts/teleoperate_real.py --leader-port /dev/ttyACM0 --follower-port /dev/ttyACM1 --leader-name leader01 --follower-name follower01 --leader-calibration-file robots/so101/calibration/leader/leader01/calibration.json --follower-calibration-file robots/so101/calibration/follower/follower01/calibration.json --baudrate 1000000 --frequency 20 --max-relative-target-deg 2 --max-gripper-target-percent 2
```

1. 程序先只读展示姿态差异。确认实物身份、周围空间足够并托稳从臂，输入 `START` 才授权写入；其他输入取消。禁止重定向输入来自动确认。
2. START 后重新核验，读取从臂最新位置，预写相同目标并回读，再逐个开启从臂扭矩。预写后若姿态移动超过 4 计数（约 0.35° 编码器角）则停止；启用过程中发生错误也尽力关闭全部从臂扭矩。逐次反馈相对限制从第一条跟随命令开始生效，逐步接近主臂姿态。
3. 正常停止：按回车或 Ctrl+C，停止发送新目标，暂时保持最后目标；先托住从臂，再输入 `OFF` 关闭扭矩。六个关节均须写入并回读确认；主臂始终只读。
4. 通信异常、终端 EOF/SIGHUP/SIGTERM、启动或关闭确认期间中断：停止新运动目标，尽力逐 ID 关闭从臂扭矩，逐项报告失败；从臂可能失去支撑。主臂扭矩不会被修改。若尚未接管扭矩，不会擅自关闭原本已经开启的从臂。
5. 断连时无法保证关扭矩，SIGKILL、进程崩溃或断电也无法依赖 Python 清理；不能把程序退出等同于硬件已安全停止。正常及异常路径均尝试释放两条串口，不无限重连或重试。

本轮只做代码与离线模拟通信检查，未打开真实串口、未启用扭矩、未发送真实位置目标，不包含摄像头、数据采集或训练。
