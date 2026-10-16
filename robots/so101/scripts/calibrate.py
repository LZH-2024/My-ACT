# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# Copyright 2026 The HuggingFace Inc. team. All rights reserved.
# 本项目改编：保留上游编码、中心计数和校准字段语义，增加交互确认、寄存器备份与有限范围采样。
# 参考：lerobot/motors/{encoding_utils,motors_bus}.py 与 motors/feetech/feetech.py。

"""SO101 主从臂交互式校准：默认 leader（主臂），现场确认后才写寄存器，不发送运动目标。"""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import select
import sys
import time
from zoneinfo import ZoneInfo

from my_act.hardware.so101.calibration import (
    CalibrationBus, HOMING_DIAGRAMS, MOTORS, REFERENCE_URL, ROLES, WRITABLE,
    half_turn_offsets, resolve_calibration_paths, validate_calibration,
)


def confirm(message: str, word: str = "WRITE") -> None:
    """要求输入完整确认词；回车或其他输入均取消，不默认同意写入。"""
    if input(f"{message}\n输入 {word} 并回车确认，否则取消：").strip() != word:
        raise RuntimeError("用户未确认，已取消")


def save_json(path: Path, value) -> None:
    """新建 JSON 并刷入磁盘，不覆盖已有备份。"""
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())


def collect_ranges(bus: CalibrationBus, role: str = 'leader') -> tuple[dict, dict]:
    """只读采样五个关节；最多每秒覆盖刷新一行，回车结束。"""
    names = [name for name in MOTORS if name != 'wrist_roll']
    print("gripper 对应从臂夹爪，请手动开合夹爪。" if role == "follower" else "gripper 对应主臂手柄开合。")
    print("依次手动缓慢移动 shoulder_pan、shoulder_lift、elbow_flex、wrist_flex、gripper 至各自完整安全行程。")
    print("不要用力顶机械止挡；不采集 wrist_roll，不要求将它旋转一整圈。")
    input("准备好后按回车开始只读采样；采样期间再次按回车结束：")
    mins, maxes = {}, {}
    last_display = 0.0
    while True:
        for name in names:
            value = bus.read(name, 'Present_Position')
            if not 0 <= value <= 4095:
                raise ValueError(f"{name} 位置 {value} 越界，停止，不跨越编码跳变或自动修正")
            mins[name] = min(mins.get(name, value), value)
            maxes[name] = max(maxes.get(name, value), value)
        now = time.monotonic()
        if now - last_display >= 1.0:
            print("\r" + " | ".join(f"{name}:{mins[name]}～{maxes[name]}" for name in names), end='', flush=True)
            last_display = now
        if select.select([sys.stdin], [], [], 0.05)[0]:  # 等待同时限制采样频率，不开启后台线程。
            if sys.stdin.readline() == '':
                raise EOFError("采样输入关闭，未完成校准")
            break
    print()
    invalid = [name for name in names if not mins[name] < 2047 < maxes[name]]
    if invalid:
        raise ValueError(f"这些关节没有有效覆盖中心计数两侧：{invalid}；不保存成功校准")
    mins['wrist_roll'], maxes['wrist_roll'] = 0, 4095  # 与 SOLeader / SOFollower 的特殊处理一致。
    return mins, maxes


