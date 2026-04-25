"""Tests for trend indicators."""

import pandas as pd
import numpy as np
import pytest

from tdx_core.indicators.trend import (
    ma, ema, sma, wma, dema, tema, macd, adx, aroon,
    ichimoku, sar, supertrend, trix, vortex,
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


@pytest.fixture
def std_df():
    np.random.seed(42)
    n = 100
    close = 10 + np.cumsum(np.random.randn(n) * 0.3)
    return pd.DataFrame({
        "open": close + np.random.rand(n) * 0.2,
        "high": close + np.random.rand(n) * 0.5,
        "low": close - np.random.rand(n) * 0.5,
        "close": close,
        "volume": np.random.randint(1000, 50000, n).astype(float),
    })


class TestMA:
    def test_default_periods(self, tdx_df):
        result = ma(tdx_df)
        for p in [5, 10, 20, 60, 120, 250]:
            assert f"ma_{p}" in result.columns

    def test_custom_periods(self, tdx_df):
        result = ma(tdx_df, periods=[3, 7])
        assert "ma_3" in result.columns
        assert "ma_7" in result.columns

    def test_preserves_tdx_columns(self, tdx_df):
        result = ma(tdx_df)
        assert "close_val" in result.columns
        assert "open_val" in result.columns

    def test_works_with_standard_columns(self, std_df):
        result = ma(std_df, periods=[5])
        assert "ma_5" in result.columns
        assert "close" in result.columns

    def test_ma_value(self, tdx_df):
        result = ma(tdx_df, periods=[3])
        # ma_3 at row 2 = mean of close[0:3]
        close_vals = tdx_df["close_val"].values
        expected = close_vals[:3].mean()
        assert abs(result["ma_3"].iloc[2] - expected) < 1e-10


class TestEMA:
    def test_default_periods(self, tdx_df):
        result = ema(tdx_df)
        assert "ema_12" in result.columns
        assert "ema_26" in result.columns


class TestMACD:
    def test_output_columns(self, tdx_df):
        result = macd(tdx_df)
        assert "macd" in result.columns
        assert "macd_signal" in result.columns
        assert "macd_hist" in result.columns

    def test_macd_equals_ema_diff(self, tdx_df):
        result = macd(tdx_df)
        ema_fast = tdx_df["close_val"].ewm(span=12, adjust=False).mean()
        ema_slow = tdx_df["close_val"].ewm(span=26, adjust=False).mean()
        expected = ema_fast - ema_slow
        pd.testing.assert_series_equal(result["macd"], expected, check_names=False)


class TestADX:
    def test_output_columns(self, tdx_df):
        result = adx(tdx_df)
        assert "adx" in result.columns
        assert "plus_di" in result.columns
        assert "minus_di" in result.columns

    def test_adx_range(self, tdx_df):
        result = adx(tdx_df)
        valid = result["adx"].dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()


class TestAroon:
    def test_output_columns(self, tdx_df):
        result = aroon(tdx_df)
        assert "aroon_up" in result.columns
        assert "aroon_down" in result.columns
        assert "aroon_osc" in result.columns

    def test_aroon_range(self, tdx_df):
        result = aroon(tdx_df)
        valid_up = result["aroon_up"].dropna()
        assert (valid_up >= 0).all()
        assert (valid_up <= 100).all()


class TestIchimoku:
    def test_output_columns(self, tdx_df):
        result = ichimoku(tdx_df)
        assert "tenkan_sen" in result.columns
        assert "kijun_sen" in result.columns
        assert "senkou_span_a" in result.columns
        assert "senkou_span_b" in result.columns
        assert "chikou_span" in result.columns


class TestSAR:
    def test_output_column(self, tdx_df):
        result = sar(tdx_df)
        assert "sar" in result.columns

    def test_sar_not_all_nan(self, tdx_df):
        result = sar(tdx_df)
        assert result["sar"].notna().any()


class TestSupertrend:
    def test_output_columns(self, tdx_df):
        result = supertrend(tdx_df)
        assert "supertrend" in result.columns
        assert "supertrend_direction" in result.columns


class TestTRIX:
    def test_output_column(self, tdx_df):
        result = trix(tdx_df)
        assert "trix" in result.columns


class TestVortex:
    def test_output_columns(self, tdx_df):
        result = vortex(tdx_df)
        assert "vortex_pos" in result.columns
        assert "vortex_neg" in result.columns
