"""真实 SO101 主臂只读遥操作仿真；首次用 --align 现场确认方向和参考姿态。"""

import argparse
import math
from pathlib import Path
import select
import sys
import time
import numpy as np
import yaml
from my_act.config import read_yaml
from my_act.hardware.so101.leader import SO101Leader
from my_act.hardware.so101.mapping import JointMapping, count_delta, validate_config
from my_act.sim.env import SO101Sim, JOINT_NAMES


def ask(viewer, prompt: str) -> str:
    """等待终端输入时暂停物理推进，同时响应窗口关闭。"""
    print(prompt, flush=True)
    while viewer.is_running():
        viewer.sync()
        if select.select([sys.stdin], [], [], 0.05)[0]:
            line = sys.stdin.readline()
            if not line:
                raise EOFError("终端输入已关闭")
            return line.strip()
    raise InterruptedError("窗口已关闭，取消操作")


def require(viewer, prompt: str, answer: str):
    """需要明确输入指定词，其余输入直接退出，不默认接受。"""
    if ask(viewer, prompt) != answer:
        raise InterruptedError("未确认，已取消")


def preview(sim, target, config):
    """对齐时仅缓慢移动仿真，让用户观察局部正方向或夹爪开口。"""
    start = sim.data.ctrl[sim.actuator_ids].copy()
    duration = max(1.0, float(np.max(np.abs(target - start))) / config['startup_speed_rad_s'])
    steps = math.ceil(duration * sim.control_freq)
    for i in range(steps):
        if not sim.viewer.is_running():
            raise InterruptedError("窗口关闭，停止预览")
        begun = time.perf_counter()
        sim.step(start + (target - start) * ((i + 1) / steps))
        sim.viewer.sync()
        time.sleep(max(0, 1 / sim.control_freq - (time.perf_counter() - begun)))


def align(leader, sim, config, args, path):
    """只记录软件映射，不校准舵机、不写真实寄存器；未全部确认就不保存。"""
    local_root = Path('robots/so101/configs/local').resolve()
    if not path.resolve().is_relative_to(local_root) or path.exists():
        raise ValueError("新对齐文件须在 robots/so101/configs/local/ 内且不存在；不覆盖旧记录")
    arm = {}
    print("本流程不会改硬件零点。先把两臂底座朝向理解为一致，按相对连杆姿态逐轴对齐。", flush=True)
    print("上游坐标说明：https://github.com/TheRobotStudio/SO-ARM100/tree/main/Simulation/SO101", flush=True)
    for i, name in enumerate(JOINT_NAMES[:5]):
        preview(sim, sim.initial_targets, config)
        require(sim.viewer, f"{name}：将主臂该关节摆到与窗口模型 0 rad 相同的相对连杆姿态。"
                "其他轴尽量保持参考姿态；看不清就取消。匹配后输入 MATCH 回车：", 'MATCH')
        reference = float(leader.read()[i])
        target = sim.initial_targets.copy()
        target[i] += config['alignment_preview_rad']
        preview(sim, target, config)
        print(f"{name} 仿真正向目标={target[i]:.4f}，实际={sim.joint_positions()[i]:.4f} rad", flush=True)
        require(sim.viewer, "观察刚才的正向运动；将主臂同一关节从参考位置沿对应方向小幅转动，"
                "保持后输入 MATCH 回车（不是要求计数增加）：", 'MATCH')
        moved = float(leader.read()[i])
        delta = count_delta(moved, reference, config['counts_per_turn']) if name == 'wrist_roll' else moved - reference
        if not config['alignment_min_counts'] <= abs(delta) <= config['alignment_max_counts']:
            raise ValueError(f"{name} 方向采样位移 {delta} 计数无效；本次不保存")
        arm[name] = dict(reference_count=reference, reference_rad=0.0, direction=1 if delta > 0 else -1)
        print(f"{name}: 参考={reference} 计数，方向={arm[name]['direction']:+d}，请手动回到参考姿态。", flush=True)
    preview(sim, sim.initial_targets, config)
    gripper = {}
    for label, word in (('closed', '闭合'), ('open', '张开')):
        target = sim.initial_targets.copy()
        target[5] = config[f'gripper_{label}_rad']
        preview(sim, target, config)
        print(f"夹爪候选目标={target[5]:.4f}，实际={sim.joint_positions()[5]:.4f} rad", flush=True)
        require(sim.viewer, f"确认窗口夹爪是你认可的{word}开口（候选值不保证是物理极限）。"
                f"把实物手柄置于{word}端点，不用力顶止挡；确认输入 MATCH 回车。"
                "若仿真开口不对请取消，调整通用配置候选角度后重新对齐：", 'MATCH')
        gripper[f'{label}_count'] = float(leader.read()[5])
        gripper[f'{label}_rad'] = float(target[5])
    alignment = dict(device_name=args.device_name, role='leader', port=args.port, baudrate=args.baudrate,
                     calibration_file=str(Path(args.calibration_file).resolve()), confirmed_by_user=True,
                     arm=arm, gripper=gripper)
    JointMapping(config, alignment, leader.calibration, sim.limits)
    print(yaml.safe_dump(alignment, allow_unicode=True, sort_keys=False), flush=True)
    require(sim.viewer, "方向/参考姿态和夹爪端点都已现场确认，输入 SAVE 保存本机映射；否则取消：", 'SAVE')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        f.write("# 现场对齐记录：计数已包含内部偏置；角度单位 rad。重新校准或换设备后须重新对齐。\n")
        yaml.safe_dump(alignment, f, allow_unicode=True, sort_keys=False)
    print(f"已保存 {path}；本次只对齐，正常遥操作请另行启动。", flush=True)


