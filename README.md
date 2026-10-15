# SO101 主臂遥操作与 ACT

本分支面向真实 SO101 主臂读取关节位置，控制自建 MuJoCo SO101 从臂，采集演示并训练现有 PyTorch ACT，再在同一环境中自主 rollout。当前分支不使用 LIBERO 环境、任务或数据；旧路线由原分支保留。

## 当前状态

已保留 ACT 网络、共享 ResNet18、CVAE、动作块与掩码损失、归一化统计量、按轨迹划分、ACTDataset、离线验证、checkpoint 保存加载及 ACTPolicy。模型和策略接口的状态、动作维度与相机数量由配置决定。

`configs/act.yaml` 是 SO101 的初始接口规划：六维实际关节状态、六维关节位置目标和一路相机；其余网络参数沿用已有设置。它尚未经过仿真或采集验证，也不是旧任务权重的配置。

以下功能尚未实现：SO101 场景与环境封装、主臂串口读取和校准映射、采集与回放、数据格式适配、任务配置、闭环 rollout 和固定初始状态评测。没有用假数据或空环境代替这些接口。

## 安装入口

从项目根目录运行，使用项目虚拟环境。下面是清理后分支的安装入口，本轮清理未执行安装或卸载。

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

系统渲染库与图形后端仍需在最小仿真阶段验证；imageio-ffmpeg 的可执行文件不能代替渲染库。现有虚拟环境仍有旧依赖，当前导入成功不代表已在全新最小环境中完成依赖验证。

## 目录

```text
configs/
  act.yaml                # 初始模型接口规划
  train.yaml              # 训练参数，输出根目录为 outputs/act_so101
requirements/             # base、cpu、gpu、sim
scripts/
  prepare_training.py     # 保留配置快照、划分、统计量保存流程
  train_one_step.py       # 保留单步训练流程
  train.py                # 保留训练、验证、日志及 checkpoint 流程
  launch_train.py         # 保留运行目录与后台启动逻辑
src/my_act/
  data/                   # 通用 Dataset、动作块、划分和归一化
  models/                 # ACT 网络与损失
  training/               # 离线验证和 checkpoint
  config.py               # YAML 读取
  policy.py               # checkpoint 动作块推理
```

## 数据接口与入口可用性

ACTDataset 接受提供以下方法的真实数据源，不依赖具体环境：

- `read_episode(episode_index)`：返回 `state[T,S]`、`action[T,A]` 的 float32 NumPy 数组，以及秒级 `timestamp[T]`。
- `read_images(episode_index, timestamp)`：返回按配置相机顺序排列的 CPU RGB uint8 Tensor，形状 `[C,3,H,W]`。
- 实验准备和单步演示另需 `get_episode_indices(task_index)`；任务配置需明确数据来源和任务编号。

当前三个准备／训练脚本的 `main(source=...)` 保留通用流程，由调用方提供与配置一致的数据源。训练 CLI 尚无 SO101 数据源构造逻辑，不会自动选择其他数据。后台 CLI 同样暂停，避免创建无效运行目录或启动必然失败的子进程；`launch_training` 保存原有启动实现，待数据入口完成后再接通。

目前可执行的命令只用于查看参数：

```bash
.venv/bin/python scripts/prepare_training.py --help
.venv/bin/python scripts/train_one_step.py --help
.venv/bin/python scripts/train.py --help
.venv/bin/python scripts/launch_train.py --help
```

不带 `--help` 请求执行时会明确报告缺少 SO101 数据源；不会开始训练、启动后台进程或创建实验产物。数据适配完成前，不提供可运行的训练、采集或 rollout 示例。训练循环、损失和模型选择规则保持原样。

## 实验与本地文件

实验目录为 `outputs/act_so101/<实验时间>/`，保存模型、任务、训练配置、`split.json`、`stats.npz` 和可选的 `experiment_note.json`。任务配置原样复制，保留注释。

每次启动使用独立的 `runs/<运行时间>/`，保存 `run_config.yaml`、`launch_record.json`、`terminal.log`、`metrics.jsonl`、`last.pt`、`best.pt` 和 `best_metrics.json`。后台启动方创建一次目录并通过 `--run-dir` 传递；直接训练入口仍保留自行创建目录的逻辑。已有训练产物禁止覆盖，不支持 resume。

`data/`、`outputs/` 和 `.venv/` 继续忽略且不随分支隔离。设备端口和校准文件放在忽略的 `configs/local/`、`calibration/`、`calibrations/` 或 `data/` 中，不提交到仓库。本次清理不修改这些共享目录和历史产物。
