import torch  # 将 NumPy 数组转换为张量
from torch.utils.data import Dataset  # 使用 PyTorch 数据集基类

from my_act.data.action_chunk import make_action_chunk  # 复用动作块截取与补齐功能
from my_act.data.libero_dataset import LiberoSource  # 使用现有数据源读取轨迹
from my_act.data.normalization import normalize  # 复用归一化函数


class ACTDataset(Dataset):  # 定义暂不包含图像的 ACT 数据集
    """每帧对应一个样本；frame_index 是轨迹数组中的位置，包含轨迹末尾不足动作块长度的帧。"""  # 类说明

    def __init__(  # 初始化并预加载传入轨迹的状态与动作
        self,  # 当前数据集实例
        source: LiberoSource,  # 已初始化的数据源
        episode_indices: list[int],  # 调用方划分好的轨迹编号
        stats: dict,  # 调用方仅用训练集计算的统计量
        chunk_size: int,  # 动作块长度 K
    ) -> None:  # 构造函数不返回数据
        """预加载状态和动作；训练集与验证集均由调用方传入训练集统计量，不在此划分或计算统计量。"""  # 构造函数说明
        self.chunk_size = chunk_size  # 保存动作块长度
        self.episodes = {}  # 按轨迹编号保存归一化后的状态和动作
        self.samples = []  # 保存每个样本对应的轨迹编号与帧位置
        for episode_index in episode_indices:  # 遍历调用方指定的轨迹
            episode = source.read_episode(episode_index)  # 初始化时读取单条轨迹
            state = normalize(episode["state"], stats["state"]["mean"], stats["state"]["std"])  # 使用训练集统计量归一化整条状态序列
            action = normalize(episode["action"], stats["action"]["mean"], stats["action"]["std"])  # 使用训练集统计量归一化整条动作序列
            self.episodes[episode_index] = {"state": state, "action": action}  # 只保存状态和动作，不保存时间戳或图像
            for frame_index in range(len(state)):  # 遍历该轨迹数组的所有帧位置，包括末帧
                self.samples.append((episode_index, frame_index))  # 将该帧加入样本索引

    def __len__(self) -> int:  # 获取数据集样本数量
        """返回传入轨迹的总帧数，每帧对应一个样本。"""  # 方法说明
        return len(self.samples)  # 返回样本索引列表的长度

    def __getitem__(self, index: int) -> dict:  # 按样本索引取得状态和动作块
        """使用已预加载的归一化数组生成样本，不重复读取 Parquet 或归一化整条轨迹。"""  # 方法说明
        episode_index, frame_index = self.samples[index]  # 找到轨迹编号及轨迹数组中的帧位置
        episode = self.episodes[episode_index]  # 取出该轨迹已归一化的状态和动作
        state = episode["state"][frame_index]  # 取得当前帧状态，不修改已有数组
        action_chunk, is_pad = make_action_chunk(episode["action"], frame_index, self.chunk_size)  # 从当前帧开始截取动作块并标记补齐位置
        return {  # 返回本轮需要的三个张量字段
            "state": torch.from_numpy(state),  # float32 状态张量，形状为 [S]
            "action": torch.from_numpy(action_chunk),  # float32 动作块张量，形状为 [K, A]
            "is_pad": torch.from_numpy(is_pad),  # bool 补齐标记张量，形状为 [K]
        }  # 完成返回字典
