# 官方下载说明：https://github.com/Lifelong-Robot-Learning/LIBERO#datasets
# 官方数据文档：https://lifelong-robot-learning.github.io/LIBERO/html/algo_data/datasets.html
# 官方仓库指定的数据源：https://huggingface.co/datasets/yifengzhu-hf/LIBERO-datasets
# 仅下载目标任务的原始 HDF5；保留 libero_goal 目录，不需要解压或格式转换。

import argparse  # 读取命令行参数
from pathlib import Path  # 根据脚本位置确定保存路径

from huggingface_hub import hf_hub_download  # 复用下载工具的缓存和续传能力


def main() -> None:  # 定义命令行下载入口
    """下载 libero_goal 中将碗放到盘子上的任务示范，保留原始 HDF5。"""  # 函数说明
    parser = argparse.ArgumentParser(description="下载 LIBERO 官方目标任务数据")  # 创建参数解析器
    parser.add_argument(  # 允许用户指定数据保存目录
        "--local-dir",  # 保存目录参数名
        type=Path,  # 将输入路径转换为 Path 对象
        default=Path(__file__).resolve().parents[1] / "data" / "libero",  # 默认保存到项目根目录下
        help="保存目录，默认为项目根目录下的 data/libero",  # 命令行帮助说明
    )  # 完成参数定义
    args = parser.parse_args()  # 读取实际传入的参数
    local_dir = args.local_dir.expanduser().resolve()  # 展开用户目录并转换为绝对路径
    path = hf_hub_download(  # 下载单个文件，并保留数据源中的子目录结构
        repo_id="yifengzhu-hf/LIBERO-datasets",  # LIBERO 官方仓库指定的数据仓库
        repo_type="dataset",  # 指定仓库类型为数据集
        filename="libero_goal/put_the_bowl_on_the_plate_demo.hdf5",  # 按任务文件名选择数据
        local_dir=local_dir,  # 指定最终保存目录
    )  # 下载完成后获得本地文件路径
    print(f"数据已保存到：{path}")  # 显示最终保存路径


if __name__ == "__main__":  # 仅在直接运行脚本时开始下载
    main()  # 执行下载入口
