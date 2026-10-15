# SO101 主臂遥操作与 ACT

本分支面向真实 SO101 主臂读取关节位置，控制自建 MuJoCo SO101 从臂，采集演示并训练现有 PyTorch ACT，再在同一环境中自主 rollout。当前分支不使用 LIBERO 环境、任务或数据；旧路线由原分支保留。

## 当前状态

已保留 ACT 网络、共享 ResNet18、CVAE、动作块与掩码损失、归一化统计量、按轨迹划分、ACTDataset、离线验证、checkpoint 保存加载及 ACTPolicy。模型和策略接口的状态、动作维度与相机数量由配置决定。

`configs/act.yaml` 是 SO101 的初始接口规划：六维实际关节状态、六维关节位置目标和一路相机；其余网络参数沿用已有设置。基础仿真已按这六个关节和一路相机实现，尚未采集数据或训练；它不是旧任务权重的配置。

已新增 SO101 最小场景及 reset/step/get_observation/close 接口，只有固定底座、桌面和相机。以下功能尚未实现：抓取物体、目标区域、成功判定、主臂串口读取和校准映射、采集与回放、训练数据格式适配及任务数据配置、闭环 rollout 和固定初始状态评测。没有用假数据或空环境代替这些接口。

## 安装入口

从项目根目录运行，使用项目虚拟环境。下面是当前分支的安装入口；本次仿真开发沿用已有环境，未安装、卸载或升级依赖。

CPU 与 NVIDIA GPU 二选一：

```bash
# CPU
.venv/bin/python -m pip install -r requirements/base.txt -r requirements/cpu.txt

# NVIDIA GPU（Linux，沿用现有 CUDA 13.0 构建）
.venv/bin/python -m pip install -r requirements/base.txt -r requirements/gpu.txt
```

MuJoCo 基础依赖与可编辑包安装：

```bash
.venv/bin/python -m pip install -r requirements/sim.txt
.venv/bin/python -m pip install -e . --no-deps
```

公共依赖仅维护在 `base.txt`，CPU/GPU 文件保留各自固定的 torch、torchvision 版本和安装源。`sim.txt` 仅保留现有 MuJoCo、PyOpenGL、glfw。imageio 和 imageio-ffmpeg 保留为后续采集的基础视频工具，当前没有采集命令。主臂通信的最小驱动及版本待确认，不安装完整 LeRobot 或其他仿真框架。

当前环境的 OSMesa 相机渲染与 GLFW 窗口已通过短检查；其他机器的系统渲染库仍需确认。imageio-ffmpeg 的可执行文件不能代替渲染库。现有虚拟环境仍有旧依赖，当前导入成功不代表已在全新最小环境中完成依赖验证。

## 目录

```text
configs/
  act.yaml                # 初始模型接口规划
  train.yaml              # 训练参数，输出根目录为 outputs/act_so101
  tasks/so101_pick_place.yaml # 仅基础仿真配置，还不是训练数据任务配置
assets/so101/             # 上游机器人、网格、许可证及自建最小场景
requirements/             # base、cpu、gpu、sim
scripts/
  prepare_training.py     # 保留配置快照、划分、统计量保存流程
  train_one_step.py       # 保留单步训练流程
  train.py                # 保留训练、验证、日志及 checkpoint 流程
  launch_train.py         # 保留运行目录与后台启动逻辑
  view_sim.py             # 基础场景查看和短控制检查
src/my_act/
  data/                   # 通用 Dataset、动作块、划分和归一化
  models/                 # ACT 网络与损失
  training/               # 离线验证和 checkpoint
  sim/                    # 原生 MuJoCo 基础环境
  config.py               # YAML 读取
  policy.py               # checkpoint 动作块推理
```

## 数据接口与入口可用性

ACTDataset 接受提供以下方法的真实数据源，不依赖具体环境：

- `read_episode(episode_index)`：返回 `state[T,S]`、`action[T,A]` 的 float32 NumPy 数组，以及秒级 `timestamp[T]`。
- `read_images(episode_index, timestamp)`：返回按配置相机顺序排列的 CPU RGB uint8 Tensor，形状 `[C,3,H,W]`。
- 实验准备和单步演示另需 `get_episode_indices(task_index)`；任务配置需明确数据来源和任务编号。

