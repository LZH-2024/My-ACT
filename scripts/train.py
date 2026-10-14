import argparse  # 解析实验目录与流程演示开关
import json  # 读取轨迹划分并写入逐条指标
import random  # 设置 Python 随机种子
from datetime import datetime  # 生成本次运行时间戳
from pathlib import Path  # 组织实验与运行文件路径
from zoneinfo import ZoneInfo  # 指定上海时区

import numpy as np  # 读取已保存的统计量并设置随机种子
import torch  # 执行训练与设备管理
import yaml  # 保存实际运行配置
from torch.utils.data import DataLoader, Subset  # 加载数据及选择演示样本

from my_act.config import read_yaml  # 读取已有实验配置
from my_act.data.libero_dataset import LiberoSource  # 创建真实数据源
from my_act.data.dataset import ACTDataset  # 复用图像、状态与动作块数据集
from my_act.models.act import ACT  # 复用完整 ACT 模型
from my_act.models.losses import compute_act_loss  # 复用后验训练损失
from my_act.training.evaluate import evaluate  # 复用零潜变量离线验证
from my_act.training.checkpoint import save_checkpoint  # 复用模型与优化器状态保存


def main() -> None:  # 从项目根目录启动指定实验的一次新运行
    """复用实验划分与统计量，按优化器更新次数训练；smoke-test 仅演示三步流程，不代表正式实验成绩，不支持恢复训练。"""  # 函数说明
    parser = argparse.ArgumentParser(description="ACT 训练入口与三步流程演示")  # 创建命令行参数解析器
    parser.add_argument("--experiment-dir", required=True, help="prepare_training.py 已生成的实验目录")  # 必须明确指定实验目录
    parser.add_argument("--smoke-test", action="store_true", help="仅用少量样本执行三步流程演示")  # 默认不启用流程演示
    args = parser.parse_args()  # 读取本次入口参数
    experiment_dir = Path(args.experiment_dir)  # 使用调用方给定路径，不自动搜索最新实验
    print("experiment_dir:", experiment_dir.resolve(), flush=True)  # 明确打印所用实验目录
    model_config = read_yaml(experiment_dir / "model_config.yaml")  # 读取保存的完整模型配置
    task_config = read_yaml(experiment_dir / "task_config.yaml")  # 读取保存的任务配置
    train_config = read_yaml(experiment_dir / "train_config.yaml")  # 读取保存的训练配置
    with (experiment_dir / "split.json").open("r", encoding="utf-8") as file:  # 打开已保存的轨迹划分
        split = json.load(file)  # 读取固定的训练与验证轨迹编号
    with np.load(experiment_dir / "stats.npz", allow_pickle=False) as arrays:  # 仅加载数值数组，不使用 pickle
        stats = {  # 恢复现有归一化接口需要的嵌套结构
            "state": {"mean": arrays["state_mean"], "std": arrays["state_std"]},  # 恢复训练集状态统计量
            "action": {"mean": arrays["action_mean"], "std": arrays["action_std"]},  # 恢复训练集动作统计量
        }  # 完成统计量恢复，不重新计算
    seed = train_config["seed"]  # 使用实验记录中的随机种子
    random.seed(seed)  # 设置 Python 随机种子
    np.random.seed(seed)  # 设置 NumPy 随机种子
    torch.manual_seed(seed)  # 设置 PyTorch 随机种子
    cuda_available = torch.cuda.is_available()  # 查询 CUDA 是否可用
    if cuda_available:  # CUDA 可用时设置其随机种子
        torch.cuda.manual_seed_all(seed)  # 设置所有 CUDA 设备的随机种子
    device = torch.device("cuda" if cuda_available else "cpu")  # 优先选择 CUDA，否则使用 CPU
    print("device:", device, flush=True)  # 打印实际设备
    source = LiberoSource(task_config)  # 创建数据源，不重新筛选或划分轨迹
    train_dataset = ACTDataset(source, split["train_episodes"], stats, model_config["chunk_size"], model_config["image_size"])  # 仅使用保存的训练轨迹和统计量
    val_dataset = ACTDataset(source, split["val_episodes"], stats, model_config["chunk_size"], model_config["image_size"])  # 验证集使用同一份训练统计量
    batch_size = train_config["batch_size"]  # 默认使用记录中的批次大小
    num_workers = train_config["num_workers"]  # 默认使用记录中的数据加载进程数
    max_steps = train_config["max_steps"]  # 优化器更新总次数，不是 epoch 数
    log_every = train_config["log_every"]  # 训练日志间隔
    eval_every = train_config["eval_every"]  # 离线验证间隔
    save_every = train_config["save_every"]  # 最近一次模型保存间隔
    if args.smoke_test:  # 只在内存中覆盖流程演示参数
        train_dataset = Subset(train_dataset, range(4))  # 仅使用前四个训练样本
        val_dataset = Subset(val_dataset, range(3))  # 仅使用前三个验证样本
        batch_size = 2  # 演示使用两个样本组成一个批次
        num_workers = 0  # 演示使用主进程加载数据
        max_steps = 3  # 演示只完成三次优化器更新
        log_every = eval_every = save_every = 1  # 演示每步记录、验证并保存
        print("这是流程演示，不是正式实验成绩。", flush=True)  # 明确说明本次指标的用途
    learning_rate = train_config["learning_rate"]  # 使用配置中的统一学习率
    weight_decay = train_config["weight_decay"]  # 使用配置中的权重衰减
    kl_weight = train_config["kl_weight"]  # 使用配置中的 KL 损失权重
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=num_workers)  # 每轮重新随机遍历训练样本
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)  # 按固定顺序遍历本次验证样本
    timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S")  # 生成上海时区的运行时间戳
    run_dir = experiment_dir / "runs" / timestamp  # 在指定实验下创建本次运行路径
    run_dir.mkdir(parents=True, exist_ok=False)  # 同名运行已存在时直接报错，不覆盖
    run_config = {  # 记录内存中实际生效的运行参数
        "smoke_test": args.smoke_test,  # 标记是否为流程演示
        "seed": seed,  # 记录随机种子
        "device": str(device),  # 记录实际计算设备
        "batch_size": batch_size,  # 记录实际批次大小
        "num_workers": num_workers,  # 记录实际加载进程数
        "learning_rate": learning_rate,  # 记录学习率
        "weight_decay": weight_decay,  # 记录权重衰减
        "kl_weight": kl_weight,  # 记录 KL 权重
        "max_steps": max_steps,  # 记录实际更新次数上限
        "log_every": log_every,  # 记录实际日志间隔
        "eval_every": eval_every,  # 记录实际验证间隔
        "save_every": save_every,  # 记录实际保存间隔
        "num_train_samples": len(train_dataset),  # 记录本次实际训练样本数量
        "num_val_samples": len(val_dataset),  # 记录本次实际验证样本数量
    }  # 完成实际运行配置
    with (run_dir / "run_config.yaml").open("w", encoding="utf-8") as file:  # 保存本次运行配置，不修改实验配置
        yaml.safe_dump(run_config, file, allow_unicode=True, sort_keys=False)  # 按字段顺序写入 UTF-8 YAML
    print("run_dir:", run_dir.resolve(), flush=True)  # 打印本次唯一运行目录
    model = ACT(model_config).to(device)  # 保持预训练设置，创建模型并移到设备
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)  # 所有参数使用相同学习率
    step = 0  # 已完成的优化器更新次数从零开始
    best_val_l1 = float("inf")  # 最佳验证误差初始为正无穷
    best_step = 0  # 记录最佳验证误差对应的更新次数
    last_path = run_dir / "last.pt"  # 最近一次 checkpoint 路径
    best_path = run_dir / "best.pt"  # 最佳验证 checkpoint 路径
    with (run_dir / "metrics.jsonl").open("w", encoding="utf-8") as metrics_file:  # 在本次新目录中创建逐行日志
        while step < max_steps:  # 未达到更新上限时继续遍历训练加载器
            for batch in train_loader:  # 每轮重新迭代，不缓存图像批次
                model.train()  # 每步开始时启用训练模式
                batch = {name: value.to(device) for name, value in batch.items()}  # 移动批次张量并保留原类型
                optimizer.zero_grad(set_to_none=True)  # 清空上一步梯度
                output = model(images=batch["images"], state=batch["state"], actions=batch["action"], is_pad=batch["is_pad"])  # 通过后验分支预测动作
                losses = compute_act_loss(output["actions"], batch["action"], batch["is_pad"], output["mu"], output["logvar"], kl_weight)  # 复用掩码重建与 KL 损失
                losses["loss"].backward()  # 反向传播计算梯度
                optimizer.step()  # 执行一次优化器更新
                step += 1  # 更新已完成的优化器步数
                if step % log_every == 0 or step == max_steps:  # 间隔或最后一步只执行一次日志记录
                    record = {"type": "train", "step": step, "loss": losses["loss"].item(), "l1": losses["l1"].item(), "kl": losses["kl"].item()}  # 当前批次更新前的前向损失，不是区间平均值
                    line = json.dumps(record, ensure_ascii=False)  # 将本条训练指标转换为 JSON
                    print(line, flush=True)  # 打印当前批次训练指标
                    metrics_file.write(line + "\n")  # 每条指标独占一行
                    metrics_file.flush()  # 写入后立即刷新日志
                if step % eval_every == 0 or step == max_steps:  # 间隔或最后一步只验证一次
                    val_metrics = evaluate(model, val_loader, device)  # 遍历本次验证加载器，计算零潜变量离线误差
                    record = {"type": "val", "step": step, **val_metrics}  # 组织验证误差和有效元素计数
                    line = json.dumps(record, ensure_ascii=False)  # 将验证指标转换为 JSON
                    print(line, flush=True)  # 打印离线验证指标，不称为任务成功率
                    metrics_file.write(line + "\n")  # 单独写入一条验证日志
                    metrics_file.flush()  # 写入后立即刷新日志
                    if val_metrics["val_l1"] < best_val_l1:  # 仅在严格优于当前最佳值时保存
                        best_val_l1 = val_metrics["val_l1"]  # 更新最佳离线误差
                        best_step = step  # 更新最佳指标对应步数
                        save_checkpoint(best_path, model, optimizer, step, model_config, stats)  # 保存本次运行的最佳模型和优化器状态
                        with (run_dir / "best_metrics.json").open("w", encoding="utf-8") as file:  # 保存与 best.pt 对应的指标
                            json.dump({"step": best_step, "val_l1": best_val_l1}, file, ensure_ascii=False, indent=2)  # 记录最佳步数与误差
                if step % save_every == 0 or step == max_steps:  # 间隔或最后一步只保存一次最近状态
                    save_checkpoint(last_path, model, optimizer, step, model_config, stats)  # step 表示已完成的更新次数
                if step >= max_steps:  # 达到上限后立即退出当前遍历
                    break  # 外层 while 随后也退出，不多更新一步
    print("completed_steps:", step)  # 打印实际完成的优化器更新次数
    print(f"best_val_l1={best_val_l1}, best_step={best_step}")  # 打印最佳离线误差及对应步数
    print("run_dir:", run_dir.resolve())  # 打印本次运行目录
    print("last.pt:", last_path.resolve())  # 打印最近 checkpoint 路径
    print("best.pt:", best_path.resolve())  # 打印最佳 checkpoint 路径


if __name__ == "__main__":  # 使用标准脚本入口
    main()  # 执行指定实验的新运行
