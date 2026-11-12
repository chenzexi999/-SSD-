# data/ 数据说明

本目录存放**正式实验的聚合结果**,是绘图与表格生成的唯一输入。

## 文件与字段

### aggregated.csv —— 10 个配置的汇总表(23 列指标)

每行对应一个 `system + bucket + L` 配置,值为三轮结果的
**中位数 / 最小值 / 最大值**(与报告表格的写法一致):

| 字段组 | 字段 | 单位 |
| --- | --- | --- |
| 分组键 | `system`, `bucket`, `L` | pipeann/gateann;low/medium/high |
| Selectivity | `selectivity_min/_median/_max` | % |
| 性能 | `recall_percent_*` | %,Recall@10,已是百分数 |
| 性能 | `mean_latency_us_*` | μs,Query Phase 延迟 |
| 性能 | `qps_*` | query/s;非 High 配置未在报告中列出,留空 |
| 性能 | `mean_ios_*` | 次/查询,系统内部逻辑 I/O |
| 资源 | `peak_rss_mib_*` | MiB,查询进程峰值 RSS |
| 资源 | `index_size_gib_*` | GiB,预构建索引大小 |

### internal_metrics.csv —— 两套系统的专有内部指标(中位数)

- PipeANN:`pre/in/post_filter_queries`、`filter_false_positives`
- GateANN:`filter_skips`、`io_time_us`、`tunnel_time_us`、`process_time_us`
- 某系统不提供的字段**留空**(不适用),不是 0。

### resources.csv —— 索引大小与查询内存

`index_size_gib` 与 `peak_rss_mib_*` 按系统一行。

## 数据来源与可信度

- 当前文件内容转录自《实验报告》4.1 / 4.2 / 4.3 三张表
  (experiment-id `20260930-072449`,三轮中位数与范围)。
- 原始结果保留在实验机 `course_runs/experiments/20260930-072449/results.csv`
  (30 行,课程成绩公布前请勿删除)。
- 当原始 CSV 可访问时,用以下命令**重新聚合**并覆盖本目录,
  保证数据与绘图完全一致:

  ```bash
  ssd refresh --results-csv course_runs/experiments/20260930-072449/results.csv
  ```

  聚合规则:按 `system + bucket + L` 分组取中位数/最小/最大;
  不对多轮 QPS/I/O 求和;空白字段保持空,不填 0。
