"""查看 SO101 桌面场景；仅保持初始姿态，不执行任务策略。"""

import argparse
from pathlib import Path
import time

import imageio.v3 as iio
import mujoco
import numpy as np


from my_act.sim.env import SO101Sim, INITIAL_TARGETS


def save_image(sim: SO101Sim, path: Path) -> None:
    """仅按请求渲染一次固定相机 RGB 图像，资源由仿真对象统一关闭。"""
    image = sim.camera_image()
    path.parent.mkdir(parents=True, exist_ok=True)
    iio.imwrite(path, image)
    print(f"相机图像：{path.resolve()}，shape={image.shape}，dtype={image.dtype}")


def main() -> None:
    """加载场景并有限步进或交互查看，物理推进独立于窗口刷新。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, default=Path("assets/scenes/so101_pick_place.xml"),
                        help="场景 XML 路径，默认从项目根目录运行")
    parser.add_argument("--headless", action="store_true", help="不打开交互窗口")
    parser.add_argument("--steps", type=int, default=None,
                        help="物理步数；无窗口默认 1000 步，窗口默认运行至用户关闭；0 表示只看初始状态")
    parser.add_argument("--save-image", type=Path, help="退出前保存一次固定相机 PNG 的路径")
    args = parser.parse_args()
    if args.steps is not None and args.steps < 0:
        parser.error("--steps 不能小于 0")
    steps = 1000 if args.headless and args.steps is None else args.steps
    sim = SO101Sim(args.scene)
    try:
        model, data = sim.model, sim.data
        print(f"MuJoCo {mujoco.__version__}，nq={model.nq}，nv={model.nv}，nu={model.nu}", flush=True)
        print(f"物理时间步={model.opt.timestep} 秒，保持目标(rad)={INITIAL_TARGETS}", flush=True)
        completed = 0
        if args.headless:
            sim.advance(steps)
            completed = steps
        else:
            viewer = sim.open_viewer()
            print("交互窗口已打开，可拖动视角或关闭窗口退出。", flush=True)
            while viewer.is_running() and (steps is None or completed < steps):
                started = time.perf_counter()
                count = 10 if steps is None else min(10, steps - completed)
                sim.advance(count)  # 仅控制 GUI 批次；不改变每个物理步的时间。
                completed += count
                viewer.sync()
                time.sleep(max(0.0, count * model.opt.timestep - (time.perf_counter() - started)))
        finite = all(np.isfinite(x).all() for x in (data.qpos, data.qvel, data.qacc))
        print(f"完成物理步数={completed}，仿真时间={data.time:.3f} 秒，状态有限={finite}")
        for name, actual in zip(INITIAL_TARGETS, sim.joint_positions()):
            print(f"{name}: 目标={INITIAL_TARGETS[name]:.6f} rad，实际={actual:.6f} rad")
        print(f"方块中心={data.body('red_cube').xpos}，底座位置={data.body('base').xpos}")
        if args.save_image is not None:
            save_image(sim, args.save_image)
    finally:
        sim.close()


if __name__ == "__main__":
    main()
