"""只读 SO101 主臂，让仿真六个关节跟随；可单独检查指定关节。"""

import argparse
from contextlib import nullcontext
import json
from pathlib import Path
from threading import Event
import time

import mujoco
import numpy as np

from my_act.hardware.so101.calibration import CalibrationBus, MOTORS, validate_calibration
from my_act.sim.scene import reset_scene

JOINTS = tuple(MOTORS)  # 底座、肩部、肘部、腕俯仰、腕旋转、夹爪。
CONTROL_PERIOD = 0.05  # 20 Hz，每周期推进固定数量的物理步。
START_SPEED = 0.5  # 仅启动同步限速 0.5 rad/s，随后直接跟随，不持续滤波。
MAX_JUMP = 0.35  # 相邻采样变化超过约 20° 就停止，用于缓慢跟随检查。
LIMIT_TOLERANCE = 0.10  # 除腕俯仰外，模型限位外超过约 5.7° 则拒绝。
COUNT_TOLERANCE = 32  # 除腕俯仰外，采集边界容许小偏差，不修改校准记录。


def count_to_radians(count: float, direction: int, calibration: dict) -> float:
    """五个臂关节以各自行程中点对应零位，不拉伸到模型限位。"""
    midpoint = (calibration["range_min"] + calibration["range_max"]) / 2
    # 沿用 LeRobot degrees 的比例；反馈已包含硬件偏置，不重复减 Homing_Offset。
    return direction * (count - midpoint) * (2.0 * np.pi / 4095)


def map_counts(counts, calibration, reverse_joints, lower, upper):
    """完整读数转为六维 rad 目标；夹爪按开度换算，保留裁剪前值。"""
    raw = []
    for index, name in enumerate(JOINTS):
        row, count = calibration[name], counts[name]
        if not np.isfinite(count):
            raise ValueError(f"{name} 读数 {count} 非有限，停止。")
        if name == "wrist_flex":
            # 当前单圈反馈约定为 0～4095；采集行程不是硬限位，超出时由终端提示。
            if not 0 <= count <= 4095:
                raise ValueError(f"{name} 读数 {count} 超出单圈反馈范围 0～4095，停止。")
        elif not row["range_min"] - COUNT_TOLERANCE <= count <= row["range_max"] + COUNT_TOLERANCE:
            raise ValueError(f"{name} 读数 {count} 明显超出校准范围，停止。")
        if name == "gripper":
            # LeRobot 使用开度比例；本次约定最小计数闭合、最大计数张开，需目视核对。
            opening = (count - row["range_min"]) / (row["range_max"] - row["range_min"])
            if name in reverse_joints:
                opening = 1.0 - opening
            target = opening * upper[index]  # 0 rad 闭合参考到模型最大正角度开口。
        else:
            target = count_to_radians(count, -1 if name in reverse_joints else 1, row)
        # 腕俯仰有效读数可以超出模型行程：保留原目标并限幅显示，不因此退出。
        # 上面的读数检查及主循环的突变检查仍生效，不放宽其他关节。
        if name != "wrist_flex" and not lower[index] - LIMIT_TOLERANCE <= target <= upper[index] + LIMIT_TOLERANCE:
            raise ValueError(f"{name} 映射目标 {target:.6f} rad 明显超出允许范围 "
                             f"[{lower[index]:.6f}, {upper[index]:.6f}]，停止。")
        raw.append(target)
    raw = np.asarray(raw, dtype=np.float64)
    return raw, np.clip(raw, lower, upper)


def read_counts(bus):
    """全部读取成功才返回；不以零或旧读数代替失败关节，不写寄存器。"""
    for name in JOINTS:
        if bus.read(name, "Torque_Enable") != 0:
            raise RuntimeError(f"{name} 扭矩已开启，退出；程序不会改变扭矩。")
    return bus.positions()  # 复用现有有限超时、符号解码和错误处理。


