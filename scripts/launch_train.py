import argparse  # 解析实验目录和流程演示选项
import json  # 保存本次启动记录
import subprocess  # 以参数列表创建后台训练进程
import sys  # 使用当前 Python 解释器
from datetime import datetime  # 一次生成目录与记录共用的启动时间
from pathlib import Path  # 组织实验、运行和日志路径
from zoneinfo import ZoneInfo  # 使用上海时区


def launch_training(experiment_dir: str | Path, smoke_test: bool = False) -> None:  # 保留独立运行目录和后台启动逻辑
    """使用现有解释器启动 train.py；仅供真实数据源接入并恢复训练命令后调用，不轮询或重启。"""  # 函数说明
    experiment_dir = Path(experiment_dir).resolve()  # 保存实验目录绝对路径
    if not experiment_dir.is_dir():  # 不意外创建尚未准备的实验目录
        raise ValueError(f"实验目录不存在：{experiment_dir}")  # 直接报告无效实验路径
    started_at = datetime.now(ZoneInfo("Asia/Shanghai"))  # 目录名称与启动记录共用同一次时间生成
    run_dir = experiment_dir / "runs" / started_at.strftime("%Y%m%d_%H%M%S_%f")  # 为每次启动创建独立时间戳目录
    run_dir.mkdir(parents=True, exist_ok=False)  # 禁止覆盖已有同名运行目录
    train_script = Path(__file__).resolve().with_name("train.py")  # 定位同目录下的训练入口
    command = [sys.executable, "-u", str(train_script), "--experiment-dir", str(experiment_dir), "--run-dir", str(run_dir)]  # 使用参数列表传入唯一的本次运行目录
    if smoke_test:  # 仅在调用方指定时启用已有 smoke-test
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
        "smoke_test": smoke_test,  # 记录是否启用流程演示
        "cwd": str(Path.cwd()),  # 记录项目相对路径的解析起点
        "log_path": str(log_path),  # 记录本次终端日志位置
    }  # 完成本次启动记录，不声称训练已完成
    with (run_dir / "launch_record.json").open("x", encoding="utf-8") as file:  # 在运行目录独占创建记录
        json.dump(record, file, ensure_ascii=False, indent=2)  # 保留中文并格式化输出
    print("run_dir:", run_dir, flush=True)  # 打印运行目录供后续查阅
    print("pid:", process.pid, flush=True)  # 打印 PID 后返回，不等待或轮询训练


def main() -> None:  # 展示入口参数并明确当前数据适配缺口
    """SO101 数据源完成前不创建运行目录或启动后台进程，--help 可正常查看。"""  # 函数说明
    parser = argparse.ArgumentParser(description="ACT 后台启动入口（等待 SO101 数据源接入）")  # 保留已有命令参数
    parser.add_argument("--experiment-dir", required=True, help="已准备好的实验目录")  # 明确实验配置来源
    parser.add_argument("--smoke-test", action="store_true", help="数据接入后用于三步流程演示")  # 保留流程演示选项
    parser.parse_args()  # --help 在这里正常退出，不创建产物
    parser.error("SO101 数据源尚未实现，后台训练入口暂不可用；未创建运行目录或启动进程。")  # 不启动必然失败的子进程


if __name__ == "__main__":  # 使用标准脚本入口
    main()  # 显示参数或报告数据源缺口，不启动训练
