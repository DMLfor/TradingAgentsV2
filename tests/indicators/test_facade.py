"""Tests for TdxIndicators facade."""

import pandas as pd
import numpy as np
import pytest

from tdx_core.indicators.facade import TdxIndicators


@pytest.fixture
def tdx_df():
    np.random.seed(42)
    n = 100
    close = 10 + np.cumsum(np.random.randn(n) * 0.3)
    return pd.DataFrame({
        "code": "000001",
        "trade_date": pd.date_range("2024-01-01", periods=n),
        "open_val": close + np.random.rand(n) * 0.2,
        "high_val": close + np.random.rand(n) * 0.5,
        "low_val": close - np.random.rand(n) * 0.5,
        "close_val": close,
        "volume": np.random.randint(1000, 50000, n).astype(float),
        "amount": close * np.random.randint(1000, 50000, n).astype(float),
    })


class TestComputeStatic:
    def test_specific_indicators(self, tdx_df):
        result = TdxIndicators.compute(tdx_df, indicators=["ma", "rsi"])
        assert "ma_5" in result.columns
        assert "rsi_14" in result.columns

    def test_all_indicators(self, tdx_df):
        result = TdxIndicators.compute(tdx_df)
        assert "ma_5" in result.columns
        assert "rsi_14" in result.columns
        assert "macd" in result.columns
        assert "bb_upper" in result.columns

    def test_custom_params(self, tdx_df):
        result = TdxIndicators.compute(
            tdx_df,
            indicators=["ma", "rsi"],
            ma={"periods": [3, 7]},
            rsi={"period": 6},
        )
        assert "ma_3" in result.columns
        assert "ma_7" in result.columns
        assert "rsi_6" in result.columns

    def test_invalid_indicator(self, tdx_df):
        with pytest.raises(ValueError, match="Unknown indicator"):
            TdxIndicators.compute(tdx_df, indicators=["nonexistent"])


class TestAvailableIndicators:
    def test_returns_list(self):
        names = TdxIndicators.available_indicators()
        assert isinstance(names, list)
        assert len(names) == 41
        assert "ma" in names
        assert "rsi" in names
