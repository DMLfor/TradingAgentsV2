"""Composite indicators: Pivot Points, Fibonacci Retracement, TD Sequential."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._core import normalize_ohlcv, restore_ohlcv


def pivot_points(df: pd.DataFrame, method: str = "standard") -> pd.DataFrame:
    """Pivot Points with support/resistance levels.

    Methods: 'standard', 'fibonacci', 'camarilla'.
    Uses the previous period's high/low/close to calculate levels.
    """
    df, meta = normalize_ohlcv(df)

    high = df["high"].shift(1)
    low = df["low"].shift(1)
    close = df["close"].shift(1)

    if method == "standard":
        pp = (high + low + close) / 3
        df["pp"] = pp
        df["r1"] = 2 * pp - low
        df["s1"] = 2 * pp - high
        df["r2"] = pp + (high - low)
        df["s2"] = pp - (high - low)
        df["r3"] = high + 2 * (pp - low)
        df["s3"] = low - 2 * (high - pp)

    elif method == "fibonacci":
        pp = (high + low + close) / 3
        df["pp"] = pp
        df["r1"] = pp + 0.382 * (high - low)
        df["s1"] = pp - 0.382 * (high - low)
        df["r2"] = pp + 0.618 * (high - low)
        df["s2"] = pp - 0.618 * (high - low)
        df["r3"] = pp + 1.000 * (high - low)
        df["s3"] = pp - 1.000 * (high - low)

    elif method == "camarilla":
        df["pp"] = (high + low + close) / 3
        df["r1"] = close + 1.1 / 12 * (high - low)
        df["s1"] = close - 1.1 / 12 * (high - low)
        df["r2"] = close + 1.1 / 6 * (high - low)
        df["s2"] = close - 1.1 / 6 * (high - low)
        df["r3"] = close + 1.1 / 4 * (high - low)
        df["s3"] = close - 1.1 / 4 * (high - low)

    else:
        raise ValueError(f"Unknown pivot method: {method}. Use 'standard', 'fibonacci', or 'camarilla'.")

    return restore_ohlcv(df, meta)


def fibonacci_retracement(df: pd.DataFrame) -> pd.DataFrame:
    """Fibonacci Retracement levels based on rolling high/low."""
    df, meta = normalize_ohlcv(df)

    high = df["high"]
    low = df["low"]

    diff = high - low
    df["fib_0"] = high
    df["fib_236"] = high - 0.236 * diff
    df["fib_382"] = high - 0.382 * diff
    df["fib_500"] = high - 0.500 * diff
    df["fib_618"] = high - 0.618 * diff
    df["fib_786"] = high - 0.786 * diff
    df["fib_1000"] = low
    return restore_ohlcv(df, meta)


def td_sequential(df: pd.DataFrame) -> pd.DataFrame:
    """TD Sequential (simplified: setup count only).

    Setup: 9 consecutive closes higher (buy setup) or lower (sell setup)
    than the close 4 bars earlier.
    """
    df, meta = normalize_ohlcv(df)

    close = df["close"]
    close4 = close.shift(4)

    # Comparison: 1 = close > close4, -1 = close < close4, 0 = equal
    compare = np.sign(close - close4)

    setup_count = np.zeros(len(df), dtype=int)
    setup_type = np.zeros(len(df), dtype=int)  # 1=buy setup, -1=sell setup

    for i in range(4, len(df)):
        c = compare.iloc[i]
        if c == 0:
            setup_count[i] = 0
            setup_type[i] = 0
        elif i > 4 and c == compare.iloc[i - 1] and setup_count[i - 1] > 0:
            setup_count[i] = setup_count[i - 1] + 1
            setup_type[i] = c
        else:
            setup_count[i] = 1
            setup_type[i] = c

    df["td_setup"] = setup_count * setup_type
    df["td_countdown"] = 0  # placeholder for full countdown implementation
    return restore_ohlcv(df, meta)
