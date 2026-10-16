"""查看 SO101 桌面场景；仅保持初始姿态，不执行任务策略。"""

import argparse
from pathlib import Path
import time

import imageio.v3 as iio
import mujoco
import numpy as np
from my_act.sim.scene import INITIAL_TARGETS, reset_scene


def save_image(model: mujoco.MjModel, data: mujoco.MjData, path: Path) -> None:
    """仅按请求渲染一次固定相机 RGB 图像，保存后释放渲染资源。"""
    renderer = mujoco.Renderer(model, height=480, width=640)
    try:
        renderer.update_scene(data, camera="overview")
        image = renderer.render()  # 原始输出为 H×W×3 的 RGB uint8，不做训练预处理。
        path.parent.mkdir(parents=True, exist_ok=True)
        iio.imwrite(path, image)
        print(f"相机图像：{path.resolve()}，shape={image.shape}，dtype={image.dtype}")
    finally:
        renderer.close()


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
    model = mujoco.MjModel.from_xml_path(str(args.scene.resolve()))
    data = mujoco.MjData(model)
    reset_scene(model, data)
    print(f"MuJoCo {mujoco.__version__}，nq={model.nq}，nv={model.nv}，nu={model.nu}", flush=True)
    print(f"物理时间步={model.opt.timestep} 秒，保持目标(rad)={INITIAL_TARGETS}", flush=True)
    completed = 0
    if args.headless:
        for _ in range(steps):
            mujoco.mj_step(model, data)  # 正常步进只由执行器和动力学更新状态。
            completed += 1
    else:
        from mujoco import viewer as mj_viewer  # 无窗口且不保存图像时，无需创建图形上下文。

        with mj_viewer.launch_passive(model, data) as viewer:
            print("交互窗口已打开，可拖动视角或关闭窗口退出。", flush=True)
            with viewer.lock():
                viewer.cam.lookat[:] = [0.19, 0.0, 0.10]
                viewer.cam.distance = 0.85
                viewer.cam.azimuth = -55
                viewer.cam.elevation = -32
            while viewer.is_running() and (steps is None or completed < steps):
                started = time.perf_counter()
                count = 10 if steps is None else min(10, steps - completed)
                for _ in range(count):  # 每次固定推进若干物理步；不随墙钟抖动改变物理步长。
                    mujoco.mj_step(model, data)
                completed += count
                viewer.sync()  # 每批刷新窗口，不每个物理步生成相机图像。
                time.sleep(max(0.0, count * model.opt.timestep - (time.perf_counter() - started)))
        print("交互窗口已关闭。", flush=True)
    mujoco.mj_forward(model, data)  # 更新最终位置对应的观测，未推进额外时间。
    finite = all(np.isfinite(x).all() for x in (data.qpos, data.qvel, data.qacc))
    print(f"完成物理步数={completed}，仿真时间={data.time:.3f} 秒，状态有限={finite}")
    if not finite:
        raise RuntimeError("仿真状态出现 NaN 或 Inf")
    for name, target in INITIAL_TARGETS.items():
        actual = data.qpos[int(model.joint(name).qposadr[0])]
        print(f"{name}: 目标={target:.6f} rad，实际={actual:.6f} rad")
    print(f"方块中心={data.body('red_cube').xpos}，底座位置={data.body('base').xpos}")
    if args.save_image is not None:
        save_image(model, data, args.save_image)


if __name__ == "__main__":
    main()