def show(counts, raw, targets, clipped, warnings, sim, joint):
    """每秒一次显示原始目标、实际角度和限位状态，不输出到持久日志。"""
    print("关节 | 解码计数 | 映射原目标 rad | 当前 ctrl rad | 实际 rad | 状态", flush=True)
    for i, name in enumerate(JOINT_NAMES):
        state = '保持初始目标' if joint is not None and name != joint else '裁剪' if clipped[i] else '跟随'
        print(f"{name} | {counts[i]:.0f} | {raw[i]:+.4f} | {targets[i]:+.4f} | "
              f"{sim.joint_positions()[i]:+.4f} | {state}", flush=True)
    if warnings:
        print('位置提示：' + '；'.join(warnings), flush=True)


def follow(leader, sim, config, alignment, args):
    """启动过渡只限目标变化速度，正常跟随无滤波；任何失败先停止推进再退出。"""
    mapping = JointMapping(config, alignment, leader.calibration, sim.limits, args.joint)
    counts = leader.read()
    raw, targets, clipped, warnings = mapping.map(counts, sim.initial_targets)
    show(counts, raw, targets, clipped, warnings, sim, args.joint)
    print(f"限位交集(rad)：{dict(zip(JOINT_NAMES, sim.limits.tolist()))}", flush=True)
    require(sim.viewer, "以上是当前主臂映射目标，请托稳主臂。输入 START 回车开始仿真平滑过渡；"
            "过渡期间保持主臂不动，关闭窗口或 Ctrl+C 退出：", 'START')
    command = sim.initial_targets.copy()
    min_steps = math.ceil(config['startup_seconds'] * sim.control_freq)
    distance_steps = math.ceil(float(np.max(np.abs(targets - command))) / config['startup_speed_rad_s'] * sim.control_freq)
    transition_limit = max(min_steps, distance_steps) + min_steps
    startup, completed, last_print = True, 0, -float('inf')
    clipping_events, range_events = set(), set()  # 合并日志间隔内事件，不漏掉短暂的小幅越界。
    while sim.viewer.is_running() and (args.steps is None or completed < args.steps):
        begun = time.perf_counter()
        counts = leader.read()
        # 完整新样本和映射检查成功之前，不写 ctrl、不执行 mj_step。
        raw, targets, clipped, warnings = mapping.map(counts, sim.initial_targets)
        clipping_events.update(name for name, flag in zip(JOINT_NAMES, clipped) if flag)
        range_events.update(warnings)
        if startup:
            increment = config['startup_speed_rad_s'] / sim.control_freq
            command += np.clip(targets - command, -increment, increment)
            if completed + 1 >= min_steps and np.allclose(command, targets, atol=1e-8, rtol=0):
                startup = False
                print("启动过渡完成，进入正常跟随（不做时间滤波）。请小幅、缓慢移动。", flush=True)
            elif completed + 1 >= transition_limit:
                raise RuntimeError("启动过渡期间目标未稳定，停止；请保持主臂不动后重新运行")
        else:
            command = targets
        sim.step(command)
        sim.viewer.sync()
        completed += 1
        if begun - last_print >= config['print_every_seconds']:
            print(f"阶段={'启动过渡' if startup else '正常跟随'}，控制周期={completed}", flush=True)
            show(counts, raw, command, clipped, warnings, sim, args.joint)
            if clipping_events or range_events:
                print(f"本显示间隔内裁剪关节={sorted(clipping_events)}；范围提示={sorted(range_events)}", flush=True)
            clipping_events.clear()
            range_events.clear()
            last_print = begun
        time.sleep(max(0, 1 / sim.control_freq - (time.perf_counter() - begun)))
    if clipping_events or range_events:
        print(f"最后区间裁剪关节={sorted(clipping_events)}；范围提示={sorted(range_events)}", flush=True)
    print(f"已结束，共推进 {completed} 个控制周期；未向主臂发送运动或配置写入。", flush=True)


