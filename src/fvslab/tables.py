"""报告表格的 Markdown 输出。

与《实验报告模板》4.1 / 4.2 / 4.3 三张表的列结构一致;
数值格式:中位数(最小–最大),与报告正文的写法相同。
"""

from __future__ import annotations

import pandas as pd

FORMAT = "{:.2f}"


def _fmt(value: object, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return f"{value:.{digits}f}"


def _range(median: object, low: object, high: object, digits: int = 2) -> str:
    if median is None or (isinstance(median, float) and pd.isna(median)):
        return ""
    return f"{_fmt(median, digits)}（{_fmt(low, digits)}–{_fmt(high, digits)}）"


def recall_latency_table(summary: pd.DataFrame) -> str:
    """表 4.1:High workload 上的 Recall–Latency。"""
    data = summary[summary["bucket"] == "high"].sort_values(
        by=["system", "L"], key=lambda s: s.map({"pipeann": 0, "gateann": 1}) if s.name == "system" else s
    )
    lines = [
        "| 系统 | L | Recall@10（%） | Mean Latency（μs） | QPS | Mean I/O（次/查询） |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, row in data.iterrows():
        system = "PipeANN-Filter" if row["system"] == "pipeann" else "GateANN"
        lines.append(
            f"| {system} | {int(row['L'])} | {_range(row['recall_percent_median'], row['recall_percent_min'], row['recall_percent_max'])} "
            f"| {_range(row['mean_latency_us_median'], row['mean_latency_us_min'], row['mean_latency_us_max'], 1)} "
            f"| {_range(row['qps_median'], row['qps_min'], row['qps_max'], 1)} "
            f"| {_range(row['mean_ios_median'], row['mean_ios_min'], row['mean_ios_max'])} |"
        )
    return "\n".join(lines)


def selectivity_table(summary: pd.DataFrame, internal: pd.DataFrame) -> str:
    """表 4.2:Selectivity–Performance(固定代表性 L)。"""
    reps = summary[
        ((summary["system"] == "pipeann") & (summary["L"] == 40))
        | ((summary["system"] == "gateann") & (summary["L"] == 320))
    ].sort_values(by=["system", "selectivity_median"])
    lines = [
        "| 系统 | Bucket | Selectivity 范围/中位数（%） | Recall@10（%） | Mean Latency（μs） | Mean I/O（次/查询） | 关键内部指标 |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for _, row in reps.iterrows():
        system = "PipeANN-Filter" if row["system"] == "pipeann" else "GateANN"
        selectivity = (
            f"{row['selectivity_min']:.3f}–{row['selectivity_max']:.3f} / {row['selectivity_median']:.3f}"
        )
        internal_row = internal[
            (internal["system"] == row["system"])
            & (internal["bucket"] == row["bucket"])
            & (internal["L"] == row["L"])
        ]
        if row["system"] == "pipeann":
            if internal_row.empty:
                detail = ""
            else:
                r = internal_row.iloc[0]
                detail = (
                    f"Pre/In/Post {int(r['pre_filter_queries'])}/{int(r['in_filter_queries'])}/"
                    f"{int(r['post_filter_queries'])}，假阳性 {_fmt(r['filter_false_positives'], 1)}"
                )
        else:
            if internal_row.empty:
                detail = ""
            else:
                r = internal_row.iloc[0]
                detail = (
                    f"Skips {_fmt(r['filter_skips'])}；Tunnel {_fmt(r['tunnel_time_us'], 0)} μs；"
                    f"I/O {_fmt(r['io_time_us'], 0)} μs；Process {_fmt(r['process_time_us'], 0)} μs"
                )
        lines.append(
            f"| {system} | {row['bucket'].capitalize()} | {selectivity} "
            f"| {_range(row['recall_percent_median'], row['recall_percent_min'], row['recall_percent_max'])} "
            f"| {_range(row['mean_latency_us_median'], row['mean_latency_us_min'], row['mean_latency_us_max'], 1)} "
            f"| {_range(row['mean_ios_median'], row['mean_ios_min'], row['mean_ios_max'])} "
            f"| {detail} |"
        )
    return "\n".join(lines)


def resources_table(resources: pd.DataFrame) -> str:
    """表 4.3:资源 Trade-off。"""
    lines = [
        "| 系统 | 索引大小（GiB） | 查询峰值 RSS（MiB） |",
        "|---|---:|---:|",
    ]
    for _, row in resources.iterrows():
        system = "PipeANN-Filter" if row["system"] == "pipeann" else "GateANN"
        index = (
            f"{row['index_size_gib']:.4g}"
            if not pd.isna(row["index_size_gib"]) and not isinstance(row["index_size_gib"], str)
            else str(row["index_size_gib"])
        )
        rss = _range(row["peak_rss_mib_median"], row["peak_rss_mib_min"], row["peak_rss_mib_max"], 1)
        lines.append(f"| {system} | {index} | {rss} |")
    return "\n".join(lines)


def all_tables(summary: pd.DataFrame, internal: pd.DataFrame, resources: pd.DataFrame) -> dict[str, str]:
    """生成全部报告表格,返回 {文件名, 内容}。"""
    return {
        "table_4_1_recall_latency.md": recall_latency_table(summary) + "\n",
        "table_4_2_selectivity.md": selectivity_table(summary, internal) + "\n",
        "table_4_3_resources.md": resources_table(resources) + "\n",
    }
