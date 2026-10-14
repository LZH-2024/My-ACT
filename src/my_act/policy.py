from pathlib import Path  # 表示 checkpoint 文件路径

import torch  # 加载权重并执行张量预处理与推理
import torch.nn.functional as F  # 使用与训练数据集一致的图像插值

from my_act.models.act import ACT  # 复用完整 ACT 模型


class ACTPolicy:  # 封装从原始观测到原始尺度动作块的推理接口
    """使用 checkpoint 中的模型与统计量进行零潜变量推理，返回完整动作块，不裁剪或执行动作。"""  # 类说明

    def __init__(  # 从一个 checkpoint 初始化推理模型
        self,  # 当前策略实例
        checkpoint_path: str | Path,  # 包含模型配置、权重和统计量的 checkpoint 路径
        device: str | torch.device,  # 推理使用的目标设备
    ) -> None:  # 构造函数不返回数据
        """仅读取一次 checkpoint，完整恢复模型权重，无需下载 ImageNet 权重，不创建或恢复优化器。"""  # 构造函数说明
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)  # 在 CPU 上以受限方式读取完整 checkpoint
        model_config = checkpoint["model_config"].copy()  # 复制模型配置，不修改 checkpoint 中的原配置
        model_config["pretrained_backbone"] = False  # 构建时跳过 ImageNet 权重加载，随后完整恢复 checkpoint 权重
        self.model = ACT(model_config)  # 按保存的模型结构创建 ACT
        self.model.load_state_dict(checkpoint["model"], strict=True)  # 严格恢复所有模型参数和缓冲区
        self.device = torch.device(device)  # 保存规范化后的目标设备
        self.model.to(self.device)  # 将完整模型移动到目标设备
        self.model.eval()  # 使用推理模式的 BatchNorm 和 Dropout 行为
        self.image_size = model_config["image_size"]  # 保存训练时使用的图像尺寸
        self.step = checkpoint["step"]  # 保存 checkpoint 对应的已完成更新次数
        self.state_mean = checkpoint["stats"]["state"]["mean"].to(device=self.device, dtype=torch.float32)  # 使用本 checkpoint 的状态均值
        self.state_std = checkpoint["stats"]["state"]["std"].to(device=self.device, dtype=torch.float32)  # 使用本 checkpoint 的状态标准差
        self.action_mean = checkpoint["stats"]["action"]["mean"].to(device=self.device, dtype=torch.float32)  # 使用本 checkpoint 的动作均值
        self.action_std = checkpoint["stats"]["action"]["std"].to(device=self.device, dtype=torch.float32)  # 使用本 checkpoint 的动作标准差

    def predict(self, images: torch.Tensor, state: torch.Tensor) -> torch.Tensor:  # 将原始观测转换为完整动作块
        """输入为 RGB uint8 图像 [B, C, 3, H, W] 和原始尺度状态 [B, state_dim]，相机顺序须与训练 camera_keys 一致；返回目标设备上的 float32 原始尺度动作 [B, chunk_size, action_dim]。"""  # 方法说明
        images = images.to(device=self.device, dtype=torch.float32) / 255.0  # 移动图像并转换到 [0, 1]，不修改输入
        batch_size, num_cameras, channels, height, width = images.shape  # 读取批次、相机和原始图像尺寸
        images = images.reshape(batch_size * num_cameras, channels, height, width)  # 合并批次与相机维，独立缩放每路图像
        images = F.interpolate(  # 使用与 ACTDataset 完全相同的插值参数
            images,  # 传入 [B*C, 3, H, W] 图像
            size=(self.image_size, self.image_size),  # 缩放到模型训练时的图像尺寸
            mode="bilinear",  # 使用双线性插值
            align_corners=False,  # 不对齐角点中心
            antialias=True,  # 启用抗锯齿
        )  # 完成图像缩放，不在这里执行 ImageNet 归一化
        images = images.reshape(batch_size, num_cameras, channels, self.image_size, self.image_size)  # 恢复批次维与相机维
        state = state.to(device=self.device, dtype=torch.float32)  # 将原始状态移动到目标设备并转为 float32
        state = (state - self.state_mean) / self.state_std  # 使用 checkpoint 统计量归一化状态，不修改输入
        with torch.inference_mode():  # 禁用推理过程的梯度记录
            output = self.model(images=images, state=state)  # 仅传图像与状态，使用零潜变量策略分支
            actions = output["actions"] * self.action_std + self.action_mean  # 将完整预测动作块还原到原始尺度
        return actions  # 返回目标设备上的 float32 动作块，不裁剪或选取第一步
