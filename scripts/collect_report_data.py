# -*- coding: utf-8 -*-
"""从课程实验结果生成 report_data.json(报告生成器的输入)。

用法(Windows 侧,SSD 项目目录内):
    python collect_report_data.py <course results.csv> <environment.txt> <figures dir>

输出:report_data.json —— 环境表、三轮汇总表、内部指标、资源表与图路径。
汇总规则与 ssd 包一致(中位数/最小/最大,空白≠0)。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ssd.aggregate import aggregate  # noqa: E402
from ssd.schema import load  # noqa: E402


def parse_environment(path: Path) -> dict[str, str]:
    """从 environment.txt 抽取关键环境信息。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    env: dict[str, str] = {}

    def grab(pattern: str, key: str, group: int = 1) -> None:
        m = re.search(pattern, text)
        if m:
            env[key] = m.group(group).strip()

    grab(r"experiment_id=(\S+)", "实验标识 experiment-id")
    grab(r"repeats=(\d+)", "重复次数")
    grab(r"threads=(\d+)", "查询线程")
    grab(r"beamwidth=(\d+)", "Beam Width")
    grab(r"topk=(\d+)", "Top-K")
    grab(r"pipeann_high_l=([0-9 ]+)", "PipeANN High 三档 L")
    grab(r"pipeann_representative_l=(\d+)", "PipeANN 代表性 L")
    grab(r"gateann_high_l=([0-9 ]+)", "GateANN High 三档 L")
    grab(r"gateann_representative_l=(\d+)", "GateANN 代表性 L")
    grab(r"pipeann_commit=([0-9a-f]+)", "PipeANN-Filter Commit")
    grab(r"gateann_commit=([0-9a-f]+)", "GateANN Commit")

    m = re.search(r"\[uname\]\n(.+)", text)
    if m:
        env["操作系统与内核"] = m.group(1).strip()
    m = re.search(r"Mem:\s+([\d.]+)Gi", text)
    if m:
        env["内存"] = f"WSL2 可用约 {m.group(1)} GiB(低于课程建议的 16 GiB,如实报告)"
    m = re.search(r"\[block-devices\]\n(.+?)\n\n", text, re.S)
    if m:
        env["块设备"] = m.group(1).strip().replace("\n", ";")
    m = re.search(r"\[compiler\]\n(.+)", text)
    if m:
        env["编译器"] = m.group(1).strip().splitlines()[0]
    m = re.search(r"model name\s*:\s*(.+)", text, re.I)
    if m:
        env["CPU"] = m.group(1).strip()
    if "WSL" in text or "microsoft" in text.lower():
        env.setdefault("环境说明", "WSL2 虚拟磁盘(ext4),宿主机 Windows 11")
    env["I/O Backend"] = "AIO"
    env["公共参数"] = "threads=1, beamwidth=8, K=10, mem_L=0, 缓存预算=0; GateANN FullAdj neighbors=32"
    return env


def fmt(v: object, digits: int = 2) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return f"{v:.{digits}f}"


def rng(med: object, lo: object, hi: object, digits: int = 2) -> str:
    if med is None or (isinstance(med, float) and pd.isna(med)):
        return ""
    return f"{fmt(med, digits)}({fmt(lo, digits)}–{fmt(hi, digits)})"


def html_table(headers: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
    )
    return f"<table><tr>{th}</tr>{trs}</table>"


