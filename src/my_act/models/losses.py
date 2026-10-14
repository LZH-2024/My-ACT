import torch  # 使用张量计算动作重建损失和潜变量 KL 损失


def compute_act_loss(  # 计算 ACT 后验分支的训练损失
    predicted_actions: torch.Tensor,  # 预测的归一化动作，形状为 [B, K, A]
    target_actions: torch.Tensor,  # 目标归一化动作，形状为 [B, K, A]
    is_pad: torch.Tensor,  # [B, K] 的 bool 标记，True 表示补齐动作
    mu: torch.Tensor,  # 后验均值，形状为 [B, Z]
    logvar: torch.Tensor,  # 后验自然对数方差，形状为 [B, Z]
    kl_weight: float,  # 非负的 KL 损失权重
) -> dict:  # 返回保留计算图的三个标量 Tensor
    """动作输入为归一化空间的 [B, K, A]，is_pad 为 [B, K] bool，后验参数为 [B, Z]；约定每个样本至少有一个有效动作且 kl_weight 非负。L1 按整个批次的有效动作元素平均，KL 沿潜变量维求和后沿批次平均。"""  # 函数说明
    absolute_error = torch.abs(predicted_actions - target_actions)  # 计算逐元素绝对误差，不修改输入
    valid = (~is_pad).unsqueeze(-1)  # 生成 [B, K, 1] 的有效位置掩码
    masked_error = absolute_error.masked_fill(~valid, 0.0)  # 广播掩码，将补齐位置误差置零，使用非原地操作
    action_dim = predicted_actions.shape[-1]  # 读取单步动作维度 A
    l1 = masked_error.sum() / (valid.sum() * action_dim)  # 按批次内全部有效动作元素平均，不按样本分别平均
    kl_per_dim = -0.5 * (1 + logvar - mu.square() - logvar.exp())  # 计算后验相对于标准正态先验的逐维 KL
    kl = kl_per_dim.sum(dim=-1).mean()  # 先沿潜变量维度求和，再沿批次取平均
    loss = l1 + kl_weight * kl  # 加权组合动作重建与 KL 损失
    return {  # 返回标量张量并保留梯度路径
        "loss": loss,  # 总损失
        "l1": l1,  # 有效动作元素的平均绝对误差
        "kl": kl,  # 批次平均的潜变量 KL 散度
    }  # 完成返回字典
