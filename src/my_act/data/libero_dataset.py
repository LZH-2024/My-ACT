import json  # 读取 JSON 格式的数据集信息
from pathlib import Path  # 表示数据目录和元数据文件路径

import pandas as pd  # 读取 Parquet 格式的轨迹元数据


class LiberoSource:  # 定义 LIBERO 数据源
    """保存数据集信息、相机顺序和整个数据集的轨迹元数据索引。"""  # 类说明

    def __init__(self, task: dict) -> None:  # 接收任务配置字典并初始化数据源
        """从配置指定的相对目录读取数据集信息和全部轨迹元数据。"""  # 构造函数说明
        self.root = Path(task["dataset"]["root"])  # 直接使用相对于项目根目录的数据路径
        self.camera_keys = task["dataset"]["camera_keys"]  # 保持配置中的相机顺序
        with (self.root / "meta" / "info.json").open("r", encoding="utf-8") as file:  # 以 UTF-8 打开数据集信息文件
            self.info = json.load(file)  # 保存数据格式、特征等数据集信息
        self.episode_metadata = {}  # 保存整个数据集的轨迹元数据，以轨迹编号作为键
        for path in sorted((self.root / "meta" / "episodes").rglob("*.parquet")):  # 按路径排序遍历全部轨迹元数据文件
            metadata = pd.read_parquet(path)  # 读取当前 Parquet 元数据表
            for record in metadata.to_dict(orient="records"):  # 将每一行转换为普通字典
                self.episode_metadata[int(record["episode_index"])] = record  # 用整数轨迹编号索引该条记录
