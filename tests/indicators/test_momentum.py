"""Tests for momentum indicators."""

import pandas as pd
import numpy as np
import pytest

from tdx_core.indicators.momentum import (
    rsi, stochastic, williams_r, cci, roc, momentum, stochrsi,
    ultimate_oscillator, awesome_oscillator,
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


class TestRSI:
    def test_output_column(self, tdx_df):
        result = rsi(tdx_df)
        assert "rsi_14" in result.columns

    def test_rsi_range(self, tdx_df):
        result = rsi(tdx_df)
        valid = result["rsi_14"].dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_custom_period(self, tdx_df):
        result = rsi(tdx_df, period=6)
        assert "rsi_6" in result.columns


class TestStochastic:
    def test_output_columns(self, tdx_df):
        result = stochastic(tdx_df)
        assert "stoch_k" in result.columns
        assert "stoch_d" in result.columns

    def test_stoch_range(self, tdx_df):
        result = stochastic(tdx_df)
        valid_k = result["stoch_k"].dropna()
        assert (valid_k >= 0).all()
        assert (valid_k <= 100).all()


class TestWilliamsR:
    def test_output_column(self, tdx_df):
        result = williams_r(tdx_df)
        assert "williams_r" in result.columns

    def test_range(self, tdx_df):
        result = williams_r(tdx_df)
        valid = result["williams_r"].dropna()
        assert (valid >= -100).all()
        assert (valid <= 0).all()


class TestCCI:
    def test_output_column(self, tdx_df):
        result = cci(tdx_df)
        assert "cci_20" in result.columns


class TestROC:
    def test_output_column(self, tdx_df):
        result = roc(tdx_df)
        assert "roc_12" in result.columns


class TestMomentum:
    def test_output_column(self, tdx_df):
        result = momentum(tdx_df)
        assert "momentum_10" in result.columns


class TestStochRSI:
    def test_output_columns(self, tdx_df):
        result = stochrsi(tdx_df)
        assert "stochrsi_k" in result.columns
        assert "stochrsi_d" in result.columns


class TestUltimateOscillator:
    def test_output_column(self, tdx_df):
        result = ultimate_oscillator(tdx_df)
        assert "ultimate_osc" in result.columns


class TestAwesomeOscillator:
    def test_output_column(self, tdx_df):
        result = awesome_oscillator(tdx_df)
        assert "awesome_osc" in result.columns
