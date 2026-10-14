import random  # 提供独立的随机数生成器


def split_episodes(episode_indices: list[int], seed: int, val_count: int) -> dict:  # 按指定种子和验证集数量划分轨迹
    """以完整轨迹而非单帧为单位划分训练集和验证集，不修改传入列表。"""  # 函数说明
    indices = sorted(episode_indices)  # 创建升序排列的新列表，保留原列表不变
    rng = random.Random(seed)  # 创建使用指定种子的独立随机数生成器
    rng.shuffle(indices)  # 打乱新列表中的轨迹编号
    val_episodes = sorted(indices[:val_count])  # 将前 val_count 条轨迹作为验证集，并升序排列
    train_episodes = sorted(indices[val_count:])  # 将其余轨迹作为训练集，并升序排列
    return {  # 返回随机种子及两组完整轨迹编号
        "seed": seed,  # 记录本次划分使用的随机种子
        "train_episodes": train_episodes,  # 训练集轨迹编号列表
        "val_episodes": val_episodes,  # 验证集轨迹编号列表
    }  # 完成返回字典
