# SO101 最小模型资源

机器人来自 [MuJoCo Menagerie / robotstudio_so101](https://github.com/google-deepmind/mujoco_menagerie/tree/main/robotstudio_so101)，其模型派生自 [TheRobotStudio 的 SO101 MJCF](https://github.com/TheRobotStudio/SO-ARM100/tree/main/Simulation/SO101)。这是 SO101 从臂模型，不是 SO100。

本目录保留上游 `LICENSE`（Apache-2.0），`so101.xml` 和其声明引用的 18 个 STL 网格；未引入整个上游仓库。机器人 XML、网格、惯性、碰撞体、执行器参数均未修改。唯一新增的模型文件是 `scene.xml`：引用机器人，加入桌面、两盏灯及固定 front 相机，并设置离屏画布尺寸。上游自带腕部相机仍在模型中，本接口只输出 front 图像。

## 模型与控制约定

底座 body 无关节，固定于世界；没有 free joint、tendon 或 equality 联动。每个关节为 hinge，绑定同名 position 执行器，夹爪是固定夹指加一个转动夹指。因此当前六维动作与六维实际关节状态均为 rad，但程序仍按名称取得 qpos 地址和执行器编号，不依赖数组前六项。

下表顺序用于 state 与 action。实际允许目标取关节范围与 ctrlrange 的交集，少数末位差异来自上游 XML 的小数舍入。

| 名称 | 含义 | 允许目标范围（rad） |
|---|---|---|
| shoulder_pan | 肩部水平旋转 | [-1.91986, 1.91986] |
| shoulder_lift | 肩部俯仰 | [-1.7453293, 1.7453293] |
| elbow_flex | 肘部弯曲 | [-1.69, 1.69] |
| wrist_flex | 腕部俯仰 | [-1.65806, 1.65806] |
| wrist_roll | 腕部旋转 | [-2.7438473, 2.8412063] |
| gripper | 活动夹指转角 | [-0.17453, 1.7453292] |

六个关节的 XML 局部轴均为 +Z，正方向按各自局部坐标系的右手规则定义，不能认为它们都是世界 Z 轴。初始臂角均为零时，世界轴依次约为 -Z、+Y、+Y、+Y、-X、(0,-0.9988,-0.0487)。夹爪由 0.05 增至 0.7 rad 时，两侧尖端球体中心距离由约 0.0202 m 增至 0.0701 m，表示开口增大；这不是线性夹爪宽度指令。演示仅小范围开合，不把 0.05 rad 宣称为机械完全闭合点。

保持上游位置伺服参数 kp=998.22、kv=2.731、力矩范围 ±2.94 N·m，以及关节阻尼、摩擦和 armature。这些不是实体舵机固件增益的一一对应值。各运动部件具有显式质量和惯性；视觉网格不参与接触，碰撞使用上游几何体及夹爪碰撞网格，未凭外观重新生成惯性。

初始姿态为 [0,0,0,0,0,0.3]。沿用 implicitfast 和 0.005 秒步长，20 Hz 控制对应十个物理步。reset 可以设置初始 qpos，正常控制只设置执行器目标；观测来自实际 qpos。

## 使用和范围

从项目根目录运行 `scripts/view_sim.py`，配置为 `configs/tasks/so101_pick_place.yaml`。场景仅有机器人、桌面与相机，没有物体、目标区域或成功判定。默认相机输出 640×480 RGB uint8，与 ACT 的 224×224 缩放分开。

本次小范围检查不能证明整个限位范围都无碰撞。上游有 [肘部极限姿态自碰撞报告](https://github.com/google-deepmind/mujoco_menagerie/issues/325)，本阶段不扫完整限位，也未通过删除碰撞体来绕过接触。
