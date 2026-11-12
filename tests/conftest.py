"""共享测试夹具:构造课程格式的 30 行聚合结果。

三轮取值围绕基准值做 ±5% 对称扰动,使聚合中位数恰等于基准值,
便于对聚合函数做确定性断言。
"""

from __future__ import annotations

import pandas as pd
import pytest

from fvslab.schema import ALL_FIELDS

#: 10 个配置的基准值(system, bucket, L, recall, latency_us, qps, mean_ios)
BASELINE = [
    ("pipeann", "high", 20, 81.7, 1445.8, 687.1, 100.0),
    ("pipeann", "high", 40, 92.7, 1830.2, 543.5, 141.1),
    ("pipeann", "high", 80, 97.3, 2515.9, 395.6, 229.2),
    ("pipeann", "medium", 40, 91.6, 3071.0, 325.6, 165.3),
    ("pipeann", "low", 40, 98.6, 660.3, 1514.4, 80.0),
    ("gateann", "high", 160, 81.3, 916.6, 1091.0, 24.66),
    ("gateann", "high", 320, 93.2, 1447.2, 691.0, 46.75),
    ("gateann", "high", 640, 98.65, 2570.7, 389.0, 88.94),
    ("gateann", "medium", 320, 72.05, 908.3, 1101.1, 16.75),
    ("gateann", "low", 320, 34.3, 676.6, 1478.0, 4.38),
]

#: 三轮相对扰动(中位数不变)
PERTURB = (-0.05, 0.0, +0.05)


def make_raw_results() -> pd.DataFrame:
    """生成 30 行课程格式结果:每配置 3 轮,数值按 PERTURB 对称扰动。"""
    rows = []
    for repeat, factor in enumerate(PERTURB, start=1):
        for system, bucket, L, recall, latency, qps, ios in BASELINE:
            row: dict[str, object] = {field: "" for field in ALL_FIELDS}
            row.update(
                {
                    "repeat": repeat,
                    "run_id": f"test-{system}-{bucket}-{L}-r{repeat}",
                    "system": system,
                    "tier": "formal_1000000",
                    "bucket": bucket,
                    "queries": 200,
                    "L": L,
                    "k": 10,
                    "threads": 1,
                    "beamwidth": 8,
                    "system_commit": "0" * 40,
                    "raw_log": "",
                    "selectivity_min": {"low": 0.250, "medium": 1.765, "high": 7.074}[bucket],
                    "selectivity_median": {"low": 0.545, "medium": 2.958, "high": 12.323}[bucket],
                    "selectivity_max": {"low": 0.851, "medium": 4.995, "high": 17.089}[bucket],
                    "recall_percent": round(recall * (1 + factor * 0.1), 4),
                    "mean_latency_us": round(latency * (1 + factor), 2),
                    "qps": round(qps * (1 - factor), 2),
                    "mean_ios": round(ios * (1 + factor), 4),
                    "peak_rss_kb": round((138.5 if system == "pipeann" else 408.4) * 1024 * (1 + factor), 1),
                    "index_bytes": int(8.43 * 1024 ** 3 if system == "pipeann" else 486 * 1024 ** 2),
                }
            )
            if system == "pipeann":
                if bucket == "low":
                    row.update(
                        {
                            "pre_filter_queries": 200,
                            "in_filter_queries": 0,
                            "post_filter_queries": 0,
                            "filter_false_positives": 0.0,
                        }
                    )
                else:
                    row.update(
                        {
                            "pre_filter_queries": 0,
                            "in_filter_queries": 200,
                            "post_filter_queries": 0,
                            "filter_false_positives": round((8.6 + 3.2 * (L // 20 - 1)) * (1 + factor * 0.05), 2),
                        }
                    )
            else:
                row.update(
                    {
                        "filter_skips": round((24.66 * L / 160 + 118.5) * (1 + factor * 0.05), 2),
                        "io_time_us": round(100 * (1 + factor), 0),
                        "tunnel_time_us": round((200 + L * 0.6) * (1 + factor), 0),
                        "process_time_us": round((150 + L * 0.5) * (1 + factor), 0),
                    }
                )
            rows.append(row)
    return pd.DataFrame(rows)


@pytest.fixture
def raw_results() -> pd.DataFrame:
    return make_raw_results()


@pytest.fixture
def aggregated_csv(tmp_path) -> str:
    """写出聚合好的 10 行汇总表(与 data/aggregated.csv 同构)。"""
    from fvslab.aggregate import aggregate

    path = tmp_path / "results.csv"
    make_raw_results().to_csv(path, index=False)
    result = aggregate(make_raw_results())
    out_dir = tmp_path / "data"
    out_dir.mkdir()
    result.to_csv(str(out_dir))
    return str(out_dir)
