"""Volume indicators: OBV, VWAP, MFI, A/D Line, Chaikin Money Flow,
Force Index, Ease of Movement, Volume ROC, NVI."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ._core import normalize_ohlcv, restore_ohlcv


def obv(df: pd.DataFrame) -> pd.DataFrame:
    """On Balance Volume."""
    df, meta = normalize_ohlcv(df)

    direction = np.sign(df["close"].diff())
    direction.iloc[0] = 0
    df["obv"] = (direction * df["volume"]).cumsum()
    return restore_ohlcv(df, meta)


def vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Volume Weighted Average Price."""
    df, meta = normalize_ohlcv(df)

    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_tp_vol = (typical_price * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    df["vwap"] = cum_tp_vol / cum_vol
    return restore_ohlcv(df, meta)


def mfi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Money Flow Index."""
    df, meta = normalize_ohlcv(df)

    tp = (df["high"] + df["low"] + df["close"]) / 3
    mf = tp * df["volume"]
    delta_tp = tp.diff()

    pos_mf = mf.where(delta_tp > 0, 0.0)
    neg_mf = mf.where(delta_tp < 0, 0.0)

    pos_sum = pos_mf.rolling(window=period, min_periods=1).sum()
    neg_sum = neg_mf.rolling(window=period, min_periods=1).sum()

    mfr = pos_sum / neg_sum
    df[f"mfi_{period}"] = 100 - 100 / (1 + mfr)
    return restore_ohlcv(df, meta)


def ad_line(df: pd.DataFrame) -> pd.DataFrame:
    """Accumulation/Distribution Line."""
    df, meta = normalize_ohlcv(df)

    high = df["high"]
    low = df["low"]
    close = df["close"]
    volume = df["volume"]

    clv = ((close - low) - (high - close)) / (high - low)
    clv = clv.replace([np.inf, -np.inf], 0.0)
    df["ad_line"] = (clv * volume).cumsum()
    return restore_ohlcv(df, meta)


def chaikin_money_flow(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Chaikin Money Flow."""
    df, meta = normalize_ohlcv(df)

    high = df["high"]
    low = df["low"]
    close = df["close"]
    volume = df["volume"]

    clv = ((close - low) - (high - close)) / (high - low)
    clv = clv.replace([np.inf, -np.inf], 0.0)

    df[f"cmf_{period}"] = (
        (clv * volume).rolling(window=period, min_periods=1).sum()
        / volume.rolling(window=period, min_periods=1).sum()
    )
    return restore_ohlcv(df, meta)


def force_index(df: pd.DataFrame, period: int = 13) -> pd.DataFrame:
    """Force Index."""
    df, meta = normalize_ohlcv(df)

    fi = df["close"].diff() * df["volume"]
    df[f"force_index_{period}"] = fi.ewm(span=period, adjust=False).mean()
    return restore_ohlcv(df, meta)


def ease_of_movement(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Ease of Movement."""
    df, meta = normalize_ohlcv(df)

    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    dm = ((high + low) / 2 - (high.shift(1) + low.shift(1)) / 2)
    br = volume / 1e6 / (high - low)
    emv = dm / br.replace(0, np.nan)

    df[f"eom_{period}"] = emv.rolling(window=period, min_periods=1).mean()
    return restore_ohlcv(df, meta)


def volume_roc(df: pd.DataFrame, period: int = 12) -> pd.DataFrame:
    """Volume Rate of Change."""
    df, meta = normalize_ohlcv(df)
    df[f"vol_roc_{period}"] = df["volume"].pct_change(periods=period) * 100
    return restore_ohlcv(df, meta)


def nvi(df: pd.DataFrame) -> pd.DataFrame:
    """Negative Volume Index."""
    df, meta = normalize_ohlcv(df)

    pct_change = df["close"].pct_change()
    vol_decrease = df["volume"] < df["volume"].shift(1)

    nvi_val = pd.Series(np.nan, index=df.index, dtype=float)
    nvi_val.iloc[0] = 1000.0

    for i in range(1, len(df)):
        prev = nvi_val.iloc[i - 1]
        if vol_decrease.iloc[i]:
            nvi_val.iloc[i] = prev + prev * pct_change.iloc[i]
        else:
            nvi_val.iloc[i] = prev

    df["nvi"] = nvi_val
    return restore_ohlcv(df, meta)
