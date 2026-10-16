"""SO101 主从臂只读检查：默认 leader（主臂），仅发送 PING 和 READ，不写舵机寄存器。"""

import argparse
import json
from pathlib import Path
import time

import scservo_sdk as scs


# 与校准流程共用寄存器地址、符号规则和用户确认的关节映射。
from my_act.hardware.so101.calibration import (
    MOTORS, REGISTERS, ROLES, SIGN_BITS, decode_sign_magnitude,
    resolve_calibration_paths, validate_calibration,
)

BASIC_REGISTERS = ("ID", "Model_Number", "Present_Position", "Torque_Enable")
RESPONSE_TIMEOUT_MS = 100


class ReadOnlyCheckPort(scs.PortHandler):
    """仅调整本进程的响应计时，不改变舵机参数或 SDK 安装文件。"""

    def getCurrentTime(self):
        """使用单调时钟，避免系统时间调整延长通信等待。"""
        return time.monotonic() * 1000.0

    def setPacketTimeout(self, packet_length):
        """SDK 每次收包会调用此方法，固定有限的毫秒级等待。"""
        self.setPacketTimeoutMillis(RESPONSE_TIMEOUT_MS)


def error_text(packet, result: int, error: int) -> str:
    """保留 SDK 原始错误文本及数值，包括设备状态错误位。"""
    return (f"comm={result}: {packet.getTxRxResult(result)}; "
            f"device_error={error}: {packet.getRxPacketError(error)}")


def check_id(port, packet, motor_id: int) -> bool:
    """每个 ID 仅 ping 一次；收到响应后逐项读取，不重试。"""
    # SDK ping() 会额外读型号并覆盖 ping 的结果；这里仅组装已核对的六字节 PING。
    # SDK txRxPacket 负责帧头和通信校验字节；此请求不包含 WRITE 指令。
    request = [0, 0, motor_id, 2, scs.INST_PING, 0]
    _, result, ping_error = packet.txRxPacket(port, request)
    if result != scs.COMM_SUCCESS:
        status = "ping 无响应" if result == scs.COMM_RX_TIMEOUT else "ping 通信失败"
        print(f"| {motor_id} | - | - | - | - | {status} |", flush=True)
        print(f"  ID {motor_id} PING: {error_text(packet, result, ping_error)}", flush=True)
        return False

    values = []
    errors = []
    if ping_error:
        errors.append(f"PING: {error_text(packet, result, ping_error)}")
    for name in BASIC_REGISTERS:
        address, length = REGISTERS[name]
        reader = packet.read1ByteTxRx if length == 1 else packet.read2ByteTxRx
        value, result, error = reader(port, motor_id, address)
        if result == scs.COMM_SUCCESS and error == 0:
            values.append(str(value))  # 只展示寄存器原始值，不猜型号名称或物理关节。
        else:
            values.append("读取失败")
            errors.append(f"{name}: {error_text(packet, result, error)}")
    if "读取失败" in values:
        status = "ping 成功，寄存器读取失败"
    elif ping_error:
        status = "ping 有响应，设备报告错误"
    else:
        status = "ping 成功，读取成功"
    print(f"| {motor_id} | " + " | ".join(values) + f" | {status} |", flush=True)
    for message in errors:
        print(f"  ID {motor_id} {message}", flush=True)
    if values[-1] == "1":
        print(f"  ID {motor_id}: Torque_Enable=1，当前扭矩已开启；仅报告，不修改。", flush=True)
    return not errors


def load_comparison(calibration_path: Path, backup_path: Path, port: str, baudrate: int,
                    role: str = 'leader', device_name: str | None = None):
    """在打开串口前核对文件和明确指定的备份身份；不自动挑选最近备份。"""
    device_dir, calibration_path = resolve_calibration_paths(
        Path(__file__).resolve().parents[1] / "calibration",
        role, device_name, calibration_path,
    )
    backup_root = device_dir / "backups"
    if (backup_root.resolve() != backup_root
            or not backup_path.absolute().is_relative_to(backup_root)
            or not backup_path.resolve().is_relative_to(backup_root)):
        raise ValueError("备份必须位于同一角色、同一设备的 backups 目录，不能通过链接跨目录")
    # 路径身份核对通过后才读取文件，拒绝把主臂文件用于从臂。
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    validate_calibration(calibration)
    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    if backup['role'] != role or backup['device_name'] != device_dir.name:
        raise ValueError("校准文件与备份的角色或设备名不一致")
    if backup['port'] != port or backup['baudrate'] != baudrate or backup['motor_ids'] != MOTORS:
        raise ValueError("备份中的串口、波特率或关节 ID 映射与本次检查不一致")
    for name in MOTORS:
        for register in ("Phase", "Lock"):
            if backup['registers_address_length'][register] != list(REGISTERS[register]):
                raise ValueError(f"备份的 {register} 寄存器定义与当前校准实现不一致")
            if type(backup['raw_values'][name][register]) is not int:
                raise ValueError(f"备份中的 {name}/{register} 不是整数")
    print(f"校准文件：{calibration_path}\n校准前备份：{backup_path}", flush=True)
    print(f"角色={role}（{ROLES[role]}），备份设备={backup['device_name']}，创建时间={backup['created_at']}；"
          "使用显式指定的备份，不按文件时间自动推断归属。", flush=True)
    return calibration, backup['raw_values']


