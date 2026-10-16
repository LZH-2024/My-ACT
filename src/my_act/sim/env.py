"""按名称控制现有 SO101 场景；硬件通信与任务评测不属于本模块。"""

from pathlib import Path
import mujoco
import numpy as np

# 与原查看入口一致：五个臂关节为模型零位，夹爪保持 0.7 rad。
INITIAL_TARGETS = dict(shoulder_pan=0.0, shoulder_lift=0.0, elbow_flex=0.0,
                       wrist_flex=0.0, wrist_roll=0.0, gripper=0.7)
JOINT_NAMES = tuple(INITIAL_TARGETS)


class SO101Sim:
    """绝对位置目标控制，六维顺序由 JOINT_NAMES 确定，全部单位为 rad。"""

    def __init__(self, scene: str | Path, control_freq: float = 20.0):
        self.model = mujoco.MjModel.from_xml_path(str(Path(scene).resolve()))
        self.data = mujoco.MjData(self.model)
        if not np.isfinite(control_freq) or control_freq <= 0:
            raise ValueError("控制频率必须是有限正数")
        ratio = 1.0 / control_freq / self.model.opt.timestep
        self.substeps = round(ratio)
        if self.substeps < 1 or not np.isclose(ratio, self.substeps):
            raise ValueError("每个控制周期必须对应整数个物理步")
        self.control_freq = control_freq
        self.qpos_addresses, self.actuator_ids, ranges = [], [], []
        for name in JOINT_NAMES:
            joint, actuator = self.model.joint(name), self.model.actuator(name)
            if (joint.type[0] != mujoco.mjtJoint.mjJNT_HINGE
                    or actuator.trnid[0] != joint.id or not joint.limited[0]
                    or not actuator.ctrllimited[0]):
                raise ValueError(f"{name} 必须是同名执行器驱动的有限位铰链")
            self.qpos_addresses.append(int(joint.qposadr[0]))
            self.actuator_ids.append(actuator.id)
            ranges.append([max(joint.range[0], actuator.ctrlrange[0]),
                           min(joint.range[1], actuator.ctrlrange[1])])
        self.limits = np.asarray(ranges)
        if np.any(self.limits[:, 0] >= self.limits[:, 1]):
            raise ValueError("关节限位与执行器范围没有有效交集")
        self.initial_targets = np.asarray(list(INITIAL_TARGETS.values()), dtype=np.float64)
        self.viewer = None
        self.renderer = None
        self.reset()

    def reset(self):
        """仅重置时设 qpos；自由方块保留场景定义的初始状态。"""
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qpos_addresses] = self.initial_targets
        self.set_targets(self.initial_targets)
        mujoco.mj_forward(self.model, self.data)

    def set_targets(self, targets):
        """只写仿真 ctrl，拒绝非有限值、维度错误和未处理的越界目标。"""
        targets = np.asarray(targets, dtype=np.float64)
        if targets.shape != (6,) or not np.isfinite(targets).all():
            raise ValueError("仿真目标必须是六维有限 rad 数组")
        if np.any(targets < self.limits[:, 0]) or np.any(targets > self.limits[:, 1]):
            raise ValueError("仿真目标超出关节与执行器允许范围")
        self.data.ctrl[self.actuator_ids] = targets

    def advance(self, physical_steps: int):
        """按固定物理步推进；不根据墙钟延迟追赶，也不覆盖 qpos。"""
        for _ in range(physical_steps):
            warnings_before = self.data.warning.number.copy()
            mujoco.mj_step(self.model, self.data)
            if (not all(np.isfinite(x).all() for x in (self.data.qpos, self.data.qvel, self.data.qacc))
                    or np.any(self.data.warning.number > warnings_before)):
                raise RuntimeError("仿真出现非有限状态或 MuJoCo 警告，停止推进")
        mujoco.mj_forward(self.model, self.data)

    def step(self, targets):
        """执行一个控制周期；20 Hz、0.002 秒时恰好推进 25 个物理步。"""
        self.set_targets(targets)
        self.advance(self.substeps)

    def joint_positions(self):
        """返回动力学计算的实际关节位置，不能用 ctrl 目标替代。"""
        return self.data.qpos[self.qpos_addresses].copy()

    def open_viewer(self):
        """打开交互窗口；遥操作不创建离屏相机渲染器。"""
        from mujoco import viewer
        self.viewer = viewer.launch_passive(self.model, self.data)
        with self.viewer.lock():
            self.viewer.cam.lookat[:] = [0.19, 0.0, 0.10]
            self.viewer.cam.distance = 0.85
            self.viewer.cam.azimuth = -55
            self.viewer.cam.elevation = -32
        self.viewer.sync()
        return self.viewer

    def camera_image(self):
        """仅显式请求时生成固定相机 RGB uint8 图像。"""
        if self.renderer is None:
            self.renderer = mujoco.Renderer(self.model, height=480, width=640)
        self.renderer.update_scene(self.data, camera="overview")
        return self.renderer.render().copy()

    def close(self):
        """关闭窗口和按需创建的渲染器；即使窗口关闭失败也释放渲染器。"""
        try:
            if self.viewer is not None:
                self.viewer.close()
                self.viewer = None
        finally:
            if self.renderer is not None:
                self.renderer.close()
                self.renderer = None
