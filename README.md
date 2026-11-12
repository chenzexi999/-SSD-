# fvs-lab-analysis

《基于 SSD 的过滤向量检索系统性能测试与设计比较》课程实验的**结果分析与绘图代码库**。

实验在统一的 YFCC 真实标签工作负载(100 万条 192 维 uint8 向量,L2)上,对
**PipeANN-Filter**(推测式过滤 + 动态路由)与 **GateANN**(Pre-I/O Filtering + Graph Tunneling)
两套 SSD 驻留过滤向量检索系统进行 3 轮独立重复测试,测量 Recall@10、查询时延、
逻辑 I/O 与峰值内存,并据此完成设计比较与优化方向设计。

- 实验报告按课程要求单独提交 PDF,不包含在本仓库;
- 正式实验 experiment-id:`20260930-072449`(3 轮 × 10 配置 = 30 行原始结果)
- 课程仓库:<https://gitee.com/wei-fangyu/fvs-course-lab>(数据集、预构建索引、
  固定源码与运行脚本均来自课程,本仓库不含这些内容)

## 仓库结构

```text
fvs-lab-analysis/
├── data/                  # 聚合结果(唯一绘图输入),含字段与来源说明
│   ├── aggregated.csv         # 10 个配置:三轮中位数/最小/最大
│   ├── internal_metrics.csv   # 两套系统的专有内部指标
│   └── resources.csv          # 索引大小与查询峰值 RSS
├── figures/               # 生成的图(pdf/png,本地产物,不入库)
├── tables/                # 生成的报告表格(markdown,本地产物,不入库)
├── scripts/
│   ├── make_figures.py        # 生成全部图与表格
│   └── refresh_data.py        # 从课程 30 行 results.csv 重新聚合 data/
├── src/fvslab/            # Python 包
│   ├── schema.py              # 课程结果 CSV 的字段定义与校验
│   ├── aggregate.py           # 三轮聚合(中位数/最小/最大)
│   ├── figures.py             # 核心图 1/2 与补充图 3/4
│   ├── tables.py              # 报告表格输出
│   ├── validate.py            # 验证计划实验执行器(GateANN Low L 扫描)
│   └── cli.py                 # 命令行入口
├── tests/                 # 单元测试与绘图冒烟测试
└── .github/workflows/ci.yml   # GitHub Actions:pytest
```

## 快速开始

```bash
pip install -e ".[dev]"

# 从 data/ 生成全部图(pdf + png)与报告表格
fvslab figures --tables

# 运行测试
pytest
```

需要 Python ≥ 3.9。绘图自动探测中文字体(Windows: SimHei/微软雅黑;
Linux: Noto CJK/WenQuanYi),找不到时给出告警但仍可运行。

## 实验与复现

实验参数由课程统一固定(报告第 1 节):threads=1、beamwidth=8、K=10、mem_L=0、
缓存预算=0、GateANN FullAdj neighbors=32、Linux AIO。两套系统的搜索预算 L 由
课程分别校准(PipeANN-Filter 20/40/80,GateANN 160/320/640),**L 数值不可直接
横向比较**,比较时以 Recall 相近的运行点为准。本仓库未修改课程源码与任何统一参数。

| 系统 | 固定源码 Commit | 查询峰值 RSS 中位数 | 索引大小 |
| --- | --- | ---: | ---: |
| PipeANN-Filter | `2ec84fe20c37dc3cc236b66f7eba31c0cc80bf1e` | 138.5 MiB | 8.43 GiB |
| GateANN | `71e87cbf0e25c0400c0109dd25a64a7c4dccc9dd` | 408.4 MiB | 486 MiB |

### 数据流

```text
course_runs/experiments/<id>/results.csv   (课程脚本聚合,30 行)
        │  fvslab refresh --results-csv ...
        ▼
data/aggregated.csv + internal_metrics.csv + resources.csv
        │  fvslab figures --tables
        ▼
figures/*.pdf|png + tables/*.md
```

`data/` 当前内容转录自《实验报告》4.1–4.3 表格;实验机恢复后运行
`refresh_data.py` 即可从原始 30 行 CSV 重新聚合,保证数据与绘图完全一致。
聚合规则与字段语义见 `data/README.md` 与 `src/fvslab/schema.py`。

## 核心结果(详见报告)

- **High workload**:预算增大时两套系统的 Recall、延迟与逻辑 I/O 同步上升。
  Recall ≈ 93% 的运行点上,GateANN(L=320)延迟 1447.2 μs、逻辑 I/O 46.75 次/查询;
  PipeANN-Filter(L=40)为 1830.2 μs、141.1 次。
- **Selectivity 敏感性**:过滤加强时 PipeANN-Filter 自动切到 Pre-filter
  (Low 上 Recall 98.60%、延迟 660.3 μs);GateANN 不换路径,Low 上逻辑 I/O 仅
  4.38 次但 Recall 降至 34.30%,时间主要花在 Graph Tunneling(410 μs)。
- **瓶颈判断**:GateANN 强过滤下的短板是过滤后图的可达性与搜索预算,而不是
  读盘次数(依据 I/O 时间 16 μs 与 Tunnel 时间 410 μs 的对照)。

## 优化方向与验证计划

报告提出的优化:按选择率/FilterSkips 动态调整 GateANN 搜索预算,而非全桶固定
L=320。本仓库提供验证计划执行器(仅 Linux 实验环境,需课程数据集与索引):

```bash
fvslab validate-plan \
  --repo ~/fvs-course-lab/systems/GateANN-public \
  --dataset-root ~/fvs-course-lab/datasets/yfcc_course_v1 \
  --run-root ~/fvs-course-lab/course_runs \
  --L 640 1280 2560 --repeats 3
```

对照组为正式实验 GateANN Low L=320;自变量仅 L;支持/否定判据见报告第 5 节
Validation Plan 与 `src/fvslab/validate.py` 文档字符串。

## 结果边界(公平性声明)

- 实验在 WSL2 虚拟磁盘上完成,页缓存偏热;绝对延迟与 QPS 不代表原生 SSD,
  只用于同一环境内的相对趋势;
- `mean_ios` 是系统内部逻辑 I/O,两套系统的页与统计方式不同,不能等同物理 I/O;
- 三档 Bucket 使用不同真实标签,桶间差异不能全部归因于 Selectivity 单变量。

## License

[MIT](LICENSE)。第三方系统源码(PipeANN-Filter、GateANN)与课程数据集、脚本
均不属于本仓库,版权归其原作者与课程所有。
