import argparse  # 解析单步训练演示的命令行参数
import random  # 设置 Python 随机种子

import numpy as np  # 设置 NumPy 随机种子
import torch  # 选择设备并执行前向、反向和参数更新
from torch.utils.data import DataLoader  # 从训练数据集中读取一个批次

from my_act.config import read_yaml  # 读取模型、任务和训练配置
from my_act.data.libero_dataset import LiberoSource  # 读取真实数据的轨迹与图像
from my_act.data.split import split_episodes  # 按完整轨迹划分训练集与验证集
from my_act.data.normalization import compute_stats  # 仅用训练轨迹计算归一化统计量
from my_act.data.dataset import ACTDataset  # 组织图像、状态、动作块和补齐标记
from my_act.models.act import ACT  # 创建完整 ACT 模型
from my_act.models.losses import compute_act_loss  # 计算掩码动作重建与 KL 损失


def main() -> None:  # 从项目根目录执行一次真实数据训练更新
    """从训练配置读取参数，命令行显式值优先；仅用一个真实批次更新一次，不执行配置中的训练步数、日志、验证或保存计划。一次更新不能证明模型已经学会任务。"""  # 函数说明
    parser = argparse.ArgumentParser(description="ACT 真实数据单步训练连通性演示，参数不代表调优结果")  # 创建参数解析器
    parser.add_argument("--model-config", default="configs/act.yaml", help="模型配置路径")  # 默认从项目根目录读取模型配置
    parser.add_argument("--task-config", default="configs/tasks/libero_task10.yaml", help="任务配置路径")  # 默认读取 task10 配置
    parser.add_argument("--train-config", default="configs/train.yaml", help="训练配置路径")  # 默认读取统一训练配置
    parser.add_argument("--seed", type=int, default=None, help="覆盖训练配置中的随机种子")  # 未指定时使用训练配置
    parser.add_argument("--val-count", type=int, default=None, help="覆盖验证轨迹数，默认按训练配置中的 val_ratio 计算")  # 允许显式沿用已有划分
    parser.add_argument("--batch-size", type=int, default=None, help="覆盖训练配置中的批次大小")  # 未指定时使用训练配置
    parser.add_argument("--lr", type=float, default=None, help="覆盖训练配置中的学习率")  # 未指定时使用训练配置
    parser.add_argument("--kl-weight", type=float, default=None, help="覆盖训练配置中的 KL 权重")  # 允许显式传入 0 作为权重
    args = parser.parse_args()  # 读取实际命令行参数
    train_config = read_yaml(args.train_config)  # 读取训练配置，不执行其中预留的训练计划
    seed = args.seed if args.seed is not None else train_config["seed"]  # 显式命令行种子优先，否则使用配置值
    batch_size = args.batch_size if args.batch_size is not None else train_config["batch_size"]  # 解析实际批次大小
    learning_rate = args.lr if args.lr is not None else train_config["learning_rate"]  # 解析实际学习率
    kl_weight = args.kl_weight if args.kl_weight is not None else train_config["kl_weight"]  # 保留 0 等有效命令行覆盖值
    num_workers = train_config["num_workers"]  # 从配置读取数据加载进程数
    weight_decay = train_config["weight_decay"]  # 从配置读取权重衰减系数
    random.seed(seed)  # 设置 Python 随机种子
    np.random.seed(seed)  # 设置 NumPy 随机种子
    torch.manual_seed(seed)  # 设置 PyTorch 随机种子
    cuda_available = torch.cuda.is_available()  # 查询当前环境是否可使用 CUDA
    if cuda_available:  # CUDA 可用时设置其随机种子
        torch.cuda.manual_seed_all(seed)  # 为所有 CUDA 设备设置随机种子
    device = torch.device("cuda" if cuda_available else "cpu")  # 优先使用 CUDA，否则使用 CPU
    print("device:", device, flush=True)  # 打印本次使用的设备
    model_config = read_yaml(args.model_config)  # 读取模型配置并保留预训练设置
    task_config = read_yaml(args.task_config)  # 读取目标任务配置
    source = LiberoSource(task_config)  # 创建真实数据源
    episode_indices = source.get_episode_indices(task_config["dataset"]["task_index"])  # 获取目标任务的全部轨迹编号
    val_count = args.val_count if args.val_count is not None else int(len(episode_indices) * train_config["val_ratio"])  # 显式验证数量优先，否则按配置比例取整
    split = split_episodes(episode_indices, seed=seed, val_count=val_count)  # 复用已有的轨迹划分函数
    print(f"seed={seed}, val_count={val_count}, train_episodes={len(split['train_episodes'])}, val_episodes={len(split['val_episodes'])}", flush=True)  # 打印实际划分参数和数量
    print(f"batch_size={batch_size}, num_workers={num_workers}, learning_rate={learning_rate}, weight_decay={weight_decay}, kl_weight={kl_weight}", flush=True)  # 打印实际生效的数据加载和优化参数
    stats = compute_stats(source, split["train_episodes"])  # 仅使用训练轨迹计算统计量
    dataset = ACTDataset(  # 创建使用训练集统计量的训练数据集
        source=source,  # 传入真实数据源
        episode_indices=split["train_episodes"],  # 只包含训练轨迹
        stats=stats,  # 使用训练集归一化统计量
        chunk_size=model_config["chunk_size"],  # 从模型配置读取动作块长度
        image_size=model_config["image_size"],  # 从模型配置读取图像尺寸
    )  # 完成训练数据集创建
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=num_workers)  # 使用实际参数随机取样，默认在主进程加载
    batch = next(iter(loader))  # 只获取一个批次，不遍历整个 DataLoader
    model = ACT(model_config).to(device)  # 保持配置中的预训练设置并将模型移到设备
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)  # 所有参数使用解析后的学习率和配置中的权重衰减
    batch = {name: value.to(device) for name, value in batch.items()}  # 移动全部批次张量，保留原有类型及 bool 补齐标记
    for name, value in batch.items():  # 遍历当前批次的四个字段
        print(f"batch {name}: shape={tuple(value.shape)}, dtype={value.dtype}")  # 打印实际形状和数据类型
    model.train()  # 启用模型的训练模式
    optimizer.zero_grad(set_to_none=True)  # 在唯一一次反向传播前清空梯度
    output = model(  # 使用带示范动作的后验分支执行前向
        images=batch["images"],  # 传入当前帧双相机图像
        state=batch["state"],  # 传入归一化状态
        actions=batch["action"],  # 传入归一化示范动作块
        is_pad=batch["is_pad"],  # 传入动作补齐标记
    )  # 完成一次训练前向
    losses = compute_act_loss(  # 计算本次前向的训练损失
        predicted_actions=output["actions"],  # 使用预测的归一化动作块
        target_actions=batch["action"],  # 使用真实归一化动作块作为目标
        is_pad=batch["is_pad"],  # 排除补齐动作的重建误差
        mu=output["mu"],  # 使用后验均值
        logvar=output["logvar"],  # 使用后验自然对数方差
        kl_weight=kl_weight,  # 使用命令行覆盖或训练配置确定的实际 KL 权重
    )  # 完成损失计算
    for name in ("actions", "mu", "logvar"):  # 查看动作预测与后验参数
        print(f"output {name}: shape={tuple(output[name].shape)}")  # 打印模型输出形状
    for name in ("loss", "l1", "kl"):  # 查看此次更新前向得到的三个损失
        print(f"{name}: {losses[name].item()}")  # 仅为演示打印标量值
    losses["loss"].backward()  # 执行唯一一次反向传播
    for name, parameter in (  # 仅查看本轮指定的三处参数梯度
        ("model.backbone.features[0].weight", model.backbone.features[0].weight),  # 视觉骨干首层卷积权重
        ("model.cvae_encoder.distribution_projection.weight", model.cvae_encoder.distribution_projection.weight),  # CVAE 后验参数投影权重
        ("model.action_head.weight", model.action_head.weight),  # 动作输出头权重
    ):  # 开始打印各处梯度信息
        grad = parameter.grad  # 取得当前参数的梯度
        print(f"{name}: grad_exists={grad is not None}, grad_norm={None if grad is None else grad.norm().item()}")  # 不存在的梯度明确打印 None
    previous_weight = model.action_head.weight.detach().clone()  # 在更新前保存动作输出头权重的独立副本
    optimizer.step()  # 只执行一次参数更新
    weight_change = (model.action_head.weight.detach() - previous_weight).abs().max().item()  # 计算动作输出头权重的最大绝对变化
    print("action_head.weight max_abs_change:", weight_change)  # 打印此次更新造成的权重变化
    print("一次更新只能展示训练链路是否连通，不能证明模型已经学会任务。")  # 明确本次演示的结论范围


if __name__ == "__main__":  # 使用标准脚本入口
    main()  # 执行单步训练演示
