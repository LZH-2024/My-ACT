import argparse  # 解析窗口和短检查选项
import json  # 保存本轮检查结果，不记录哈希
import time  # 窗口节奏与墙钟计时
from contextlib import nullcontext  # 无窗口时使用相同资源管理结构
from datetime import datetime  # 为检查产物生成独立目录
from pathlib import Path  # 管理配置和图像路径
from zoneinfo import ZoneInfo  # 使用上海时区

import imageio.v3 as iio  # 保存一张原始 RGB 相机图像
import numpy as np  # 构造平滑目标并检查实际状态

from my_act.config import read_yaml  # 复用配置读取
from my_act.sim.env import SO101Sim  # 使用本阶段基础环境


def joint_targets(initial: np.ndarray):
    """一次只改变一个关节；缓慢偏移并返回，不扫完整限位。"""
    for _ in range(20):  # 先保持初始目标一秒，观察重力下的位置伺服
        yield initial.copy(), None
    for index in range(6):
        current = initial.copy()
        values = [initial[index] + 0.12, initial[index]] if index < 5 else [0.7, 0.05, initial[index]]
        for value in values:  # 夹爪单独检查张开、接近闭合和返回，均为转角
            goal = initial.copy()
            goal[index] = value
            for fraction in np.linspace(0.05, 1.0, 20):  # 一秒线性斜坡，避免目标瞬间大幅跳变
                yield current + fraction * (goal - current), None
            for hold in range(5):  # 保持四分之一秒后打印目标和实际值
                yield goal.copy(), index if hold == 4 else None
            current = goal


def main() -> None:
    """显示基础场景或执行短检查；无真实硬件、数据采集和抓取成功判定。"""
    parser = argparse.ArgumentParser(description="SO101 基础场景查看与小幅关节位置检查；从项目根目录运行")
    parser.add_argument("--config", default="configs/tasks/so101_pick_place.yaml", help="基础场景配置")
    parser.add_argument("--headless", action="store_true", help="无窗口运行；渲染后端在启动进程前设置")
    parser.add_argument("--check-joints", action="store_true", help="依次检查五个臂关节和夹爪，完成后退出")
    parser.add_argument("--steps", type=int, help="最多控制步数；无窗口默认20步，关节检查默认完整短序列，窗口默认等关闭")
    parser.add_argument("--save-image", action="store_true", help="保存一次初始相机 RGB 图像")
    args = parser.parse_args()
    if args.steps is not None and args.steps < 1:
        parser.error("--steps 必须为正整数")
    output_dir = Path("outputs/sim_checks") / datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S_%f")
    output_dir.mkdir(parents=True, exist_ok=False)  # 保留每次检查产物，不覆盖
    print("output_dir:", output_dir.resolve(), flush=True)
    env = SO101Sim(read_yaml(args.config))
    try:
        obs = env.reset()
        print("关节顺序:", env.joint_names, "单位: rad", flush=True)
        print("目标下限:", env.low, "目标上限:", env.high, flush=True)
        print("初始实际状态:", obs["state"], "图像:", obs["images"].shape, obs["images"].dtype, flush=True)
        print("control_freq:", env.control_freq, "physics_timestep:", env.model.opt.timestep, "substeps:", env.substeps, flush=True)
        if args.save_image:
            iio.imwrite(output_dir / "camera_initial.png", obs["images"][0])
        context = nullcontext(None)
        if not args.headless:
            import mujoco.viewer  # 仅窗口模式导入 viewer，不修改进程环境变量
            context = mujoco.viewer.launch_passive(env.model, env.data)
        initial_base = env.data.body("base").xpos.copy()
        initial_rotation = env.data.body("base").xquat.copy()
        previous = obs["state"].copy()
        max_change, max_penetration, base_drift = 0.0, 0.0, 0.0
        records = []
        steps = 0
        limit = args.steps if args.steps is not None else (20 if args.headless and not args.check_joints else None)
        targets = iter(joint_targets(env.initial_positions)) if args.check_joints else None
        started = time.perf_counter()
        with context as viewer:  # 关闭窗口或异常时都释放 viewer
            if viewer is not None:
                with viewer.lock():
                    viewer.cam.lookat[:] = [0.18, 0, 0.18]
                    viewer.cam.distance = 1.15
                    viewer.cam.azimuth = 135
                    viewer.cam.elevation = -25
                viewer.sync()
                print("GUI 已创建；请目视检查关节运动，关闭窗口可提前结束。", flush=True)
            while limit is None or steps < limit:
                if viewer is not None and not viewer.is_running():
                    break
                if targets is None:
                    target, report_index = env.initial_positions, None
                else:
                    item = next(targets, None)
                    if item is None:
                        break
                    target, report_index = item
                tick = time.perf_counter()
                with viewer.lock() if viewer is not None else nullcontext():
                    obs = env.step(target)
                steps += 1
                max_change = max(max_change, float(np.max(np.abs(obs["state"] - previous))))
                previous = obs["state"].copy()
                base_drift = max(base_drift, float(np.max(np.abs(env.data.body("base").xpos - initial_base))), float(np.max(np.abs(env.data.body("base").xquat - initial_rotation))))
                max_penetration = max(max_penetration, max((-float(c.dist) for c in env.data.contact), default=0.0))
                if report_index is not None:
                    record = {"joint": env.joint_names[report_index], "target": float(target[report_index]), "actual": float(obs["state"][report_index])}
                    records.append(record)
                    print(record, flush=True)
                if viewer is not None:
                    viewer.sync()
                    time.sleep(max(0.0, 1.0 / env.control_freq - (time.perf_counter() - tick)))  # 只调节显示节奏，不改变物理步数
        result = {"control_steps": steps, "sim_seconds": obs["timestamp"], "wall_seconds": time.perf_counter() - started,
                  "joint_names": list(env.joint_names), "state": obs["state"].tolist(), "state_finite": bool(np.isfinite(obs["state"]).all()),
                  "image_shape": list(obs["images"].shape), "image_dtype": str(obs["images"].dtype),
                  "max_control_step_joint_change_rad": max_change, "max_contact_penetration_m": max_penetration,
                  "base_pose_max_change": base_drift, "joint_checks": records}
        with (output_dir / "check.json").open("w", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=2)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    finally:
        env.close()  # 保证正常退出和 Python 异常时关闭相机渲染器


if __name__ == "__main__":
    main()
