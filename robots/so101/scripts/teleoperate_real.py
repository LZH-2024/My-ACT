"""真实 SO101 主从遥操作；从臂校准核对通过且现场输入 START 后才允许写入。"""

import argparse
import math
from pathlib import Path
import select
import signal
import sys
import time

from my_act.hardware.so101.calibration import MOTORS
from my_act.hardware.so101.real_teleop import (
    FollowerArm, ReadOnlyArm, check_distinct_ports, check_read_jump,
    load_arm_calibration, normalize_positions, plan_targets,
)


def print_preview(leader, follower, leader_counts, follower_counts, goals, mapped, range_limited, relative_limited):
    """展示同单位下的主臂目标、从臂当前姿态及差值；夹爪单位单独标注。"""
    present = normalize_positions(follower_counts, follower.calibration)
    print("关节 | 单位 | 主臂映射目标 | 从臂当前 | 差值 | 本周期限制后目标计数", flush=True)
    for name in MOTORS:
        unit = "百分点" if name == "gripper" else "度"
        print(f"{name} | {unit} | {mapped[name]:.3f} | {present[name]:.3f} | "
              f"{mapped[name] - present[name]:+.3f} | {goals[name]}", flush=True)
    outside = [n for n in MOTORS if not leader.calibration[n]["range_min"] <= leader_counts[n] <= leader.calibration[n]["range_max"]]
    print(f"从臂范围限幅={range_limited}；反馈相对限制={relative_limited}；主臂超采集范围提示={outside}", flush=True)


def follow_loop(leader, follower, args):
    """逐周期使用双方新反馈；按回车或 Ctrl+C 正常停止，不缓存失败读数。"""
    previous_leader = previous_follower = None
    last_display = time.perf_counter()
    interval_steps = 0
    print("正在跟随。按回车或 Ctrl+C 停止跟随，随后按提示托住从臂并关闭扭矩。", flush=True)
    try:
        while True:
            started = time.perf_counter()
            if select.select([sys.stdin], [], [], 0)[0]:
                if sys.stdin.readline() == "":
                    raise EOFError("终端输入已关闭")
                return "用户按回车停止"
            leader_counts = leader.positions(expected_torque=0)
            follower_counts = follower.positions(expected_torque=1)
            check_read_jump(leader_counts, previous_leader, "leader")
            check_read_jump(follower_counts, previous_follower, "follower")
            goals, mapped, range_limited, relative_limited = plan_targets(
                leader_counts, leader.calibration, follower_counts, follower.calibration,
                args.max_relative_target_deg, args.max_gripper_target_percent,
            )
            # 完整读数与全部目标检查通过才发送；从臂失败时不能继续发送余下运动目标。
            follower.write_goals(goals)
            previous_leader, previous_follower = leader_counts, follower_counts
            interval_steps += 1
            now = time.perf_counter()
            if now - last_display >= 1.0:
                print(f"双臂通信正常；实际跟随频率={interval_steps / (now - last_display):.1f} Hz，"
                      f"设定={args.frequency:g} Hz；范围限幅={range_limited}；相对限制={relative_limited}", flush=True)
                last_display, interval_steps = now, 0
            time.sleep(max(0.0, 1.0 / args.frequency - (time.perf_counter() - started)))
    except KeyboardInterrupt:
        return "用户 Ctrl+C 停止"  # 仅循环内的 Ctrl+C 走正常托住确认流程。


def report_disable(failures):
    """以写入和回读结果说明关扭矩状态，不将断连描述为已安全停止。"""
    if failures:
        print("无法确认全部从臂扭矩已关闭：\n" + "\n".join(failures), file=sys.stderr, flush=True)
        print("断连或设备无响应时无法保证关闭扭矩，请现场处置；没有继续发送运动目标。", file=sys.stderr, flush=True)
    else:
        print("已逐关节回读确认从臂六个 Torque_Enable=0。主臂设置未改变。", flush=True)


