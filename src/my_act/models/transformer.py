import torch  # 表示特征、位置编码和掩码张量
from torch import nn  # 构建注意力、前馈网络和归一化模块


class TransformerEncoderLayer(nn.Module):  # 定义单层 Transformer 编码器
    """采用 Post-LayerNorm 的双向编码器；位置编码只加入 Q、K，padding mask 屏蔽 key/value，不保证被屏蔽位置的输出为零。"""  # 类说明

    def __init__(  # 初始化注意力和前馈模块
        self,  # 当前编码器层实例
        hidden_dim: int,  # 特征维度 D
        nheads: int,  # 多头注意力的头数
        dim_feedforward: int,  # 前馈网络的中间维度
        dropout: float,  # 各 Dropout 模块的丢弃概率
    ) -> None:  # 构造函数不返回数据
        """创建批次维在前的自注意力、前馈网络及两组独立的残差 Dropout 和 LayerNorm。"""  # 构造函数说明
        super().__init__()  # 初始化 PyTorch 模块
        self.self_attn = nn.MultiheadAttention(  # 创建多头自注意力模块
            embed_dim=hidden_dim,  # 设置输入输出特征维度
            num_heads=nheads,  # 设置注意力头数
            dropout=dropout,  # 设置注意力权重的丢弃概率
            batch_first=True,  # 使用 [B, L, D] 的序列布局
        )  # 完成自注意力模块创建
        self.linear1 = nn.Linear(hidden_dim, dim_feedforward)  # 将特征映射到前馈中间维度
        self.relu = nn.ReLU()  # 使用非原地的 ReLU 激活
        self.dropout_ff = nn.Dropout(dropout)  # 对前馈中间激活应用 Dropout
        self.linear2 = nn.Linear(dim_feedforward, hidden_dim)  # 将前馈特征映射回原维度
        self.norm1 = nn.LayerNorm(hidden_dim)  # 对注意力残差相加后的特征归一化
        self.norm2 = nn.LayerNorm(hidden_dim)  # 对前馈残差相加后的特征独立归一化
        self.dropout1 = nn.Dropout(dropout)  # 在注意力残差相加之前应用 Dropout
        self.dropout2 = nn.Dropout(dropout)  # 在前馈残差相加之前独立应用 Dropout

    def forward(  # 执行带位置编码的双向自注意力和前馈变换
        self,  # 当前编码器层实例
        src: torch.Tensor,  # 输入特征，形状为 [B, L, D]
        pos: torch.Tensor,  # 可广播到 [B, L, D] 的位置编码
        src_key_padding_mask: torch.Tensor | None = None,  # [B, L] 的 bool 掩码，True 屏蔽对应 key/value
    ) -> torch.Tensor:  # 返回 [B, L, D] 的编码特征
        """仅在 Q、K 中加入位置编码，按残差后归一化执行；掩码不屏蔽 query，因此不保证被屏蔽位置自身输出为零。"""  # 前向方法说明
        q = src + pos  # 将位置编码加入查询，不修改输入
        k = src + pos  # 将位置编码加入键，不修改输入
        v = src  # 值保留原始特征，不加入位置编码
        attention_output, _ = self.self_attn(  # 计算自注意力，只使用特征输出
            query=q,  # 使用带位置编码的查询
            key=k,  # 使用带位置编码的键
            value=v,  # 使用不含位置编码的值
            key_padding_mask=src_key_padding_mask,  # 屏蔽填充位置的 key/value，不设置因果掩码
            need_weights=False,  # 不返回注意力权重
        )  # 完成有效 token 之间的双向交互
        src = self.norm1(src + self.dropout1(attention_output))  # 注意力输出经 Dropout 与原特征相加，再归一化
        ff = self.linear2(self.dropout_ff(self.relu(self.linear1(src))))  # 依次执行线性映射、ReLU、Dropout 和线性映射
        src = self.norm2(src + self.dropout2(ff))  # 前馈输出经 Dropout 与残差相加，再归一化
        return src  # 返回编码结果，不原地修改传入张量


class TransformerEncoder(nn.Module):  # 定义由独立编码器层组成的多层编码器
    """顺序堆叠 Post-LayerNorm 编码器层，每层接收相同的位置编码和 padding mask，不额外添加末尾归一化。"""  # 类说明

    def __init__(  # 初始化多层编码器
        self,  # 当前编码器实例
        hidden_dim: int,  # 特征维度 D
        nheads: int,  # 每层多头注意力的头数
        dim_feedforward: int,  # 每层前馈网络的中间维度
        dropout: float,  # 每层使用的丢弃概率
        num_layers: int,  # 编码器层数
    ) -> None:  # 构造函数不返回数据
        """使用 ModuleList 注册各层，每次循环新建一层，使各层拥有独立参数。"""  # 构造函数说明
        super().__init__()  # 初始化 PyTorch 模块
        self.layers = nn.ModuleList()  # 使用模块列表保存并注册所有编码器层
        for _ in range(num_layers):  # 按指定层数逐层创建模块
            self.layers.append(  # 将新建的独立层加入模块列表
                TransformerEncoderLayer(  # 每次循环创建新的编码器层对象
                    hidden_dim=hidden_dim,  # 设置特征维度
                    nheads=nheads,  # 设置注意力头数
                    dim_feedforward=dim_feedforward,  # 设置前馈中间维度
                    dropout=dropout,  # 设置丢弃概率
                )  # 完成当前层创建
            )  # 完成当前层注册

    def forward(  # 按顺序执行所有编码器层
        self,  # 当前编码器实例
        src: torch.Tensor,  # 输入特征，形状为 [B, L, D]
        pos: torch.Tensor,  # 每层共用的位置编码，可广播到输入形状
        src_key_padding_mask: torch.Tensor | None = None,  # 每层共用的 [B, L] bool 掩码，True 屏蔽 key/value
    ) -> torch.Tensor:  # 返回 [B, L, D] 的最终编码特征
        """逐层传递特征，并将同一份位置编码和 padding mask 交给每一层；只返回最后一层输出。"""  # 前向方法说明
        output = src  # 将原始特征作为初始输出，不提前加入位置编码
        for layer in self.layers:  # 按注册顺序遍历独立的编码器层
            output = layer(output, pos, src_key_padding_mask=src_key_padding_mask)  # 传入上一层输出与相同的位置编码和掩码
        return output  # 返回最终特征，不再添加 LayerNorm