def print_targets(counts, calibration, raw, command, actual, targets):
    """低频显示六关节读数、未裁剪映射、执行目标和仿真实际角度。"""
    for index, name in enumerate(JOINTS):
        row = calibration[name]
        print(f"{name:14} 计数={counts[name]:7g} 映射={np.degrees(raw[index]):8.3f}° "
              f"执行目标={np.degrees(command[index]):8.3f}° 实际={np.degrees(actual[index]):8.3f}° "
              f"限位裁剪={raw[index] != targets[index]} "
              f"超采集范围={not row['range_min'] <= counts[name] <= row['range_max']}", flush=True)


def main() -> None:
    """核对六关节后，由用户按空格开始跟随；退出始终关闭串口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyACM0", help="主臂串口；只读，不写舵机寄存器")
    parser.add_argument("--baudrate", type=int, default=1000000, help="主机串口波特率，默认 1000000")
    parser.add_argument("--calibration-file", type=Path,
                        default=Path("robots/so101/calibration/leader/leader01/calibration.json"))
    parser.add_argument("--scene", type=Path, default=Path("assets/scenes/so101_pick_place.xml"))
    parser.add_argument("--joint", choices=JOINTS, help="只跟随指定关节；省略时全部六关节跟随")
    parser.add_argument("--reverse-joints", nargs="+", choices=JOINTS, default=[],
                        help="反转指定关节；夹爪反转开合，其余反转角度符号，只影响仿真")
    parser.add_argument("--headless", action="store_true", help="有限步检查，不开窗口，直接开始")
    parser.add_argument("--steps", type=int, help="最多执行的控制周期数；窗口默认直到关闭")
    args = parser.parse_args()
    if args.steps is not None and args.steps <= 0:
        parser.error("--steps 必须为正数")
    if args.headless and args.steps is None:
        parser.error("无窗口检查必须指定 --steps，不能无限后台运行")
    with args.calibration_file.open(encoding="utf-8") as stream:
        calibration = json.load(stream)
    validate_calibration(calibration)
    model = mujoco.MjModel.from_xml_path(str(args.scene.resolve()))
    data = mujoco.MjData(model)
    reset_scene(model, data)
    substeps = round(CONTROL_PERIOD / model.opt.timestep)
    if substeps < 1 or not np.isclose(substeps * model.opt.timestep, CONTROL_PERIOD):
        raise ValueError("场景物理时间步必须整除 0.05 秒控制周期")
    joints = [model.joint(name) for name in JOINTS]
    actuators = [model.actuator(name) for name in JOINTS]
    lower = np.array([max(j.range[0], a.ctrlrange[0]) for j, a in zip(joints, actuators)])
    upper = np.array([min(j.range[1], a.ctrlrange[1]) for j, a in zip(joints, actuators)])
    gripper_index = JOINTS.index("gripper")
    if not lower[gripper_index] <= 0 < upper[gripper_index]:
        raise ValueError("当前模型不支持夹爪 0 rad 闭合参考及正角度开口")
    lower[gripper_index] = 0  # 不使用负角度余量强压夹爪闭合。
    qpos_addresses = np.array([int(j.qposadr[0]) for j in joints])
    actuator_ids = np.array([a.id for a in actuators])  # 按名称绑定，避免误操作方块自由关节。
    selected = np.array([args.joint is None or name == args.joint for name in JOINTS])
    initial_targets = data.ctrl[actuator_ids].copy()
    bus = CalibrationBus(args.port, args.baudrate)
    try:
        bus.open()
        for name, motor_id in MOTORS.items():
            for register, expected in {
                "ID": motor_id, "Model_Number": 777, "Operating_Mode": 0, "Torque_Enable": 0,
                "Homing_Offset": calibration[name]["homing_offset"],
                "Min_Position_Limit": calibration[name]["range_min"],
                "Max_Position_Limit": calibration[name]["range_max"],
            }.items():
                actual = bus.read(name, register)
                if actual != expected:
                    raise RuntimeError(f"{name}/{register}: 实际 {actual}，预期 {expected}；停止，不修复。")
            if bus.read(name, "Phase") & (1 << 4):
                raise RuntimeError(f"{name} Phase bit 4 与校准后的反馈约定不同，停止。")
        counts = read_counts(bus)
        raw, targets = map_counts(counts, calibration, args.reverse_joints, lower, upper)
        print(f"只读 ID 1～6；跟随={args.joint or '全部六关节'}；反向={args.reverse_joints}；20 Hz，每周期 {substeps} 个物理步。", flush=True)
        for name in JOINTS[:-1]:
            midpoint = (calibration[name]["range_min"] + calibration[name]["range_max"]) / 2
            print(f"{name} 行程中点 {midpoint:g} → 0°", flush=True)
        print(f"夹爪测试约定：开度 0～100% → 0～{np.degrees(upper[gripper_index]):.3f}°；开合方向待人工确认。", flush=True)
        print_targets(counts, calibration, raw, initial_targets, data.qpos[qpos_addresses], targets)
        start = Event()
        if args.headless:
            start.set()
            window = nullcontext(None)
        else:
            from mujoco import viewer as mj_viewer

            def on_key(key):
                """空格只发出开始信号，串口仍由主线程访问。"""
                if key == 32:
                    start.set()

            window = mj_viewer.launch_passive(model, data, key_callback=on_key)
        with window as viewer:
            if viewer is not None:
                with viewer.lock():
                    viewer.cam.lookat[:] = [0.19, 0.0, 0.10]
                    viewer.cam.distance, viewer.cam.azimuth, viewer.cam.elevation = 0.85, -55, -32
                print("点击窗口后按空格开始；先保持实物不动，等待启动同步完成，再逐关节小幅移动。关闭窗口或 Ctrl+C 退出。", flush=True)
            completed, previous, transitioning = 0, None, True
            last_print = -float("inf")
            while (args.steps is None or completed < args.steps) and (viewer is None or viewer.is_running()):
                started = time.perf_counter()
                if not start.is_set():
                    viewer.sync()
                    time.sleep(CONTROL_PERIOD)
                    continue
                counts = read_counts(bus)
                raw, targets = map_counts(counts, calibration, args.reverse_joints, lower, upper)
                if previous is not None and np.any(np.abs(raw - previous) > MAX_JUMP):
                    changed = [name for name, jump in zip(JOINTS, np.abs(raw - previous)) if jump > MAX_JUMP]
                    raise RuntimeError(f"{changed} 读数突变超过 0.35 rad，停止；腕旋转跨计数边界也停止，不绕回整圈目标。")
                previous = raw
                target = np.where(selected, targets, initial_targets)
                if transitioning:
                    current = data.ctrl[actuator_ids].copy()
                    command = current + np.clip(target - current, -START_SPEED * CONTROL_PERIOD, START_SPEED * CONTROL_PERIOD)
                    if np.all(np.abs(command - target) < 1e-9):
                        transitioning = False
                        print("启动同步完成，现在跟随选定关节。", flush=True)
                else:
                    command = target
                data.ctrl[actuator_ids] = command  # 只改变执行器目标，正常运行绝不覆盖 qpos。
                mujoco.mj_step(model, data, nstep=substeps)
                if not all(np.isfinite(v).all() for v in (data.qpos, data.qvel, data.qacc)):
                    raise RuntimeError("仿真状态出现非有限数值，停止。")
                completed += 1
                if viewer is not None:
                    viewer.sync()
                if started - last_print >= 1.0 or completed == args.steps:
                    print_targets(counts, calibration, raw, command, data.qpos[qpos_addresses], targets)
                    last_print = started
                time.sleep(max(0.0, CONTROL_PERIOD - (time.perf_counter() - started)))
            print(f"结束：完成 {completed} 个控制周期；未写入真实舵机寄存器。", flush=True)
    finally:
        bus.close()  # 通信失败、窗口关闭及 Ctrl+C 均只释放串口，不恢复或修改舵机设置。


if __name__ == "__main__":
    main()
