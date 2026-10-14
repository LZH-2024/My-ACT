import torch  # 创建相机编号并表示特征张量
from torch import nn  # 构建模块与可训练的相机身份编码

from my_act.models.position_encoding import PositionEmbeddingSine  # 复用二维正弦余弦位置编码


class VisualTokenizer(nn.Module):  # 将视觉骨干输出组织为特征序列与独立的位置序列
    """按相机、行、列的顺序组织视觉 token，相机编号与任务配置 camera_keys 的顺序一致。"""  # 类说明

    def __init__(self, hidden_dim: int, num_cameras: int) -> None:  # 接收特征维度与相机数量
        """创建空间位置编码和可训练相机身份编码，不在内部创建视觉骨干。"""  # 构造函数说明
        super().__init__()  # 初始化 PyTorch 模块
        self.position_encoding = PositionEmbeddingSine(hidden_dim)  # 创建共享的二维空间位置编码
        self.camera_embedding = nn.Embedding(num_cameras, hidden_dim)  # 为配置顺序中的每路相机学习身份编码

    def forward(self, features: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:  # 返回相互独立的视觉特征与组合位置编码
        """输入 [B, C, D, Hf, Wf]，约定 C、D 等于构造时的相机数和特征维度；返回两个 [B, C*Hf*Wf, D] 张量。"""  # 前向方法说明
        batch_size, num_cameras, hidden_dim, height, width = features.shape  # 读取批次、相机、通道和空间尺寸
        tokens = features.permute(0, 1, 3, 4, 2).reshape(batch_size, num_cameras * height * width, hidden_dim)  # 按先相机、再行、最后列的顺序整理特征，不修改输入
        spatial_positions = self.position_encoding(features)  # 生成 [1, 1, D, Hf, Wf] 的空间位置编码
        camera_indices = torch.arange(num_cameras, device=features.device)  # 在输入设备上按配置顺序创建整数相机编号
        camera_positions = self.camera_embedding(camera_indices).to(dtype=features.dtype)  # 取得 [C, D] 相机编码并匹配输入类型
        camera_positions = camera_positions.reshape(1, num_cameras, hidden_dim, 1, 1)  # 将相机编码整理为可沿空间维广播的形状
        positions = spatial_positions + camera_positions  # 广播相加，得到 [1, C, D, Hf, Wf] 的组合编码
        positions = positions.permute(0, 1, 3, 4, 2).reshape(1, num_cameras * height * width, hidden_dim)  # 使用与特征完全相同的相机、行、列顺序展平
        positions = positions.expand(batch_size, -1, -1)  # 使用视图扩展批次维，不复制每个样本的位置编码
        return tokens, positions  # 分别返回特征和位置编码，不在这里将两者相加
