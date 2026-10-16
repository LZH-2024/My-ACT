# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
# Copyright 2026 The HuggingFace Inc. team. All rights reserved.
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
# 本项目改编：LeRobot motors_bus 的归一化/反归一化、robots/utils 的反馈相对限幅。
# 增加双臂校准核对、只读连接封装及仅允许从臂目标/扭矩写入的接口。

"""真实 SO101 主从转换与有限通信接口；不依赖 MuJoCo 或完整 LeRobot。"""

import json
import math
from pathlib import Path
import stat

from .calibration import CalibrationBus, MOTORS, REGISTERS, resolve_calibration_paths, validate_calibration

GOAL_POSITION_ADDRESS = 42  # LeRobot STS_SMS_SERIES_CONTROL_TABLE：2 字节，单圈正数目标。
HOLD_DRIFT_COUNTS = 4  # 开扭矩前，相对刚预写保持目标的最大变化；约 0.35° 编码器角。
MAX_READ_JUMP_COUNTS = 512  # 相邻完整采样超过约 45° 编码器角即停，不处理跨圈绕回。


def load_arm_calibration(root: Path, role: str, device_name: str, path: Path) -> dict:
    """打开串口之前检查角色、设备目录、文件和 ID，不自动创建或写回校准。"""
    _, path = resolve_calibration_paths(root, role, device_name, path)
    if not path.is_file():
        raise FileNotFoundError(f"{role}/{device_name} 校准文件不存在：{path}。请先现场校准并只读核验，禁止驱动。")
    calibration = json.loads(path.read_text(encoding="utf-8"))
    validate_calibration(calibration)  # 本项目已确认的文件使用 drive_mode=0，拒绝未知方向配置。
    return calibration


def check_distinct_ports(leader_port: str, follower_port: str) -> None:
    """核对真实设备号，阻止两个路径或符号链接指向同一个串口；不打开端口。"""
    leader, follower = Path(leader_port).resolve(), Path(follower_port).resolve()
    if leader == follower:
        raise ValueError("主从串口不能指向同一设备")
    first, second = leader.stat(), follower.stat()
    if not stat.S_ISCHR(first.st_mode) or not stat.S_ISCHR(second.st_mode):
        raise ValueError("主从串口必须是字符设备")
    if first.st_rdev == second.st_rdev:
        raise ValueError("主从串口的设备号相同，禁止同时使用")


def validate_positions(positions: dict) -> None:
    """要求完整六关节和当前单圈模式的整数计数；采集边界不用于判定主臂坏读数。"""
    if set(positions) != set(MOTORS):
        raise ValueError("没有取得完整六关节位置，不使用旧值或补零")
    for name, value in positions.items():
        if not math.isfinite(value) or value != int(value) or not 0 <= value <= 4095:
            raise ValueError(f"{name} 位置 {value} 不是 0～4095 内的有效整数计数")


def normalize_positions(positions: dict, calibration: dict) -> dict:
    """LeRobot use_degrees=True：臂关节为度，夹爪为开度百分比；不再减硬件偏置。"""
    validate_positions(positions)
    values = {}
    for name, count in positions.items():
        row = calibration[name]
        minimum, maximum = row["range_min"], row["range_max"]
        if name == "gripper":
            bounded = min(maximum, max(minimum, count))
            values[name] = (bounded - minimum) * 100.0 / (maximum - minimum)
        else:
            values[name] = (count - (minimum + maximum) / 2) * 360.0 / 4095
    return values


def denormalize_positions(values: dict, calibration: dict) -> dict:
    """使用从臂自己的范围反归一化，沿用 LeRobot 的 int 截断；这里尚未限位。"""
    if set(values) != set(MOTORS) or not all(math.isfinite(v) for v in values.values()):
        raise ValueError("目标必须是完整且有限的六关节值")
    counts = {}
    for name, value in values.items():
        row = calibration[name]
        minimum, maximum = row["range_min"], row["range_max"]
        if name == "gripper":
            counts[name] = int(min(100.0, max(0.0, value)) / 100 * (maximum - minimum) + minimum)
        else:
            counts[name] = int(value * 4095 / 360 + (minimum + maximum) / 2)
    return counts


