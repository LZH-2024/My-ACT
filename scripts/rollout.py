import argparse  # 解析单回合评估参数
import json  # 保存可追溯的运行结果
import os  # 读取启动命令传入的环境变量
import random  # 固定 Python 随机种子
import time  # 测量策略循环的墙钟耗时
from collections import deque  # 按顺序执行预测动作，不做时间集成
from pathlib import Path  # 组织输入与输出路径

import imageio.v2 as imageio  # 逐帧编码视频并保存初始图像
import numpy as np  # 处理动作、随机种子和数组文件
import pandas as pd  # 从任务元数据核对固定支持的任务
import torch  # 加载初始化状态并使用 CUDA 策略

from my_act.config import read_yaml  # 读取任务配置
from my_act.envs.libero import convert_observation  # 复用图像方向与状态转换
from my_act.policy import ACTPolicy  # 复用 checkpoint 策略推理


def make_frame(observation: dict) -> np.ndarray:  # 将转换后的双相机图像拼成视频帧
    """按照训练方向将外部、腕部相机从左到右拼接，返回 RGB uint8 图像。"""  # 函数说明
    images = observation["images"][0].permute(0, 2, 3, 1).numpy()  # 从 CPU 张量恢复两路 HWC 图像
    return np.concatenate((images[0], images[1]), axis=1)  # 沿宽度拼接，不再翻转或缩放


