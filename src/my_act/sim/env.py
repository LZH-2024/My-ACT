from pathlib import Path  # 解析本地场景路径

import mujoco  # 使用原生物理仿真与相机渲染
import numpy as np  # 处理关节数组与动作合法性


class SO101Sim:
    """六维绝对位置控制：五个臂关节加夹爪 hinge，均为 rad；无抓取任务与成功判定。"""

    joint_names = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")

    def __init__(self, config: dict) -> None:
        """按名称绑定关节和同名位置执行器；配置路径相对于项目根目录。"""
        self.model = mujoco.MjModel.from_xml_path(str(Path(config["scene"])))
        self.data = mujoco.MjData(self.model)
        self.control_freq = float(config["control_freq"])
        timestep = float(config["physics_timestep"])
        if not np.isfinite([self.control_freq, timestep]).all() or min(self.control_freq, timestep) <= 0:
            raise ValueError("控制频率与物理时间步必须是有限正数")
        ratio = 1.0 / self.control_freq / timestep
        self.substeps = round(ratio)
        if self.substeps < 1 or not np.isclose(ratio, self.substeps, rtol=0, atol=1e-9):
            raise ValueError("一个控制周期必须对应整数个物理步")
        self.model.opt.timestep = timestep  # 固定物理步长，不随窗口刷新改变
        joint_ids = [mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name) for name in self.joint_names]
        actuator_ids = [mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, name) for name in self.joint_names]
        if min(joint_ids + actuator_ids) < 0:
            raise ValueError("模型缺少接口约定的关节或同名执行器")
        self.joint_ids = np.asarray(joint_ids)
        self.actuator_ids = np.asarray(actuator_ids)
        if np.any(self.model.jnt_type[self.joint_ids] != mujoco.mjtJoint.mjJNT_HINGE):
            raise ValueError("当前接口要求六个转动关节，单位为 rad")
        if np.any(self.model.actuator_trnid[self.actuator_ids, 0] != self.joint_ids):
            raise ValueError("同名执行器未绑定对应关节")
        self.qpos_indices = self.model.jnt_qposadr[self.joint_ids]  # 不假设关节是 qpos 的前六项
        self.low = np.maximum(self.model.jnt_range[self.joint_ids, 0], self.model.actuator_ctrlrange[self.actuator_ids, 0])
        self.high = np.minimum(self.model.jnt_range[self.joint_ids, 1], self.model.actuator_ctrlrange[self.actuator_ids, 1])
        self.initial_positions = self._validate_action(config["initial_joint_positions"]).copy()
        self.camera = dict(config["camera"])
        if mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, self.camera["name"]) < 0:
            raise ValueError("场景中不存在配置指定的相机")
        self.renderer = None  # 首次获取观测时创建，纯加载不要求图形上下文

    def _validate_action(self, action) -> np.ndarray:
        """拒绝维度错误、非有限数和越界目标，不静默裁剪。"""
        target = np.asarray(action, dtype=np.float64)
        if target.shape != (len(self.joint_names),):
            raise ValueError(f"动作应为六维数组，实际为 {target.shape}")
        if not np.isfinite(target).all():
            raise ValueError("动作包含 NaN 或 Inf")
        if np.any(target < self.low) or np.any(target > self.high):
            raise ValueError(f"关节目标越界：{target}；下限 {self.low}，上限 {self.high}")
        return target

    def reset(self) -> dict:
        """恢复固定初始姿态，目标与初始关节角一致；不执行隐藏等待动作。"""
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qpos_indices] = self.initial_positions  # 仅 reset 直接设置初始状态
        self.data.ctrl[self.actuator_ids] = self.initial_positions
        mujoco.mj_forward(self.model, self.data)
        return self.get_observation()

    def step(self, action) -> dict:
        """将绝对目标交给位置执行器，推进一个固定控制周期后返回实际观测。"""
        target = self._validate_action(action)
        self.data.ctrl[self.actuator_ids] = target  # 控制过程中不直接覆盖实际关节位置
        mujoco.mj_step(self.model, self.data, nstep=self.substeps)
        mujoco.mj_forward(self.model, self.data)  # 让渲染与接触信息对应最终状态
        if not np.isfinite(self.data.qpos).all() or not np.isfinite(self.data.qvel).all():
            raise RuntimeError("仿真状态包含 NaN 或 Inf")
        return self.get_observation()

    def get_observation(self) -> dict:
        """返回 state[6] float32 实际关节角、images[1,H,W,3] RGB uint8 和秒级仿真时间。"""
        if self.renderer is None:
            self.renderer = mujoco.Renderer(self.model, height=self.camera["height"], width=self.camera["width"])
        self.renderer.update_scene(self.data, camera=self.camera["name"])
        image = self.renderer.render().copy()  # 保留原始 RGB 方向，不套用旧环境的图像翻转
        return {"state": self.data.qpos[self.qpos_indices].astype(np.float32), "images": image[None], "timestamp": float(self.data.time)}

    def close(self) -> None:
        """释放已经创建的相机渲染器，窗口由演示入口关闭。"""
        if self.renderer is not None:
            self.renderer.close()
            self.renderer = None
