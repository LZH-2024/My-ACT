import json  # 读取 JSON 格式的数据集信息
from pathlib import Path  # 表示数据目录和元数据文件路径

import numpy as np  # 堆叠状态与动作，并指定数组的数据类型
import pandas as pd  # 读取 Parquet 格式的轨迹元数据
import torch  # 堆叠双相机图像并返回张量
from torchcodec.decoders import VideoDecoder  # 使用 TorchCodec 解码视频中的单帧图像


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

    def get_episode_indices(self, task_index: int) -> list[int]:  # 获取指定任务的全部轨迹编号
        """按任务编号筛选轨迹，返回去重后升序排列的整数编号列表。"""  # 方法说明
        episode_indices = set()  # 用集合去除重复的轨迹编号
        for path in sorted((self.root / "data").rglob("*.parquet")):  # 按路径排序遍历数据目录下的 Parquet 文件
            data = pd.read_parquet(path, columns=["episode_index", "task_index"])  # 每个文件只读取轨迹编号和任务编号
            selected = data.loc[data["task_index"] == task_index, "episode_index"]  # 取出属于目标任务的轨迹编号
            episode_indices.update(int(index) for index in selected)  # 转换为 Python 整数并加入集合去重
        return sorted(episode_indices)  # 返回升序排列的轨迹编号列表

    def get_video_location(  # 定位指定相机的视频文件及文件内时间
        self,  # 当前数据源实例
        episode_index: int,  # 目标轨迹编号
        camera_key: str,  # 配置中的完整相机字段名称
        timestamp: float,  # read_episode 返回的轨迹内时间戳，单位为秒
    ) -> tuple[Path, float]:  # 返回视频路径及 Python 浮点数时间
        """将轨迹内的秒级时间戳加上指定相机的片段起点，定位视频文件；timestamp 不是帧编号。"""  # 方法说明
        metadata = self.episode_metadata[episode_index]  # 取得目标轨迹的元数据
        prefix = f"videos/{camera_key}"  # 使用完整相机字段定位该相机自己的元数据
        chunk_index = int(metadata[f"{prefix}/chunk_index"])  # 读取该相机的视频块编号并转为整数
        file_index = int(metadata[f"{prefix}/file_index"])  # 读取该相机的视频文件编号并转为整数
        video_path = self.root / self.info["video_path"].format(  # 按元数据中的模板拼出视频路径
            video_key=camera_key,  # 将完整相机字段填入 video_key
            chunk_index=chunk_index,  # 填入该相机的视频块编号
            file_index=file_index,  # 填入该相机的视频文件编号
        )  # 完成视频路径拼接，结果为 Path
        from_timestamp = float(metadata[f"{prefix}/from_timestamp"])  # 读取该相机的片段起始时间并转为 Python float
        video_timestamp = from_timestamp + float(timestamp)  # 加上轨迹内时间，得到视频文件内的秒级时间
        return video_path, video_timestamp  # 返回路径和 Python float 时间，不读取或解码视频

    def read_images(  # 按配置中的相机顺序读取同一时刻的图像
        self,  # 当前数据源实例
        episode_index: int,  # 目标轨迹编号
        timestamp: float,  # 轨迹内时间戳，单位为秒
    ) -> torch.Tensor:  # 返回原始图像张量
        """返回 RGB uint8 图像 [C, 3, H, W]，C 为相机数量；保留原始尺寸，时间偏移仅由 get_video_location 添加。"""  # 方法说明
        images = []  # 按相机顺序收集各路图像
        for camera_key in self.camera_keys:  # 保持任务配置中的相机输入顺序
            video_path, video_timestamp = self.get_video_location(episode_index, camera_key, timestamp)  # 定位该相机的视频文件和文件内时间
            decoder = VideoDecoder(  # 每次为当前相机创建 CPU 解码器
                video_path,  # 读取定位得到的视频路径
                dimension_order="NCHW",  # 单帧按通道、高度、宽度排列
                device="cpu",  # 在 CPU 上解码并返回张量
                seek_mode="exact",  # 使用精确定位模式
            )  # 完成解码器创建
            frame = decoder.get_frame_played_at(seconds=video_timestamp)  # 读取指定视频时间正在显示的帧
            images.append(frame.data)  # 保存原始 RGB uint8 图像，不缩放或归一化
        return torch.stack(images)  # 沿相机维堆叠为 [C, 3, H, W]
