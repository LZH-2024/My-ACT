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
# 本项目改编：保留上游编码、中心计数和校准字段语义，增加受限访问与离线可检查函数。
# 参考：lerobot/motors/{encoding_utils,motors_bus}.py 与 motors/feetech/feetech.py。

"""SO101 校准使用的有限寄存器访问、编码与文件字段检查。"""

import time
import scservo_sdk as scs

MOTORS = {"shoulder_pan": 1, "shoulder_lift": 2, "elbow_flex": 3,
          "wrist_flex": 4, "wrist_roll": 5, "gripper": 6}
# 来自 LeRobot STS_SMS_SERIES_CONTROL_TABLE；只为校准开放以下可写字段。
WRITABLE = {"Torque_Enable": (40, 1), "Lock": (55, 1), "Operating_Mode": (33, 1),
            "Phase": (18, 1), "Homing_Offset": (31, 2),
            "Min_Position_Limit": (9, 2), "Max_Position_Limit": (11, 2)}
REGISTERS = {**WRITABLE, "Model_Number": (3, 2), "ID": (5, 1), "Present_Position": (56, 2)}
SIGN_BITS = {"Homing_Offset": 11, "Present_Position": 15}
REFERENCE_URL = "https://huggingface.co/docs/lerobot/main/en/so101#calibration-video"


def decode_sign_magnitude(raw: int, sign_bit: int) -> int:
    """按寄存器指定的符号位解码，不使用二进制补码 int16。"""
    magnitude = raw & ((1 << sign_bit) - 1)
    return -magnitude if raw & (1 << sign_bit) else magnitude


def encode_sign_magnitude(value: int, sign_bit: int) -> int:
    """编码符号与幅值，并拒绝超出该寄存器表示范围的偏置。"""
    if abs(value) >= 1 << sign_bit:
        raise ValueError(f"数值 {value} 超出符号位 {sign_bit} 的可表示范围")
    return abs(value) | ((1 << sign_bit) if value < 0 else 0)


def half_turn_offsets(positions: dict) -> dict:
    """仅接受已清零内部偏置后的计数，沿用 LeRobot 的中心值 2047。"""
    offsets = {}
    for name in MOTORS:
        value = positions[name]
        if not 0 <= value <= 4095:
            raise ValueError(f"{name} 清零后的计数 {value} 不在 0～4095，请检查反馈模式和参考姿态")
        offsets[name] = value - 2047
        encode_sign_magnitude(offsets[name], 11)
    return offsets


def validate_calibration(calibration: dict) -> None:
    """拒绝错误关节、ID、编码或无效范围；这里只支持已确认的主臂。"""
    if set(calibration) != set(MOTORS):
        raise ValueError("校准文件必须恰好包含已确认的六个关节")
    for name, motor_id in MOTORS.items():
        row = calibration[name]
        if set(row) != {"id", "drive_mode", "homing_offset", "range_min", "range_max"}:
            raise ValueError(f"{name} 校准字段不完整或包含未知字段")
        if any(type(value) is not int for value in row.values()):
            raise ValueError(f"{name} 校准字段必须为整数")
        if row['id'] != motor_id or row['drive_mode'] != 0:
            raise ValueError(f"{name} ID 不符，或 drive_mode 不是本流程的 0")
        encode_sign_magnitude(row['homing_offset'], 11)
        if not 0 <= row['range_min'] < row['range_max'] <= 4095:
            raise ValueError(f"{name} 范围无效或发生计数越界，不保存")
    if (calibration['wrist_roll']['range_min'], calibration['wrist_roll']['range_max']) != (0, 4095):
        raise ValueError("wrist_roll 沿用上游特殊处理：范围必须为 0～4095")


class _TimedPort(scs.PortHandler):
    """设置本进程的有限通信超时，不修改舵机通信参数。"""

    def getCurrentTime(self):
        return time.monotonic() * 1000

    def setPacketTimeout(self, packet_length):
        self.setPacketTimeoutMillis(100)


class CalibrationBus:
    """只提供本次校准的寄存器访问；构造时不打开串口、不自动初始化。"""

    def __init__(self, port: str, baudrate: int):
        self.port = _TimedPort(port)
        self.baudrate = baudrate
        self.packet = scs.PacketHandler(0)  # STS3215 小端字序。

    def open(self):
        """仅设置主机串口波特率，不写舵机 Baud_Rate。"""
        if not self.port.setBaudRate(self.baudrate):
            raise ValueError(f"SDK 不支持波特率 {self.baudrate}")
        self.port.ser.write_timeout = 0.1

    def close(self):
        """只关闭串口，不自动恢复扭矩或执行其他寄存器写入。"""
        if self.port.ser is not None and self.port.ser.is_open:
            self.port.closePort()

    def _check(self, name, register, comm, error):
        if comm != scs.COMM_SUCCESS or error:
            raise ConnectionError(f"{name}/{register}: comm={comm} {self.packet.getTxRxResult(comm)}; "
                                  f"error={error} {self.packet.getRxPacketError(error)}")

    def read_raw(self, name, register):
        """读取原始寄存器字，供写入前备份使用，不重试。"""
        address, length = REGISTERS[register]
        read = self.packet.read1ByteTxRx if length == 1 else self.packet.read2ByteTxRx
        value, comm, error = read(self.port, MOTORS[name], address)
        self._check(name, register, comm, error)
        return value

    def read(self, name, register):
        """仅对控制表声明的字段做符号幅值解码。"""
        raw = self.read_raw(name, register)
        return decode_sign_magnitude(raw, SIGN_BITS[register]) if register in SIGN_BITS else raw

    def write(self, name, register, value):
        """只允许校准字段，禁止启用扭矩；写后立即读取确认。"""
        address, length = WRITABLE[register]  # ID、波特率及目标位置不在白名单内。
        if register == 'Torque_Enable' and value != 0:
            raise ValueError("校准工具不允许开启扭矩")
        raw = encode_sign_magnitude(value, 11) if register == 'Homing_Offset' else value
        if not 0 <= raw < 1 << (8 * length):
            raise ValueError(f"{register} 数值越界")
        write = self.packet.write1ByteTxRx if length == 1 else self.packet.write2ByteTxRx
        comm, error = write(self.port, MOTORS[name], address, raw)
        self._check(name, register, comm, error)
        if self.read_raw(name, register) != raw:
            raise RuntimeError(f"{name}/{register} 写后读回不一致，停止校准")

    def positions(self):
        """返回舵机已经应用 Homing_Offset 后的位置，不再次减偏置。"""
        return {name: self.read(name, 'Present_Position') for name in MOTORS}

# 上游 SOLeader 的原始参考姿态示意，结合官方文档查看。
HOMING_DIAGRAM = r"""
       ╭─────┬────────────────────┬──────╮ ◉╲═════╗   ← moveable claw
       │     │      forearm       │  ▤▤  │╤══╲════╝
       ╰┬───┬┴────────────────────┴──────┴┴═══════╝
        │   │                                  ███
        │   │                                  ███  ← handle
        │   │                                  ███
        │   │   upper arm
        │   │
        │   │
        │   │
   ╭────┴───┴────╮
   │   base ◉    │
   ╰──┬───────┬──╯
  ╭───┴───────┴───╮
  │▓▓▓ C-clamp ▓▓▓│
  ╰───────────────╯
 ═══════════════════════════════════════════════════
                table edge
"""
