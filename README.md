# SO101 自建场景与 ACT

目标是用真实 SO101 主臂遥操作 MuJoCo 从臂，后续采集演示并训练现有 PyTorch ACT。当前已完成官方机器人资源、静态桌面布局、位置保持步进、交互查看与固定相机截图；已加入只读主臂采样、现场映射对齐和遥操作入口，主从姿态与方向仍需用户现场验收；尚未实现数据采集、抓取策略或成功判定。

## 文件与坐标

- `robots/so101/model/so101_new_calib.xml`：TheRobotStudio 官方从臂模型及 `assets/` 网格，保持原样；来源、许可证和关节约定见 `robots/so101/README.md`。
- `assets/scenes/so101_pick_place.xml`：通过相对路径 include 本体，添加桌面、自由方块、目标标记和相机。场景在 include 后指定自己的 meshdir，按主场景目录找到唯一一份官方网格；未复制或改写机器人 XML。
- `src/my_act/sim/env.py`：供查看和遥操作共用的 MuJoCo 加载、控制与渲染；`scripts/view_sim.py` 提供查看入口。按名称重置机器人关节和位置执行器目标。之后只用动力学步进，不持续覆盖 qpos。自由方块增加了位置和速度维度，场景为 `nq=13、nv=12、nu=6`。

长度单位为米、质量为千克、关节角为弧度。世界 Z 向上，初始机械臂向 +X 展开。机器人底座在世界原点固定，底座视觉网格最低处为 z=-0.0024，因此桌面顶面取 z=-0.0024，不改变机器人安装坐标。

| 内容 | 初始参数 |
| --- | --- |
| 桌面 | 完整尺寸 0.70×0.60×0.04，中心 (0.20, 0, -0.0224)，哑光浅灰色 |
| 红方块 | 边长 0.03，质量 0.03 kg，中心 (0.25, -0.05, 0.0176)，底面起始离桌 0.005 |
| 接触摩擦 | 桌面和方块均为滑动 0.8、扭转 0.005、滚动 0.0001；未经实物标定的设计初值 |
| 绿色标记 | 0.07×0.07，中心 (0.25, 0.05, -0.0021)，无碰撞、无边框，略高于桌面避免闪烁 |
| 固定相机 overview | 位置 (0.65, -0.65, 0.60)，看向 (0.19, 0, 0.10)，垂直视场角 45°，RGB uint8 640×480 |
| 初始姿态 | 五个机械臂关节为 0 rad，夹爪为 0.7 rad；位置执行器保持相同目标 |
| 物理推进 | 时间步 0.002 秒，implicitfast 积分器；窗口每 10 个物理步刷新一次并进行墙钟节奏控制 |

初始姿态下，夹爪前端 x∈(0.373, 0.378) 的网格截面两侧 z 边界间隔约 0.0645 米；模型末端位置约 (0.391, 0, 0.226)。因此 0.03 米方块与机器人尺度相称，但截面间隙不是完整有效抓取空间测量。方块与目标相距 0.10 米，处于机器人前方的初始布局；可达性、夹持与放置尚未实际验证。

## 查看与截图

从项目根目录、使用已有虚拟环境执行。窗口运行至关闭；可拖动视角，固定相机截图与交互视角独立。

```bash
cd /home/lzh/projects/my-act
MUJOCO_GL=glfw .venv/bin/python scripts/view_sim.py

# 窗口运行 1000 个物理步，即 2 秒仿真时间，然后退出。
MUJOCO_GL=glfw .venv/bin/python scripts/view_sim.py --steps 1000

# 使用本机已验证的 OSMesa，只在最后保存一次固定相机图像。
check_dir="outputs/sim_checks/$(TZ=Asia/Shanghai date +%Y%m%d_%H%M%S)"
MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa .venv/bin/python scripts/view_sim.py \
  --headless --steps 1000 --save-image "$check_dir/overview.png"

.venv/bin/python scripts/view_sim.py --help
```

`--scene` 可指定场景路径；入口要求场景保留本轮机器人命名、`red_cube` 和 `overview`。`--steps` 是物理步数，不是策略控制次数；无窗口模式默认 1000 步，`--headless --steps 0` 可保存初始状态。仅提供 `--save-image` 时才生成相机图像，其分辨率与后续 ACT 输入缩放尺寸独立。保存路径由调用方指定，应使用新的输出目录避免覆盖旧图片。

## 当前验证边界

MuJoCo 3.3.2 下已通过语法、帮助入口、模型及网格加载、初始接触检查、2 秒物理步进和固定相机截图检查。初始没有接触，短步进只记录到方块与桌面接触；方块最终中心高度约 0.012486 米，软接触允许约 0.114 毫米的几何沉入量。最后 0.5 秒中心变化小于 1e-10 米，底座位置不变，状态有限且警告计数为零。底座由原模型固定约束安装，不依赖被上游移除的底座碰撞网格。

固定相机画面已查看，覆盖夹爪、工作区域、方块和目标。WSLg 下 GUI 已成功打开、完成有限步进并退出；手动视角操作及关闭按钮尚待用户确认。没有运行关节扫描、抓取尝试或任务评测，这些短检查不代表长期动态稳定性或抓取成功率。

ACT 网络、损失、训练配置和实验输出规则保持不变；本轮没有安装依赖。检查产物放在已忽略的 `outputs/sim_checks/`，机器人资源放在 `robots/so101/`，任务场景放在 `assets/scenes/`。

## 主臂遥操作入口

硬件入口为 `robots/so101/scripts/teleoperate.py`，通信在 `src/my_act/hardware/so101/leader.py`，计数映射在同目录 `mapping.py`。通用参数在 `robots/so101/configs/mapping.yaml`，现场对齐文件在已忽略的 `robots/so101/configs/local/`；原硬件校准文件不变。

第一次必须运行交互对齐，确认五轴参考姿态/方向及夹爪两端点，再按单关节顺序验收。完整命令、换算依据和注意事项见 [机器人说明](robots/so101/README.md#主臂遥操作仿真)。这里仅向仿真发送 rad 位置目标，真实主臂全程只读。

```bash
MUJOCO_GL=glfw .venv/bin/python robots/so101/scripts/teleoperate.py --help
# 首次：现场确认后才生成本机文件；不会覆盖已有文件。
MUJOCO_GL=glfw .venv/bin/python robots/so101/scripts/teleoperate.py --align --port /dev/ttyACM0
# 对齐完成后，先从底座单关节开始，输入 START 才推进仿真。
MUJOCO_GL=glfw .venv/bin/python robots/so101/scripts/teleoperate.py --joint shoulder_pan
# 全部单关节验收后再使用完整跟随。
MUJOCO_GL=glfw .venv/bin/python robots/so101/scripts/teleoperate.py
```

20 Hz 控制周期内固定推进 25 个 0.002 秒物理步；墙钟过慢时不补跑积压周期。只有启动阶段做显式限速过渡，正常跟随不做平滑滤波。遥操作不生成离屏相机图像，不保存演示。串口读取失败、异常跳变或明显越界会停止仿真推进并退出；不自动重连、复位或改扭矩。关闭窗口或 Ctrl+C 释放串口与窗口资源。