def run_session(leader, follower, args):
    """执行只读门禁、确认、保持目标初始化和退出流程；所有路径释放两条串口。"""
    torque_may_be_on = False
    try:
        if not args.preview and not sys.stdin.isatty():
            raise ValueError("真实运动必须由用户在交互终端现场确认，不接受重定向自动输入 START")
        leader.open()
        follower.open()
        leader.verify()
        follower.verify()  # 包括从臂已有扭矩为 0；已有扭矩非零时只报告，不接管或关闭。
        leader_counts = leader.positions(expected_torque=0)
        follower_counts = follower.positions(expected_torque=0)
        plan = plan_targets(leader_counts, leader.calibration, follower_counts, follower.calibration,
                            args.max_relative_target_deg, args.max_gripper_target_percent)
        print("双臂偏置、限位、ID、型号、工作模式及必要反馈设置回读一致；没有写入。", flush=True)
        print_preview(leader, follower, leader_counts, follower_counts, *plan)
        if args.preview:
            print("只读预览完成：未预写目标、未开关扭矩、未执行运动。", flush=True)
            return
        print("请确认串口对应的实物身份，周围空间足够，并托稳从臂。", flush=True)
        print("START 后会重新核对并读取从臂当前位置，预写同位置目标并回读，再逐关节启用扭矩。", flush=True)
        print(f"每次目标距从臂当前反馈最多 {args.max_relative_target_deg:g} 度；夹爪最多 "
              f"{args.max_gripper_target_percent:g} 个百分点。这不是速度/力矩保证或碰撞规避。", flush=True)
        print("异常时将停止新目标并尽力关闭从臂扭矩，从臂可能失去支撑；断连时不能保证关闭。", flush=True)
        if input("输入 START 并回车才启用；其他输入取消：").strip() != "START":
            print("已取消，没有写入任何寄存器。", flush=True)
            return
        # 用户可能在确认期间移动设备，不能使用确认前的旧姿态或核验结果。
        leader.verify()
        follower.verify()
        holding_positions = follower.initialize_hold()
        torque_may_be_on = True  # 首次开扭矩写入前标记，覆盖写成功但响应丢失及部分启用。
        follower.enable_torque(holding_positions)
        reason = follow_loop(leader, follower, args)
        print(f"{reason}：已停止发送跟随目标，从臂暂时保持最后目标。", flush=True)
        while input("请先托住从臂；输入 OFF 并回车关闭从臂扭矩：").strip() != "OFF":
            print("尚未确认关闭，仍保持最后目标；请托住后输入 OFF。", flush=True)
        # 清理只执行一轮，每个 ID 都尝试；有失败则报告，不能自动无限重试。
        torque_may_be_on = False
        failures = follower.disable_torque()
        report_disable(failures)
        if failures:
            raise RuntimeError("正常退出时未能确认全部从臂扭矩关闭")
    except BaseException:
        if torque_may_be_on:
            print("异常退出：停止新运动目标，正在尽力关闭从臂扭矩；臂体可能失去支撑。", file=sys.stderr, flush=True)
            report_disable(follower.disable_torque())
        raise  # 保留原始通信异常、终端关闭或用户中断信息。
    finally:
        for arm in (follower, leader):
            try:
                arm.close()
            except Exception as error:
                print(f"{arm.role} 串口关闭失败：{error}", file=sys.stderr, flush=True)


def main() -> None:
    """读取角色隔离的配置；不缺省校准、不安装依赖、不导入仿真模块。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--leader-port", default="/dev/ttyACM0")
    parser.add_argument("--follower-port", default="/dev/ttyACM1")
    parser.add_argument("--leader-name", default="leader01")
    parser.add_argument("--follower-name", default="follower01")
    parser.add_argument("--leader-calibration-file", type=Path,
                        default=Path("robots/so101/calibration/leader/leader01/calibration.json"))
    parser.add_argument("--follower-calibration-file", type=Path,
                        default=Path("robots/so101/calibration/follower/follower01/calibration.json"))
    parser.add_argument("--baudrate", type=int, default=1_000_000)
    parser.add_argument("--frequency", type=float, default=20.0, help="期望控制频率 Hz，默认 20；不保证实际吞吐量")
    parser.add_argument("--max-relative-target-deg", type=float, default=2.0,
                        help="每次目标相对从臂当前反馈的最大偏差，五个臂关节单位为度，默认 2")
    parser.add_argument("--max-gripper-target-percent", type=float, default=2.0,
                        help="每次夹爪目标相对当前开度的最大偏差，单位为百分点，默认 2")
    parser.add_argument("--preview", action="store_true", help="一次双臂只读核验与转换预览，不写目标或扭矩")
    args = parser.parse_args()
    if any(not math.isfinite(v) or v <= 0 for v in
           (args.frequency, args.max_relative_target_deg, args.max_gripper_target_percent)):
        parser.error("控制频率和目标变化限制必须为有限正数")
    root = Path(__file__).resolve().parents[1] / "calibration"
    try:
        leader_calibration = load_arm_calibration(root, "leader", args.leader_name, args.leader_calibration_file)
        follower_calibration = load_arm_calibration(root, "follower", args.follower_name, args.follower_calibration_file)
        check_distinct_ports(args.leader_port, args.follower_port)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    leader = ReadOnlyArm(args.leader_port, args.baudrate, leader_calibration, "leader")
    follower = FollowerArm(args.follower_port, args.baudrate, follower_calibration, preview=args.preview)

    def terminal_closed(signum, frame):
        """终端挂断/终止信号走异常关闭；SIGKILL、断电等无法由 Python 清理。"""
        raise RuntimeError(f"收到终止信号 {signum}")

    original = {sig: signal.getsignal(sig) for sig in (signal.SIGHUP, signal.SIGTERM)}
    try:
        for sig in original:
            signal.signal(sig, terminal_closed)
        run_session(leader, follower, args)
    finally:
        for sig, handler in original.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    main()
