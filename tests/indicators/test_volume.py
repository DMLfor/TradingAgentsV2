"""Tests for volume indicators."""

import pandas as pd
import numpy as np
import pytest

from tdx_core.indicators.volume import (
    obv, vwap, mfi, ad_line, chaikin_money_flow, force_index,
    ease_of_movement, volume_roc, nvi,
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


class TestOBV:
    def test_output_column(self, tdx_df):
        result = obv(tdx_df)
        assert "obv" in result.columns


class TestVWAP:
    def test_output_column(self, tdx_df):
        result = vwap(tdx_df)
        assert "vwap" in result.columns

    def test_vwap_reasonable(self, tdx_df):
        result = vwap(tdx_df)
        valid = result["vwap"].dropna()
        assert (valid > 0).all()


class TestMFI:
    def test_output_column(self, tdx_df):
        result = mfi(tdx_df)
        assert "mfi_14" in result.columns

    def test_mfi_range(self, tdx_df):
        result = mfi(tdx_df)
        valid = result["mfi_14"].dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()


class TestADLine:
    def test_output_column(self, tdx_df):
        result = ad_line(tdx_df)
        assert "ad_line" in result.columns


class TestChaikinMoneyFlow:
    def test_output_column(self, tdx_df):
        result = chaikin_money_flow(tdx_df)
        assert "cmf_20" in result.columns


class TestForceIndex:
    def test_output_column(self, tdx_df):
        result = force_index(tdx_df)
        assert "force_index_13" in result.columns


class TestEaseOfMovement:
    def test_output_column(self, tdx_df):
        result = ease_of_movement(tdx_df)
        assert "eom_14" in result.columns


class TestVolumeROC:
    def test_output_column(self, tdx_df):
        result = volume_roc(tdx_df)
        assert "vol_roc_12" in result.columns


class TestNVI:
    def test_output_column(self, tdx_df):
        result = nvi(tdx_df)
        assert "nvi" in result.columns
