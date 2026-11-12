"""fvslab 命令行入口。

子命令:
- figures:  从 data/ 生成全部图与表格;
- refresh:  从课程聚合结果 CSV(30 行)重新生成 data/ 下的数据文件;
- validate-plan: 运行验证计划实验(GateANN Low L 扫描,Linux 实验环境)。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .aggregate import aggregate
from .figures import make_all_figures
from .schema import load
from .tables import all_tables


def _cmd_figures(args: argparse.Namespace) -> int:
    import pandas as pd

    summary = pd.read_csv(args.data_dir / "aggregated.csv")
    internal = pd.read_csv(args.data_dir / "internal_metrics.csv")
    resources = pd.read_csv(args.data_dir / "resources.csv")
    make_all_figures(summary, internal, args.output_dir, formats=tuple(args.formats))
    if args.tables:
        tables_dir = args.output_dir.parent / "tables"
        tables_dir.mkdir(parents=True, exist_ok=True)
        for name, content in all_tables(summary, internal, resources).items():
            (tables_dir / name).write_text(content, encoding="utf-8")
    print(f"完成:图输出至 {args.output_dir}")
    return 0


def _cmd_refresh(args: argparse.Namespace) -> int:
    raw = load(str(args.results_csv))
    result = aggregate(raw)
    paths = result.to_csv(str(args.data_dir))
    for path in paths:
        print(f"已写入 {path}")
    return 0


def _cmd_validate_plan(args: argparse.Namespace) -> int:
    from .validate import main as validate_main

    return validate_main(
        [
            "--repo", str(args.repo),
            "--dataset-root", str(args.dataset_root),
            "--run-root", str(args.run_root),
            "--L", *(str(v) for v in args.L),
            "--repeats", str(args.repeats),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fvslab", description="SSD 过滤向量检索实验分析工具")
    parser.add_argument("--version", action="version", version=f"fvslab {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fig = sub.add_parser("figures", help="从 data/ 生成图与表格")
    p_fig.add_argument("--data-dir", type=Path, default=Path("data"))
    p_fig.add_argument("--output-dir", type=Path, default=Path("figures"))
    p_fig.add_argument("--formats", nargs="+", default=["pdf", "png"])
    p_fig.add_argument("--tables", action="store_true", help="同时生成 tables/*.md")
    p_fig.set_defaults(func=_cmd_figures)

    p_ref = sub.add_parser("refresh", help="从课程 results.csv(30 行)重新聚合 data/")
    p_ref.add_argument("--results-csv", type=Path, required=True, help="course_runs/experiments/<id>/results.csv")
    p_ref.add_argument("--data-dir", type=Path, default=Path("data"))
    p_ref.set_defaults(func=_cmd_refresh)

    p_val = sub.add_parser("validate-plan", help="验证计划实验:GateANN Low L 扫描(Linux)")
    p_val.add_argument("--repo", type=Path, required=True)
    p_val.add_argument("--dataset-root", type=Path, required=True)
    p_val.add_argument("--run-root", type=Path, required=True)
    p_val.add_argument("--L", type=int, nargs="+", default=[640, 1280, 2560])
    p_val.add_argument("--repeats", type=int, default=3)
    p_val.set_defaults(func=_cmd_validate_plan)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