def validate_follower_positions(positions: dict, calibration: dict) -> None:
    """从臂当前姿态必须在其已核对的允许范围内；越界时拒绝启动或继续发送目标。"""
    validate_positions(positions)
    for name, count in positions.items():
        row = calibration[name]
        if not row["range_min"] <= count <= row["range_max"]:
            raise ValueError(f"从臂 {name} 当前计数 {count} 超出其范围 {row['range_min']}～{row['range_max']}，请先现场检查")


def check_read_jump(current: dict, previous: dict | None, role: str) -> None:
    """拒绝突变和编码器跨圈，不能把一次整圈跳变当成正常目标。"""
    validate_positions(current)
    if previous is not None:
        for name in MOTORS:
            if abs(current[name] - previous[name]) > MAX_READ_JUMP_COUNTS:
                raise ValueError(f"{role}/{name} 相邻读数跳变超过 {MAX_READ_JUMP_COUNTS} 计数，停止")


def plan_targets(leader_positions, leader_calibration, follower_positions, follower_calibration,
                 max_degrees: float, max_gripper_percent: float) -> tuple[dict, dict, list, list]:
    """将目标限制在从臂当前反馈附近；不是上一条命令附近，不会因受阻而累加。"""
    if any(not math.isfinite(v) or v <= 0 for v in (max_degrees, max_gripper_percent)):
        raise ValueError("每次反馈相对目标限制必须是有限正数")
    validate_follower_positions(follower_positions, follower_calibration)
    normalized = normalize_positions(leader_positions, leader_calibration)
    desired = denormalize_positions(normalized, follower_calibration)
    goals, range_limited, relative_limited = {}, [], []
    for name in MOTORS:
        row, present = follower_calibration[name], follower_positions[name]
        bounded = min(row["range_max"], max(row["range_min"], desired[name]))
        if bounded != desired[name]:
            range_limited.append(name)
        # 与 max_relative_target 等价的计数限制；臂为度，夹爪为百分点，不混用单位。
        delta = (max_gripper_percent * (row["range_max"] - row["range_min"]) / 100
                 if name == "gripper" else max_degrees * 4095 / 360)
        low = max(row["range_min"], math.ceil(present - delta))
        high = min(row["range_max"], math.floor(present + delta))
        goals[name] = min(high, max(low, bounded))  # 向内取整，避免量化后越过相对限制。
        if goals[name] != bounded:
            relative_limited.append(name)
    return goals, normalized, range_limited, relative_limited


class ReadOnlyArm:
    """复用现有总线的有限超时与符号解码，对调用方不提供写入方法。"""

    def __init__(self, port: str, baudrate: int, calibration: dict, role: str):
        self._bus = CalibrationBus(port, baudrate)
        self.calibration = calibration
        self.role = role

    def open(self):
        """只配置并打开主机串口，不执行高级连接初始化。"""
        self._bus.open()

    def close(self):
        """只释放串口，扭矩关闭由显式退出流程负责。"""
        self._bus.close()

    def verify(self):
        """现场只读核对，不需要备份；Phase 只核对当前必需位，不宣称核对历史全部位。"""
        for name, motor_id in MOTORS.items():
            row = self.calibration[name]
            for register, expected in {
                "ID": motor_id, "Model_Number": 777, "Operating_Mode": 0, "Torque_Enable": 0,
                "Homing_Offset": row["homing_offset"],
                "Min_Position_Limit": row["range_min"], "Max_Position_Limit": row["range_max"],
            }.items():
                actual = self._bus.read(name, register)
                if actual != expected:
                    raise ValueError(f"{self.role}/{name}/{register}: 实际 {actual}，预期 {expected}。"
                                     "请先校准或只读核验；不会自动修复或切换已有扭矩。")
            if self._bus.read(name, "Phase") & 0x10:
                raise ValueError(f"{self.role}/{name} Phase bit 4 未清零，请先核验；不会自动修改")

    def positions(self, expected_torque: int) -> dict:
        """每次返回新的完整读数，先核对各关节扭矩状态，不自动重试。"""
        for name in MOTORS:
            actual = self._bus.read(name, "Torque_Enable")
            if actual != expected_torque:
                raise RuntimeError(f"{self.role}/{name} 扭矩={actual}，预期={expected_torque}，停止")
        positions = self._bus.positions()
        validate_positions(positions)
        return positions


