"""TdxIndicators: high-level facade integrating TdxQuery with indicator computation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from . import trend, momentum, volatility, volume, composite

if TYPE_CHECKING:
    from ..query import TdxQuery

_INDICATOR_REGISTRY = {
    # trend
    "ma": trend.ma, "ema": trend.ema, "sma": trend.sma, "wma": trend.wma,
    "dema": trend.dema, "tema": trend.tema, "macd": trend.macd,
    "adx": trend.adx, "aroon": trend.aroon, "ichimoku": trend.ichimoku,
    "sar": trend.sar, "supertrend": trend.supertrend, "trix": trend.trix,
    "vortex": trend.vortex,
    # momentum
    "rsi": momentum.rsi, "stochastic": momentum.stochastic,
    "williams_r": momentum.williams_r, "cci": momentum.cci,
    "roc": momentum.roc, "momentum": momentum.momentum,
    "stochrsi": momentum.stochrsi,
    "ultimate_oscillator": momentum.ultimate_oscillator,
    "awesome_oscillator": momentum.awesome_oscillator,
    # volatility
    "bollinger": volatility.bollinger, "atr": volatility.atr,
    "keltner": volatility.keltner, "donchian": volatility.donchian,
    "std_dev": volatility.std_dev, "chaikin_volatility": volatility.chaikin_volatility,
    # volume
    "obv": volume.obv, "vwap": volume.vwap, "mfi": volume.mfi,
    "ad_line": volume.ad_line, "chaikin_money_flow": volume.chaikin_money_flow,
    "force_index": volume.force_index, "ease_of_movement": volume.ease_of_movement,
    "volume_roc": volume.volume_roc, "nvi": volume.nvi,
    # composite
    "pivot_points": composite.pivot_points,
    "fibonacci_retracement": composite.fibonacci_retracement,
    "td_sequential": composite.td_sequential,
}

_ALL_INDICATOR_NAMES = list(_INDICATOR_REGISTRY.keys())


class TdxIndicators:
    """High-level indicator computation facade.

    Integrates with TdxQuery to fetch data and compute indicators
    in a single call. Also supports computing on an existing DataFrame.

    Usage:
        query = TdxQuery()
        ind = TdxIndicators(query)

        # By stock code
        df = ind.calc("000001", indicators=["ma", "macd", "rsi"])

        # On existing DataFrame
        df = TdxIndicators.compute(df, indicators=["ma", "bollinger"])
    """

    def __init__(self, query: TdxQuery):
        self._query = query

    def calc(self, code: str,
             indicators: list[str] | None = None,
             data_type: str = "daily",
             start_date: str | None = None,
             end_date: str | None = None,
             trade_date: str | None = None,
             **params) -> pd.DataFrame:
        """Fetch data for a stock and compute indicators.

        Args:
            code: Stock code, e.g. "000001"
            indicators: List of indicator names. None = all indicators.
            data_type: "daily", "minute_5", or "minute_1"
            start_date: Start date for daily data (YYYY-MM-DD)
            end_date: End date for daily data (YYYY-MM-DD)
            trade_date: Trade date for minute data (YYYY-MM-DD)
            **params: Per-indicator params, keyed by indicator name.
                      e.g. ma={"periods": [5, 10]}, rsi={"period": 6}
        """
        if data_type == "daily":
            df = self._query.get_daily(code, start_date=start_date, end_date=end_date)
        elif data_type == "minute_5":
            df = self._query.get_minute_5(code, trade_date=trade_date)
        elif data_type == "minute_1":
            df = self._query.get_minute_1(code, trade_date=trade_date)
        else:
            raise ValueError(f"Unknown data_type: {data_type}")

        if df is None or df.empty:
            return df

        return self._apply_indicators(df, indicators, params)

    @staticmethod
    def compute(df: pd.DataFrame,
                indicators: list[str] | None = None,
                **params) -> pd.DataFrame:
        """Compute indicators on an existing DataFrame (no TdxQuery needed)."""
        return TdxIndicators._apply_indicators_static(df, indicators, params)

    @staticmethod
    def available_indicators() -> list[str]:
        """Return list of available indicator names."""
        return _ALL_INDICATOR_NAMES.copy()

    def _apply_indicators(self, df: pd.DataFrame,
                          indicators: list[str] | None,
                          params: dict) -> pd.DataFrame:
        return self._apply_indicators_static(df, indicators, params)

    @staticmethod
    def _apply_indicators_static(df: pd.DataFrame,
                                 indicators: list[str] | None,
                                 params: dict) -> pd.DataFrame:
        # Ensure numeric types for OHLCV columns (MySQL may return Decimal)
        for col in ["open", "high", "low", "close", "volume", "amount",
                    "open_val", "high_val", "low_val", "close_val"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        names = indicators if indicators is not None else _ALL_INDICATOR_NAMES

        for name in names:
            if name not in _INDICATOR_REGISTRY:
                raise ValueError(
                    f"Unknown indicator: '{name}'. "
                    f"Available: {', '.join(_ALL_INDICATOR_NAMES)}"
                )
            func = _INDICATOR_REGISTRY[name]
            ind_params = params.get(name, {})
            if isinstance(ind_params, dict):
                df = func(df, **ind_params)
            else:
                df = func(df, ind_params)

        return df
