from pathlib import Path  # 创建 checkpoint 父目录并表示文件路径

import torch  # 序列化状态字典并转换统计量为张量


def save_checkpoint(  # 保存模型、优化器和实验所需的基础信息
    path: str | Path,  # 调用方指定的 checkpoint 文件路径
    model: torch.nn.Module,  # 提供参数状态字典的模型
    optimizer: torch.optim.Optimizer,  # 提供优化器状态字典的优化器
    step: int,  # 已完成的优化器更新次数
    model_config: dict,  # 完整模型配置字典
    stats: dict,  # 状态和动作的嵌套 NumPy 统计量字典
) -> None:  # 保存文件，不返回数据
    """保存状态字典并允许覆盖指定文件，统计量转为 CPU float32 Tensor 且不修改调用方数据；不保存随机数状态或 DataLoader 位置，不保证逐步精确复现训练轨迹。"""  # 函数说明
    path = Path(path)  # 将字符串或路径统一为 Path
    path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录，允许父目录已经存在
    tensor_stats = {  # 创建新的嵌套字典，不修改原始统计量
        "state": {  # 保存状态统计量
            "mean": torch.tensor(stats["state"]["mean"], dtype=torch.float32, device="cpu"),  # 将状态均值复制为 CPU float32 张量
            "std": torch.tensor(stats["state"]["std"], dtype=torch.float32, device="cpu"),  # 将状态标准差复制为 CPU float32 张量
        },  # 完成状态统计量转换
        "action": {  # 保存动作统计量
            "mean": torch.tensor(stats["action"]["mean"], dtype=torch.float32, device="cpu"),  # 将动作均值复制为 CPU float32 张量
            "std": torch.tensor(stats["action"]["std"], dtype=torch.float32, device="cpu"),  # 将动作标准差复制为 CPU float32 张量
        },  # 完成动作统计量转换
    }  # 完成四个数组转换，避免保存 NumPy 对象
    checkpoint = {  # 创建普通字典，不保存整个模型或优化器对象
        "model": model.state_dict(),  # 保存模型参数和缓冲区
        "optimizer": optimizer.state_dict(),  # 保存优化器状态与参数组信息
        "step": step,  # 记录已完成的更新次数
        "model_config": model_config,  # 保存完整模型配置
        "stats": tensor_stats,  # 保存嵌套结构的张量统计量
    }  # 完成 checkpoint 内容组织
    torch.save(checkpoint, path)  # 写入调用方指定的文件，允许覆盖同名文件


def load_checkpoint(  # 恢复模型和可选的优化器状态
    path: str | Path,  # checkpoint 文件路径
    model: torch.nn.Module,  # 调用方按保存配置创建并提前放到目标设备的模型
    optimizer: torch.optim.Optimizer | None = None,  # 可选的优化器，参数组结构需与保存时一致
    device: str | torch.device = "cpu",  # 加载张量的目标设备
) -> dict:  # 返回加载后的完整 checkpoint 字典
    """调用方负责按保存的 model_config 创建模型并放到目标设备，恢复优化器时需保持参数组结构一致；不切换模型模式。返回的 stats 保持 Tensor，供 NumPy 归一化使用时由调用方通过 .cpu().numpy() 转换。"""  # 函数说明
    checkpoint = torch.load(path, map_location=device, weights_only=True)  # 以受限方式加载状态字典并映射到指定设备
    model.load_state_dict(checkpoint["model"], strict=True)  # 严格匹配模型参数与缓冲区，不修复键名
    if optimizer is not None:  # 仅在调用方提供优化器时恢复其状态
        optimizer.load_state_dict(checkpoint["optimizer"])  # 恢复优化器的状态与参数组
    return checkpoint  # 返回全部保存信息，不自动创建模型或推断配置
