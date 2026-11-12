"""绘图冒烟测试:四张图均可从 data/ 生成且文件非空。

使用 Agg 后端,不依赖显示器;字体回退保证无 CJK 字体环境也能运行。
"""

import matplotlib

matplotlib.use("Agg")

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from ssd.figures import (  # noqa: E402
    fig_gateann_time_decomposition,
    fig_internal_behavior,
    fig_recall_latency,
    fig_selectivity,
    make_all_figures,
)


@pytest.fixture
def summary() -> pd.DataFrame:
    return pd.read_csv("data/aggregated.csv")


@pytest.fixture
def internal() -> pd.DataFrame:
    return pd.read_csv("data/internal_metrics.csv")


def test_fig1_recall_latency(summary):
    fig = fig_recall_latency(summary)
    ax = fig.axes[0]
    assert ax.get_xlabel()  # 轴须标明指标与单位
    assert ax.get_ylabel()
    # 两套系统各一条主折线(误差线帽线不计入)
    legend_labels = ax.get_legend_handles_labels()[1]
    assert sum(x in ("PipeANN-Filter", "GateANN") for x in legend_labels) == 2


def test_fig2_selectivity(summary):
    fig = fig_selectivity(summary)
    assert len(fig.axes) == 3


def test_fig3_gateann_decomposition(internal):
    fig = fig_gateann_time_decomposition(internal)
    ax = fig.axes[0]
    assert len(ax.patches) == 9  # 3 组件 x 3 档 L


def test_fig4_internal_behavior(summary, internal):
    fig = fig_internal_behavior(summary, internal)
    assert len(fig.axes) == 2


def test_make_all_figures_writes_files(summary, internal, tmp_path):
    paths = make_all_figures(summary, internal, tmp_path, formats=("png",))
    assert len(paths) == 4
    for path in paths:
        assert path.is_file()
        assert path.stat().st_size > 1000  # 非空图像


def test_figures_missing_data_raises(summary):
    empty = summary[summary["bucket"] == "low"]  # 无 high -> 图 1 应报错
    with pytest.raises(ValueError):
        fig_recall_latency(empty)