def main() -> None:  # 从项目根目录执行一次闭环评估
    """仅支持 libero_goal / put_the_bowl_on_the_plate；执行一个回合，动作队列不做时间集成，结果不代表多回合成功率。"""  # 函数说明
    parser = argparse.ArgumentParser(description="LIBERO 固定目标任务单回合 ACT 闭环评估")  # 创建命令行解析器
    parser.add_argument("--checkpoint", required=True, help="ACT checkpoint 路径")  # 必须明确指定模型权重
    parser.add_argument("--task-config", default="configs/tasks/libero_task10.yaml", help="已确认任务的数据配置")  # 默认使用现有 task10 配置
    parser.add_argument("--initial-state-index", type=int, default=0, help="官方固定初始化状态编号")  # 默认使用第一个初始化状态
    parser.add_argument("--seed", type=int, default=42, help="随机种子")  # 默认沿用已有种子
    parser.add_argument("--max-steps", type=int, default=300, help="最多执行的策略控制步数")  # 等待动作不计入此上限
    parser.add_argument("--action-steps", type=int, default=16, help="每次预测后连续执行的动作数")  # 按动作队列执行部分或完整动作块
    parser.add_argument("--output-dir", required=True, help="尚不存在的本回合输出目录")  # 禁止覆盖已有结果
    args = parser.parse_args()  # 解析本次实际运行参数
    backend = {name: os.environ.get(name) for name in ("NUMBA_DISABLE_JIT", "MUJOCO_GL", "PYOPENGL_PLATFORM")}  # 只读取进程启动前设置的变量
    print("启动环境变量:", backend, flush=True)  # 在仿真包导入前打印实际配置
    from libero.libero import benchmark, get_libero_path  # 使用已有 LIBERO 路径配置和任务注册表
    from libero.libero.envs import OffScreenRenderEnv  # 环境变量已由启动命令传入后才导入仿真环境
    import numba  # 读取实际生效的 JIT 开关

    print("实际 DISABLE_JIT:", numba.config.DISABLE_JIT, flush=True)  # 确认本进程使用的 JIT 配置
    output_dir = Path(args.output_dir).resolve()  # 将输出目录规范为绝对路径
    output_dir.mkdir(parents=True, exist_ok=False)  # 创建全新目录，已存在时直接报错
    task_config = read_yaml(args.task_config)  # 读取调用方指定的任务配置
    tasks = pd.read_parquet(Path(task_config["dataset"]["root"]) / "meta/tasks.parquet")  # 只读取任务元数据核对语义
    task_description = tasks.index[tasks["task_index"] == task_config["dataset"]["task_index"]].tolist()  # 获取数据集任务编号对应的名称
    expected_cameras = ["observation.images.image", "observation.images.image2"]  # 当前转换仅支持此相机顺序
    if task_description != ["put the bowl on the plate"] or task_config["dataset"]["camera_keys"] != expected_cameras:  # 拒绝把其他配置当作已确认任务
        raise ValueError("本脚本仅支持 put the bowl on the plate 及已确认的双相机顺序")  # 明确说明单任务限制
    random.seed(args.seed)  # 固定 Python 随机种子
    np.random.seed(args.seed)  # 固定 NumPy 随机种子
    torch.manual_seed(args.seed)  # 固定 PyTorch 随机种子
    torch.cuda.manual_seed_all(args.seed)  # 固定 CUDA 随机种子，本轮不回退到 CPU
    checkpoint_path = Path(args.checkpoint).resolve()  # 记录 checkpoint 的绝对路径
    print("加载策略:", checkpoint_path, "device=cuda", flush=True)  # 明确使用 CUDA 和指定权重
    policy = ACTPolicy(checkpoint_path, device="cuda")  # 完整加载 checkpoint，保持已有推理接口
    chunk_size = policy.model.query_embedding.num_embeddings  # 从实际模型读取动作块长度
    if not 1 <= args.action_steps <= chunk_size:  # 检查动作队列长度，不静默截断参数
        raise ValueError(f"action_steps 必须在 1 到 {chunk_size} 之间，实际为 {args.action_steps}")  # 明确报告无效参数
    suite_name, task_name = "libero_goal", "put_the_bowl_on_the_plate"  # 本轮只支持已确认的固定任务
    suite = benchmark.get_benchmark_dict()[suite_name](task_order_index=0)  # 使用官方默认任务顺序
    task_id = next(i for i, task in enumerate(suite.tasks) if task.name == task_name)  # 根据任务名定位套件编号
    task = suite.get_task(task_id)  # 取得任务文件信息，不使用数据集 task_index 作为套件编号
    init_path = Path(get_libero_path("init_states")) / task.problem_folder / task.init_states_file  # 定位已确认的官方初始化状态
    init_states = torch.load(init_path, map_location="cpu", weights_only=False)  # 读取本地可信官方状态文件中的 NumPy 对象
    control_freq, num_steps_wait = 20, 10  # 固定仿真控制频率与初始化等待步数
    env, writer = None, None  # 为 finally 保存成功创建的资源
    predicted_actions, executed_actions = [], []  # 仅保存实际执行的动作记录，不积累视频帧
    num_steps, policy_queries, clipped_steps = 0, 0, 0  # 初始化策略步、查询和裁剪计数
    try:  # 保证正常结束和异常路径均关闭资源
        print("创建环境:", suite_name, task_name, "task_id=", task_id, flush=True)  # 打印明确任务身份
        env = OffScreenRenderEnv(  # 沿用已成功的无窗口环境创建方式
            bddl_file_name=suite.get_task_bddl_file_path(task_id),  # 使用官方任务 BDDL
            camera_names=["agentview", "robot0_eye_in_hand"],  # 保持转换函数的双相机顺序
            camera_heights=256, camera_widths=256,  # 保持原始图像尺寸
            controller="OSC_POSE", control_freq=control_freq,  # 使用默认增量控制，不修改缩放或夹爪符号
        )  # 完成环境构造
        env.seed(args.seed)  # 设置环境随机种子
        obs = env.reset()  # 重置环境，不执行模型动作
        obs = env.set_init_state(init_states[args.initial_state_index])  # 加载指定固定初始化状态
        low, high = env.env.action_spec  # 读取实际动作边界用于裁剪
        print("控制器 use_delta:", env.robots[0].controller.use_delta, "control_freq:", env.env.control_freq, "action_spec:", (low, high), flush=True)  # 打印实际控制设置
        for wait_step in range(num_steps_wait):  # 执行明确记录的十步初始化等待
            obs, _, done, _ = env.step(np.array([0, 0, 0, 0, 0, 0, -1], dtype=np.float32))  # 零末端增量并张开夹爪，不计入策略步数
            if done:  # 等待期间结束时不继续向已结束环境发送动作
                raise RuntimeError(f"初始化等待第 {wait_step + 1} 步返回 done，尚未开始策略评估")  # 异常退出，不写成普通任务失败
        initial_success = bool(env.check_success())  # 等待结束后单独检查初始成功状态
        observation = convert_observation(obs)  # 转为训练方向图像和原始尺度状态
        frame = make_frame(observation)  # 构造等待结束后的初始双相机画面
        imageio.imwrite(output_dir / "initial_frame.png", frame)  # 保存策略执行前的并排图像
        writer = imageio.get_writer(str(output_dir / "rollout.mp4"), format="FFMPEG", mode="I", fps=control_freq)  # 按仿真时间播放速度逐帧编码视频
        writer.append_data(frame)  # 视频包含初始帧，不把全部帧留在内存
        queue = deque()  # 创建动作队列，不做时间集成
        success = initial_success  # 初始已成功时不执行策略
        stop_reason = "initial_success" if initial_success else "max_steps"  # 区分初始成功与策略执行后的结果
        print("策略循环开始，initial_success:", initial_success, "checkpoint step:", policy.step, flush=True)  # 标记策略阶段起点
        started = time.perf_counter()  # 墙钟计时包含循环内推理、控制和视频写入
        while num_steps < args.max_steps and not success:  # 最多执行指定步数，初始成功时直接跳过
            if not queue:  # 队列用完后根据最新观测重新预测
                block = policy.predict(**observation)[0]  # 取得完整原始尺度动作块
                policy_queries += 1  # 每次模型调用只计一次查询
                queue.extend(block[:args.action_steps].unbind(0))  # 只放入指定数量的逐步动作
            predicted = queue.popleft().detach().to(device="cpu", dtype=torch.float32).numpy().copy()  # 每步仅取一个动作并转换为独立 NumPy float32 数组
            if not np.isfinite(predicted).all():  # 禁止将 NaN 或 Inf 传入环境
                raise ValueError(f"策略第 {num_steps + 1} 步动作含 NaN 或 Inf: {predicted}")  # 保留原始错误，不自动修补
            executed = np.clip(predicted, low, high).astype(np.float32)  # 按实际边界裁剪，不添加其他动作变换
            obs, reward, done, _ = env.step(executed)  # 一次只执行队列中的一个动作
            success = bool(env.check_success())  # 每次执行后单独读取官方成功判定
            predicted_actions.append(predicted.copy())  # 保存本次实际取出并执行的裁剪前动作
            executed_actions.append(executed.copy())  # 保存对应的实际控制动作
            num_steps += 1  # 仅对成功返回的控制步计数
            clipped_steps += int(np.any(predicted != executed))  # 统计至少一个元素被裁剪的控制步
            observation = convert_observation(obs)  # 最新观测同时用于下一次查询和视频
            writer.append_data(make_frame(observation))  # 逐帧写入动作后的训练方向画面，计入墙钟耗时
            if success:  # 成功优先于 done 和步数上限
                stop_reason = "success"  # 明确由官方成功判定结束
            elif done:  # 环境结束且未成功时停止
                stop_reason = "done"  # 不从 done 推断成功
            print(f"step={num_steps}, queries={policy_queries}, reward={reward}, done={done}, success={success}", flush=True)  # 记录每个控制步的实际状态
            if success or done:  # 满足结束条件立即退出，不补齐动作队列
                break  # 不重置或开始第二回合
        wall_seconds = time.perf_counter() - started  # 记录完整策略循环耗时，不称为纯推理耗时
    finally:  # 发生异常时仍释放已成功创建的资源，不吞掉原始异常
        try:  # 即使视频关闭失败也尝试关闭环境
            if writer is not None:  # 只关闭已创建的视频写入器
                writer.close()  # 完成编码并释放视频资源
        finally:  # 始终尝试释放环境资源
            if env is not None:  # 只关闭成功创建的环境
                env.close()  # 释放仿真和渲染资源
                print("环境已关闭", flush=True)  # 明确记录关闭完成
    np.savez(  # 仅在正常结束后保存动作记录，异常不会伪装为普通失败
        output_dir / "actions.npz",  # 保存到本回合新目录
        predicted_actions=np.asarray(predicted_actions, dtype=np.float32).reshape(-1, 7),  # 零步时也保持 [0, 7]
        executed_actions=np.asarray(executed_actions, dtype=np.float32).reshape(-1, 7),  # 保存同形状的裁剪后动作
    )  # 完成动作记录保存
    result = {  # 保存本回合配置、来源和结果，不解释为多回合成功率
        "checkpoint": str(checkpoint_path),  # 记录本次使用的权重绝对路径
        "checkpoint_step": policy.step,  # 记录权重对应的训练更新次数
        "suite": suite_name, "task_name": task_name, "task_id": task_id,  # 明确套件编号不同于数据集编号
        "supported_task_only": "libero_goal / put_the_bowl_on_the_plate",  # 记录当前脚本仅支持的任务范围
        "task_config": str(Path(args.task_config).resolve()), "dataset_task_index": task_config["dataset"]["task_index"],  # 保存本次数据任务配置来源
        "initial_state_index": args.initial_state_index, "seed": args.seed,  # 记录固定场景与种子
        "control_freq": control_freq, "num_steps_wait": num_steps_wait,  # 等待动作不计入策略步数
        "chunk_size": chunk_size, "action_steps": args.action_steps, "max_steps": args.max_steps,  # 记录实际动作队列参数
        "render_backend": backend["MUJOCO_GL"], "PYOPENGL_PLATFORM": backend["PYOPENGL_PLATFORM"],  # 记录实际启动的渲染后端设置
        "NUMBA_DISABLE_JIT": int(numba.config.DISABLE_JIT), "device": str(policy.device),  # 记录实际 JIT 开关和推理设备
        "initial_success": initial_success, "success": success, "stop_reason": stop_reason,  # 初始成功不代表策略完成任务
        "num_steps": num_steps, "policy_queries": policy_queries, "clipped_steps": clipped_steps,  # 记录实际控制、查询和裁剪次数
        "wall_seconds": wall_seconds,  # 包含推理、环境执行和循环内视频写入的墙钟耗时
    }  # 完成正常回合的结果字典
    with (output_dir / "result.json").open("w", encoding="utf-8") as file:  # 使用 UTF-8 保存结果
        json.dump(result, file, ensure_ascii=False, indent=2)  # 保留中文并格式化 JSON
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)  # 打印完整运行结果
    print("输出目录:", output_dir, "；单回合行为观察，不代表多回合成功率。", flush=True)  # 明确结论边界


if __name__ == "__main__":  # 标准命令行入口
    main()  # 只执行调用方指定的一个回合
