import argparse  # 解析三份配置文件的路径
import json  # 保存轨迹划分信息
import shutil  # 原样复制任务配置以保留来源注释
from datetime import datetime  # 生成实验目录的时间戳
from pathlib import Path  # 组织实验文件路径
from zoneinfo import ZoneInfo  # 使用 Asia/Shanghai 时区

import numpy as np  # 保存独立的数值统计量数组
import yaml  # 保存读取后的完整 YAML 配置

from my_act.config import read_yaml  # 复用已有配置读取函数
from my_act.data.split import split_episodes  # 按完整轨迹划分训练集与验证集
from my_act.data.normalization import compute_stats  # 仅用训练轨迹计算归一化统计量


def main(source=None) -> None:  # 从项目根目录准备一次新的实验
    """调用方须传入与任务配置对应的真实数据源；保存配置快照、轨迹划分和训练集统计量，不读取视频、不创建模型或启动训练。"""  # 函数说明
    parser = argparse.ArgumentParser(description="准备 ACT 实验配置、轨迹划分与归一化统计量")  # 创建命令行参数解析器
    parser.add_argument("--model-config", default="configs/act.yaml", help="模型配置路径")  # 默认使用现有模型配置
    parser.add_argument("--task-config", required=True, help="任务配置路径；SO101 配置尚未实现")  # 数据接入后由调用方显式指定
    parser.add_argument("--train-config", default="configs/train.yaml", help="训练配置路径")  # 默认使用统一训练配置
    args = parser.parse_args()  # 读取实际配置路径
    if source is None:  # 尚未接入真实的 SO101 数据源，拒绝产生实验或训练产物
        parser.error("SO101 数据源尚未实现；当前仅支持 --help。接入真实数据源后才能准备实验或训练。")  # 明确报告缺失适配，不使用假数据
    model_config = read_yaml(args.model_config)  # 读取完整模型配置
    task_config = read_yaml(args.task_config)  # 读取完整任务配置
    train_config = read_yaml(args.train_config)  # 读取完整训练配置
    task_index = task_config["dataset"]["task_index"]  # 取得目标任务编号
    episode_indices = source.get_episode_indices(task_index)  # 获取目标任务的全部轨迹编号
    seed = train_config["seed"]  # 使用训练配置中的随机种子
    val_ratio = train_config["val_ratio"]  # 使用训练配置中的验证轨迹比例
    val_count = int(len(episode_indices) * val_ratio)  # 按比例向下取整得到验证轨迹数量
    split = split_episodes(episode_indices, seed=seed, val_count=val_count)  # 复用已有轨迹划分函数
    stats = compute_stats(source, split["train_episodes"])  # 仅用训练轨迹计算状态与动作统计量
    timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S")  # 使用上海时区生成秒级时间戳
    experiment_dir = Path(train_config["output_dir"]) / timestamp  # 在配置的输出根目录下创建本次实验路径
    experiment_dir.mkdir(parents=True, exist_ok=False)  # 同名目录存在时直接报错，避免覆盖已有实验
    print("experiment_dir:", experiment_dir.resolve())  # 打印本次实验的绝对路径
    print("task_index:", task_index)  # 打印目标任务编号
    print(f"train_episodes={len(split['train_episodes'])}, val_episodes={len(split['val_episodes'])}")  # 打印训练和验证轨迹数量
    for filename, config in (  # 保存读取后的模型与训练配置
        ("model_config.yaml", model_config),  # 模型配置快照
        ("train_config.yaml", train_config),  # 训练配置快照
    ):  # 依次处理模型与训练配置
        path = experiment_dir / filename  # 拼接当前配置的保存路径
        with path.open("w", encoding="utf-8") as file:  # 使用 UTF-8 写入 YAML 文件
            yaml.safe_dump(config, file, allow_unicode=True, sort_keys=False)  # 保留中文与配置字段顺序
        print("saved:", path.resolve())  # 打印当前配置快照路径
    task_path = experiment_dir / "task_config.yaml"  # 仅保存一份带来源注释的任务配置
    shutil.copyfile(args.task_config, task_path)  # 原样保留任务名称、数据版本和 revision 等注释
    print("saved:", task_path.resolve())  # 打印任务配置快照路径
    split_record = {  # 组织本次实验使用的划分信息
        "task_index": task_index,  # 记录目标任务编号
        "seed": seed,  # 记录划分种子
        "val_ratio": val_ratio,  # 记录验证轨迹比例
        "val_count": val_count,  # 记录实际验证轨迹数量
        "train_episodes": split["train_episodes"],  # 记录全部训练轨迹编号
        "val_episodes": split["val_episodes"],  # 记录全部验证轨迹编号
    }  # 完成划分信息字典
    split_path = experiment_dir / "split.json"  # 划分信息的保存路径
    with split_path.open("w", encoding="utf-8") as file:  # 使用 UTF-8 写入 JSON 文件
        json.dump(split_record, file, ensure_ascii=False, indent=2)  # 保留中文并使用两空格缩进
    print("saved:", split_path.resolve())  # 打印划分信息路径
    arrays = {  # 将现有统计量展开为四个一维 float32 数组
        "state_mean": stats["state"]["mean"],  # 状态逐维均值
        "state_std": stats["state"]["std"],  # 状态逐维标准差
        "action_mean": stats["action"]["mean"],  # 动作逐维均值
        "action_std": stats["action"]["std"],  # 动作逐维标准差
    }  # 完成数值数组映射，不保存嵌套字典或 object 数组
    stats_path = experiment_dir / "stats.npz"  # 统计量的保存路径
    np.savez(stats_path, **arrays)  # 将四个数值数组分别写入 NPZ，不使用 pickle
    for name, array in arrays.items():  # 查看本次保存的四个统计量
        print(f"{name}: shape={array.shape}, dtype={array.dtype}")  # 打印数组名称、形状和数据类型
    print("saved:", stats_path.resolve())  # 打印统计量文件路径


if __name__ == "__main__":  # 使用标准脚本入口
    main()  # 执行实验准备流程
