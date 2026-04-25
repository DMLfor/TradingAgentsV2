"""Trend indicators: MA, EMA, SMA, WMA, DEMA, TEMA, MACD, ADX, Aroon,
Ichimoku, SAR, Supertrend, TRIX, Vortex."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._core import normalize_ohlcv, restore_ohlcv, validate_ohlcv, true_range


def ma(df: pd.DataFrame, periods: list[int] | None = None) -> pd.DataFrame:
    """Simple Moving Average."""
    if periods is None:
        periods = [5, 10, 20, 60, 120, 250]
    df, meta = normalize_ohlcv(df)
    for p in periods:
        df[f"ma_{p}"] = df["close"].rolling(window=p, min_periods=1).mean()
    return restore_ohlcv(df, meta)


def ema(df: pd.DataFrame, periods: list[int] | None = None) -> pd.DataFrame:
    """Exponential Moving Average."""
    if periods is None:
        periods = [12, 26]
    df, meta = normalize_ohlcv(df)
    for p in periods:
        df[f"ema_{p}"] = df["close"].ewm(span=p, adjust=False).mean()
    return restore_ohlcv(df, meta)


def sma(df: pd.DataFrame, periods: list[int] | None = None) -> pd.DataFrame:
    """Smoothed Moving Average (Wilder's smoothing)."""
    if periods is None:
        periods = [20]
    df, meta = normalize_ohlcv(df)
    for p in periods:
        df[f"sma_{p}"] = df["close"].ewm(alpha=1.0 / p, adjust=False).mean()
    return restore_ohlcv(df, meta)


def wma(df: pd.DataFrame, periods: list[int] | None = None) -> pd.DataFrame:
    """Weighted Moving Average."""
    if periods is None:
        periods = [20]
    df, meta = normalize_ohlcv(df)
    for p in periods:
        weights = np.arange(1, p + 1, dtype=float)
        df[f"wma_{p}"] = (
            df["close"]
            .rolling(window=p, min_periods=p)
            .apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
        )
    return restore_ohlcv(df, meta)


def dema(df: pd.DataFrame, periods: list[int] | None = None) -> pd.DataFrame:
    """Double Exponential Moving Average."""
    if periods is None:
        periods = [20]
    df, meta = normalize_ohlcv(df)
    for p in periods:
        e1 = df["close"].ewm(span=p, adjust=False).mean()
        e2 = e1.ewm(span=p, adjust=False).mean()
        df[f"dema_{p}"] = 2 * e1 - e2
    return restore_ohlcv(df, meta)


def tema(df: pd.DataFrame, periods: list[int] | None = None) -> pd.DataFrame:
    """Triple Exponential Moving Average."""
    if periods is None:
        periods = [20]
    df, meta = normalize_ohlcv(df)
    for p in periods:
        e1 = df["close"].ewm(span=p, adjust=False).mean()
        e2 = e1.ewm(span=p, adjust=False).mean()
        e3 = e2.ewm(span=p, adjust=False).mean()
        df[f"tema_{p}"] = 3 * e1 - 3 * e2 + e3
    return restore_ohlcv(df, meta)


def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26,
         signal: int = 9) -> pd.DataFrame:
    """MACD (Moving Average Convergence Divergence)."""
    df, meta = normalize_ohlcv(df)
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    df["macd"] = ema_fast - ema_slow
    df["macd_signal"] = df["macd"].ewm(span=signal, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    return restore_ohlcv(df, meta)


def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Average Directional Index with +DI and -DI."""
    df, meta = normalize_ohlcv(df)

    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = low.diff().abs()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr = true_range(high, low, close)
    atr_val = tr.ewm(alpha=1.0 / period, adjust=False).mean()

    plus_di = 100 * plus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr_val
    minus_di = 100 * minus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr_val

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di
    df["adx"] = dx.ewm(alpha=1.0 / period, adjust=False).mean()
    return restore_ohlcv(df, meta)


def aroon(df: pd.DataFrame, period: int = 25) -> pd.DataFrame:
    """Aroon Up/Down/Oscillator."""
    df, meta = normalize_ohlcv(df)

    high = df["high"]
    low = df["low"]

    days_since_high = high.rolling(window=period + 1, min_periods=1).apply(
        lambda x: period - np.argmax(x), raw=True
    )
    days_since_low = low.rolling(window=period + 1, min_periods=1).apply(
        lambda x: period - np.argmin(x), raw=True
    )

    df["aroon_up"] = 100 * (period - days_since_high) / period
    df["aroon_down"] = 100 * (period - days_since_low) / period
    df["aroon_osc"] = df["aroon_up"] - df["aroon_down"]
    return restore_ohlcv(df, meta)


def ichimoku(df: pd.DataFrame, tenkan: int = 9, kijun: int = 26,
             senkou: int = 52) -> pd.DataFrame:
    """Ichimoku Cloud."""
    df, meta = normalize_ohlcv(df)

    high = df["high"]
    low = df["low"]
    close = df["close"]

    def _midpoint(h, l, period):
        hh = h.rolling(window=period, min_periods=1).max()
        ll = l.rolling(window=period, min_periods=1).min()
        return (hh + ll) / 2

    tenkan_sen = _midpoint(high, low, tenkan)
    kijun_sen = _midpoint(high, low, kijun)
    senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun)
    senkou_b = _midpoint(high, low, senkou).shift(kijun)
    chikou = close.shift(-kijun)

    df["tenkan_sen"] = tenkan_sen
    df["kijun_sen"] = kijun_sen
    df["senkou_span_a"] = senkou_a
    df["senkou_span_b"] = senkou_b
    df["chikou_span"] = chikou
    return restore_ohlcv(df, meta)


def sar(df: pd.DataFrame, af_start: float = 0.02,
        af_max: float = 0.2) -> pd.DataFrame:
    """Parabolic SAR."""
    df, meta = normalize_ohlcv(df)

    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    n = len(df)

    sar_vals = np.empty(n)
    sar_vals[:] = np.nan

    if n < 2:
        return restore_ohlcv(df, meta)

    # Initial trend: up if close[1] > close[0], else down
    is_long = close[1] > close[0]
    af = af_start

    if is_long:
        sar_vals[0] = low[0]
        ep = high[0]
    else:
        sar_vals[0] = high[0]
        ep = low[0]

    for i in range(1, n):
        prev_sar = sar_vals[i - 1]

        if is_long:
            new_sar = prev_sar + af * (ep - prev_sar)
            new_sar = min(new_sar, low[i - 1], low[max(i - 2, 0)])
            if low[i] < new_sar:
                is_long = False
                sar_vals[i] = ep
                ep = low[i]
                af = af_start
            else:
                sar_vals[i] = new_sar
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + af_start, af_max)
        else:
            new_sar = prev_sar + af * (ep - prev_sar)
            new_sar = max(new_sar, high[i - 1], high[max(i - 2, 0)])
            if high[i] > new_sar:
                is_long = True
                sar_vals[i] = ep
                ep = high[i]
                af = af_start
            else:
                sar_vals[i] = new_sar
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + af_start, af_max)

    df["sar"] = sar_vals
    return restore_ohlcv(df, meta)


def supertrend(df: pd.DataFrame, period: int = 10,
               multiplier: float = 3.0) -> pd.DataFrame:
    """Supertrend indicator."""
    df, meta = normalize_ohlcv(df)

    tr = true_range(df["high"], df["low"], df["close"])
    atr_val = tr.ewm(alpha=1.0 / period, adjust=False).mean()

    hl2 = (df["high"] + df["low"]) / 2
    upper_band = hl2 + multiplier * atr_val
    lower_band = hl2 - multiplier * atr_val

    n = len(df)
    st = np.empty(n)
    direction = np.empty(n, dtype=int)

    close = df["close"].values
    upper = upper_band.values
    lower = lower_band.values

    st[0] = upper[0]
    direction[0] = 1  # 1 = downtrend, -1 = uptrend

    for i in range(1, n):
        if close[i] > upper[i - 1]:
            direction[i] = -1
        elif close[i] < lower[i - 1]:
            direction[i] = 1
        else:
            direction[i] = direction[i - 1]

        if direction[i] == -1:
            st[i] = lower[i] if lower[i] > lower[i - 1] or direction[i] != direction[i - 1] else lower[i - 1]
        else:
            st[i] = upper[i] if upper[i] < upper[i - 1] or direction[i] != direction[i - 1] else upper[i - 1]

    df["supertrend"] = st
    df["supertrend_direction"] = direction
    return restore_ohlcv(df, meta)


def trix(df: pd.DataFrame, period: int = 15) -> pd.DataFrame:
    """TRIX indicator (triple-smoothed EMA rate of change)."""
    df, meta = normalize_ohlcv(df)

    e1 = df["close"].ewm(span=period, adjust=False).mean()
    e2 = e1.ewm(span=period, adjust=False).mean()
    e3 = e2.ewm(span=period, adjust=False).mean()
    df["trix"] = e3.pct_change() * 10000
    return restore_ohlcv(df, meta)


def vortex(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Vortex Indicator."""
    df, meta = normalize_ohlcv(df)

    high = df["high"]
    low = df["low"]
    close = df["close"]

    vm_plus = (high - low.shift(1)).abs().rolling(window=period, min_periods=1).sum()
    vm_minus = (low - high.shift(1)).abs().rolling(window=period, min_periods=1).sum()
    tr_sum = true_range(high, low, close).rolling(window=period, min_periods=1).sum()

    df["vortex_pos"] = vm_plus / tr_sum
    df["vortex_neg"] = vm_minus / tr_sum
    return restore_ohlcv(df, meta)
