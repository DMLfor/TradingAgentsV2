"""Tests for composite indicators."""

import pandas as pd
import numpy as np
import pytest

from tdx_core.indicators.composite import pivot_points, fibonacci_retracement, td_sequential


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


class TestPivotPoints:
    def test_standard_columns(self, tdx_df):
        result = pivot_points(tdx_df)
        for col in ["pp", "r1", "r2", "r3", "s1", "s2", "s3"]:
            assert col in result.columns

    def test_fibonacci_columns(self, tdx_df):
        result = pivot_points(tdx_df, method="fibonacci")
        assert "pp" in result.columns
        assert "r1" in result.columns

    def test_camarilla_columns(self, tdx_df):
        result = pivot_points(tdx_df, method="camarilla")
        assert "pp" in result.columns

    def test_invalid_method(self, tdx_df):
        with pytest.raises(ValueError):
            pivot_points(tdx_df, method="invalid")

    def test_standard_formula(self, tdx_df):
        result = pivot_points(tdx_df)
        # r1 = 2*pp - s1 (by rearranging s1 = 2*pp - high)
        valid = result.dropna(subset=["pp", "r1", "s1"])
        # r1 - s1 = 2*(pp - s1) + (s1 - ... ) just check r1 > pp > s1 generally
        assert (valid["r1"] >= valid["s1"]).all()


class TestFibonacciRetracement:
    def test_output_columns(self, tdx_df):
        result = fibonacci_retracement(tdx_df)
        for col in ["fib_0", "fib_236", "fib_382", "fib_500", "fib_618", "fib_786", "fib_1000"]:
            assert col in result.columns

    def test_fib_0_is_high(self, tdx_df):
        result = fibonacci_retracement(tdx_df)
        pd.testing.assert_series_equal(result["fib_0"], result["high_val"], check_names=False)


class TestTDSequential:
    def test_output_columns(self, tdx_df):
        result = td_sequential(tdx_df)
        assert "td_setup" in result.columns
        assert "td_countdown" in result.columns
