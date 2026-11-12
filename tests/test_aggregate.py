"""聚合逻辑的单元测试:中位数/范围、内部指标与资源换算。"""

import pandas as pd
import pytest

from ssd.aggregate import aggregate
from conftest import BASELINE, make_raw_results


def test_summary_has_10_configs(raw_results):
    result = aggregate(raw_results)
    assert len(result.summary) == 10


def test_median_matches_baseline(raw_results):
    """三轮对称扰动下,聚合中位数应等于基准值。"""
    result = aggregate(raw_results)
    by_key = {
        (row["system"], row["bucket"], row["L"]): row
        for _, row in result.summary.iterrows()
    }
    for system, bucket, L, recall, latency, qps, ios in BASELINE:
        row = by_key[(system, bucket, L)]
        assert row["recall_percent_median"] == pytest.approx(recall, abs=1e-9)
        assert row["mean_latency_us_median"] == pytest.approx(latency, abs=1e-6)
        assert row["qps_median"] == pytest.approx(qps, abs=1e-6)
        assert row["mean_ios_median"] == pytest.approx(ios, abs=1e-9)


def test_range_is_min_to_max(raw_results):
    result = aggregate(raw_results)
    row = result.summary.iloc[0]
    assert row["mean_latency_us_min"] < row["mean_latency_us_median"] < row["mean_latency_us_max"]


def test_internal_fields_split_by_system(raw_results):
    result = aggregate(raw_results)
    internal = result.internal
    pipeann = internal[internal["system"] == "pipeann"].iloc[0]
    gateann = internal[internal["system"] == "gateann"].iloc[0]
    assert pipeann["pre_filter_queries"] == 200 or pipeann["in_filter_queries"] == 200
    assert pd.notna(gateann["filter_skips"])
    # 跨系统字段保持空白(NaN),不互相污染
    assert pd.isna(pipeann["filter_skips"])
    assert pd.isna(gateann["filter_false_positives"])


def test_resources_unit_conversion(raw_results):
    result = aggregate(raw_results)
    pipeann = result.resources[result.resources["system"] == "pipeann"].iloc[0]
    gateann = result.resources[result.resources["system"] == "gateann"].iloc[0]
    assert pipeann["index_size_gib"] == pytest.approx(8.43)
    assert gateann["index_size_gib"] == pytest.approx(486 / 1024, abs=1e-4)
    assert pipeann["peak_rss_mib_median"] == pytest.approx(138.5, abs=1e-6)


def test_aggregate_output_csv_columns(raw_results, tmp_path):
    result = aggregate(raw_results)
    paths = result.to_csv(str(tmp_path))
    assert len(paths) == 3
    summary = pd.read_csv(tmp_path / "aggregated.csv")
    for col in (
        "system", "bucket", "L", "selectivity_median",
        "recall_percent_median", "mean_latency_us_median",
        "mean_ios_median", "index_size_gib_median",
    ):
        assert col in summary.columns
