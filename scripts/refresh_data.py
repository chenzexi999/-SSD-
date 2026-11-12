#!/usr/bin/env python3
"""从课程聚合结果 CSV(30 行)重新生成 data/ 下的数据文件。

用法:
    python scripts/refresh_data.py course_runs/experiments/<id>/results.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ssd.cli import main  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python scripts/refresh_data.py <course results.csv>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(["refresh", "--results-csv", sys.argv[1]]))