def expected_values(name: str, calibration: dict, before: dict) -> dict:
    """按校准脚本实际写入计划生成预期值，drive_mode 不作为寄存器值。"""
    row = calibration[name]
    return {
        "ID": MOTORS[name],
        "Homing_Offset": row['homing_offset'],
        "Min_Position_Limit": row['range_min'],
        "Max_Position_Limit": row['range_max'],
        "Torque_Enable": 0,  # 校准只允许关闭扭矩，不恢复此前开启状态。
        "Operating_Mode": 0,  # 校准设置的位置模式，不取文件中的 drive_mode。
        "Phase": before[name]['Phase'] & ~0x10,  # 仅清 bit 4，其余位应与备份一致。
        "Lock": before[name]['Lock'],  # 成功校准后恢复原配置锁值。
    }


def check_calibration_id(port, packet, motor_id: int, calibration: dict, before: dict) -> str:
    """每项只读一次；位置仅显示，偏置、范围和设置分别核对，不写寄存器。"""
    name = next(name for name, value in MOTORS.items() if value == motor_id)
    row = calibration[name]
    expected = expected_values(name, calibration, before)
    raw, values, errors = {}, {}, []
    request = [0, 0, motor_id, 2, scs.INST_PING, 0]
    _, result, ping_error = packet.txRxPacket(port, request)
    if result != scs.COMM_SUCCESS:
        errors.append(f"PING: {error_text(packet, result, ping_error)}")
        ping_status = "ping 无响应" if result == scs.COMM_RX_TIMEOUT else "ping 通信失败"
    else:
        ping_status = "ping 成功" if not ping_error else "ping 设备错误"
        if ping_error:
            errors.append(f"PING: {error_text(packet, result, ping_error)}")
        for register, (address, length) in REGISTERS.items():
            reader = packet.read1ByteTxRx if length == 1 else packet.read2ByteTxRx
            value, comm, error = reader(port, motor_id, address)
            if comm != scs.COMM_SUCCESS or error:
                errors.append(f"{register}: {error_text(packet, comm, error)}")
                continue  # 保留其他字段的读取机会，不重试失败字段。
            raw[register] = value
            values[register] = (decode_sign_magnitude(value, SIGN_BITS[register])
                                if register in SIGN_BITS else value)
    mismatches = [f"{key}: 预期 {value}，实际 {values[key]}"
                  for key, value in expected.items() if key in values and values[key] != value]
    status = "读取失败" if errors else "值不一致" if mismatches else "全部一致"
    actual_range = f"{values.get('Min_Position_Limit', '-')}～{values.get('Max_Position_Limit', '-')}"
    print(f"| {name} | {motor_id} | {row['homing_offset']} | {values.get('Homing_Offset', '-')} | "
          f"{row['range_min']}～{row['range_max']} | {actual_range} | "
          f"{values.get('Torque_Enable', '-')} | {status} |", flush=True)
    print(f"  {ping_status}；读取 ID={values.get('ID', '-')}，型号编号={values.get('Model_Number', '-')}；"
          f"位置原始字={raw.get('Present_Position', '-')}，解码计数={values.get('Present_Position', '-')}；"
          f"偏置原始字={raw.get('Homing_Offset', '-')}", flush=True)
    print("  " + "；".join(f"{key}={values.get(key, '-')}（预期 {expected[key]}）"
                            for key in ('Operating_Mode', 'Phase', 'Lock'))
          + f"；备份 Phase={before[name]['Phase']}，Lock={before[name]['Lock']}", flush=True)
    for message in errors + mismatches:
        print(f"  {name}: {message}", flush=True)
    position = values.get('Present_Position')
    if position is not None and not row['range_min'] <= position <= row['range_max']:
        print("  当前位置超出文件采集范围，仅作位置提示，不计为校准写入失败。", flush=True)
    if values.get('Torque_Enable', 0) != 0:
        print("  扭矩未关闭；只报告，不修改。", flush=True)
    return status


