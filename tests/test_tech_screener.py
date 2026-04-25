"""Tests for tech_screener.py — pullback-screener scoring + trade plan generation."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.tech_screener import _compute_scores, _generate_trade_plan, TradePlan


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def pullback_df() -> pd.DataFrame:
    """A stock in uptrend with a healthy pullback from recent high."""
    n = 60
    # Price: strong uptrend then 8% pullback from high
    close = np.concatenate([
        np.linspace(90, 108, 40),   # uptrend to 108
        np.linspace(108, 99.4, 20), # pullback ~8%
    ])
    high = close + np.random.uniform(0.3, 1.5, n)
    low = close - np.random.uniform(0.3, 1.5, n)
    open_val = close - np.random.uniform(-0.5, 0.5, n)
    volume = np.concatenate([
        np.random.uniform(2_000_000, 3_000_000, 40),  # strong volume during uptrend
        np.random.uniform(800_000, 1_200_000, 20),     # shrinking volume during pullback
    ])
    amount = close * volume

    df = pd.DataFrame({
        "trade_date": pd.date_range("2024-01-01", periods=n, freq="D").strftime("%Y-%m-%d"),
        "open_val": open_val,
        "high_val": high,
        "low_val": low,
        "close_val": close,
        "volume": volume,
        "amount": amount,
    })

    # Inject indicators
    df["ma_5"] = close
    df["ma_20"] = close * 0.95
    df["ma_60"] = close * 0.85  # well below close => uptrend

    df["macd"] = 0.8   # above zero
    df["macd_signal"] = 0.5
    df["macd_hist"] = 0.3

    df["rsi_14"] = 42.0  # oversold zone

    return df


@pytest.fixture
def chasing_df() -> pd.DataFrame:
    """A stock near recent high with no pullback — should score low on pullback."""
    n = 60
    close = np.linspace(100, 108, n)
    high = close + np.random.uniform(0.3, 1.0, n)
    low = close - np.random.uniform(0.3, 1.0, n)
    open_val = close - np.random.uniform(-0.5, 0.5, n)
    volume = np.random.uniform(2_000_000, 3_000_000, n)
    amount = close * volume

    df = pd.DataFrame({
        "trade_date": pd.date_range("2024-01-01", periods=n, freq="D").strftime("%Y-%m-%d"),
        "open_val": open_val,
        "high_val": high,
        "low_val": low,
        "close_val": close,
        "volume": volume,
        "amount": amount,
    })

    df["ma_5"] = close * 0.98
    df["ma_20"] = close * 0.95
    df["ma_60"] = close * 0.85

    df["macd"] = 1.2
    df["macd_signal"] = 0.8
    df["macd_hist"] = 0.4

    df["rsi_14"] = 72.0  # overbought

    return df


@pytest.fixture
def downtrend_df() -> pd.DataFrame:
    """A stock below MA60 — should get zero trend score."""
    n = 60
    close = np.linspace(100, 80, n)
    high = close + np.random.uniform(0.3, 1.0, n)
    low = close - np.random.uniform(0.3, 1.0, n)
    open_val = close - np.random.uniform(-0.5, 0.5, n)
    volume = np.random.uniform(1_000_000, 2_000_000, n)
    amount = close * volume

    df = pd.DataFrame({
        "trade_date": pd.date_range("2024-01-01", periods=n, freq="D").strftime("%Y-%m-%d"),
        "open_val": open_val,
        "high_val": high,
        "low_val": low,
        "close_val": close,
        "volume": volume,
        "amount": amount,
    })

    df["ma_5"] = close
    df["ma_20"] = close * 1.05
    df["ma_60"] = close * 1.20  # above close => downtrend

    df["macd"] = -1.0
    df["macd_signal"] = -0.5
    df["macd_hist"] = -0.5

    df["rsi_14"] = 25.0

    return df


# ─── Scoring tests ────────────────────────────────────────────────────────────

def test_compute_scores_pullback(pullback_df):
    scores = _compute_scores(pullback_df)
    assert scores
    assert scores["trend"] >= 15     # above MA60 (MA60 may or may not be rising during pullback)
    assert scores["pullback"] > 15   # 8% pullback from high
    assert scores["oversold"] > 12   # RSI 42
    assert scores["volume"] >= 4     # volume at or below MA20
    assert scores["momentum"] > 10   # MACD > 0
    total = sum(scores.values())
    assert total > 60


def test_compute_scores_chasing(chasing_df):
    scores = _compute_scores(chasing_df)
    assert scores
    assert scores["trend"] > 15      # still in uptrend
    assert scores["pullback"] < 12   # barely pulled back
    assert scores["oversold"] < 8    # RSI 72 = overbought
    total = sum(scores.values())
    assert total <= 65


def test_compute_scores_downtrend(downtrend_df):
    scores = _compute_scores(downtrend_df)
    assert scores
    assert scores["trend"] == 0.0    # below MA60
    # Pullback score can be high on recent window, but total is killed by trend=0
    total = sum(scores.values())
    assert total < 60


def test_compute_scores_empty():
    df = pd.DataFrame()
    scores = _compute_scores(df)
    assert scores == {}


def test_compute_scores_missing_columns():
    df = pd.DataFrame({"close_val": [100, 101, 102]})
    scores = _compute_scores(df)
    assert scores == {}


# ─── Trade plan tests ─────────────────────────────────────────────────────────

def test_generate_trade_plan_pullback(pullback_df):
    scores = _compute_scores(pullback_df)
    plan = _generate_trade_plan(pullback_df, scores, "000001", "Test")
    assert plan is not None
    assert plan.code == "000001"
    assert plan.total_score > 60
    assert plan.entry_price > 0
    assert plan.stop_price > 0
    # Stop should be max(MA60, recent_low * 0.97)
    assert plan.stop_price >= pullback_df.iloc[-1]["ma_60"]
    # Target should be recent 20-day high
    recent_high = pullback_df["high_val"].tail(20).max()
    assert plan.target_price == pytest.approx(recent_high, rel=0.01)


def test_generate_trade_plan_none_scores():
    plan = _generate_trade_plan(pd.DataFrame(), {}, "000003", "None")
    assert plan is None


def test_entry_stop_target_relationships(pullback_df):
    scores = _compute_scores(pullback_df)
    plan = _generate_trade_plan(pullback_df, scores, "000001", "Test")
    assert plan is not None
    # Stop should be below entry
    assert plan.stop_price < plan.entry_price
    # Target should be above entry
    assert plan.target_price > plan.entry_price
    # Risk-reward formula check
    expected_rr = (plan.target_price - plan.entry_price) / (plan.entry_price - plan.stop_price)
    assert abs(plan.risk_reward - expected_rr) < 0.01


# ─── Position suggestion tests ────────────────────────────────────────────────

def test_position_suggestion_high_score(pullback_df):
    # Manually craft very high scores
    scores = {
        "trend": 25,
        "pullback": 25,
        "oversold": 20,
        "volume": 15,
        "momentum": 15,
    }
    plan = _generate_trade_plan(pullback_df, scores, "000001", "Test")
    assert plan is not None
    assert plan.total_score == 100.0
    if plan.risk_reward >= 2.0:
        assert plan.position_suggestion == "重仓 60-80%"


def test_position_suggestion_low_score():
    df = pd.DataFrame({
        "trade_date": ["2024-01-01", "2024-01-02"],
        "open_val": [100, 101],
        "high_val": [101, 102],
        "low_val": [99, 100],
        "close_val": [100, 101],
        "volume": [1_000_000, 1_000_000],
        "amount": [100_000_000, 101_000_000],
        "ma_5": [100, 101],
        "ma_20": [100, 101],
        "ma_60": [100, 101],
        "macd": [0, 0],
        "macd_signal": [0, 0],
        "macd_hist": [0, 0],
        "rsi_14": [50, 50],
    })
    scores = {
        "trend": 10,
        "pullback": 10,
        "oversold": 8,
        "volume": 5,
        "momentum": 5,
    }
    plan = _generate_trade_plan(df, scores, "000001", "Test")
    assert plan is not None
    assert plan.position_suggestion == "观望"