def build_tables(summary: pd.DataFrame, internal: pd.DataFrame, resources: pd.DataFrame) -> dict[str, str]:
    # 表 4.1
    high = summary[summary["bucket"] == "high"].sort_values(
        by=["system", "L"], key=lambda s: s.map({"pipeann": 0, "gateann": 1}) if s.name == "system" else s
    )
    rows = []
    for _, r in high.iterrows():
        name = "PipeANN-Filter" if r["system"] == "pipeann" else "GateANN"
        rows.append([
            name, str(int(r["L"])),
            rng(r["recall_percent_median"], r["recall_percent_min"], r["recall_percent_max"]),
            rng(r["mean_latency_us_median"], r["mean_latency_us_min"], r["mean_latency_us_max"], 1),
            rng(r["qps_median"], r["qps_min"], r["qps_max"], 1),
            rng(r["mean_ios_median"], r["mean_ios_min"], r["mean_ios_max"]),
        ])
    t41 = html_table(
        ["系统", "L", "Recall@10(%)", "Mean Latency(μs)", "QPS", "Mean I/O(次/查询)"], rows
    )

    # 表 4.2
    reps = summary[
        ((summary["system"] == "pipeann") & (summary["L"] == 40))
        | ((summary["system"] == "gateann") & (summary["L"] == 320))
    ].sort_values(by=["system", "selectivity_median"])
    rows = []
    for _, r in reps.iterrows():
        name = "PipeANN-Filter" if r["system"] == "pipeann" else "GateANN"
        ir = internal[
            (internal["system"] == r["system"])
            & (internal["bucket"] == r["bucket"])
            & (internal["L"] == r["L"])
        ]
        if r["system"] == "pipeann":
            if ir.empty:
                detail = ""
            else:
                x = ir.iloc[0]
                detail = (
                    f"Pre/In/Post {int(x['pre_filter_queries'])}/{int(x['in_filter_queries'])}/"
                    f"{int(x['post_filter_queries'])},假阳性 {fmt(x['filter_false_positives'], 1)}"
                )
        else:
            if ir.empty:
                detail = ""
            else:
                x = ir.iloc[0]
                detail = (
                    f"Skips {fmt(x['filter_skips'])};Tunnel {fmt(x['tunnel_time_us'], 0)} μs;"
                    f"I/O {fmt(x['io_time_us'], 0)} μs;Process {fmt(x['process_time_us'], 0)} μs"
                )
        rows.append([
            name, r["bucket"].capitalize(),
            f"{r['selectivity_min']:.3f}–{r['selectivity_max']:.3f} / {r['selectivity_median']:.3f}",
            rng(r["recall_percent_median"], r["recall_percent_min"], r["recall_percent_max"]),
            rng(r["mean_latency_us_median"], r["mean_latency_us_min"], r["mean_latency_us_max"], 1),
            rng(r["mean_ios_median"], r["mean_ios_min"], r["mean_ios_max"]),
            detail,
        ])
    t42 = html_table(
        ["系统", "Bucket", "Selectivity 范围/中位数(%)", "Recall@10(%)",
         "Mean Latency(μs)", "Mean I/O(次/查询)", "关键内部指标"], rows
    )

    # 表 4.3
    rows = []
    for _, r in resources.iterrows():
        name = "PipeANN-Filter" if r["system"] == "pipeann" else "GateANN"
        idx = r["index_size_gib"]
        idx_s = f"{idx:.4g}" if not pd.isna(idx) and not isinstance(idx, str) else str(idx)
        rows.append([name, idx_s, rng(r["peak_rss_mib_median"], r["peak_rss_mib_min"], r["peak_rss_mib_max"], 1)])
    t43 = html_table(["系统", "索引大小(GiB)", "查询峰值 RSS(MiB)"], rows)

    return {"t41": t41, "t42": t42, "t43": t43}


def main() -> int:
    results_csv = Path(sys.argv[1])
    env_txt = Path(sys.argv[2])
    figures_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("figures")

    raw = load(str(results_csv))
    agg = aggregate(raw)
    environment = parse_environment(env_txt)
    tables = build_tables(agg.summary, agg.internal, agg.resources)

    data = {
        "title": "基于 SSD 的过滤向量检索系统性能测试与设计比较",
        "date": "2026 年 11 月 12 日",
        "experiment_id": environment.get("实验标识 experiment-id", ""),
        "environment": environment,
        "tables": tables,
        "figures": {
            "fig1": str(figures_dir / "fig1_recall_latency.png"),
            "fig2": str(figures_dir / "fig2_selectivity.png"),
            "fig3": str(figures_dir / "fig3_gateann_time_decomposition.png"),
            "fig4": str(figures_dir / "fig4_internal_behavior.png"),
        },
        "sections": {},  # 分析文字由 build_report 阶段填入
    }
    out = Path("report_data.json")
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {out}(结果 {len(raw)} 行)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
