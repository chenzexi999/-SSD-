"""报告"优化方向"中验证计划的实验执行器(仅 Linux 实验环境使用)。

验证计划(报告第 5 节):固定 GateANN 在 Low workload 上扫描更大的搜索预算
L ∈ {640, 1280, 2560},检验"强过滤下 Recall 受限于搜索预算而非读盘次数"
这一假设。

- 对照组:课程正式实验中 GateANN Low L=320 的结果(Recall 34.30%、
  mean I/O 4.38、Tunnel 410 μs);
- 自变量:仅 L;
- 控制变量:同一台机器、同一正式索引、同一 Low 查询集、AIO、threads=1、
  beamwidth=8、K=10、FullAdj neighbors=32;
- 每档独立重复 3 次;
- 支持判据:Recall 升至 80% 以上、新增延迟主要由 Tunnel time 解释、
  mean I/O 仍显著低于 PipeANN-Filter 的 80 次/查询 -> 支持假设;
  Recall 停在 ~40% 且 Tunnel time 近似线性上升 -> 否定假设。

前置条件:课程仓库(含预构建索引)与 GateANN 源码已按课程脚本就绪;
本脚本不修改任何课程参数,只按课程适配器的既有接口追加运行 L 扫描。
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_SWEEP_L = (640, 1280, 2560)
DEFAULT_REPEATS = 3
BASELINE = {
    "L": 320,
    "recall_percent": 34.30,
    "mean_ios": 4.38,
    "tunnel_time_us": 410,
}


def run_one(
    adapter: Path,
    repo: Path,
    dataset_root: Path,
    run_root: Path,
    *,
    L: int,
    run_id: str,
    threads: int = 1,
    beamwidth: int = 8,
    k: int = 10,
) -> subprocess.CompletedProcess:
    """调用课程 GateANN 适配器执行一次 Low workload 查询。"""
    command = [
        sys.executable,
        str(adapter),
        "search",
        "--repo",
        str(repo),
        "--dataset-root",
        str(dataset_root),
        "--tier",
        "formal",
        "--run-root",
        str(run_root),
        "--threads",
        str(threads),
        "--beamwidth",
        str(beamwidth),
        "--k",
        str(k),
        "--bucket",
        "low",
        "--L",
        str(L),
        "--full-adj-neighbors",
        "32",
        "--run-id",
        run_id,
    ]
    return subprocess.run(command, check=False, capture_output=True, text=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GateANN Low workload 搜索预算扫描(验证计划,Linux 实验环境)",
    )
    parser.add_argument("--repo", type=Path, required=True, help="GateANN 源码目录(课程固定提交)")
    parser.add_argument("--adapter", type=Path, default=None, help="gateann_adapter.py 路径;默认 <repo>/../adapters/")
    parser.add_argument("--dataset-root", type=Path, required=True, help="课程数据集根目录(含 formal_1000000)")
    parser.add_argument("--run-root", type=Path, required=True, help="course_runs 目录")
    parser.add_argument("--L", type=int, nargs="+", default=list(DEFAULT_SWEEP_L), help="扫描的搜索预算")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--beamwidth", type=int, default=8)
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args(argv)

    adapter = args.adapter or (args.repo.parent / "adapters" / "gateann_adapter.py")
    if not adapter.is_file():
        print(f"错误:找不到适配器 {adapter}", file=sys.stderr)
        return 2

    experiment_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    manifest: dict[str, object] = {
        "experiment_id": experiment_id,
        "system": "gateann",
        "bucket": "low",
        "baseline": BASELINE,
        "L_sweep": list(args.L),
        "repeats": args.repeats,
        "fixed": {
            "threads": args.threads,
            "beamwidth": args.beamwidth,
            "k": args.k,
            "full_adj_neighbors": 32,
            "io_backend": "aio",
        },
    }
    for L in args.L:
        for repeat in range(1, args.repeats + 1):
            run_id = f"validation-{experiment_id}-L{L}-r{repeat}"
            print(f"[{L}] 第 {repeat}/{args.repeats} 轮,run-id={run_id}", flush=True)
            result = run_one(
                adapter,
                args.repo,
                args.dataset_root,
                args.run_root,
                L=L,
                run_id=run_id,
                threads=args.threads,
                beamwidth=args.beamwidth,
                k=args.k,
            )
            if result.returncode != 0:
                print(f"运行失败(exit={result.returncode}),日志见 {args.run_root}/results/", file=sys.stderr)
                return 1

    manifest_path = args.run_root / "experiments" / f"validation-{experiment_id}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成。结果目录:{args.run_root}/results/gateann/formal_1000000/low/validation-{experiment_id}-*")
    print(f"清单:{manifest_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
