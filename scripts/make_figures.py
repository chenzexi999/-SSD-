#!/usr/bin/env python3
"""生成全部图与报告表格(等价于 `fvslab figures --tables`)。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fvslab.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["figures", "--tables"]))
