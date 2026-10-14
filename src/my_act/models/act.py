import torch  # 拼接特征序列并创建零潜变量和查询内容
from torch import nn  # 构建模型、线性投影和位置 Embedding

from my_act.models.backbone import VisualBackbone  # 复用共享 ResNet18 视觉骨干
from my_act.models.visual_tokens import VisualTokenizer  # 复用视觉 token 与相机位置编码
from my_act.models.cvae import CVAEEncoder, reparameterize  # 复用后验编码器与重参数化采样
from my_act.models.transformer import TransformerEncoder, TransformerDecoder  # 复用多层编码器与解码器


class ACT(nn.Module):  # 组装视觉、潜变量和动作块预测模块
    """使用共享 ResNet18 预测归一化动作块；传入示范动作时采样后验，不传动作时使用零潜变量，与 train/eval 状态无关。"""  # 类说明

    def __init__(self, config: dict) -> None:  # 从已有模型配置创建全部模块
        """创建彼此独立的 CVAE 与策略编码器及状态投影，复用已有视觉和 Transformer 模块。"""  # 构造函数说明
        super().__init__()  # 初始化 PyTorch 模块
        hidden_dim = config["hidden_dim"]  # 读取模型内部特征维度
        self.latent_dim = config["latent_dim"]  # 保存前向推理创建零潜变量所需的维度
        self.backbone = VisualBackbone(hidden_dim, pretrained=config["pretrained_backbone"])  # 按配置创建已有的 ResNet18 骨干
        self.visual_tokenizer = VisualTokenizer(hidden_dim, config["num_cameras"])  # 创建视觉序列和相机身份编码模块
        self.cvae_encoder = CVAEEncoder(  # 独立创建示范动作后验编码器
            state_dim=config["state_dim"],  # 设置状态输入维度
            action_dim=config["action_dim"],  # 设置单步动作维度
            hidden_dim=hidden_dim,  # 设置内部特征维度
            latent_dim=self.latent_dim,  # 设置潜变量维度
            chunk_size=config["chunk_size"],  # 设置固定动作块长度
            nheads=config["nheads"],  # 设置注意力头数
            dim_feedforward=config["dim_feedforward"],  # 设置前馈中间维度
            dropout=config["dropout"],  # 设置丢弃概率
            num_layers=config["cvae_layers"],  # 使用 CVAE 专用编码器层数
        )  # 完成后验编码器创建
        self.encoder = TransformerEncoder(  # 新建策略编码器，不共享 CVAE 内部编码器参数
            hidden_dim=hidden_dim,  # 设置特征维度
            nheads=config["nheads"],  # 设置注意力头数
            dim_feedforward=config["dim_feedforward"],  # 设置前馈中间维度
            dropout=config["dropout"],  # 设置丢弃概率
            num_layers=config["encoder_layers"],  # 使用策略编码器层数
        )  # 完成策略编码器创建
        self.decoder = TransformerDecoder(  # 创建动作查询解码器
            hidden_dim=hidden_dim,  # 设置特征维度
            nheads=config["nheads"],  # 设置注意力头数
            dim_feedforward=config["dim_feedforward"],  # 设置前馈中间维度
            dropout=config["dropout"],  # 设置丢弃概率
            num_layers=config["decoder_layers"],  # 使用解码器层数
        )  # 完成解码器创建
        self.state_projection = nn.Linear(config["state_dim"], hidden_dim)  # 独立创建策略状态投影，不共享 CVAE 的状态投影
        self.latent_projection = nn.Linear(self.latent_dim, hidden_dim)  # 将潜变量投影为内部特征
        self.prefix_position = nn.Embedding(2, hidden_dim)  # 按潜变量、状态的顺序定义两个前缀位置
        self.query_embedding = nn.Embedding(config["chunk_size"], hidden_dim)  # 创建 K 个可训练动作查询位置
        self.action_head = nn.Linear(hidden_dim, config["action_dim"])  # 将查询特征映射为归一化动作

    def forward(  # 执行后验采样或零潜变量推理的前向流程
        self,  # 当前 ACT 模型实例
        images: torch.Tensor,  # [B, C, 3, H, W] 的 float32 图像，像素范围为 [0, 1]
        state: torch.Tensor,  # [B, state_dim] 的归一化当前状态
        actions: torch.Tensor | None = None,  # 可选的 [B, K, action_dim] 归一化示范动作块
        is_pad: torch.Tensor | None = None,  # 有示范动作时必须同时提供的 [B, K] bool 补齐标记
    ) -> dict:  # 返回预测动作及可选的后验分布参数
        """输入图像为 [0,1] float32，状态和动作已归一化；有 actions 必须提供 is_pad，K 等于配置动作块长度。eval 下传入动作仍采样后验，策略推理不传动作。"""  # 前向方法说明
        batch_size = state.shape[0]  # 读取当前批次大小
        if actions is not None:  # 根据是否提供示范动作选择后验分支
            mu, logvar = self.cvae_encoder(state, actions, is_pad)  # 使用状态、示范动作及补齐标记预测后验参数
            z = reparameterize(mu, logvar)  # 从后验重参数化采样，不根据训练状态切换
        else:  # 未提供示范动作时执行策略推理
            z = state.new_zeros((batch_size, self.latent_dim))  # 创建与状态设备和类型一致的零潜变量
            mu, logvar = None, None  # 推理分支不计算后验分布参数
        visual_features = self.backbone(images)  # 提取各相机的空间特征
        visual_tokens, visual_positions = self.visual_tokenizer(visual_features)  # 生成视觉特征序列与独立的位置编码
        latent_token = self.latent_projection(z).unsqueeze(1)  # 将潜变量投影为一个序列 token
        state_token = self.state_projection(state).unsqueeze(1)  # 将当前状态投影为一个序列 token
        src = torch.cat((latent_token, state_token, visual_tokens), dim=1)  # 按潜变量、状态、视觉序列的固定顺序拼接输入
        prefix_positions = self.prefix_position.weight.to(dtype=src.dtype).unsqueeze(0).expand(batch_size, -1, -1)  # 匹配特征类型并扩展两个前缀位置的批次维
        pos = torch.cat((prefix_positions, visual_positions.to(dtype=src.dtype)), dim=1)  # 按相同顺序拼接位置编码，并匹配特征类型
        memory = self.encoder(src, pos)  # 全部输入 token 均有效，不传示范动作的补齐掩码
        query_pos = self.query_embedding.weight.to(dtype=memory.dtype).unsqueeze(0).expand(batch_size, -1, -1)  # 扩展 K 个动作查询位置，并匹配 memory 类型
        tgt = torch.zeros_like(query_pos)  # 创建与动作查询位置形状、设备和类型一致的零内容
        decoded = self.decoder(  # 使用动作查询读取编码器输出
            tgt=tgt,  # 传入初始查询内容
            memory=memory,  # 传入编码后的潜变量、状态与视觉特征
            pos=pos,  # 传入 memory 对应的位置编码
            query_pos=query_pos,  # 传入 K 个动作查询的位置编码
        )  # 完成动作查询解码，不传动作补齐标记
        predicted_actions = self.action_head(decoded)  # 输出 [B, K, action_dim] 的归一化动作，不裁剪或反归一化
        return {  # 返回预测动作和后验参数
            "actions": predicted_actions,  # 预测的归一化动作块
            "mu": mu,  # 后验均值，策略推理时为 None
            "logvar": logvar,  # 后验自然对数方差，策略推理时为 None
        }  # 完成返回字典
