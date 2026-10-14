import torch  # 创建图像统计量并表示输入输出张量
from torch import nn  # 构建视觉骨干网络和通道投影层
from torchvision.models import ResNet18_Weights, resnet18  # 使用 ResNet18 及其官方预训练权重


class VisualBackbone(nn.Module):  # 定义所有相机共享的视觉骨干
    """将 [B, C, 3, H, W] 图像转为保留空间布局的特征，C 为相机数量。"""  # 类说明

    def __init__(self, hidden_dim: int, pretrained: bool) -> None:  # 接收模型内部维度与预训练开关
        """构建共享 ResNet18 和通道投影，保留默认 BatchNorm，所有参数均可训练。"""  # 构造函数说明
        super().__init__()  # 初始化 PyTorch 模块
        weights = ResNet18_Weights.IMAGENET1K_V1 if pretrained else None  # 根据开关选择官方权重或随机初始化
        resnet = resnet18(weights=weights)  # 创建 ResNet18，优先复用 torchvision 权重缓存
        self.features = nn.Sequential(*list(resnet.children())[:-2])  # 去掉全局平均池化和分类层，保留到 layer4 的空间特征
        self.projection = nn.Conv2d(512, hidden_dim, kernel_size=1)  # 用共享的 1×1 卷积映射到模型内部特征维度
        self.register_buffer(  # 注册随设备移动并保存到 state_dict 的非训练均值
            "mean",  # 保存图像均值的缓冲区名称
            torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32).reshape(1, 3, 1, 1),  # 按 RGB 通道广播的 ImageNet 均值
        )  # 完成均值注册
        self.register_buffer(  # 注册随设备移动并保存到 state_dict 的非训练标准差
            "std",  # 保存图像标准差的缓冲区名称
            torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32).reshape(1, 3, 1, 1),  # 按 RGB 通道广播的 ImageNet 标准差
        )  # 完成标准差注册

    def forward(self, images: torch.Tensor) -> torch.Tensor:  # 提取各相机的空间特征图
        """接收 [0, 1] 范围的 float32 图像 [B, C, 3, H, W]，返回 [B, C, hidden_dim, Hf, Wf] 特征。"""  # 前向方法说明
        batch_size, num_cameras, channels, height, width = images.shape  # 读取批次、相机、通道和输入空间尺寸
        images = images.reshape(batch_size * num_cameras, channels, height, width)  # 合并批次维与相机维，让各相机共享网络
        images = (images - self.mean) / self.std  # 执行 ImageNet 归一化，不原地修改输入
        features = self.features(images)  # 提取保留空间布局的 ResNet18 特征
        features = self.projection(features)  # 将 512 个通道投影到模型内部维度
        _, hidden_dim, feature_height, feature_width = features.shape  # 从实际输出读取通道数和空间尺寸
        return features.reshape(batch_size, num_cameras, hidden_dim, feature_height, feature_width)  # 恢复批次维与相机维，不平均或展平空间特征
