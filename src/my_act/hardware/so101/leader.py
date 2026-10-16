"""SO101 主臂只读采样；不调用校准写入、扭矩切换或运动指令。"""

import json
from pathlib import Path
import time
import numpy as np
from my_act.hardware.so101.calibration import (
    CalibrationBus, MOTORS, SIGN_BITS, decode_sign_magnitude, validate_calibration,
)


class SO101Leader:
    """复用现有寄存器与符号解码，六个位置顺序对应已确认的 MOTORS。"""

    def __init__(self, port: str, baudrate: int, calibration_file: str | Path,
                 max_sample_seconds: float = 0.2):
        self.calibration = json.loads(Path(calibration_file).read_text(encoding="utf-8"))
        validate_calibration(self.calibration)
        self.bus = CalibrationBus(port, baudrate)  # 构造不打开端口，不隐式初始化。
        self.max_sample_seconds = max_sample_seconds

    def open(self):
        """打开后只读核验；扭矩开启、模式或校准不匹配就关闭端口并报错。"""
        try:
            self.bus.open()
            for name, motor_id in MOTORS.items():
                if self.bus.read(name, "Torque_Enable") != 0:
                    raise RuntimeError(f"{name} 扭矩未关闭；只读工具不会切换扭矩，请退出后现场处理")
                row = self.calibration[name]
                expected = {"ID": motor_id, "Model_Number": 777, "Operating_Mode": 0,
                            "Homing_Offset": row['homing_offset'],
                            "Min_Position_Limit": row['range_min'], "Max_Position_Limit": row['range_max']}
                for register, value in expected.items():
                    actual = self.bus.read(name, register)
                    if actual != value:
                        raise RuntimeError(f"{name}/{register}: 实际 {actual}，预期 {value}；不自动修复")
                if self.bus.read(name, "Phase") & 0x10:
                    raise RuntimeError(f"{name} 不是单圈位置反馈；不自动修改 Phase")
        except BaseException:
            self.close()
            raise

    def read(self):
        """逐个读取完整六关节新样本，失败不返回部分数组或旧值。"""
        started = time.perf_counter()
        raw = [self.bus.read_raw(name, "Present_Position") for name in MOTORS]
        # 与校准使用同一符号规则；返回位置已经包含内部偏置，不能再次减去它。
        counts = np.asarray([decode_sign_magnitude(x, SIGN_BITS['Present_Position']) for x in raw], dtype=np.float64)
        elapsed = time.perf_counter() - started
        if not np.isfinite(counts).all() or elapsed > self.max_sample_seconds:
            raise RuntimeError(f"主臂样本非有限或采样超时（{elapsed:.3f} 秒）；拒绝更新仿真")
        return counts  # 顺序采样不是硬件同步快照，不声称六轴同时刻读取。

    def close(self):
        """只关闭串口，绝不写扭矩或其他寄存器。"""
        self.bus.close()
