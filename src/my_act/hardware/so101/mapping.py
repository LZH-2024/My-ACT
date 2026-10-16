"""计数到 MuJoCo 绝对 rad 目标；实物零点/方向由现场对齐文件明确给出。"""

import numpy as np
from my_act.hardware.so101.calibration import MOTORS

JOINT_NAMES = tuple(MOTORS)


def count_delta(current: float, reference: float, period: int) -> float:
    """仅用于腕转单圈跨界，取最近的有符号计数差，不制造整圈跳变。"""
    return (current - reference + period / 2) % period - period / 2


def validate_config(config: dict):
    """门限均有明确单位；拒绝缺失、非有限或非正的参数。"""
    positive = ('control_freq', 'startup_seconds', 'startup_speed_rad_s', 'print_every_seconds',
                'max_sample_seconds', 'range_tolerance_counts', 'clip_tolerance_rad', 'max_step_rad',
                'alignment_preview_rad', 'alignment_min_counts', 'alignment_max_counts')
    if config['counts_per_turn'] != 4096:
        raise ValueError("当前只支持已核对的 STS3215 4096 计数/圈")
    for key in positive:
        if not np.isfinite(config[key]) or config[key] <= 0:
            raise ValueError(f"{key} 必须为有限正数")
    if config['alignment_min_counts'] >= config['alignment_max_counts']:
        raise ValueError("方向采样最小位移必须小于最大位移")
    endpoints = [config['gripper_closed_rad'], config['gripper_open_rad']]
    if not np.isfinite(endpoints).all() or endpoints[0] == endpoints[1]:
        raise ValueError("夹爪候选角度必须有限且不同")


class JointMapping:
    """五轴用固定计数比例；夹爪按已确认的两个手柄端点单独映射。"""

    def __init__(self, config: dict, alignment: dict, calibration: dict, limits, joint=None):
        validate_config(config)
        self.config, self.calibration = config, calibration
        self.period = config['counts_per_turn']
        self.scale = 2 * np.pi / self.period
        self.limits = np.asarray(limits, dtype=np.float64)
        if self.limits.shape != (6, 2) or not np.isfinite(self.limits).all():
            raise ValueError("模型限位必须是有限的 [6,2] 数组")
        self.active = np.asarray([joint is None or name == joint for name in JOINT_NAMES])
        if not self.active.any():
            raise ValueError("未知的单关节名称")
        if alignment['confirmed_by_user'] is not True or set(alignment['arm']) != set(JOINT_NAMES[:5]):
            raise ValueError("需要完整且经现场确认的五关节对齐记录，请先运行 --align")
        self.references, self.directions, self.reference_rad = [], [], []
        for name in JOINT_NAMES[:5]:
            row = alignment['arm'][name]
            if row['direction'] not in (-1, 1):
                raise ValueError(f"{name} 方向必须为 +1 或 -1")
            if not np.isfinite([row['reference_count'], row['reference_rad']]).all():
                raise ValueError(f"{name} 参考点必须有限")
            self.references.append(row['reference_count'])
            self.directions.append(row['direction'])
            self.reference_rad.append(row['reference_rad'])
        self.references = np.asarray(self.references, dtype=np.float64)
        self.directions = np.asarray(self.directions)
        self.reference_rad = np.asarray(self.reference_rad)
        if np.any(self.reference_rad < self.limits[:5, 0]) or np.any(self.reference_rad > self.limits[:5, 1]):
            raise ValueError("参考姿态超出模型限位")
        self.gripper = alignment['gripper']
        g = self.gripper
        endpoints = [g[k] for k in ('closed_count', 'open_count', 'closed_rad', 'open_rad')]
        if not np.isfinite(endpoints).all() or abs(g['open_count'] - g['closed_count']) < config['alignment_min_counts']:
            raise ValueError("夹爪对齐端点无效")
        if (min(g['closed_rad'], g['open_rad']) < self.limits[5, 0]
                or max(g['closed_rad'], g['open_rad']) > self.limits[5, 1]
                or g['closed_rad'] == g['open_rad']):
            raise ValueError("夹爪对齐角度超出模型范围或端点重合")
        self.validate_counts(np.r_[self.references, g['closed_count']])
        self.validate_counts(np.r_[self.references, g['open_count']])
        self.previous_counts = None
        self.previous_targets = None
        self.wrist_count = None

    def validate_counts(self, counts):
        """采集范围只用于异常检查，绝不作为五轴角度缩放范围。"""
        counts = np.asarray(counts, dtype=np.float64)
        if counts.shape != (6,) or not np.isfinite(counts).all():
            raise ValueError("主臂样本必须为完整六维有限计数")
        warnings = []
        tolerance = self.config['range_tolerance_counts']
        for i, name in enumerate(JOINT_NAMES):
            row = self.calibration[name]
            if name == 'wrist_roll':
                if not 0 <= counts[i] < self.period:
                    raise ValueError("腕转单圈读数不在 0～4095，停止，不静默取模")
                continue
            excess = max(row['range_min'] - counts[i], counts[i] - row['range_max'], 0)
            if excess > tolerance:
                raise ValueError(f"{name} 超采集范围 {excess:.1f} 计数，大于 {tolerance}，停止")
            if excess:
                warnings.append(f"{name} 超采集范围 {excess:.1f} 计数")
        return counts, warnings

    def map(self, counts, held_targets):
        """先完整校验再更新内部连续状态；返回裁剪前目标、控制目标和提示。"""
        counts, warnings = self.validate_counts(counts)
        if self.previous_counts is None:
            wrist = self.references[4] + count_delta(counts[4], self.references[4], self.period)
        else:
            wrist = self.wrist_count + count_delta(counts[4], self.previous_counts[4], self.period)
        continuous = counts[:5].copy()
        continuous[4] = wrist  # 连续积累小增量；不会把多圈运动周期性跳回合法限位。
        arm = self.reference_rad + self.directions * (continuous - self.references) * self.scale
        g = self.gripper
        opening = (counts[5] - g['closed_count']) / (g['open_count'] - g['closed_count'])
        raw = np.r_[arm, g['closed_rad'] + opening * (g['open_rad'] - g['closed_rad'])]
        if not np.isfinite(raw).all():
            raise ValueError("映射目标存在 NaN/Inf")
        if self.previous_targets is not None:
            jump = np.abs(raw - self.previous_targets)
            if np.any(jump[self.active] > self.config['max_step_rad']):
                raise ValueError(f"目标跳变超过 {self.config['max_step_rad']} rad/样本：{dict(zip(JOINT_NAMES, jump))}")
        excess = np.maximum(self.limits[:, 0] - raw, raw - self.limits[:, 1])
        if np.any(excess[self.active] > self.config['clip_tolerance_rad']):
            names = [JOINT_NAMES[i] for i in range(6) if self.active[i] and excess[i] > self.config['clip_tolerance_rad']]
            raise ValueError(f"{names} 明显超出仿真范围，停止；请检查参考姿态和方向")
        clipped = self.active & (excess > 0)
        targets = np.asarray(held_targets, dtype=np.float64).copy()
        targets[self.active] = np.clip(raw, self.limits[:, 0], self.limits[:, 1])[self.active]
        self.previous_counts, self.previous_targets, self.wrist_count = counts.copy(), raw.copy(), wrist
        return raw, targets, clipped, warnings