def main():
    """配置在项目根目录解析，串口和仿真资源统一在 finally 中释放。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', help='主臂串口；省略时使用本机对齐文件，首次 --align 必填')
    parser.add_argument('--baudrate', type=int, help='默认使用本机配置；首次对齐默认 1000000')
    parser.add_argument('--device-name', default='leader01', help='主臂设备名称')
    parser.add_argument('--calibration-file', type=Path, help='主臂校准 JSON；默认按设备名称定位')
    parser.add_argument('--scene', type=Path, default=Path('assets/scenes/so101_pick_place.xml'))
    parser.add_argument('--mapping-config', type=Path, default=Path('robots/so101/configs/mapping.yaml'))
    parser.add_argument('--alignment-file', type=Path, help='本机对齐 YAML；默认 configs/local/<设备名>.yaml')
    parser.add_argument('--align', action='store_true', help='交互记录参考姿态、正方向和夹爪端点；不校准舵机')
    parser.add_argument('--joint', choices=JOINT_NAMES, help='只让指定关节跟随，其余保持初始目标')
    parser.add_argument('--steps', type=int, help='可选：最多推进多少个控制周期，包含启动过渡')
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error('本工具需要现场交互终端；不会在后台自动开始跟随')
    if Path(args.device_name).name != args.device_name or args.device_name in ('.', '..'):
        parser.error('设备名称不能包含路径')
    if args.steps is not None and args.steps <= 0:
        parser.error('--steps 必须为正整数')
    path = args.alignment_file or Path(f'robots/so101/configs/local/{args.device_name}.yaml')
    config = read_yaml(args.mapping_config)
    validate_config(config)
    if not args.align and not path.is_file():
        parser.error(f"缺少现场对齐文件 {path}；先用 --align --port <串口> 完成参考姿态与方向确认")
    alignment = None if args.align else read_yaml(path)
    if args.align and path.exists():
        parser.error('对齐文件已存在；请指定新的本机文件路径，不覆盖')
    if alignment is not None and (alignment['device_name'] != args.device_name or alignment['role'] != 'leader'):
        parser.error('本机映射的设备名或角色不一致')
    args.port = args.port or (alignment['port'] if alignment is not None else None)
    args.baudrate = args.baudrate if args.baudrate is not None else (alignment['baudrate'] if alignment is not None else 1000000)
    args.calibration_file = args.calibration_file or (Path(alignment['calibration_file']) if alignment is not None
                                                    else Path(f'robots/so101/calibration/leader/{args.device_name}/calibration.json'))
    if not args.port:
        parser.error('首次 --align 必须指定 --port')
    leader = SO101Leader(args.port, args.baudrate, args.calibration_file, config['max_sample_seconds'])
    sim = None
    try:
        sim = SO101Sim(args.scene, config['control_freq'])
        sim.open_viewer()
        leader.open()
        print(f"端口={args.port}，波特率={args.baudrate}，六轴扭矩关闭；只读模式。\n"
              f"控制频率={sim.control_freq} Hz，物理步长={sim.model.opt.timestep} 秒，子步数={sim.substeps}", flush=True)
        if args.align:
            align(leader, sim, config, args, path)
        else:
            follow(leader, sim, config, alignment, args)
    except BaseException:
        print("停止目标更新与仿真推进，释放资源；不会重连、写寄存器或自动恢复运动。", flush=True)
        raise
    finally:
        try:
            leader.close()
        finally:
            if sim is not None:
                sim.close()


if __name__ == '__main__':
    main()
