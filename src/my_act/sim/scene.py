"""查看场景与主臂跟随共用的初始姿态。"""

import mujoco

# 五个臂关节以模型零位开始，夹爪保持 0.7 rad 开口。
INITIAL_TARGETS = {
    "shoulder_pan": 0.0,
    "shoulder_lift": 0.0,
    "elbow_flex": 0.0,
    "wrist_flex": 0.0,
    "wrist_roll": 0.0,
    "gripper": 0.7,
}


def reset_scene(model: mujoco.MjModel, data: mujoco.MjData) -> None:
    """仅在初始化时按名称设置 qpos，随后由位置执行器保持姿态。"""
    mujoco.mj_resetData(model, data)
    for name, target in INITIAL_TARGETS.items():
        data.qpos[int(model.joint(name).qposadr[0])] = target
        data.ctrl[model.actuator(name).id] = target
    mujoco.mj_forward(model, data)
