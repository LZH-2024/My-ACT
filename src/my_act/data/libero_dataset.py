import json  # 读取 JSON 格式的数据集信息
from pathlib import Path  # 表示数据目录和元数据文件路径

import numpy as np  # 堆叠状态与动作，并指定数组的数据类型
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

    def read_episode(self, episode_index: int) -> dict:  # 读取指定编号轨迹的状态、动作和时间戳
        """返回状态 [T, S]、动作 [T, A] 和时间戳 [T]；T 为时间步数，S 为状态维度，A 为单步动作维度。"""  # 方法说明
        metadata = self.episode_metadata[episode_index]  # 取得指定轨迹的元数据
        chunk_index = int(metadata["data/chunk_index"])  # 将数据块编号转换为整数
        file_index = int(metadata["data/file_index"])  # 将文件编号转换为整数
        path = self.root / self.info["data_path"].format(  # 使用数据集路径模板拼出实际 Parquet 路径
            chunk_index=chunk_index,  # 填入数据块编号
            file_index=file_index,  # 填入文件编号
        )  # 完成数据文件路径拼接
        data = pd.read_parquet(  # 读取轨迹所在的 Parquet 文件
            path,  # 指定实际数据文件路径
            columns=["episode_index", "frame_index", "observation.state", "action", "timestamp"],  # 仅加载本次需要的五列
        )  # 完成指定列的读取
        episode = data.loc[data["episode_index"] == episode_index].sort_values("frame_index")  # 筛选目标轨迹，并按帧编号升序排列
        return {  # 将轨迹数据作为普通字典返回
            "state": np.stack(episode["observation.state"].to_numpy()).astype(np.float32),  # 堆叠为 [T, S] 的 float32 状态数组
            "action": np.stack(episode["action"].to_numpy()).astype(np.float32),  # 堆叠为 [T, A] 的 float32 动作数组
            "timestamp": episode["timestamp"].to_numpy(dtype=np.float64),  # 转换为 [T] 的 float64 时间戳数组
        }  # 完成返回字典
