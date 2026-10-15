"""SO101 主臂只读检查：仅发送 PING 和 READ，不写舵机寄存器。"""

import argparse
import time

import scservo_sdk as scs


# 地址与长度来自本地 LeRobot motors/feetech/tables.py 的 STS/SMS 控制表。
REGISTERS = (("ID", 5, 1), ("Model_Number", 3, 2),
             ("Present_Position", 56, 2), ("Torque_Enable", 40, 1))
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
    for name, address, length in REGISTERS:
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


def main() -> int:
    """打开一次串口检查指定 ID，任何退出路径均释放已打开的端口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="主臂串口，例如 /dev/ttyACM0")
    parser.add_argument("--baudrate", type=int, default=1_000_000,
                        help="主机串口波特率，默认 1000000，依据 LeRobot SO101/Feetech 配置")
    parser.add_argument("--ids", type=int, nargs="+", default=list(range(1, 7)),
                        help="指定检查 ID，默认 1 2 3 4 5 6；不据此认定物理关节")
    args = parser.parse_args()
    if any(not 0 <= motor_id < scs.BROADCAST_ID for motor_id in args.ids):
        parser.error("ID 必须在 0～253 之间，禁止广播 ID")
    if len(set(args.ids)) != len(args.ids):
        parser.error("--ids 不应重复，避免重复检查同一 ID")
    port = ReadOnlyCheckPort(args.port)
    packet = scs.PacketHandler(0)  # LeRobot 的 STS/SMS 配置；本 SDK 的 0 选择小端字序。
    try:
        # setBaudRate 只配置主机串口并打开端口，不发送舵机波特率寄存器写入。
        if not port.setBaudRate(args.baudrate):
            raise ValueError(f"SDK 不支持主机串口波特率 {args.baudrate}")
        port.ser.write_timeout = RESPONSE_TIMEOUT_MS / 1000.0  # 约束请求报文的串口发送等待。
        print(f"端口={args.port}，波特率={port.getBaudRate()}，STS/SMS 小端，"
              f"每次响应超时={RESPONSE_TIMEOUT_MS} ms", flush=True)
        print("位置为未校准的两字节原始计数；默认 ID 顺序不代表已确认的物理关节。", flush=True)
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