当前三个准备／训练脚本的 `main(source=...)` 保留通用流程，由调用方提供与配置一致的数据源。训练 CLI 尚无 SO101 数据源构造逻辑，不会自动选择其他数据。后台 CLI 同样暂停，避免创建无效运行目录或启动必然失败的子进程；`launch_training` 保存原有启动实现，待数据入口完成后再接通。

以下训练相关命令目前只支持查看参数（仿真入口见下一节）：

```bash
.venv/bin/python scripts/prepare_training.py --help
.venv/bin/python scripts/train_one_step.py --help
.venv/bin/python scripts/train.py --help
.venv/bin/python scripts/launch_train.py --help
```

这些训练相关入口不带 `--help` 请求执行时会明确报告缺少 SO101 数据源；不会开始训练、启动后台进程或创建实验产物。数据适配完成前，不提供可运行的训练、采集或 rollout 示例。训练循环、损失和模型选择规则保持原样。

## 基础仿真查看

使用现有项目环境，从项目根目录执行。GUI 模式与无窗口模式分别使用独立进程环境变量，不写入 shell 配置，也不导入 robosuite 或连接串口。

```bash
# 窗口保持初始目标，关闭窗口结束
MUJOCO_GL=glfw PYOPENGL_PLATFORM=glx .venv/bin/python scripts/view_sim.py --save-image

# 窗口内依次检查各关节及夹爪，小幅检查完成后自动退出
MUJOCO_GL=glfw PYOPENGL_PLATFORM=glx .venv/bin/python scripts/view_sim.py --check-joints --save-image

# 无窗口短步进；--check-joints 可改为执行完整小幅序列
MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa .venv/bin/python -X faulthandler scripts/view_sim.py --headless --steps 20 --save-image
```

`--config` 可指定配置，`--steps` 可限制控制步数。20 Hz 下完整检查为 345 步：先保持初始目标，五个臂关节各缓慢增加 0.12 rad 并返回；夹爪按 0.3→0.7→0.05→0.3 rad 小范围开合。物理每周期固定十步，不随窗口帧率变化；若渲染较慢，墙钟会慢于仿真时间。

环境 `state[6]` 是实际关节角，`images[1,H,W,3]` 是未经缩放或翻转的 RGB uint8，`timestamp` 是仿真秒数。六维名称、正方向、限位及夹爪含义见 [模型说明](assets/so101/README.md)。动作必须是有限的六维绝对关节目标；越界报错，不静默裁剪。此原始图像接口尚未接入 ACTPolicy 的张量转换。

每次生成新的 `outputs/sim_checks/<时间>/`，保存 `check.json`，指定 `--save-image` 时另存一次 `camera_initial.png`。检查记录中的接触穿透和位姿变化是在控制步结束时采样，不能替代全部物理子步或整个工作空间的碰撞验证。

本机已完成 OSMesa 全部小幅检查和 GLFW 有限步数窗口运行；保存的静态相机图像已查看。窗口内动态运动是否有视觉抖动、遮挡等仍请实际观察，不将窗口创建成功当作动态目视验收。

## 后续主臂接入

还需要串口与设备发现，核对连接、舵机 ID 和型号，读取校准文件并在必要时执行明确的校准流程。逐关节确认主臂到仿真的方向、零点、单位、范围和夹爪开合映射；原始主臂读数不能直接视为仿真弧度。还需定义断连、非有限或异常读数、退出时的安全处理与资源释放。本阶段未实现这些功能，未访问真实串口或启用真实舵机扭矩。

## 实验与本地文件

实验目录为 `outputs/act_so101/<实验时间>/`，保存模型、任务、训练配置、`split.json`、`stats.npz` 和可选的 `experiment_note.json`。任务配置原样复制，保留注释。

每次启动使用独立的 `runs/<运行时间>/`，保存 `run_config.yaml`、`launch_record.json`、`terminal.log`、`metrics.jsonl`、`last.pt`、`best.pt` 和 `best_metrics.json`。后台启动方创建一次目录并通过 `--run-dir` 传递；直接训练入口仍保留自行创建目录的逻辑。已有训练产物禁止覆盖，不支持 resume。

`data/`、`outputs/` 和 `.venv/` 继续忽略且不随分支隔离。设备端口和校准文件放在忽略的 `configs/local/`、`calibration/`、`calibrations/` 或 `data/` 中，不提交到仓库。本次清理不修改这些共享目录和历史产物。