def main() -> int:
    """打开一次串口检查指定 ID，任何退出路径均释放已打开的端口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=tuple(ROLES), default="leader",
                        help="设备角色：leader 主臂 / follower 从臂；默认 leader（兼容旧命令）")
    parser.add_argument("--device-name", help="设备名称；校准核验省略时从对应角色的校准路径推断")
    parser.add_argument("--port", required=True, help="串口：主臂例如 /dev/ttyACM0，从臂例如 /dev/ttyACM1")
    parser.add_argument("--baudrate", type=int, default=1_000_000,
                        help="主机串口波特率，默认 1000000，依据 LeRobot SO101/Feetech 配置")
    parser.add_argument("--ids", type=int, nargs="+", default=list(range(1, 7)),
                        help="指定检查 ID，默认 1 2 3 4 5 6；不据此认定物理关节")
    parser.add_argument("--calibration-file", type=Path,
                        help="可选：核对指定角色/设备的校准文件，须同时指定本次校准前备份")
    parser.add_argument("--register-backup", type=Path,
                        help="本次校准对应的 registers_before.json；不自动选择最新备份")
    args = parser.parse_args()
    if any(not 0 <= motor_id < scs.BROADCAST_ID for motor_id in args.ids):
        parser.error("ID 必须在 0～253 之间，禁止广播 ID")
    if len(set(args.ids)) != len(args.ids):
        parser.error("--ids 不应重复，避免重复检查同一 ID")
    if (args.calibration_file is None) != (args.register_backup is None):
        parser.error("--calibration-file 和 --register-backup 必须一起提供")
    comparison = None
    try:
        if args.device_name is not None:
            resolve_calibration_paths(Path(__file__).resolve().parents[1] / "calibration",
                                      args.role, args.device_name, args.calibration_file)
        if args.calibration_file is not None:
            if any(motor_id not in MOTORS.values() for motor_id in args.ids):
                parser.error("校准核验仅支持已确认的 ID 1～6")
            comparison = load_comparison(args.calibration_file, args.register_backup,
                                         args.port, args.baudrate, args.role, args.device_name)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(f"角色={args.role}（{ROLES[args.role]}；省略 --role 时默认 leader），"
          f"设备名称={args.device_name or '由校准路径推断；普通连接检查未指定'}", flush=True)
    port = ReadOnlyCheckPort(args.port)
    packet = scs.PacketHandler(0)  # LeRobot 的 STS/SMS 配置；本 SDK 的 0 选择小端字序。
    try:
        # setBaudRate 只配置主机串口并打开端口，不发送舵机波特率寄存器写入。
        if not port.setBaudRate(args.baudrate):
            raise ValueError(f"SDK 不支持主机串口波特率 {args.baudrate}")
        port.ser.write_timeout = RESPONSE_TIMEOUT_MS / 1000.0  # 约束请求报文的串口发送等待。
        print(f"端口={args.port}，波特率={port.getBaudRate()}，STS/SMS 小端，"
              f"每次响应超时={RESPONSE_TIMEOUT_MS} ms", flush=True)
        if comparison is not None:
            print("位置已包含内部偏置，不再次补偿、不要求处于参考姿态、不转换角度。", flush=True)
            print("| 关节 | ID | 文件偏置 | 实际偏置 | 文件范围 | 实际范围 | Torque_Enable | 核验结果 |", flush=True)
            print("| --- | --- | --- | --- | --- | --- | --- | --- |", flush=True)
            statuses = [check_calibration_id(port, packet, motor_id, *comparison) for motor_id in args.ids]
            print("汇总：" + "，".join(f"{status} {statuses.count(status)}"
                  for status in ('全部一致', '值不一致', '读取失败')) + "；未写入任何舵机寄存器。", flush=True)
            return 0 if all(status == '全部一致' for status in statuses) else 1
        print("位置显示两字节原始字；普通连接检查不确认物理关节映射。", flush=True)
        print("| 请求 ID | 读取 ID | 型号编号 | 原始位置计数 | Torque_Enable | 状态 |", flush=True)
        print("| --- | --- | --- | --- | --- | --- |", flush=True)
        successful = 0
        for motor_id in args.ids:
            successful += check_id(port, packet, motor_id)
        print(f"完整读取成功 {successful}/{len(args.ids)}；未写入任何舵机寄存器。", flush=True)
        return 0 if successful == len(args.ids) else 1
    finally:
        if port.ser is not None and port.ser.is_open:
            port.closePort()
            print("串口已关闭。", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
