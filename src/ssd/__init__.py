"""ssd: SSD 过滤向量检索实验的分析与绘图工具包。

包含:
- schema:     课程结果 CSV 的字段定义与校验;
- aggregate:  按 system + bucket + L 聚合三轮结果(中位数 / 最小 / 最大);
- figures:    课程要求的两张核心图与补充内部指标图;
- tables:     报告表格的 Markdown 输出;
- validate:   报告"优化方向"中验证计划的实验执行器(Linux 实验环境使用);
- cli:        命令行入口。
"""

__version__ = "1.0.0"
