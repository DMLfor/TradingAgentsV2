# -*- coding: utf-8 -*-
"""Tests for scripts/sync_minishare.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tdx_core.db import TdxDatabase
from tdx_core.config import TdxConfig


@pytest.fixture
def mock_minishare():
    """Provide a patched minishare module."""
    fake_ms = MagicMock()
    fake_api = MagicMock()
    fake_ms.pro_api = MagicMock(return_value=fake_api)
    with patch.dict("sys.modules", {"minishare": fake_ms}):
        yield fake_api


@pytest.fixture
def mem_db(tmp_path):
    """Create an in-memory-like SQLite database for testing."""
    db_path = tmp_path / "test_sync.db"
    config = TdxConfig(db_type="sqlite", db_path=str(db_path))
    db = TdxDatabase(config)
    # Pre-seed with some data so --all-shsz has something to sync
    seed = pd.DataFrame({
        "code": ["600519", "000001"],
        "trade_date": ["2026-04-20", "2026-04-20"],
        "open_val": [1500.0, 10.5],
        "high_val": [1520.0, 10.8],
        "low_val": [1480.0, 10.2],
        "close_val": [1510.0, 10.6],
        "volume": [10000, 20000],
        "amount": [15000000.0, 210000.0],
    })
    db.upsert_dataframe(seed, "tdx_daily")
    return db


class TestClassifyCodes:
    """Test _classify_codes heuristic."""

    def test_stock(self, mock_minishare):
        with patch.dict("sys.modules", {"minishare": MagicMock()}):
            from scripts.sync_minishare import _classify_codes
            result = _classify_codes(["600519", "600000", "300750"])
            assert "600519" in result["stock"]
            assert "600000" in result["stock"]
            assert "300750" in result["stock"]

    def test_etf(self, mock_minishare):
        with patch.dict("sys.modules", {"minishare": MagicMock()}):
            from scripts.sync_minishare import _classify_codes
            result = _classify_codes(["515180", "159545"])
            assert "515180" in result["etf"]
            assert "159545" in result["etf"]

    def test_index(self, mock_minishare):
        with patch.dict("sys.modules", {"minishare": MagicMock()}):
            from scripts.sync_minishare import _classify_codes
            result = _classify_codes(["000001", "399001", "399300"])
            # 000001 is ambiguous (both stock and index), heuristic puts it in index
            assert "399001" in result["index"]
            assert "399300" in result["index"]


class TestFetchAndNormalize:
    """Test the fetch -> normalize -> upsert pipeline."""

    def test_upsert_pipeline(self, mock_minishare, mem_db, tmp_path, monkeypatch):
        monkeypatch.setenv("MINISHARE_TOKEN", "test_tok")

        # Mock API response
        mock_df = pd.DataFrame({
            "ts_code": ["600519.SH"],
            "name": ["贵州茅台"],
            "open": [1505.0],
            "high": [1525.0],
            "low": [1495.0],
            "close": [1515.0],
            "vol": [12000],
            "amount": [18000000.0],
        })
        mock_minishare.rt_k_ms.return_value = mock_df

        with patch.dict("sys.modules", {"minishare": MagicMock(pro_api=MagicMock(return_value=mock_minishare))}):
            from tdx_core.minishare_client import MinishareClient
            client = MinishareClient("test_tok")
            df = client.get_snapshot(["600519"])

        assert len(df) == 1
        assert df["code"].iloc[0] == "600519"
        assert df["close_val"].iloc[0] == 1515.0
        assert df["volume"].iloc[0] == 12000

        # Write to DB
        rows = mem_db.upsert_dataframe(df, "tdx_daily")
        assert rows == 1

        # Verify the new row is in DB
        with mem_db._connect() as conn:
            result = conn.execute(
                "SELECT close_val, volume FROM tdx_daily WHERE code = '600519' ORDER BY trade_date DESC LIMIT 1"
            ).fetchone()
            assert result[0] == 1515.0
            assert result[1] == 12000
