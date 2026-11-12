"""课程要求的两张核心图与补充内部指标图。

绘图约定(报告图 1 / 图 2 与《结果分析指南》一致):
- 点为三轮中位数,误差线为三轮最小到最大(非对称误差线);
- 横轴/纵轴均标明指标名称与单位;
- Recall 保持百分数单位,延迟使用 ``mean_latency_us``;
- Selectivity 图横轴使用 ``selectivity_median``,并用横向误差线标出桶内范围。

视觉规范(dataviz 校验过的默认调色板,light 模式):
- 分类色:蓝 #2a78d6(PipeANN-Filter)、橙 #eb6834(GateANN)、青 #1baf7a(第三序列);
- 青 #1baf7a 在浅色表面对比度 < 3:1,必须配直接数值标签(分解图已带);
- 细线 2px、点标记 ≥ 8px、网格弱化、文字不使用序列色。
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 视觉常量
# --------------------------------------------------------------------------- #

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"

#: 系统 -> 分类色槽位(顺序固定:PipeANN-Filter 恒为蓝,GateANN 恒为橙)
SYSTEM_COLORS = {"pipeann": "#2a78d6", "gateann": "#eb6834"}
SYSTEM_LABELS = {"pipeann": "PipeANN-Filter", "gateann": "GateANN"}

#: GateANN 时间分解的三个组成部分(第三序列青,需直接标签)
TIME_COMPONENT_COLORS = {
    "io_time_us": "#2a78d6",
    "tunnel_time_us": "#eb6834",
    "process_time_us": "#1baf7a",
}
TIME_COMPONENT_LABELS = {
    "io_time_us": "I/O time",
    "tunnel_time_us": "Tunnel time",
    "process_time_us": "Process time",
}

LINE_WIDTH = 2.0
MARKER_SIZE = 8.0
ERROR_CAP_SIZE = 3.0


# --------------------------------------------------------------------------- #
# 字体(跨平台 CJK 支持)
# --------------------------------------------------------------------------- #

_FONT_CANDIDATES = (
    # (font name, 字体文件路径或 None)
    ("SimHei", "C:/Windows/Fonts/simhei.ttf"),
    ("Microsoft YaHei", "C:/Windows/Fonts/msyh.ttc"),
    ("SimSun", "C:/Windows/Fonts/simsun.ttc"),
    ("Noto Sans CJK SC", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ("Noto Sans CJK SC", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
    ("WenQuanYi Zen Hei", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
)


def setup_fonts() -> list[str]:
    """注册可用的中文字体并应用到 rcParams;返回已注册的字体名列表。

    找不到 CJK 字体时仅告警(标签可能显示为方框),不中断绘图,
    以保证无中文字体的 CI 环境仍能运行。
    """
    from matplotlib import font_manager

    registered: list[str] = []
    for name, path in _FONT_CANDIDATES:
        if path and Path(path).exists():
            try:
                font_manager.fontManager.addfont(path)
                registered.append(name)
                break
            except Exception as exc:  # pragma: no cover - 取决于具体环境
                logger.debug("注册字体 %s 失败: %s", path, exc)
    if not registered:
        logger.warning("未找到 CJK 字体,图中文字可能显示为方框")

    families = list(dict.fromkeys(registered + ["DejaVu Sans"]))
    matplotlib.rcParams["font.sans-serif"] = families
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["axes.unicode_minus"] = False
    return registered


def apply_style() -> None:
    """统一图表样式:浅色表面、弱化网格、细线。"""
    matplotlib.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "axes.edgecolor": BASELINE,
            "axes.labelcolor": INK_SECONDARY,
            "axes.titlecolor": INK,
            "text.color": INK,
            "xtick.color": INK_MUTED,
            "ytick.color": INK_MUTED,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "legend.facecolor": SURFACE,
            "legend.edgecolor": GRID,
            "legend.framealpha": 1.0,
            "axes.linewidth": 1.0,
            "savefig.facecolor": SURFACE,
        }
    )


# --------------------------------------------------------------------------- #
# 绘图辅助
# --------------------------------------------------------------------------- #

def _asymmetric_errors(median: pd.Series, low: pd.Series, high: pd.Series) -> np.ndarray:
    """三轮范围 -> matplotlib 非对称误差线 (2, N)。"""
    return np.vstack(
        [(median - low).clip(lower=0).to_numpy(), (high - median).clip(lower=0).to_numpy()]
    )


def _annotate_L(ax, frame: pd.DataFrame, system: str, *, dy: float = 0.0) -> None:
    """在图 1 每个点旁直接标注 L(选择性直接标签,不逐点标数值)。"""
    for _, row in frame.iterrows():
        ax.annotate(
            f"L={int(row['L'])}",
            (row["mean_latency_us_median"], row["recall_percent_median"] + dy),
            ha="center",
            va="bottom",
            fontsize=9,
            color=INK_SECONDARY,
        )


def _style_axes(ax) -> None:
    ax.grid(True, axis="both", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


# --------------------------------------------------------------------------- #
# 图 1:Recall@10 – Mean Latency(High,三档 L)
# --------------------------------------------------------------------------- #

def fig_recall_latency(summary: pd.DataFrame) -> plt.Figure:
    """核心图 1:High workload 上 Recall@10 与 Query Phase 平均延迟。

    每套系统连接自己的三档 L,点为三轮中位数,误差线为三轮范围。
    """
    data = summary[summary["bucket"] == "high"].copy()
    if data.empty:
        raise ValueError("summary 中缺少 bucket=high 的数据")

    fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=200)
    for system, color in SYSTEM_COLORS.items():
        frame = data[data["system"] == system].sort_values("L")
        ax.errorbar(
            frame["mean_latency_us_median"],
            frame["recall_percent_median"],
            xerr=_asymmetric_errors(
                frame["mean_latency_us_median"],
                frame["mean_latency_us_min"],
                frame["mean_latency_us_max"],
            ),
            yerr=_asymmetric_errors(
                frame["recall_percent_median"],
                frame["recall_percent_min"],
                frame["recall_percent_max"],
            ),
            fmt="o-",
            linewidth=LINE_WIDTH,
            markersize=MARKER_SIZE,
            capsize=ERROR_CAP_SIZE,
            color=color,
            label=SYSTEM_LABELS[system],
            zorder=3,
        )
        _annotate_L(ax, frame, system, dy=1.1)

    _style_axes(ax)
    ax.set_xlabel("Mean Latency (μs,Query Phase)")
    ax.set_ylabel("Recall@10 (%)")
    ax.set_ylim(bottom=max(0.0, data["recall_percent_min"].min() - 6))
    ax.legend(loc="lower right", frameon=True)
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- #
# 图 2:Selectivity – Performance(固定代表性 L,三子图)
# --------------------------------------------------------------------------- #

def fig_selectivity(summary: pd.DataFrame) -> plt.Figure:
    """核心图 2:固定 PipeANN L=40、GateANN L=320,三档选择率下
    Recall@10、Mean Latency、Mean I/O 三个子图。

    横轴为选择率中位数(对数轴),横向误差线为桶内选择率范围,
    纵向误差线为三轮范围。
    """
    reps = summary[
        ((summary["system"] == "pipeann") & (summary["L"] == 40))
        | ((summary["system"] == "gateann") & (summary["L"] == 320))
    ].copy()
    if reps.empty:
        raise ValueError("summary 中缺少代表性 L 的配置")

    panels = (
        ("recall_percent", "Recall@10 (%)"),
        ("mean_latency_us", "Mean Latency (μs)"),
        ("mean_ios", "Mean I/O (次/查询)"),
    )
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 4.2), dpi=200, sharex=True)
    for ax, (metric, ylabel) in zip(axes, panels):
        for system, color in SYSTEM_COLORS.items():
            frame = reps[reps["system"] == system].sort_values("selectivity_median")
            x = frame["selectivity_median"]
            ax.errorbar(
                x,
                frame[f"{metric}_median"],
                xerr=_asymmetric_errors(
                    frame["selectivity_median"],
                    frame["selectivity_min"],
                    frame["selectivity_max"],
                ),
                yerr=_asymmetric_errors(
                    frame[f"{metric}_median"],
                    frame[f"{metric}_min"],
                    frame[f"{metric}_max"],
                ),
                fmt="o-",
                linewidth=LINE_WIDTH,
                markersize=MARKER_SIZE,
                capsize=ERROR_CAP_SIZE,
                color=color,
                label=SYSTEM_LABELS[system],
                zorder=3,
            )
            # 桶名直接标注(选择性标签,不标数值)
            for _, row in frame.iterrows():
                ax.annotate(
                    row["bucket"].capitalize(),
                    (row["selectivity_median"], row[f"{metric}_median"]),
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    color=INK_SECONDARY,
                    xytext=(0, 6),
                    textcoords="offset points",
                )
        _style_axes(ax)
        ax.set_xscale("log")
        ax.set_xlabel("Selectivity (%,中位数)")
        ax.set_ylabel(ylabel)

    axes[1].legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=2, frameon=True)
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.24)
    return fig


# --------------------------------------------------------------------------- #
# 补充图 3:GateANN 时间分解(High,随 L)
# --------------------------------------------------------------------------- #

def fig_gateann_time_decomposition(internal: pd.DataFrame) -> plt.Figure:
    """补充图:GateANN 在 High 上三档 L 的 I/O / Tunnel / Process 时间中位数。

    分组柱状图,每根柱直接标注数值(第三序列青色对比度 < 3:1,
    按视觉规范必须配直接标签)。
    """
    data = internal[
        (internal["system"] == "gateann") & (internal["bucket"] == "high")
    ].sort_values("L")
    if data.empty:
        raise ValueError("internal 中缺少 GateANN High 数据")

    components = ["io_time_us", "tunnel_time_us", "process_time_us"]
    x = np.arange(len(data))
    width = 0.26

    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=200)
    for offset, component in enumerate(components):
        values = pd.to_numeric(data[component], errors="coerce")
        bars = ax.bar(
            x + (offset - 1) * width,
            values,
            width=width,
            color=TIME_COMPONENT_COLORS[component],
            label=TIME_COMPONENT_LABELS[component],
            zorder=3,
        )
        for bar, value in zip(bars, values):
            if np.isfinite(value):
                ax.annotate(
                    f"{value:g}",
                    (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    ha="center",
                    va="bottom",
                    fontsize=8.5,
                    color=INK_SECONDARY,
                    xytext=(0, 2),
                    textcoords="offset points",
                )

    _style_axes(ax)
    ax.set_xticks(x)
    ax.set_xticklabels([f"L={int(v)}" for v in data["L"]])
    ax.set_xlabel("搜索预算 L(High workload)")
    ax.set_ylabel("时间中位数 (μs/查询)")
    ax.legend(loc="upper left", frameon=True)
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- #
# 补充图 4:内部行为指标(High,随 L)——小多图
# --------------------------------------------------------------------------- #

def fig_internal_behavior(summary: pd.DataFrame, internal: pd.DataFrame) -> plt.Figure:
    """补充图:两套系统的内部行为证据(High)。

    左:PipeANN-Filter 的过滤假阳性中位数(全部走 In-filter);
    右:GateANN 的 FilterSkips 中位数。
    单序列小多图,子图标题即序列名,无需图例。
    """
    high = summary[summary["bucket"] == "high"]
    internal_high = internal[internal["bucket"] == "high"]
    pipeann = internal_high[internal_high["system"] == "pipeann"].sort_values("L")
    gateann = internal_high[internal_high["system"] == "gateann"].sort_values("L")
    if pipeann.empty or gateann.empty:
        raise ValueError("缺少 High 内部指标数据")

    panels = (
        (pipeann, "filter_false_positives", "PipeANN-Filter:过滤假阳性中位数(High)"),
        (gateann, "filter_skips", "GateANN:FilterSkips(High)"),
    )
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.0), dpi=200)
    for ax, (frame, metric, title) in zip(axes, panels):
        if metric not in frame.columns:
            logger.warning("缺少指标 %s,跳过子图", metric)
            continue
        color = (
            SYSTEM_COLORS[frame["system"].iloc[0]]
            if frame["system"].iloc[0] in SYSTEM_COLORS
            else "#2a78d6"
        )
        values = pd.to_numeric(frame[metric], errors="coerce")
        ax.plot(
            frame["L"], values, "o-",
            linewidth=LINE_WIDTH, markersize=MARKER_SIZE,
            color=color, zorder=3,
        )
        for x_value, y_value in zip(frame["L"], values):
            if np.isfinite(y_value):
                ax.annotate(
                    f"{y_value:g}",
                    (x_value, y_value),
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    color=INK_SECONDARY,
                    xytext=(0, 5),
                    textcoords="offset points",
                )
        _style_axes(ax)
        ax.set_title(title, fontsize=10.5)
        ax.set_xlabel("搜索预算 L")
        ax.set_ylabel("中位数")

    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- #
# 生成全部图
# --------------------------------------------------------------------------- #

def make_all_figures(
    summary: pd.DataFrame,
    internal: pd.DataFrame,
    output_dir: str | Path,
    *,
    formats: tuple[str, ...] = ("pdf", "png"),
) -> list[Path]:
    """生成全部图,返回输出文件路径列表。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    setup_fonts()
    apply_style()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        figures = {
            "fig1_recall_latency": fig_recall_latency(summary),
            "fig2_selectivity": fig_selectivity(summary),
            "fig3_gateann_time_decomposition": fig_gateann_time_decomposition(internal),
            "fig4_internal_behavior": fig_internal_behavior(summary, internal),
        }
    written: list[Path] = []
    for name, fig in figures.items():
        for fmt in formats:
            path = output_dir / f"{name}.{fmt}"
            fig.savefig(path, format=fmt, bbox_inches="tight")
            written.append(path)
        plt.close(fig)
    logger.info("已生成 %d 个图文件", len(written))
    return written
