"""Tests for backtest_screener.py — pullback strategy backtest logic."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.backtest_screener import simulate_trade, BacktestTrade


# ─── simulate_trade tests ─────────────────────────────────────────────────────

def _make_future_df(rows: list[dict]) -> pd.DataFrame:
    """Helper to create a future DataFrame."""
    dates = pd.date_range("2024-01-08", periods=len(rows), freq="D").strftime("%Y-%m-%d")
    df = pd.DataFrame(rows)
    df["trade_date"] = dates[:len(df)]
    return df


def test_simulate_buy_at_open():
    """Always buys at day1 open."""
    df = _make_future_df([
        {"open_val": 100, "high_val": 102, "low_val": 99, "close_val": 101, "ma_60": 90},
        {"open_val": 101, "high_val": 103, "low_val": 100, "close_val": 102, "ma_60": 91},
    ])
    result = simulate_trade(df, entry=999, stop=90, target=110, max_days=5)
    assert result["triggered"] is True
    assert result["buy_price"] == 100.0  # day1 open
    assert result["result"] == "expired"


def test_simulate_profit_by_target():
    """Close reaches target => profit."""
    df = _make_future_df([
        {"open_val": 100, "high_val": 102, "low_val": 99, "close_val": 101, "ma_60": 90},
        {"open_val": 101, "high_val": 106, "low_val": 100, "close_val": 105, "ma_60": 91},
        {"open_val": 105, "high_val": 108, "low_val": 104, "close_val": 107, "ma_60": 92},
    ])
    result = simulate_trade(df, entry=100, stop=90, target=107, max_days=5)
    assert result["triggered"] is True
    assert result["result"] == "profit"
    assert result["sell_price"] == 107.0
    assert result["return_pct"] == 7.0


def test_simulate_loss_by_ma60():
    """Close drops below MA60 => loss."""
    df = _make_future_df([
        {"open_val": 100, "high_val": 102, "low_val": 99, "close_val": 101, "ma_60": 95},
        {"open_val": 101, "high_val": 102, "low_val": 93, "close_val": 94, "ma_60": 95},
    ])
    result = simulate_trade(df, entry=100, stop=95, target=110, max_days=5)
    assert result["triggered"] is True
    assert result["result"] == "loss"
    assert result["sell_price"] == 94.0


def test_simulate_no_ma60_no_stop():
    """If MA60 is NaN, stop is never triggered."""
    df = _make_future_df([
        {"open_val": 100, "high_val": 102, "low_val": 99, "close_val": 101, "ma_60": np.nan},
        {"open_val": 101, "high_val": 103, "low_val": 100, "close_val": 102, "ma_60": np.nan},
    ])
    result = simulate_trade(df, entry=100, stop=90, target=110, max_days=2)
    assert result["result"] == "expired"


def test_simulate_empty_df():
    result = simulate_trade(pd.DataFrame(), entry=100, stop=95, target=105, max_days=5)
    assert result["triggered"] is False
    assert result["result"] == "no_trigger"


def test_simulate_max_days_zero():
    df = _make_future_df([
        {"open_val": 100, "high_val": 102, "low_val": 99, "close_val": 101, "ma_60": 90},
    ])
    result = simulate_trade(df, entry=100, stop=95, target=105, max_days=0)
    assert result["triggered"] is False


# ─── BacktestTrade dataclass tests ────────────────────────────────────────────

def test_backtest_trade_creation():
    trade = BacktestTrade(
        code="000001",
        name="Test",
        signal_date="2024-01-01",
        buy_date="2024-01-02",
        sell_date="2024-01-05",
        buy_price=100.0,
        sell_price=105.0,
        return_pct=5.0,
        hold_days=3,
        result="profit",
        score=75.0,
        entry_price=100.0,
        stop_price=95.0,
        target_price=110.0,
        risk_reward=2.0,
    )
    assert trade.code == "000001"
    assert trade.return_pct == 5.0
    assert trade.result == "profit"
