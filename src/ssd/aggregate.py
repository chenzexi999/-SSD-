"""三轮结果聚合:按 system + bucket + L 分组计算中位数 / 最小 / 最大。

规则(以《结果分析指南》为准):
- 不得对多轮 QPS、I/O 或查询数求和;
- 不得只取最快一轮;
- 不得把 High 的三档 L 合并;
- ``index_bytes`` 在同一系统的多行中重复,先确认一致再报一个值;
- 空白字段保持 NaN,不当作 0。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .schema import GATEANN_FIELDS, METRIC_FIELDS, PIPEANN_FIELDS, SELECTIVITY_FIELDS

KEY_FIELDS = ("system", "bucket", "L")

#: 汇总表的核心字段(报告表格与绘图输入)
SUMMARY_FIELDS = (
    "selectivity_min",
    "selectivity_median",
    "selectivity_max",
    "recall_percent",
    "mean_latency_us",
    "qps",
    "mean_ios",
    "peak_rss_kb",
    "index_bytes",
)


@dataclass
class AggregatedResult:
    """聚合产物:汇总表、内部指标表、资源表。"""

    summary: pd.DataFrame      # 10 行,system/bucket/L + 各指标 median/min/max
    internal: pd.DataFrame     # 10 行,两套系统的专有内部指标(中位数)
    resources: pd.DataFrame    # 2 行,index_size_gib 与 peak_rss 中位数/范围

    def to_csv(self, directory: str) -> list[str]:
        """写出三个 CSV,返回写入路径。"""
        import os

        paths = {
            "aggregated.csv": self.summary,
            "internal_metrics.csv": self.internal,
            "resources.csv": self.resources,
        }
        written = []
        for name, frame in paths.items():
            path = os.path.join(directory, name)
            frame.to_csv(path, index=False)
            written.append(path)
        return written


def _median_min_max(group: pd.DataFrame, column: str) -> pd.Series:
    """对一组(3 行)数值取中位数/最小/最大;全为 NaN 时返回全 NaN。"""
    values = pd.to_numeric(group[column], errors="coerce")
    if values.isna().all():
        return pd.Series({"median": float("nan"), "min": float("nan"), "max": float("nan")})
    return pd.Series(
        {"median": values.median(), "min": values.min(), "max": values.max()}
    )


def _build_summary(raw: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (system, bucket, L), group in raw.groupby(list(KEY_FIELDS)):
        row: dict[str, object] = {"system": system, "bucket": bucket, "L": L}
        for field in SELECTIVITY_FIELDS:
            values = pd.to_numeric(group[field], errors="coerce")
            row[field] = values.median() if values.notna().any() else float("nan")
        for field in SUMMARY_FIELDS:
            if field in SELECTIVITY_FIELDS or field not in group.columns:
                continue
            stats = _median_min_max(group, field)
            base = field.removesuffix("_kb").removesuffix("_bytes")
            prefix = "peak_rss_mib" if field == "peak_rss_kb" else "index_size_gib" if field == "index_bytes" else base
            row[f"{prefix}_median"] = stats["median"]
            row[f"{prefix}_min"] = stats["min"]
            row[f"{prefix}_max"] = stats["max"]
        rows.append(row)
    summary = pd.DataFrame(rows)
    # 课程 CSV 中 Selectivity 以比例存储(0.545% -> 0.00545),统一转为百分数
    for field in SELECTIVITY_FIELDS:
        if field in summary.columns:
            summary[field] = summary[field] * 100.0
    # 统一单位换算
    if "peak_rss_mib_median" in summary.columns:
        for part in ("median", "min", "max"):
            summary[f"peak_rss_mib_{part}"] = summary[f"peak_rss_mib_{part}"] / 1024.0
    if "index_size_gib_median" in summary.columns:
        for part in ("median", "min", "max"):
            summary[f"index_size_gib_{part}"] = summary[f"index_size_gib_{part}"] / (1024.0 ** 3)
    order = {system: i for i, system in enumerate(("pipeann", "gateann"))}
    order_b = {bucket: i for i, bucket in enumerate(("low", "medium", "high"))}
    summary = summary.sort_values(
        by=["system", "bucket", "L"],
        key=lambda s: s.map(order) if s.name == "system" else s.map(order_b) if s.name == "bucket" else s,
        kind="stable",
    ).reset_index(drop=True)
    return summary


def _build_internal(raw: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (system, bucket, L), group in raw.groupby(list(KEY_FIELDS)):
        row: dict[str, object] = {"system": system, "bucket": bucket, "L": L}
        fields = PIPEANN_FIELDS if system == "pipeann" else GATEANN_FIELDS
        for field in fields:
            if field not in group.columns:
                row[field] = float("nan")
                continue
            values = pd.to_numeric(group[field], errors="coerce")
            row[field] = values.median() if values.notna().any() else float("nan")
        rows.append(row)
    internal = pd.DataFrame(rows)
    internal = internal.sort_values(by=["system", "bucket", "L"]).reset_index(drop=True)
    return internal


def _build_resources(raw: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for system, group in raw.groupby("system"):
        # index_bytes 在同一系统多行中应一致;不一致时给出范围而非单一值
        index_values = pd.to_numeric(group["index_bytes"], errors="coerce")
        if index_values.notna().any():
            idx_min, idx_max = index_values.min(), index_values.max()
            if idx_min != idx_max:
                index_gib = f"{idx_min / 1024**3:.4f}–{idx_max / 1024**3:.4f}"
            else:
                index_gib = idx_min / 1024 ** 3
        else:
            index_gib = float("nan")
        rss = _median_min_max(group, "peak_rss_kb")
        rows.append(
            {
                "system": system,
                "index_size_gib": index_gib,
                "peak_rss_mib_median": rss["median"] / 1024.0,
                "peak_rss_mib_min": rss["min"] / 1024.0,
                "peak_rss_mib_max": rss["max"] / 1024.0,
            }
        )
    return pd.DataFrame(rows)


def aggregate(raw: pd.DataFrame) -> AggregatedResult:
    """把课程聚合结果(30 行)汇总为 10 个配置的中位数与范围。

    Args:
        raw: 已经过 :func:`ssd.schema.load` 校验与数值化的 DataFrame。

    Returns:
        AggregatedResult(summary, internal, resources)。
    """
    return AggregatedResult(
        summary=_build_summary(raw),
        internal=_build_internal(raw),
        resources=_build_resources(raw),
    )
