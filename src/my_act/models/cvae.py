import torch  # 创建固定位置编码并组织状态与动作张量
from torch import nn  # 构建可训练的 token、投影层和编码器模块

from my_act.models.transformer import TransformerEncoder  # 复用已有多层 Transformer 编码器


class CVAEEncoder(nn.Module):  # 根据当前状态与示范动作块编码潜变量后验
    """输出给定当前状态和示范动作块的潜变量后验参数，不读取图像；hidden_dim 约定为偶数，动作块长度固定为 chunk_size。"""  # 类说明

    def __init__(  # 初始化序列投影、编码器和固定位置编码
        self,  # 当前 CVAE 编码器实例
        state_dim: int,  # 当前状态的维度
        action_dim: int,  # 单步动作的维度
        hidden_dim: int,  # 编码器内部特征维度，约定为偶数
        latent_dim: int,  # 潜变量维度
        chunk_size: int,  # 固定动作块长度 K
        nheads: int,  # 多头注意力的头数
        dim_feedforward: int,  # 前馈网络的中间维度
        dropout: float,  # 编码器使用的丢弃概率
        num_layers: int,  # Transformer 编码器层数
    ) -> None:  # 构造函数不返回数据
        """创建可训练的 CLS 与投影模块，并将长度为 chunk_size+2 的一维正弦余弦编码注册为缓冲区。"""  # 构造函数说明
        super().__init__()  # 初始化 PyTorch 模块
        self.cls_embedding = nn.Embedding(1, hidden_dim)  # 创建汇总整个序列的可训练 CLS token
        self.state_projection = nn.Linear(state_dim, hidden_dim)  # 将当前状态投影到内部特征维度
        self.action_projection = nn.Linear(action_dim, hidden_dim)  # 将每一步动作投影到内部特征维度
        self.encoder = TransformerEncoder(  # 创建已有的多层编码器
            hidden_dim=hidden_dim,  # 设置内部特征维度
            nheads=nheads,  # 设置注意力头数
            dim_feedforward=dim_feedforward,  # 设置前馈中间维度
            dropout=dropout,  # 设置丢弃概率
            num_layers=num_layers,  # 设置编码器层数
        )  # 完成编码器创建
        self.distribution_projection = nn.Linear(hidden_dim, 2 * latent_dim)  # 将 CLS 输出映射为均值和自然对数方差
        positions = torch.arange(chunk_size + 2, dtype=torch.float32).unsqueeze(1)  # 生成从 0 到 K+1 的一维序列位置
        frequencies = torch.arange(hidden_dim // 2, dtype=torch.float32)  # 生成各对正弦余弦通道的频率编号 i
        denominators = 10000.0 ** (2 * frequencies / hidden_dim)  # 按 10000 的 2i/hidden_dim 次幂计算频率分母
        phases = positions / denominators  # 广播得到每个位置和频率的相位
        position = torch.stack((phases.sin(), phases.cos()), dim=-1).flatten(-2)  # 按偶数 sin、奇数 cos 的顺序交替排列通道
        self.register_buffer("position", position.unsqueeze(0))  # 保存 [1, K+2, hidden_dim] 的固定 float32 位置编码

    def forward(  # 从当前状态和动作块预测潜变量后验参数
        self,  # 当前 CVAE 编码器实例
        state: torch.Tensor,  # 归一化后的当前状态，形状为 [B, state_dim]
        actions: torch.Tensor,  # 归一化后的固定长度动作块，形状为 [B, K, action_dim]
        is_pad: torch.Tensor,  # [B, K] 的 bool 标记，True 表示补齐动作
    ) -> tuple[torch.Tensor, torch.Tensor]:  # 返回两个 [B, latent_dim] 的分布参数张量
        """按 CLS、当前状态、动作序列编码后验，返回 mu 和 logvar；logvar 是自然对数方差 log(σ²)，不是标准差或 log(σ)。"""  # 前向方法说明
        batch_size = state.shape[0]  # 读取当前批次大小
        cls = self.cls_embedding.weight.unsqueeze(0).expand(batch_size, -1, -1)  # 将 CLS 扩展为 [B, 1, hidden_dim]
        state_token = self.state_projection(state).unsqueeze(1)  # 将状态投影并增加长度为 1 的序列维
        action_tokens = self.action_projection(actions)  # 逐步投影动作，得到 [B, K, hidden_dim]
        sequence = torch.cat((cls, state_token, action_tokens), dim=1)  # 按 CLS、状态、动作0到动作K-1 的顺序拼接序列
        prefix_mask = torch.zeros((batch_size, 2), dtype=torch.bool, device=is_pad.device)  # 为始终有效的 CLS 和状态创建两个 False
        padding_mask = torch.cat((prefix_mask, is_pad), dim=1)  # 将动作补齐标记接在前缀后，得到 [B, K+2] 掩码
        encoded = self.encoder(  # 使用固定位置编码和 padding mask 编码整个序列
            sequence,  # 传入状态和动作组成的内容序列
            self.position.to(dtype=sequence.dtype),  # 匹配序列类型并保持缓冲区所在设备
            src_key_padding_mask=padding_mask,  # 每层屏蔽补齐动作的 key/value
        )  # 完成后验序列编码
        cls_output = encoded[:, 0]  # 取第 0 个 token 的 CLS 汇总结果
        parameters = self.distribution_projection(cls_output)  # 预测 [B, 2*latent_dim] 的原始分布参数
        mu, logvar = parameters.chunk(2, dim=-1)  # 沿最后一维拆分均值和自然对数方差，不添加裁剪或激活
        return mu, logvar  # 返回后验参数，不采样潜变量或计算 KL


def reparameterize(  # 使用重参数化方法采样潜变量
    mu: torch.Tensor,  # 潜变量均值，形状为 [B, latent_dim]
    logvar: torch.Tensor,  # 潜变量的自然对数方差，形状为 [B, latent_dim]
) -> torch.Tensor:  # 返回同形状的潜变量样本
    """始终采样 [B, latent_dim] 潜变量，保留到 mu、logvar 的梯度路径，不修改输入或根据训练状态切换行为。"""  # 函数说明
    std = torch.exp(0.5 * logvar)  # 从自然对数方差计算标准差
    eps = torch.randn_like(std)  # 生成与标准差形状、设备和类型一致的标准正态噪声
    return mu + std * eps  # 平移并缩放噪声，保留可微的重参数化路径
