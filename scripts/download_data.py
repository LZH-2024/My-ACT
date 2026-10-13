# 数据来源：https://huggingface.co/datasets/lerobot/libero
# 已确认默认 revision 的 meta/info.json 中 codebase_version 为 v3.0。
# 下载完整快照，保留共享 Parquet 和视频分片的原始目录结构。

import argparse  # 读取命令行参数
from pathlib import Path  # 根据脚本位置计算项目根目录

from huggingface_hub import snapshot_download  # 复用下载库的快照下载能力


def main() -> None:  # 定义命令行入口
    """下载固定版本的 LeRobot LIBERO v3.0 完整数据快照。"""  # 函数说明
    parser = argparse.ArgumentParser(description="下载 LeRobot 格式 LIBERO v3.0 数据")  # 创建参数解析器
    parser.add_argument(  # 允许指定数据版本
        "--revision",  # 数据版本参数名
        default="a1aaacb7f6cd6ee5fb43120f673cebb0cfea7dd4",  # 已确认格式为 v3.0 的完整提交 SHA
        help="数据仓库 revision，默认使用已确认的 v3.0 提交",  # 参数帮助说明
    )  # 完成版本参数定义
    parser.add_argument(  # 允许指定数据保存目录
        "--local-dir",  # 保存目录参数名
        type=Path,  # 将输入路径转换为 Path 对象
        default=Path(__file__).resolve().parents[1] / "data" / "libero",  # 默认保存到项目根目录下
        help="保存目录，默认为项目根目录下的 data/libero",  # 参数帮助说明
    )  # 完成目录参数定义
    args = parser.parse_args()  # 读取实际传入的参数
    path = snapshot_download(  # 下载完整快照，不按任务编号筛选文件
        repo_id="lerobot/libero",  # 指定 LeRobot 格式 LIBERO 数据仓库
        repo_type="dataset",  # 指定仓库类型为数据集
        revision=args.revision,  # 固定本次下载的数据版本
        local_dir=args.local_dir.expanduser().resolve(),  # 展开用户目录并使用绝对路径
    )  # 下载完成后获得本地目录路径
    print(f"数据 revision：{args.revision}")  # 显示本次使用的数据版本
    print(f"数据已保存到：{path}")  # 显示最终保存目录


if __name__ == "__main__":  # 仅在直接运行脚本时开始下载
    main()  # 执行下载入口
