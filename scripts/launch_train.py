import argparse  # 解析实验目录和流程演示选项
import json  # 保存本次启动记录
import subprocess  # 以参数列表创建后台训练进程
import sys  # 使用当前 Python 解释器
from datetime import datetime  # 一次生成目录与记录共用的启动时间
from pathlib import Path  # 组织实验、运行和日志路径
from zoneinfo import ZoneInfo  # 使用上海时区


def main() -> None:  # 创建独立运行目录并启动一次后台训练
    """只负责启动和日志归属，打印运行目录与 PID 后返回；不轮询、不重启、不恢复 checkpoint。"""  # 函数说明
    parser = argparse.ArgumentParser(description="创建运行目录并后台启动 ACT 训练")  # 创建命令行参数解析器
    parser.add_argument("--experiment-dir", required=True, help="已准备好的实验目录")  # 必须指定实验配置来源
    parser.add_argument("--smoke-test", action="store_true", help="仅启动三步流程演示")  # 仅透传已有演示选项
    args = parser.parse_args()  # 读取实际启动参数
    experiment_dir = Path(args.experiment_dir).resolve()  # 保存实验目录绝对路径
    if not experiment_dir.is_dir():  # 不意外创建尚未准备的实验目录
        parser.error(f"实验目录不存在：{experiment_dir}")  # 直接报告无效实验路径
    started_at = datetime.now(ZoneInfo("Asia/Shanghai"))  # 目录名称与启动记录共用同一次时间生成
    run_dir = experiment_dir / "runs" / started_at.strftime("%Y%m%d_%H%M%S_%f")  # 为每次启动创建独立时间戳目录
    run_dir.mkdir(parents=True, exist_ok=False)  # 禁止覆盖已有同名运行目录
    train_script = Path(__file__).resolve().with_name("train.py")  # 定位同目录下的训练入口
    command = [sys.executable, "-u", str(train_script), "--experiment-dir", str(experiment_dir), "--run-dir", str(run_dir)]  # 使用参数列表传入唯一的本次运行目录
    if args.smoke_test:  # 仅在调用方指定时启用已有 smoke-test
        command.append("--smoke-test")  # 将演示选项原样传给训练入口
    log_path = run_dir / "terminal.log"  # stdout 和 stderr 归属本次运行目录
    with log_path.open("x", encoding="utf-8") as log:  # 独占创建终端日志，不覆盖已有内容
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)  # 脱离启动方会话在 WSL 后台运行，无需 supervisor
    record = {  # 保存直接有用的启动信息，不记录哈希或 Git 提交
        "command": command,  # 保存实际执行的参数列表，不拼接 shell 命令
        "experiment_dir": str(experiment_dir),  # 记录配置和数据划分所在实验目录
        "run_dir": str(run_dir),  # 记录所有本次运行产物的目录
        "started_at": started_at.isoformat(),  # 使用创建目录时的同一个时间值
        "pid": process.pid,  # 记录后台训练子进程 PID
        "smoke_test": args.smoke_test,  # 记录是否启用流程演示
        "cwd": str(Path.cwd()),  # 记录项目相对路径的解析起点
        "log_path": str(log_path),  # 记录本次终端日志位置
    }  # 完成本次启动记录，不声称训练已完成
    with (run_dir / "launch_record.json").open("x", encoding="utf-8") as file:  # 在运行目录独占创建记录
        json.dump(record, file, ensure_ascii=False, indent=2)  # 保留中文并格式化输出
    print("run_dir:", run_dir, flush=True)  # 打印运行目录供后续查阅
    print("pid:", process.pid, flush=True)  # 打印 PID 后返回，不等待或轮询训练


if __name__ == "__main__":  # 使用标准脚本入口
    main()  # 仅在直接执行时启动后台训练