def main() -> None:
    """备份、展示计划、确认、校准、读回验证，最后按角色和设备保存校准文件。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=tuple(ROLES), default='leader',
                        help='设备角色：leader 主臂 / follower 从臂；默认 leader（兼容旧命令）')
    parser.add_argument('--port', required=True, help='串口：主臂例如 /dev/ttyACM0，从臂例如 /dev/ttyACM1')
    parser.add_argument('--baudrate', type=int, default=1_000_000, help='主机波特率，默认 1000000')
    parser.add_argument('--device-name', required=True, help='这条设备的稳定名称，例如 leader01 / follower01，不能用于另一台设备')
    parser.add_argument('--calibration-file', type=Path,
                        help='校准 JSON，必须位于 robots/so101/calibration/<role>/<设备名称>/ 下')
    args = parser.parse_args()
    try:
        device_dir, path = resolve_calibration_paths(
            Path(__file__).resolve().parents[1] / 'calibration',
            args.role, args.device_name, args.calibration_file,
        )
        backup_root = device_dir / 'backups'
        if backup_root.resolve() != backup_root:
            raise ValueError('备份目录不能通过符号链接指向其他设备或目录')
    except ValueError as error:
        parser.error(str(error))
    if not sys.stdin.isatty():
        parser.error('必须由用户在交互终端现场运行；不接受重定向输入自动确认')

    role_label = ROLES[args.role]
    print(f'角色={args.role}（{role_label}；省略 --role 时默认 leader），设备名称={args.device_name}，端口={args.port}，波特率={args.baudrate}')
    print(f'已确认的关节 ID：{MOTORS}；请确认当前连接的确实是这条{role_label}。')
    print(f'校准文件：{path}')
    previous = path.read_bytes() if path.exists() else None
    reuse = False
    calibration = None
    if previous is not None:
        choice = input(f'已有校准文件：{path}\n输入 reuse 复用并写回舵机，或 new 重新校准；其他输入取消：').strip()
        if choice not in ('reuse', 'new'):
            raise RuntimeError('用户取消，尚未打开串口')
        reuse = choice == 'reuse'
        if reuse:
            calibration = json.loads(previous)
            validate_calibration(calibration)

    bus = CalibrationBus(args.port, args.baudrate)
    writing_started = False
    backup_dir = None
    try:
        bus.open()  # 到确认提示之前只读取寄存器，不做高级连接初始化。
        original = {}
        for name, motor_id in MOTORS.items():
            if bus.read_raw(name, 'ID') != motor_id or bus.read_raw(name, 'Model_Number') != 777:
                raise ValueError(f'{name} 的 ID 或型号与已确认的 STS3215 不符，停止且不写入')
            original[name] = {reg: bus.read_raw(name, reg) for reg in WRITABLE}
        timestamp = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S_%f')
        backup_dir = backup_root / timestamp
        backup_dir.mkdir(parents=True, exist_ok=False)
        save_json(backup_dir / 'registers_before.json', {
            'role': args.role, 'device_name': args.device_name, 'port': args.port,
            'baudrate': args.baudrate, 'created_at': timestamp, 'motor_ids': MOTORS,
            'registers_address_length': WRITABLE, 'raw_values': original,
        })
        if previous is not None:
            with (backup_dir / 'previous_calibration.json').open('xb') as handle:
                handle.write(previous)
                handle.flush()
                os.fsync(handle.fileno())
        print(f'原始寄存器及已有文件备份：{backup_dir}')
        print('原始寄存器字（Homing_Offset 为尚未解码的原始字）：')
        print(json.dumps(original, ensure_ascii=False, indent=2))
        print('计划：Torque_Enable(40)=0；Lock(55)=0 解锁；Operating_Mode(33)=0；')
        print('Phase(18) 只清 bit 4，保留其他位；不修改返回延迟、加速度、ID、波特率或目标位置。')
        print('完成后恢复各电机原 Lock 值；扭矩始终保持关闭，不自动恢复原来的开启状态。')
        if reuse:
            print('将以下文件的 homing_offset、range_min、range_max 写入地址 31、9、11：')
            print(json.dumps(calibration, ensure_ascii=False, indent=2))
        else:
            print('新校准将先把 Homing_Offset(31) 清零、限位(9/11) 设为 0/4095，')
            print('再按参考姿态写新偏置，最后写手动采集的限位；wrist_roll 固定为 0/4095。')
        if any(row['Torque_Enable'] != 0 for row in original.values()):
            confirm(f'检测到扭矩非零：请先托住{role_label}，关闭扭矩后手臂可能下落。确认允许将六个扭矩值设为 0。', 'DISABLE')
        confirm(f'请托住{role_label}。确认当前设备身份、备份和上述写入计划；中断可能留下部分写入，不自动回滚。')
        writing_started = True
        for name in MOTORS:
            bus.write(name, 'Torque_Enable', 0)
            bus.write(name, 'Lock', 0)
            bus.write(name, 'Operating_Mode', 0)
            phase = original[name]['Phase']
            if phase & 0x10:
                bus.write(name, 'Phase', phase & ~0x10)

        if not reuse:
            print(f'{role_label}参考姿态（来自官方 SOFollower，末端为夹爪）：' if args.role == 'follower'
                  else '主臂参考姿态（来自官方 SOLeader，末端为手柄）：')
            print(HOMING_DIAGRAMS[args.role])
            print(f'官方校准文档（请查看 {args.role} 对应小节及视频）：{REFERENCE_URL}')
            print('按上游图示把各关节摆至行程中部；不能用仿真 qpos=0 代替。不要猜测设备零位。')
            input('托住并保持参考姿态，按回车后清除旧偏置/限位并读取位置；此时不要移动：')
            for name in MOTORS:
                bus.write(name, 'Homing_Offset', 0)
                bus.write(name, 'Min_Position_Limit', 0)
                bus.write(name, 'Max_Position_Limit', 4095)
            offsets = half_turn_offsets(bus.positions())
            print(f'新偏置（计数）：{offsets}')
            confirm('这些偏置将使当前参考位置接近 2047。保持姿态，确认写入 Homing_Offset。')
            for name in MOTORS:
                bus.write(name, 'Homing_Offset', offsets[name])
            print(f'写后位置（已包含内部偏置）：{bus.positions()}')
            mins, maxes = collect_ranges(bus, args.role)
            calibration = {name: {'id': motor_id, 'drive_mode': 0, 'homing_offset': offsets[name],
                                  'range_min': mins[name], 'range_max': maxes[name]}
                           for name, motor_id in MOTORS.items()}
            validate_calibration(calibration)
            print(json.dumps(calibration, ensure_ascii=False, indent=2))
            confirm('请确认五个采集关节都已手动覆盖完整安全行程；仅有计数变化不能证明行程完整。确认写入限位并保存。', 'SAVE')

        for name, row in calibration.items():
            bus.write(name, 'Homing_Offset', row['homing_offset'])
            bus.write(name, 'Min_Position_Limit', row['range_min'])
            bus.write(name, 'Max_Position_Limit', row['range_max'])
        for name in MOTORS:
            bus.write(name, 'Lock', original[name]['Lock'])
            if bus.read(name, 'Torque_Enable') != 0:
                raise RuntimeError(f'{name} 扭矩不是 0，不能报告成功；未自动修改')
        if not reuse:
            # 只有全部校准写入和读回成功后，才替换成功文件；旧文件已有独立备份。
            pending = backup_dir / 'completed_calibration.json'
            save_json(pending, calibration)
            path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(pending, path)
        print(f'校准已验证并{"复用" if reuse else "保存"}：{path}；未启用扭矩，未发送运动目标。')
        print(f'{role_label}校准完成，六个关节扭矩保持关闭；请继续托住或妥善放置{role_label}，再松手。')
    except BaseException:
        if writing_started:
            print(f'校准未完成，可能已有部分寄存器写入；未保存新的成功文件。原始备份：{backup_dir}', file=sys.stderr)
            print(f'请先托住或妥善放置{role_label}。不会自动回滚或开启扭矩；保留现场并核对备份后再处理。', file=sys.stderr)
        raise
    finally:
        bus.close()


if __name__ == '__main__':
    main()
