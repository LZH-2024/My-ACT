from pathlib import Path  # 导入路径类型，支持传入 Path 对象

import yaml  # 导入 YAML 读取工具


def read_yaml(path: str | Path) -> dict:  # 接收文件路径，返回配置字典
    """以 UTF-8 读取 YAML 配置文件并返回普通字典。"""  # 函数用途说明
    with open(path, "r", encoding="utf-8") as file:  # 以 UTF-8 打开文件，读取后自动关闭
        return yaml.safe_load(file)  # 安全读取 YAML 内容并返回字典
