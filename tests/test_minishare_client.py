# -*- coding: utf-8 -*-
"""Tests for tdx_core.minishare_client."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tdx_core import minishare_client as _ms_module
from tdx_core.minishare_client import MinishareClient, MinishareError


@pytest.fixture(autouse=True)
def _patch_minishare_module(monkeypatch):
    """Ensure minishare module is mocked for all tests in this file."""
    fake_ms = MagicMock()
    fake_api = MagicMock()
    fake_ms.pro_api = MagicMock(return_value=fake_api)
    monkeypatch.setattr(_ms_module, "_ms", fake_ms)
    yield
    monkeypatch.setattr(_ms_module, "_ms", None)


class TestToTsCode:
    """Test _to_ts_code mapping."""

    def test_sh_600(self):
        assert MinishareClient._to_ts_code("600519") == "600519.SH"

    def test_sh_688(self):
        assert MinishareClient._to_ts_code("688008") == "688008.SH"

    def test_sz_000(self):
        assert MinishareClient._to_ts_code("000001") == "000001.SZ"

    def test_sz_300(self):
        assert MinishareClient._to_ts_code("300750") == "300750.SZ"

    def test_bj_900(self):
        assert MinishareClient._to_ts_code("900901") == "900901.BJ"

    def test_invalid_length(self):
        with pytest.raises(MinishareError):
            MinishareClient._to_ts_code("12345")


class TestToDbSchema:
    """Test _to_db_schema column mapping."""

    def test_basic_mapping(self):
        df = pd.DataFrame({
            "ts_code": ["600519.SH", "000001.SZ"],
            "name": ["贵州茅台", "平安银行"],
            "open": [1500.0, 10.5],
            "high": [1520.0, 10.8],
            "low": [1480.0, 10.2],
            "close": [1510.0, 10.6],
            "vol": [10000, 20000],
            "amount": [15000000.0, 210000.0],
            "change": [10.0, 0.1],
            "pct_chg": [0.67, 0.95],
        })
        result = MinishareClient._to_db_schema(df)

        assert list(result.columns) == [
            "code", "trade_date", "open_val", "high_val", "low_val",
            "close_val", "volume", "amount",
        ]
        assert result["code"].tolist() == ["600519", "000001"]
        assert result["open_val"].tolist() == [1500.0, 10.5]
        assert result["volume"].tolist() == [10000, 20000]
        assert "change" not in result.columns
        assert "pct_chg" not in result.columns

    def test_empty_dataframe(self):
        result = MinishareClient._to_db_schema(pd.DataFrame())
        assert result.empty

    def test_none_input(self):
        result = MinishareClient._to_db_schema(None)
        assert result.empty


class TestMinishareClientInit:
    """Test client initialization and token handling."""

    def test_token_from_env(self, monkeypatch):
        monkeypatch.setenv("MINISHARE_TOKEN", "test_token_123")
        client = MinishareClient()
        assert client._token == "test_token_123"

    def test_token_from_arg(self):
        client = MinishareClient(token="arg_token")
        assert client._token == "arg_token"

    def test_missing_token(self, monkeypatch):
        monkeypatch.delenv("MINISHARE_TOKEN", raising=False)
        with pytest.raises(MinishareError, match="缺少 minishare API token"):
            MinishareClient()


class TestRetryLogic:
    """Test API call retry behavior."""

    def test_success_on_first_attempt(self, monkeypatch):
        monkeypatch.setenv("MINISHARE_TOKEN", "tok")
        client = MinishareClient()

        mock_df = pd.DataFrame({"ts_code": ["600519.SH"], "close": [1500.0]})
        client._api.rt_k_ms = MagicMock(return_value=mock_df)

        df = client._call_with_retry("rt_k_ms", ts_code="600519.SH")
        assert df is mock_df
        client._api.rt_k_ms.assert_called_once()

    def test_retry_then_success(self, monkeypatch):
        monkeypatch.setenv("MINISHARE_TOKEN", "tok")
        client = MinishareClient()

        mock_df = pd.DataFrame({"ts_code": ["600519.SH"], "close": [1500.0]})
        client._api.rt_k_ms = MagicMock(
            side_effect=[ConnectionError("timeout"), mock_df]
        )

        with patch("tdx_core.minishare_client.time.sleep"):
            df = client._call_with_retry("rt_k_ms", ts_code="600519.SH")
        assert df is mock_df
        assert client._api.rt_k_ms.call_count == 2

    def test_retry_exhausted(self, monkeypatch):
        monkeypatch.setenv("MINISHARE_TOKEN", "tok")
        client = MinishareClient()

        client._api.rt_k_ms = MagicMock(side_effect=ConnectionError("fail"))

        with patch("tdx_core.minishare_client.time.sleep"):
            with pytest.raises(MinishareError, match="调用失败"):
                client._call_with_retry("rt_k_ms", ts_code="600519.SH")
        assert client._api.rt_k_ms.call_count == 3
