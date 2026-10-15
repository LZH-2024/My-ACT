import numpy as np  # 拼接原始尺度状态并统一数值类型
import torch  # 将图像和状态转换为 CPU 张量


def convert_observation(raw: dict) -> dict:  # 将 LIBERO 原始观测转换为 ACTPolicy 输入
    """按外部、腕部相机顺序翻转 RGB 图像，拼接位置、弧度轴角和夹爪位置；返回未归一化的 CPU 张量，调用进程须提前设置仿真环境变量。"""  # 函数说明
    from robosuite.utils.transform_utils import quat2axisangle  # 调用时才导入，避免仅导入本模块就初始化 robosuite

    images = []  # 按固定相机顺序收集图像
    for key in ("agentview_image", "robot0_eye_in_hand_image"):  # 先外部相机，再腕部相机
        image = raw[key][::-1, ::-1, :].copy()  # 同时翻转高度和宽度并复制，消除负步长且不修改原图
        images.append(torch.from_numpy(image).permute(2, 0, 1))  # 将 RGB uint8 图像从 HWC 转为 CHW
    images = torch.stack(images, dim=0).unsqueeze(0)  # 堆叠为 CPU uint8 张量 [1, 2, 3, H, W]
    axis_angle = quat2axisangle(raw["robot0_eef_quat"].copy())  # 将 xyzw 四元数副本转为三维轴角，保护原始观测
    state = np.concatenate((raw["robot0_eef_pos"], axis_angle, raw["robot0_gripper_qpos"])).astype(np.float32)  # 按位置、轴角、夹爪原顺序拼成八维 float32 状态
    return {  # 返回未经缩放或归一化的策略输入
        "images": images,  # CPU uint8 双相机图像，保留原始尺寸与像素范围
        "state": torch.from_numpy(state).unsqueeze(0),  # CPU float32 原始尺度状态，形状为 [1, 8]
    }  # 完成输入字典
