"""Core utilities for the indicator library.

Handles column name normalization between TDX naming (open_val/high_val/...)
and standard naming (open/high/...), validation, and shared computations.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


class IndicatorError(Exception):
    """Raised when indicator computation fails."""


# Mapping from TDX column names to standard names
_TDX_TO_STANDARD = {
    "open_val": "open",
    "high_val": "high",
    "low_val": "low",
    "close_val": "close",
}

_STANDARD_TO_TDX = {v: k for k, v in _TDX_TO_STANDARD.items()}

_STANDARD_OHLC = {"open", "high", "low", "close"}
_TDX_OHLC = {"open_val", "high_val", "low_val", "close_val"}


def normalize_ohlcv(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Normalize OHLCV column names to standard (open/high/low/close).

    Detects whether the DataFrame uses TDX naming (open_val/high_val/...)
    or standard naming (open/high/...), and renames to standard internally.

    Returns:
        Tuple of (normalized DataFrame, metadata dict) where metadata contains:
        - "convention": "tdx" or "standard"
        - "rename_map": dict mapping standard names back to original names
    """
    cols = set(df.columns)

    has_tdx = _TDX_OHLC.issubset(cols)
    has_standard = _STANDARD_OHLC.issubset(cols)

    if has_standard and not has_tdx:
        return df.copy(), {"convention": "standard", "rename_map": {}}

    if has_tdx:
        result = df.rename(columns=_TDX_TO_STANDARD)
        return result, {
            "convention": "tdx",
            "rename_map": _STANDARD_TO_TDX,
        }

    raise IndicatorError(
        f"DataFrame must contain either standard columns "
        f"{sorted(_STANDARD_OHLC)} or TDX columns {sorted(_TDX_OHLC)}. "
        f"Found: {sorted(cols)}"
    )


def restore_ohlcv(df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    """Restore OHLCV column names from standard back to original convention.

    Only renames the 4 OHLCV columns back; indicator columns pass through.
    """
    if meta["convention"] == "standard":
        return df
    return df.rename(columns=meta["rename_map"])


def validate_ohlcv(df: pd.DataFrame) -> None:
    """Validate that DataFrame has required OHLCV columns.

    Accepts either naming convention.
    """
    cols = set(df.columns)
    if _STANDARD_OHLC.issubset(cols) or _TDX_OHLC.issubset(cols):
        return
    missing_standard = _STANDARD_OHLC - cols
    missing_tdx = _TDX_OHLC - cols
    raise IndicatorError(
        f"Missing OHLCV columns. Need either {sorted(_STANDARD_OHLC)} "
        f"or {sorted(_TDX_OHLC)}. Missing standard: {sorted(missing_standard)}, "
        f"missing TDX: {sorted(missing_tdx)}"
    )


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Compute True Range.

    TR = max(high - low, |high - prev_close|, |low - prev_close|)
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
