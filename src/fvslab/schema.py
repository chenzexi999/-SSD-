"""课程统一结果 CSV 的字段定义与校验。

字段语义与单位以《结果分析指南》为准,此处为程序化描述。
关键约定:
- 某系统不提供的专有字段保持**空白**,空白表示"不适用",不是数值 0;
- ``recall_percent`` 已经是百分数,不得再次乘 100;
- 延迟使用 Query Phase 的 ``mean_latency_us``,不使用 ``elapsed_seconds``;
- ``mean_ios`` 是系统内部逻辑 I/O,不是物理 I/O。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

import pandas as pd

# --------------------------------------------------------------------------- #
# 字段定义
# --------------------------------------------------------------------------- #

SYSTEMS = ("pipeann", "gateann")
BUCKETS = ("low", "medium", "high")
TIER_FORMAL = "formal_1000000"
EXPECTED_QUERIES = 200

#: 实验身份与控制变量(不可聚合)
IDENTITY_FIELDS = (
    "repeat",
    "run_id",
    "system",
    "tier",
    "bucket",
    "queries",
    "L",
    "k",
    "threads",
    "beamwidth",
    "system_commit",
    "raw_log",
)

#: 数值字段:聚合时取中位数/最小/最大
METRIC_FIELDS = (
    "recall_percent",      # % ,Recall@10,已是百分数
    "mean_latency_us",     # μs,Query Phase 平均延迟
    "qps",                 # query/s
    "mean_ios",            # 次/查询,系统内部逻辑 I/O
    "p999_latency_us",     # μs,仅原系统提供时才有值
    "elapsed_seconds",     # s,含加载与初始化,仅诊断
    "peak_rss_kb",         # KiB,查询子进程峰值 RSS
    "index_bytes",         # byte,索引文件总大小
)

#: PipeANN 专有内部指标(聚合时取中位数)
PIPEANN_FIELDS = (
    "pre_filter_queries",   # 路由到 Pre-filter 的查询数
    "in_filter_queries",    # 路由到 In-filter 的查询数
    "post_filter_queries",  # 路由到 Post-filter 的查询数
    "filter_false_positives",  # 过滤假阳性
)

#: GateANN 专有内部指标(聚合时取中位数)
GATEANN_FIELDS = (
    "filter_skips",        # 次/查询,I/O 前跳过的候选
    "io_time_us",          # μs/查询,I/O 时间
    "tunnel_time_us",      # μs/查询,Graph Tunneling 时间
    "process_time_us",     # μs/查询,其他候选处理时间
)

INTERNAL_FIELDS = PIPEANN_FIELDS + GATEANN_FIELDS

#: Selectivity 描述字段(同一 bucket 内恒定,不做跨轮聚合)
SELECTIVITY_FIELDS = ("selectivity_min", "selectivity_median", "selectivity_max")

ALL_FIELDS = IDENTITY_FIELDS + SELECTIVITY_FIELDS + METRIC_FIELDS + INTERNAL_FIELDS

#: 每个 system + bucket + L 组应有的重复轮数
EXPECTED_REPEATS = 3

#: 默认 10 个配置(system, bucket, L)
DEFAULT_CONFIGS = (
    ("pipeann", "high", 20),
    ("pipeann", "high", 40),
    ("pipeann", "high", 80),
    ("pipeann", "medium", 40),
    ("pipeann", "low", 40),
    ("gateann", "high", 160),
    ("gateann", "high", 320),
    ("gateann", "high", 640),
    ("gateann", "medium", 320),
    ("gateann", "low", 320),
)


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #

@dataclass
class SchemaError:
    """一条校验错误:定位到具体行/列,便于人工回溯原始 run.log。"""

    message: str
    rows: list[int] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - 展示用
        loc = f" (rows={self.rows[:5]})" if self.rows else ""
        return f"{self.message}{loc}"


def _numeric_or_nan(value: object) -> float:
    """把 CSV 单元格转成 float;空白视为 NaN(区别于 0)。"""
    if value is None:
        return math.nan
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return math.nan
    return float(value)


def validate(raw: pd.DataFrame, *, expected_configs: Iterable[tuple[str, str, int]] = DEFAULT_CONFIGS) -> list[SchemaError]:
    """校验课程聚合结果 CSV(30 行)。

    返回错误列表;空列表表示通过。错误信息只描述问题本身,
    修正数据应回到 ``course_runs/results/`` 的原始 run.log,不修改 CSV。
    """
    errors: list[SchemaError] = []

    def rows_of(mask: pd.Series) -> list[int]:
        return mask.index[mask].astype(int).tolist()

    if raw.empty:
        return [SchemaError("空结果文件")]

    # 1. 必需的列
    missing = [c for c in ALL_FIELDS if c not in raw.columns]
    if missing:
        errors.append(SchemaError(f"缺少列: {missing}"))
        return errors

    # 2. 系统与数据层级
    for col, allowed in (("system", SYSTEMS), ("bucket", BUCKETS)):
        bad = ~raw[col].isin(allowed)
        if bad.any():
            errors.append(SchemaError(f"{col} 出现非法取值", rows_of(bad)))
    bad_tier = raw["tier"] != TIER_FORMAL
    if bad_tier.any():
        errors.append(SchemaError(f"tier 应为 {TIER_FORMAL}", rows_of(bad_tier)))

    # 3. 查询数与关键数值范围
    bad_q = raw["queries"] != EXPECTED_QUERIES
    if bad_q.any():
        errors.append(SchemaError(f"queries 应为 {EXPECTED_QUERIES}", rows_of(bad_q)))
    recall = pd.to_numeric(raw["recall_percent"], errors="coerce")
    bad_recall = recall.isna() | (recall < 0) | (recall > 100)
    if bad_recall.any():
        errors.append(SchemaError("recall_percent 缺失或超出 [0, 100]", rows_of(bad_recall)))

    # 4. 分组与重复:每个配置恰有 EXPECTED_REPEATS 行
    grouped = raw.groupby(["system", "bucket", "L"], dropna=False)
    bad_groups = [
        f"{sys}/{bucket}/L={L}: {len(g)} 行"
        for (sys, bucket, L), g in grouped
        if len(g) != EXPECTED_REPEATS
    ]
    if bad_groups:
        errors.append(SchemaError("分组重复数不正确: " + "; ".join(bad_groups)))
    seen = set(zip(raw["system"], raw["bucket"], raw["L"]))
    expected = set(expected_configs)
    if seen - expected:
        errors.append(SchemaError(f"出现非预期配置: {sorted(seen - expected)}"))
    if expected - seen:
        errors.append(SchemaError(f"缺少配置: {sorted(expected - seen)}"))

    # 5. 空字段与零值区分:数值字段空白记为 NaN,不静默填 0
    for col in METRIC_FIELDS + INTERNAL_FIELDS:
        if col not in raw.columns:
            continue
        for idx, value in raw[col].items():
            if isinstance(value, str) and value.strip() == "":
                raw.loc[idx, col] = math.nan

    return errors


def load(path: str, *, expected_configs: Iterable[tuple[str, str, int]] = DEFAULT_CONFIGS) -> pd.DataFrame:
    """读取课程聚合结果 CSV 并做数值化与校验。

    Raises:
        ValueError: 校验失败(信息汇总于异常消息)。
    """
    raw = pd.read_csv(path)
    errors = validate(raw, expected_configs=expected_configs)
    if errors:
        raise ValueError("结果校验失败:\n" + "\n".join(f"  - {e}" for e in errors))
    for col in METRIC_FIELDS + INTERNAL_FIELDS:
        if col in raw.columns:
            raw[col] = raw[col].map(_numeric_or_nan)
    return raw
