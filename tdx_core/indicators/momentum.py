"""Momentum indicators: RSI, Stochastic, Williams %R, CCI, ROC, Momentum,
StochRSI, Ultimate Oscillator, Awesome Oscillator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._core import normalize_ohlcv, restore_ohlcv, true_range


def rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Relative Strength Index."""
    df, meta = normalize_ohlcv(df)

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    df[f"rsi_{period}"] = 100 - 100 / (1 + rs)
    return restore_ohlcv(df, meta)


def stochastic(df: pd.DataFrame, k_period: int = 14,
               d_period: int = 3) -> pd.DataFrame:
    """Stochastic Oscillator (%K and %D)."""
    df, meta = normalize_ohlcv(df)

    lowest_low = df["low"].rolling(window=k_period, min_periods=1).min()
    highest_high = df["high"].rolling(window=k_period, min_periods=1).max()

    df["stoch_k"] = 100 * (df["close"] - lowest_low) / (highest_high - lowest_low)
    df["stoch_d"] = df["stoch_k"].rolling(window=d_period, min_periods=1).mean()
    return restore_ohlcv(df, meta)


def williams_r(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Williams %R."""
    df, meta = normalize_ohlcv(df)

    highest_high = df["high"].rolling(window=period, min_periods=1).max()
    lowest_low = df["low"].rolling(window=period, min_periods=1).min()

    df["williams_r"] = -100 * (highest_high - df["close"]) / (highest_high - lowest_low)
    return restore_ohlcv(df, meta)


def cci(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Commodity Channel Index."""
    df, meta = normalize_ohlcv(df)

    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = tp.rolling(window=period, min_periods=1).mean()
    mad = tp.rolling(window=period, min_periods=1).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=True
    )
    df[f"cci_{period}"] = (tp - sma_tp) / (0.015 * mad)
    return restore_ohlcv(df, meta)


def roc(df: pd.DataFrame, period: int = 12) -> pd.DataFrame:
    """Rate of Change."""
    df, meta = normalize_ohlcv(df)
    df[f"roc_{period}"] = df["close"].pct_change(periods=period) * 100
    return restore_ohlcv(df, meta)


def momentum(df: pd.DataFrame, period: int = 10) -> pd.DataFrame:
    """Momentum (close - close[n])."""
    df, meta = normalize_ohlcv(df)
    df[f"momentum_{period}"] = df["close"] - df["close"].shift(period)
    return restore_ohlcv(df, meta)


def stochrsi(df: pd.DataFrame, rsi_period: int = 14, stoch_period: int = 14,
             k_period: int = 3, d_period: int = 3) -> pd.DataFrame:
    """Stochastic RSI."""
    df, meta = normalize_ohlcv(df)

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / rsi_period, min_periods=rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / rsi_period, min_periods=rsi_period, adjust=False).mean()
    rsi_val = 100 - 100 / (1 + avg_gain / avg_loss)

    lowest_rsi = rsi_val.rolling(window=stoch_period, min_periods=1).min()
    highest_rsi = rsi_val.rolling(window=stoch_period, min_periods=1).max()

    df["stochrsi_k"] = 100 * (rsi_val - lowest_rsi) / (highest_rsi - lowest_rsi)
    df["stochrsi_d"] = df["stochrsi_k"].rolling(window=d_period, min_periods=1).mean()
    return restore_ohlcv(df, meta)


def ultimate_oscillator(df: pd.DataFrame, period1: int = 7,
                        period2: int = 14, period3: int = 28) -> pd.DataFrame:
    """Ultimate Oscillator."""
    df, meta = normalize_ohlcv(df)

    high = df["high"]
    low = df["low"]
    close = df["close"]

    bp = close - pd.concat([low, close.shift(1)], axis=1).max(axis=1)
    tr = true_range(high, low, close)

    avg1 = bp.rolling(window=period1, min_periods=1).sum() / tr.rolling(window=period1, min_periods=1).sum()
    avg2 = bp.rolling(window=period2, min_periods=1).sum() / tr.rolling(window=period2, min_periods=1).sum()
    avg3 = bp.rolling(window=period3, min_periods=1).sum() / tr.rolling(window=period3, min_periods=1).sum()

    df["ultimate_osc"] = 100 * (4 * avg1 + 2 * avg2 + avg3) / 7
    return restore_ohlcv(df, meta)


def awesome_oscillator(df: pd.DataFrame, fast: int = 5,
                       slow: int = 34) -> pd.DataFrame:
    """Awesome Oscillator."""
    df, meta = normalize_ohlcv(df)

    midprice = (df["high"] + df["low"]) / 2
    df["awesome_osc"] = (
        midprice.rolling(window=fast, min_periods=1).mean()
        - midprice.rolling(window=slow, min_periods=1).mean()
    )
    return restore_ohlcv(df, meta)
