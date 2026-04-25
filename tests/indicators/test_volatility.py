"""Tests for volatility indicators."""

import pandas as pd
import numpy as np
import pytest

from tdx_core.indicators.volatility import (
    bollinger, atr, keltner, donchian, std_dev, chaikin_volatility,
)


@pytest.fixture
def tdx_df():
    np.random.seed(42)
    n = 100
    close = 10 + np.cumsum(np.random.randn(n) * 0.3)
    return pd.DataFrame({
        "open_val": close + np.random.rand(n) * 0.2,
        "high_val": close + np.random.rand(n) * 0.5,
        "low_val": close - np.random.rand(n) * 0.5,
        "close_val": close,
        "volume": np.random.randint(1000, 50000, n).astype(float),
    })


class TestBollinger:
    def test_output_columns(self, tdx_df):
        result = bollinger(tdx_df)
        for col in ["bb_upper", "bb_middle", "bb_lower", "bb_bandwidth", "bb_pctb"]:
            assert col in result.columns

    def test_upper_above_lower(self, tdx_df):
        result = bollinger(tdx_df)
        valid = result.dropna(subset=["bb_upper", "bb_lower"])
        assert (valid["bb_upper"] >= valid["bb_lower"]).all()


class TestATR:
    def test_output_column(self, tdx_df):
        result = atr(tdx_df)
        assert "atr_14" in result.columns

    def test_atr_positive(self, tdx_df):
        result = atr(tdx_df)
        valid = result["atr_14"].dropna()
        assert (valid > 0).all()


class TestKeltner:
    def test_output_columns(self, tdx_df):
        result = keltner(tdx_df)
        assert "keltner_upper" in result.columns
        assert "keltner_middle" in result.columns
        assert "keltner_lower" in result.columns


class TestDonchian:
    def test_output_columns(self, tdx_df):
        result = donchian(tdx_df)
        assert "donchian_upper" in result.columns
        assert "donchian_middle" in result.columns
        assert "donchian_lower" in result.columns

    def test_upper_above_lower(self, tdx_df):
        result = donchian(tdx_df)
        valid = result.dropna(subset=["donchian_upper", "donchian_lower"])
        assert (valid["donchian_upper"] >= valid["donchian_lower"]).all()


class TestStdDev:
    def test_output_column(self, tdx_df):
        result = std_dev(tdx_df)
        assert "stddev_20" in result.columns


class TestChaikinVolatility:
    def test_output_column(self, tdx_df):
        result = chaikin_volatility(tdx_df)
        assert "chaikin_vol" in result.columns
