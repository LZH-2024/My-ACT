import torch  # 控制模型模式、设备和无梯度验证
from torch.utils.data import DataLoader  # 标注验证数据加载器类型


def evaluate(  # 计算零潜变量策略的离线动作预测误差
    model: torch.nn.Module,  # 待验证的 ACT 模型
    loader: DataLoader,  # 非空且包含有效动作的验证数据加载器
    device: torch.device,  # 与模型所在设备一致的计算设备
) -> dict:  # 返回 Python 标量形式的指标和计数
    """在归一化动作空间统计所有样本的有效动作元素，动作块之间可能重叠；这是零潜变量策略的离线预测误差，不是后验重建误差或 rollout 成功率。约定 loader 非空且包含有效动作，正常完成后恢复调用前的模型模式。"""  # 函数说明
    was_training = model.training  # 保存调用前的模型训练模式
    model.eval()  # 切换为验证模式
    total_absolute_error = 0.0  # 累加整个加载器的有效动作元素绝对误差
    num_valid_elements = 0  # 累加有效动作元素数量
    num_samples = 0  # 累加实际处理的样本数量
    with torch.no_grad():  # 验证过程不构建梯度计算图
        for batch in loader:  # 遍历调用方提供的验证批次
            images = batch["images"].to(device)  # 将图像移到指定设备并保持类型
            state = batch["state"].to(device)  # 将状态移到指定设备并保持类型
            actions = batch["action"].to(device)  # 将目标动作移到指定设备并保持类型
            is_pad = batch["is_pad"].to(device)  # 将补齐标记移到指定设备并保持 bool 类型
            output = model(images=images, state=state)  # 不传示范动作和补齐标记，使用零潜变量策略推理
            absolute_error = (output["actions"] - actions).abs()  # 计算归一化动作空间的逐元素绝对误差
            valid = (~is_pad).unsqueeze(-1)  # 创建可沿动作维广播的有效位置掩码
            masked_error = absolute_error.masked_fill(~valid, 0.0)  # 将补齐位置误差置零，不修改原张量
            total_absolute_error += masked_error.sum().item()  # 累加有效误差总和，不平均各批次损失
            action_dim = actions.shape[-1]  # 读取单步动作维度
            num_valid_elements += int((~is_pad).sum().item()) * action_dim  # 按有效时间步数乘动作维度累加元素数量
            num_samples += int(actions.shape[0])  # 按实际批次大小累加样本数，包括不足整批的末批
    val_l1 = total_absolute_error / num_valid_elements  # 在整个加载器的有效动作元素上计算平均绝对误差
    model.train(was_training)  # 正常完成后恢复调用前的训练或验证模式
    return {  # 返回 Python float 和 int，不保存实验成绩
        "val_l1": val_l1,  # 零潜变量策略的离线平均绝对误差
        "num_samples": num_samples,  # 实际处理的样本总数
        "num_valid_elements": num_valid_elements,  # 实际参与误差统计的动作元素总数
    }  # 完成结果字典