class FollowerArm(ReadOnlyArm):
    """从臂只额外开放 Goal_Position 和 Torque_Enable；预览实例禁止所有写入。"""

    def __init__(self, port, baudrate, calibration, *, preview: bool):
        super().__init__(port, baudrate, calibration, "follower")
        self.preview = preview

    def _write(self, name: str, register: str, value: int):
        """逐 ID 请求并检查设备响应及写后回读，不用无状态反馈的广播写入。"""
        if self.preview:
            raise RuntimeError("只读预览禁止写入任何寄存器")
        if register == "Goal_Position":
            row = self.calibration[name]
            if type(value) is not int or not row["range_min"] <= value <= row["range_max"]:
                raise ValueError(f"{name} 目标计数无效或超出已核对的从臂限位")
            address, length = GOAL_POSITION_ADDRESS, 2
        elif register == "Torque_Enable" and type(value) is int and value in (0, 1):
            address, length = REGISTERS[register]
        else:
            raise ValueError("真实跟随只允许写合法目标位置和扭矩开关")
        writer = self._bus.packet.write2ByteTxRx if length == 2 else self._bus.packet.write1ByteTxRx
        comm, error = writer(self._bus.port, MOTORS[name], address, value)
        self._bus._check(name, register, comm, error)
        reader = self._bus.packet.read2ByteTxRx if length == 2 else self._bus.packet.read1ByteTxRx
        actual, comm, error = reader(self._bus.port, MOTORS[name], address)
        self._bus._check(name, register, comm, error)
        if actual != value:
            raise RuntimeError(f"{name}/{register} 写后回读 {actual} != {value}")

    def write_goals(self, positions: dict):
        """先检查完整目标，再逐关节写；部分失败由上层立即进入异常关闭流程。"""
        validate_follower_positions(positions, self.calibration)
        for name in MOTORS:
            self._write(name, "Goal_Position", int(positions[name]))

    def initialize_hold(self) -> dict:
        """START 后、扭矩关闭时读取最新姿态并预写相同目标，避免旧目标生效。"""
        positions = self.positions(expected_torque=0)
        self.write_goals(positions)
        return positions

    def enable_torque(self, holding_positions: dict):
        """逐关节核对保持目标与当前姿态足够接近，才启用该关节；用户需托住臂体。"""
        for name in MOTORS:
            if self._bus.read(name, "Torque_Enable") != 0:
                raise RuntimeError(f"{name} 扭矩状态在启动期间改变，停止")
            actual = self._bus.read(name, "Present_Position")
            row = self.calibration[name]
            if (not math.isfinite(actual) or not row["range_min"] <= actual <= row["range_max"]
                    or abs(actual - holding_positions[name]) > HOLD_DRIFT_COUNTS):
                raise RuntimeError(f"{name} 预写保持目标后移动超过 {HOLD_DRIFT_COUNTS} 计数，请托稳后再启动")
            self._write(name, "Torque_Enable", 1)

    def disable_torque(self) -> list[str]:
        """每关节尽力关闭一次并回读；一个失败仍处理其他关节，不无限重试。"""
        failures = []
        for name in MOTORS:
            try:
                self._write(name, "Torque_Enable", 0)
            except BaseException as error:
                # 清理途中再收到 Ctrl+C 也继续处理余下关节，并保留失败信息。
                failures.append(f"{name}: {type(error).__name__}: {error}")
        return failures
