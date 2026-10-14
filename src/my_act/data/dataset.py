import torch  # 将 NumPy 数组转换为张量
import torch.nn.functional as F  # 使用双线性插值缩放各相机图像
from torch.utils.data import Dataset  # 使用 PyTorch 数据集基类

from my_act.data.action_chunk import make_action_chunk  # 复用动作块截取与补齐功能
from my_act.data.libero_dataset import LiberoSource  # 使用现有数据源读取轨迹
from my_act.data.normalization import normalize  # 复用归一化函数


class ACTDataset(Dataset):  # 定义包含双相机图像、状态和动作块的 ACT 数据集
    """每帧对应图像、状态和动作块起点一致的样本；frame_index 是轨迹数组中的位置，包含轨迹末尾不足动作块长度的帧。"""  # 类说明

    def __init__(  # 初始化并预加载传入轨迹的状态、动作与原始时间戳
        self,  # 当前数据集实例
        source: LiberoSource,  # 已初始化的数据源
        episode_indices: list[int],  # 调用方划分好的轨迹编号
        stats: dict,  # 调用方仅用训练集计算的统计量
        chunk_size: int,  # 动作块长度 K
        image_size: int,  # 缩放后图像的高度和宽度
    ) -> None:  # 构造函数不返回数据
        """预加载状态、动作和原始时间戳，按需读取图像；训练集与验证集均使用调用方传入的训练集统计量，不在此划分或计算统计量。"""  # 构造函数说明
        self.source = source  # 保存数据源，用于按当前帧时间读取图像
        self.image_size = image_size  # 保存输出图像尺寸
        self.chunk_size = chunk_size  # 保存动作块长度
        self.episodes = {}  # 按轨迹编号保存归一化后的状态、动作和原始时间戳
        self.samples = []  # 保存每个样本对应的轨迹编号与帧位置
        for episode_index in episode_indices:  # 遍历调用方指定的轨迹
            episode = source.read_episode(episode_index)  # 初始化时读取单条轨迹
            state = normalize(episode["state"], stats["state"]["mean"], stats["state"]["std"])  # 使用训练集统计量归一化整条状态序列
            action = normalize(episode["action"], stats["action"]["mean"], stats["action"]["std"])  # 使用训练集统计量归一化整条动作序列
            self.episodes[episode_index] = {  # 保存数值序列，不预加载图像
                "state": state,  # 保存归一化后的状态数组
                "action": action,  # 保存归一化后的动作数组
                "timestamp": episode["timestamp"],  # 保存原始轨迹内时间戳，不做归一化
            }  # 完成当前轨迹的数据保存
            for frame_index in range(len(state)):  # 遍历该轨迹数组的所有帧位置，包括末帧
                self.samples.append((episode_index, frame_index))  # 将该帧加入样本索引

    def __len__(self) -> int:  # 获取数据集样本数量
        """返回传入轨迹的总帧数，每帧对应一个样本。"""  # 方法说明
        return len(self.samples)  # 返回样本索引列表的长度

    def __getitem__(self, index: int) -> dict:  # 按样本索引取得当前帧图像、状态和动作块
        """使用预加载数组与当前帧时间读取图像；图像保持相机顺序，只除以 255 并缩放，不做 ImageNet 归一化或增强。"""  # 方法说明
        episode_index, frame_index = self.samples[index]  # 找到轨迹编号及轨迹数组中的帧位置
        episode = self.episodes[episode_index]  # 取出该轨迹已归一化的状态、动作及原始时间戳
        state = episode["state"][frame_index]  # 取得当前帧状态，不修改已有数组
        action_chunk, is_pad = make_action_chunk(episode["action"], frame_index, self.chunk_size)  # 从当前帧开始截取动作块并标记补齐位置
        timestamp = float(episode["timestamp"][frame_index])  # 取得当前帧的轨迹内时间，转换为 Python float
        images = self.source.read_images(episode_index, timestamp)  # 按配置中的相机顺序读取当前帧的 uint8 图像
        images = images.to(dtype=torch.float32) / 255.0  # 转为新的 float32 张量，将像素值映射到 [0, 1]
        images = F.interpolate(  # 将相机维作为批次维，独立缩放各路图像
            images,  # 输入形状为 [C, 3, H, W] 的图像
            size=(self.image_size, self.image_size),  # 统一输出图像的高度和宽度
            mode="bilinear",  # 使用双线性插值
            align_corners=False,  # 按像素区域对齐，不对齐角点中心
            antialias=True,  # 缩小时进行抗锯齿处理
        )  # 得到 [C, 3, image_size, image_size] 的图像
        return {  # 返回图像、状态、动作块和补齐标记
            "images": images,  # float32 图像张量，保持配置中的相机顺序
            "state": torch.from_numpy(state),  # float32 状态张量，形状为 [S]
            "action": torch.from_numpy(action_chunk),  # float32 动作块张量，形状为 [K, A]
            "is_pad": torch.from_numpy(is_pad),  # bool 补齐标记张量，形状为 [K]
        }  # 完成返回字典
