"""schema.load / validate 的单元测试。"""

import math

import pandas as pd
import pytest

from ssd.schema import load, validate
from conftest import make_raw_results


def test_validate_accepts_well_formed_results(raw_results):
    assert validate(raw_results) == []


def test_validate_rejects_missing_column():
    raw = make_raw_results().drop(columns=["recall_percent"])
    errors = validate(raw)
    assert any("缺少列" in str(e) for e in errors)


def test_validate_rejects_wrong_queries(raw_results):
    raw = raw_results.copy()
    raw.loc[0, "queries"] = 199
    errors = validate(raw)
    assert any("queries" in str(e) for e in errors)


def test_validate_rejects_short_group(raw_results):
    raw = raw_results.drop(index=0).reset_index(drop=True)
    errors = validate(raw)
    assert any("分组重复数" in str(e) for e in errors)


def test_validate_rejects_extra_config(raw_results):
    extra = raw_results.iloc[[0]].copy()
    extra["system"] = "pipeann"
    extra["bucket"] = "low"
    extra["L"] = 999
    raw = pd.concat([raw_results, extra], ignore_index=True)
    errors = validate(raw)
    assert any("非预期配置" in str(e) for e in errors)


def test_blank_fields_stay_nan_not_zero(tmp_path):
    raw = make_raw_results()
    # GateANN 行中 PipeANN 专有字段为空白,加载后应为 NaN 而非 0
    gateann_row = raw[raw["system"] == "gateann"].iloc[0]
    assert gateann_row["pre_filter_queries"] == ""
    path = tmp_path / "results.csv"
    raw.to_csv(path, index=False)
    loaded = load(str(path))
    gateann_loaded = loaded[loaded["system"] == "gateann"].iloc[0]
    assert math.isnan(gateann_loaded["pre_filter_queries"])
    assert not math.isnan(gateann_loaded["filter_skips"])


def test_load_raises_on_invalid(tmp_path):
    raw = make_raw_results()
    raw.loc[0, "recall_percent"] = 123.4
    path = tmp_path / "results.csv"
    raw.to_csv(path, index=False)
    with pytest.raises(ValueError, match="校验失败"):
        load(str(path))
