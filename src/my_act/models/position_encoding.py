import torch  # 创建坐标网格并计算正弦余弦编码
from torch import nn  # 使用 PyTorch 模块基类


class PositionEmbeddingSine(nn.Module):  # 定义二维正弦余弦位置编码
    """为特征图生成可广播的位置编码；约定 hidden_dim 是 4 的倍数，当前配置为 256。"""  # 类说明

    def __init__(self, hidden_dim: int, temperature: float = 10000.0) -> None:  # 接收编码维度和频率温度
        """保存编码维度与温度，不创建可训练参数。"""  # 构造函数说明
        super().__init__()  # 初始化 PyTorch 模块
        self.hidden_dim = hidden_dim  # 保存完整位置编码的通道数
        self.temperature = temperature  # 保存控制频率分母的温度

    def forward(self, features: torch.Tensor) -> torch.Tensor:  # 根据特征图形状生成位置编码
        """输入 [B, C, D, Hf, Wf]，D 等于 hidden_dim；仅依据形状、设备和类型返回 [1, 1, D, Hf, Wf] 编码，不读取特征数值。"""  # 前向方法说明
        height, width = features.shape[-2:]  # 读取实际特征图的高度和宽度
        y = torch.arange(1, height + 1, dtype=torch.float32, device=features.device) / height * (2 * torch.pi)  # 将特征图纵向坐标归一化到 2π
        x = torch.arange(1, width + 1, dtype=torch.float32, device=features.device) / width * (2 * torch.pi)  # 将特征图横向坐标归一化到 2π
        y_grid, x_grid = torch.meshgrid(y, x, indexing="ij")  # 生成特征图坐标网格，不使用原图像素坐标
        num_features = self.hidden_dim // 2  # 纵向和横向各占一半编码通道，即 M
        dim_t = torch.arange(num_features, dtype=torch.float32, device=features.device)  # 创建从 0 到 M-1 的通道索引
        dim_t = self.temperature ** (2 * torch.floor(dim_t / 2) / num_features)  # 按相邻两通道共享频率的公式计算分母
        pos_y = y_grid.unsqueeze(-1) / dim_t  # 将纵向坐标展开为 [Hf, Wf, M] 的相位
        pos_x = x_grid.unsqueeze(-1) / dim_t  # 将横向坐标展开为 [Hf, Wf, M] 的相位
        pos_y = torch.stack((pos_y[..., 0::2].sin(), pos_y[..., 1::2].cos()), dim=-1).flatten(-2)  # 纵向偶数通道取 sin、奇数通道取 cos，并交替排列
        pos_x = torch.stack((pos_x[..., 0::2].sin(), pos_x[..., 1::2].cos()), dim=-1).flatten(-2)  # 横向偶数通道取 sin、奇数通道取 cos，并交替排列
        position = torch.cat((pos_y, pos_x), dim=-1)  # 按先纵向后横向的顺序拼成 [Hf, Wf, D]
        position = position.permute(2, 0, 1).unsqueeze(0).unsqueeze(0)  # 调整为 [1, 1, D, Hf, Wf]，不复制批次维和相机维
        return position.to(dtype=features.dtype)  # 转为输入类型并保持设备一致，不修改或加到输入特征上
