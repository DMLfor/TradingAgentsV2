"""Tests for indicator core utilities."""

import pandas as pd
import numpy as np
import pytest

from tdx_core.indicators._core import (
    normalize_ohlcv, restore_ohlcv, validate_ohlcv, true_range, IndicatorError,
)


@pytest.fixture
def std_df():
    """DataFrame with standard column names."""
    np.random.seed(42)
    n = 50
    close = 10 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "open": close + 0.1,
        "high": close + 0.3,
        "low": close - 0.3,
        "close": close,
        "volume": 10000.0,
    })


@pytest.fixture
def tdx_df():
    """DataFrame with TDX column names."""
    np.random.seed(42)
    n = 50
    close = 10 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "open_val": close + 0.1,
        "high_val": close + 0.3,
        "low_val": close - 0.3,
        "close_val": close,
        "volume": 10000.0,
    })


class TestNormalize:
    def test_standard_columns_pass_through(self, std_df):
        result, meta = normalize_ohlcv(std_df)
        assert meta["convention"] == "standard"
        assert "open" in result.columns
        assert "close" in result.columns

    def test_tdx_columns_renamed(self, tdx_df):
        result, meta = normalize_ohlcv(tdx_df)
        assert meta["convention"] == "tdx"
        assert "open" in result.columns
        assert "close" in result.columns
        assert "open_val" not in result.columns

    def test_restore_tdx_columns(self, tdx_df):
        result, meta = normalize_ohlcv(tdx_df)
        result["ma_5"] = 1.0  # add indicator column
        restored = restore_ohlcv(result, meta)
        assert "open_val" in restored.columns
        assert "close_val" in restored.columns
        assert "ma_5" in restored.columns  # indicator column unchanged

    def test_no_mutation(self, tdx_df):
        original_cols = list(tdx_df.columns)
        normalize_ohlcv(tdx_df)
        assert list(tdx_df.columns) == original_cols

    def test_missing_columns_raises(self):
        df = pd.DataFrame({"a": [1], "b": [2]})
        with pytest.raises(IndicatorError):
            normalize_ohlcv(df)


class TestValidate:
    def test_standard_valid(self, std_df):
        validate_ohlcv(std_df)

    def test_tdx_valid(self, tdx_df):
        validate_ohlcv(tdx_df)

    def test_invalid_raises(self):
        df = pd.DataFrame({"a": [1]})
        with pytest.raises(IndicatorError):
            validate_ohlcv(df)


class TestTrueRange:
    def test_true_range_values(self):
        high = pd.Series([11, 12, 10])
        low = pd.Series([9, 8, 9])
        close = pd.Series([10, 11, 9.5])
        tr = true_range(high, low, close)
        # TR[0] = 11-9 = 2
        assert tr.iloc[0] == 2.0
        # TR[1] = max(12-8, |12-10|, |8-10|) = max(4, 2, 2) = 4
        assert tr.iloc[1] == 4.0
        # TR[2] = max(10-9, |10-11|, |9-11|) = max(1, 1, 2) = 2
        assert tr.iloc[2] == 2.0
