"""Volatility indicators: Bollinger Bands, ATR, Keltner Channel,
Donchian Channel, Standard Deviation, Chaikin Volatility."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._core import normalize_ohlcv, restore_ohlcv, true_range


def bollinger(df: pd.DataFrame, period: int = 20,
              std_dev: float = 2.0) -> pd.DataFrame:
    """Bollinger Bands."""
    df, meta = normalize_ohlcv(df)

    middle = df["close"].rolling(window=period, min_periods=1).mean()
    std = df["close"].rolling(window=period, min_periods=1).std()

    df["bb_upper"] = middle + std_dev * std
    df["bb_middle"] = middle
    df["bb_lower"] = middle - std_dev * std
    df["bb_bandwidth"] = (df["bb_upper"] - df["bb_lower"]) / middle
    df["bb_pctb"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])
    return restore_ohlcv(df, meta)


def atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Average True Range."""
    df, meta = normalize_ohlcv(df)

    tr = true_range(df["high"], df["low"], df["close"])
    df[f"atr_{period}"] = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    return restore_ohlcv(df, meta)


def keltner(df: pd.DataFrame, ema_period: int = 20, atr_period: int = 10,
            multiplier: float = 1.5) -> pd.DataFrame:
    """Keltner Channel."""
    df, meta = normalize_ohlcv(df)

    middle = df["close"].ewm(span=ema_period, adjust=False).mean()
    tr = true_range(df["high"], df["low"], df["close"])
    atr_val = tr.ewm(alpha=1.0 / atr_period, adjust=False).mean()

    df["keltner_upper"] = middle + multiplier * atr_val
    df["keltner_middle"] = middle
    df["keltner_lower"] = middle - multiplier * atr_val
    return restore_ohlcv(df, meta)


def donchian(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Donchian Channel."""
    df, meta = normalize_ohlcv(df)

    df["donchian_upper"] = df["high"].rolling(window=period, min_periods=1).max()
    df["donchian_lower"] = df["low"].rolling(window=period, min_periods=1).min()
    df["donchian_middle"] = (df["donchian_upper"] + df["donchian_lower"]) / 2
    return restore_ohlcv(df, meta)


def std_dev(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Rolling Standard Deviation."""
    df, meta = normalize_ohlcv(df)
    df[f"stddev_{period}"] = df["close"].rolling(window=period, min_periods=1).std()
    return restore_ohlcv(df, meta)


def chaikin_volatility(df: pd.DataFrame, ema_period: int = 10,
                       roc_period: int = 10) -> pd.DataFrame:
    """Chaikin Volatility."""
    df, meta = normalize_ohlcv(df)

    hl_diff = df["high"] - df["low"]
    ema_hl = hl_diff.ewm(span=ema_period, adjust=False).mean()
    df["chaikin_vol"] = (ema_hl - ema_hl.shift(roc_period)) / ema_hl.shift(roc_period) * 100
    return restore_ohlcv(df, meta)
