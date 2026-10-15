# SO101 机器人资源与只读硬件检查

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

目前只实现本节只读连接检查；尚未实现端口发现、校准、实物关节映射或遥操作。本工具不执行运动或校准。
