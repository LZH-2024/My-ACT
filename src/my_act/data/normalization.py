import numpy as np  # 拼接轨迹数组并计算逐维统计量

from my_act.data.libero_dataset import LiberoSource  # 使用现有数据源读取轨迹


def compute_stats(source: LiberoSource, episode_indices: list[int]) -> dict:  # 计算传入训练轨迹的状态与动作统计量
    """按训练轨迹的全部帧计算逐维均值和总体标准差，返回一维 float32 数组。"""  # 函数说明
    states = []  # 收集各条训练轨迹的状态数组
    actions = []  # 收集各条训练轨迹的动作数组
    for episode_index in episode_indices:  # 遍历传入的训练集轨迹编号
        episode = source.read_episode(episode_index)  # 沿用现有接口读取单条轨迹
        states.append(episode["state"])  # 保存该轨迹的全部状态帧
        actions.append(episode["action"])  # 保存该轨迹的全部动作帧
    state = np.concatenate(states, axis=0).astype(np.float64)  # 沿时间维拼成 [N, S] 并转为 float64，N 为总帧数、S 为状态维度
    action = np.concatenate(actions, axis=0).astype(np.float64)  # 沿时间维拼成 [N, A] 并转为 float64，A 为单步动作维度
    state_mean = state.mean(axis=0).astype(np.float32)  # 按全部帧计算逐维状态均值，最终转为 float32
    state_std = np.maximum(state.std(axis=0, ddof=0), 1e-6).astype(np.float32)  # 计算总体标准差，并限制下限以避免后续除以零
    action_mean = action.mean(axis=0).astype(np.float32)  # 按全部帧计算逐维动作均值，最终转为 float32
    action_std = np.maximum(action.std(axis=0, ddof=0), 1e-6).astype(np.float32)  # 计算总体标准差，并限制下限以避免后续除以零
    return {  # 返回状态和动作的一维统计量数组
        "state": {"mean": state_mean, "std": state_std},  # 状态均值与标准差，形状均为 [S]
        "action": {"mean": action_mean, "std": action_std},  # 动作均值与标准差，形状均为 [A]
    }  # 完成返回字典


def normalize(values: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:  # 将状态或动作数组归一化
    """用 [D] 统计量广播处理 [D]、[T, D] 或 [B, T, D] 输入；D 为状态或动作维度，不修改输入。"""  # 函数说明
    return ((values - mean) / std).astype(np.float32)  # 使用已限制下限的标准差进行变换，并返回新的 float32 数组


def denormalize(values: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:  # 将归一化后的状态或动作还原
    """用 [D] 统计量广播还原 [D]、[T, D] 或 [B, T, D] 输入；D 为状态或动作维度，不修改输入。"""  # 函数说明
    return (values * std + mean).astype(np.float32)  # 按原统计量还原数值，并返回新的 float32 数组
