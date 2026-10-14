import numpy as np  # 创建动作块数组和补齐标记


def make_action_chunk(  # 截取包含当前帧的动作块，并标记补齐位置
    actions: np.ndarray,  # 单条轨迹已经归一化的动作数组
    start_index: int,  # 当前帧在动作数组中的位置
    chunk_size: int,  # 动作块长度 K
) -> tuple[np.ndarray, np.ndarray]:  # 返回动作块和补齐标记
    """输入为单条轨迹归一化后的 [T, A] 动作，约定 0 <= start_index < T 且 K 为正整数；从当前帧开始截取，不跨轨迹、不修改输入，补零为归一化空间中的占位值。"""  # 函数说明与输入约定
    selected = actions[start_index:start_index + chunk_size]  # 从当前帧开始截取最多 K 步动作
    valid_count = len(selected)  # 记录实际截取的有效动作数量
    action_chunk = np.zeros((chunk_size, actions.shape[1]), dtype=np.float32)  # 创建 [K, A] 的 float32 全零数组
    action_chunk[:valid_count] = selected  # 将有效动作复制到动作块前部，不修改输入数组
    is_pad = np.ones(chunk_size, dtype=bool)  # 创建 [K] 的布尔数组，初始全部标记为补齐位置
    is_pad[:valid_count] = False  # 将有效动作位置标记为 False，其余补齐位置保持 True
    return action_chunk, is_pad  # 返回动作块及对应的补齐标记
