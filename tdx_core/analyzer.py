"""Indicator analysis engine: cross-sectional scan, signal detection, backtest.

Usage:
    from tdx_core import TdxIndicatorAnalyzer, TdxQuery

    query = TdxQuery()
    analyzer = TdxIndicatorAnalyzer(query)

    # 1. 扫描全市场当前指标状态
    df = analyzer.scan(["000001", "000002", "600000"], indicator="rsi")

    # 2. 找出出现超卖信号的股票
    signals = analyzer.find_signals(
        ["000001", "000002", "600000"],
        indicator="rsi",
        signal_type="oversold",
        rsi={"period": 14}
    )

    # 3. 回测 MACD 金叉后5日收益
    report = analyzer.backtest(
        ["000001", "000002", "600000"],
        indicator="macd",
        signal_type="golden_cross",
        hold_days=5,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from .indicators.facade import TdxIndicators
from .query import TdxQuery

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Indicator profiles: output columns & signal detectors
# ---------------------------------------------------------------------------

SignalFunc = Callable[[pd.DataFrame, dict], pd.Series]


@dataclass
class IndicatorProfile:
    """Metadata for an indicator including signal detectors."""

    name: str
    # Function that returns list of column names produced by this indicator
    # given user params.
    get_columns: Callable[[dict], List[str]]
    # Signal name -> detector function (returns bool Series)
    signals: Dict[str, SignalFunc] = field(default_factory=dict)
    # Default lookback bars needed for meaningful calculation
    min_bars: int = 60


# ---------------------------------------------------------------------------
# Helper utilities for signal detectors
# ---------------------------------------------------------------------------


def _cross_above(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    """True when a crosses above b."""
    return (series_a > series_b) & (series_a.shift(1) <= series_b.shift(1))


def _cross_below(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    """True when a crosses below b."""
    return (series_a < series_b) & (series_a.shift(1) >= series_b.shift(1))


# ---------------------------------------------------------------------------
# Profile registry
# ---------------------------------------------------------------------------


def _macd_cols(_p: dict) -> List[str]:
    return ["macd", "macd_signal", "macd_hist"]


def _rsi_cols(p: dict) -> List[str]:
    return [f"rsi_{p.get('period', 14)}"]


def _bb_cols(_p: dict) -> List[str]:
    return ["bb_upper", "bb_middle", "bb_lower", "bb_bandwidth", "bb_pctb"]


def _ma_cols(p: dict) -> List[str]:
    periods = p.get("periods", [5, 10, 20, 60, 120, 250])
    return [f"ma_{x}" for x in periods]


def _stoch_cols(_p: dict) -> List[str]:
    return ["stoch_k", "stoch_d"]


def _supertrend_cols(_p: dict) -> List[str]:
    return ["supertrend", "supertrend_direction"]


def _sar_cols(_p: dict) -> List[str]:
    return ["sar"]


def _williams_cols(_p: dict) -> List[str]:
    return ["williams_r"]


def _cci_cols(p: dict) -> List[str]:
    return [f"cci_{p.get('period', 20)}"]


def _adx_cols(_p: dict) -> List[str]:
    return ["plus_di", "minus_di", "adx"]


def _aroon_cols(_p: dict) -> List[str]:
    return ["aroon_up", "aroon_down", "aroon_osc"]


def _td_cols(_p: dict) -> List[str]:
    return ["td_setup", "td_countdown"]


def _roc_cols(p: dict) -> List[str]:
    return [f"roc_{p.get('period', 12)}"]


def _momentum_cols(p: dict) -> List[str]:
    return [f"momentum_{p.get('period', 10)}"]


def _atr_cols(p: dict) -> List[str]:
    return [f"atr_{p.get('period', 14)}"]


def _keltner_cols(_p: dict) -> List[str]:
    return ["keltner_upper", "keltner_middle", "keltner_lower"]


def _donchian_cols(_p: dict) -> List[str]:
    return ["donchian_upper", "donchian_lower", "donchian_middle"]


def _stddev_cols(p: dict) -> List[str]:
    return [f"stddev_{p.get('period', 20)}"]


def _trix_cols(p: dict) -> List[str]:
    return ["trix"]


def _vortex_cols(_p: dict) -> List[str]:
    return ["vortex_pos", "vortex_neg"]


def _obv_cols(_p: dict) -> List[str]:
    return ["obv"]


def _vwap_cols(_p: dict) -> List[str]:
    return ["vwap"]


def _mfi_cols(p: dict) -> List[str]:
    return [f"mfi_{p.get('period', 14)}"]


def _cmf_cols(p: dict) -> List[str]:
    return [f"cmf_{p.get('period', 20)}"]


def _force_cols(p: dict) -> List[str]:
    return [f"force_index_{p.get('period', 13)}"]


def _eom_cols(p: dict) -> List[str]:
    return [f"eom_{p.get('period', 14)}"]


def _vol_roc_cols(p: dict) -> List[str]:
    return [f"vol_roc_{p.get('period', 12)}"]


def _nvi_cols(_p: dict) -> List[str]:
    return ["nvi"]


def _ao_cols(_p: dict) -> List[str]:
    return ["awesome_osc"]


def _uo_cols(_p: dict) -> List[str]:
    return ["ultimate_osc"]


def _stochrsi_cols(_p: dict) -> List[str]:
    return ["stochrsi_k", "stochrsi_d"]


def _ichimoku_cols(_p: dict) -> List[str]:
    return ["tenkan_sen", "kijun_sen", "senkou_span_a", "senkou_span_b", "chikou_span"]


def _ema_cols(p: dict) -> List[str]:
    periods = p.get("periods", [12, 26])
    return [f"ema_{x}" for x in periods]


def _sma_cols(p: dict) -> List[str]:
    periods = p.get("periods", [20])
    return [f"sma_{x}" for x in periods]


def _wma_cols(p: dict) -> List[str]:
    periods = p.get("periods", [20])
    return [f"wma_{x}" for x in periods]


def _dema_cols(p: dict) -> List[str]:
    periods = p.get("periods", [20])
    return [f"dema_{x}" for x in periods]


def _tema_cols(p: dict) -> List[str]:
    periods = p.get("periods", [20])
    return [f"tema_{x}" for x in periods]


def _pivot_cols(p: dict) -> List[str]:
    return ["pp", "r1", "s1", "r2", "s2", "r3", "s3"]


def _fib_cols(_p: dict) -> List[str]:
    return ["fib_0", "fib_236", "fib_382", "fib_500", "fib_618", "fib_786", "fib_1000"]


# ---------------------------------------------------------------------------
# Signal detectors
# ---------------------------------------------------------------------------


def _macd_golden_cross(df: pd.DataFrame, _p: dict) -> pd.Series:
    return _cross_above(df["macd"], df["macd_signal"])


def _macd_death_cross(df: pd.DataFrame, _p: dict) -> pd.Series:
    return _cross_below(df["macd"], df["macd_signal"])


def _macd_hist_positive(df: pd.DataFrame, _p: dict) -> pd.Series:
    return (df["macd_hist"] > 0) & (df["macd_hist"].shift(1) <= 0)


def _macd_hist_negative(df: pd.DataFrame, _p: dict) -> pd.Series:
    return (df["macd_hist"] < 0) & (df["macd_hist"].shift(1) >= 0)


def _rsi_oversold(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"rsi_{p.get('period', 14)}"
    return df[col] < 30


def _rsi_overbought(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"rsi_{p.get('period', 14)}"
    return df[col] > 70


def _bb_touch_lower(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["close_val"] <= df["bb_lower"]


def _bb_touch_upper(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["close_val"] >= df["bb_upper"]


def _bb_squeeze(df: pd.DataFrame, p: dict) -> pd.Series:
    """Bollinger bandwidth at 20-period low."""
    window = p.get("squeeze_period", 20)
    return df["bb_bandwidth"] == df["bb_bandwidth"].rolling(window=window, min_periods=1).min()


def _ma_bullish(df: pd.DataFrame, p: dict) -> pd.Series:
    """Short MA crosses above long MA (default 5 vs 20)."""
    short = p.get("short", 5)
    long = p.get("long", 20)
    return _cross_above(df[f"ma_{short}"], df[f"ma_{long}"])


def _ma_bearish(df: pd.DataFrame, p: dict) -> pd.Series:
    short = p.get("short", 5)
    long = p.get("long", 20)
    return _cross_below(df[f"ma_{short}"], df[f"ma_{long}"])


def _stoch_golden_cross(df: pd.DataFrame, _p: dict) -> pd.Series:
    return _cross_above(df["stoch_k"], df["stoch_d"])


def _stoch_death_cross(df: pd.DataFrame, _p: dict) -> pd.Series:
    return _cross_below(df["stoch_k"], df["stoch_d"])


def _stoch_oversold(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["stoch_k"] < 20


def _stoch_overbought(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["stoch_k"] > 80


def _supertrend_buy(df: pd.DataFrame, _p: dict) -> pd.Series:
    return (df["supertrend_direction"] == -1) & (df["supertrend_direction"].shift(1) == 1)


def _supertrend_sell(df: pd.DataFrame, _p: dict) -> pd.Series:
    return (df["supertrend_direction"] == 1) & (df["supertrend_direction"].shift(1) == -1)


def _sar_buy(df: pd.DataFrame, _p: dict) -> pd.Series:
    return (df["close_val"] > df["sar"]) & (df["close_val"].shift(1) <= df["sar"].shift(1))


def _sar_sell(df: pd.DataFrame, _p: dict) -> pd.Series:
    return (df["close_val"] < df["sar"]) & (df["close_val"].shift(1) >= df["sar"].shift(1))


def _williams_oversold(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["williams_r"] < -80


def _williams_overbought(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["williams_r"] > -20


def _cci_oversold(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"cci_{p.get('period', 20)}"
    return df[col] < -100


def _cci_overbought(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"cci_{p.get('period', 20)}"
    return df[col] > 100


def _adx_strong_trend(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["adx"] > 25


def _adx_trend_start(df: pd.DataFrame, _p: dict) -> pd.Series:
    return (df["adx"] > 20) & (df["adx"].shift(1) <= 20)


def _aroon_bullish(df: pd.DataFrame, _p: dict) -> pd.Series:
    return _cross_above(df["aroon_up"], df["aroon_down"])


def _aroon_bearish(df: pd.DataFrame, _p: dict) -> pd.Series:
    return _cross_below(df["aroon_up"], df["aroon_down"])


def _td_buy_setup(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["td_setup"] == 9


def _td_sell_setup(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["td_setup"] == -9


def _roc_positive(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"roc_{p.get('period', 12)}"
    return (df[col] > 0) & (df[col].shift(1) <= 0)


def _roc_negative(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"roc_{p.get('period', 12)}"
    return (df[col] < 0) & (df[col].shift(1) >= 0)


def _momentum_positive(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"momentum_{p.get('period', 10)}"
    return (df[col] > 0) & (df[col].shift(1) <= 0)


def _momentum_negative(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"momentum_{p.get('period', 10)}"
    return (df[col] < 0) & (df[col].shift(1) >= 0)


def _atr_spike(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"atr_{p.get('period', 14)}"
    return df[col] > df[col].rolling(window=20, min_periods=1).mean() * 1.5


def _keltner_breakout_up(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["close_val"] > df["keltner_upper"]


def _keltner_breakout_down(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["close_val"] < df["keltner_lower"]


def _donchian_breakout_up(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["close_val"] >= df["donchian_upper"]


def _donchian_breakout_down(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["close_val"] <= df["donchian_lower"]


def _stddev_expansion(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"stddev_{p.get('period', 20)}"
    return df[col] > df[col].rolling(window=20, min_periods=1).mean() * 1.5


def _trix_positive(df: pd.DataFrame, _p: dict) -> pd.Series:
    return (df["trix"] > 0) & (df["trix"].shift(1) <= 0)


def _trix_negative(df: pd.DataFrame, _p: dict) -> pd.Series:
    return (df["trix"] < 0) & (df["trix"].shift(1) >= 0)


def _vortex_bullish(df: pd.DataFrame, _p: dict) -> pd.Series:
    return _cross_above(df["vortex_pos"], df["vortex_neg"])


def _vortex_bearish(df: pd.DataFrame, _p: dict) -> pd.Series:
    return _cross_below(df["vortex_pos"], df["vortex_neg"])


def _obv_positive(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["obv"] > df["obv"].shift(1)


def _mfi_oversold(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"mfi_{p.get('period', 14)}"
    return df[col] < 20


def _mfi_overbought(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"mfi_{p.get('period', 14)}"
    return df[col] > 80


def _cmf_positive(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"cmf_{p.get('period', 20)}"
    return (df[col] > 0) & (df[col].shift(1) <= 0)


def _cmf_negative(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"cmf_{p.get('period', 20)}"
    return (df[col] < 0) & (df[col].shift(1) >= 0)


def _force_positive(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"force_index_{p.get('period', 13)}"
    return (df[col] > 0) & (df[col].shift(1) <= 0)


def _force_negative(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"force_index_{p.get('period', 13)}"
    return (df[col] < 0) & (df[col].shift(1) >= 0)


def _eom_positive(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"eom_{p.get('period', 14)}"
    return (df[col] > 0) & (df[col].shift(1) <= 0)


def _eom_negative(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"eom_{p.get('period', 14)}"
    return (df[col] < 0) & (df[col].shift(1) >= 0)


def _vol_roc_spike(df: pd.DataFrame, p: dict) -> pd.Series:
    col = f"vol_roc_{p.get('period', 12)}"
    return df[col] > 50


def _ao_positive(df: pd.DataFrame, _p: dict) -> pd.Series:
    return (df["awesome_osc"] > 0) & (df["awesome_osc"].shift(1) <= 0)


def _ao_negative(df: pd.DataFrame, _p: dict) -> pd.Series:
    return (df["awesome_osc"] < 0) & (df["awesome_osc"].shift(1) >= 0)


def _uo_oversold(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["ultimate_osc"] < 30


def _uo_overbought(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["ultimate_osc"] > 70


def _stochrsi_oversold(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["stochrsi_k"] < 20


def _stochrsi_overbought(df: pd.DataFrame, _p: dict) -> pd.Series:
    return df["stochrsi_k"] > 80


def _stochrsi_golden_cross(df: pd.DataFrame, _p: dict) -> pd.Series:
    return _cross_above(df["stochrsi_k"], df["stochrsi_d"])


def _stochrsi_death_cross(df: pd.DataFrame, _p: dict) -> pd.Series:
    return _cross_below(df["stochrsi_k"], df["stochrsi_d"])


def _ichimoku_bullish(df: pd.DataFrame, _p: dict) -> pd.Series:
    return (df["close_val"] > df["senkou_span_a"]) & (df["close_val"] > df["senkou_span_b"])


def _ichimoku_bearish(df: pd.DataFrame, _p: dict) -> pd.Series:
    return (df["close_val"] < df["senkou_span_a"]) & (df["close_val"] < df["senkou_span_b"])


def _ema_bullish(df: pd.DataFrame, p: dict) -> pd.Series:
    short = p.get("short", 12)
    long = p.get("long", 26)
    return _cross_above(df[f"ema_{short}"], df[f"ema_{long}"])


def _ema_bearish(df: pd.DataFrame, p: dict) -> pd.Series:
    short = p.get("short", 12)
    long = p.get("long", 26)
    return _cross_below(df[f"ema_{short}"], df[f"ema_{long}"])


def _pivot_near_support(df: pd.DataFrame, _p: dict) -> pd.Series:
    return (df["close_val"] - df["s1"]).abs() / df["close_val"] < 0.02


def _pivot_near_resistance(df: pd.DataFrame, _p: dict) -> pd.Series:
    return (df["close_val"] - df["r1"]).abs() / df["close_val"] < 0.02


# ---------------------------------------------------------------------------
# Build registry
# ---------------------------------------------------------------------------

INDICATOR_PROFILES: Dict[str, IndicatorProfile] = {
    "macd": IndicatorProfile(
        name="macd",
        get_columns=_macd_cols,
        signals={
            "golden_cross": _macd_golden_cross,
            "death_cross": _macd_death_cross,
            "hist_positive": _macd_hist_positive,
            "hist_negative": _macd_hist_negative,
        },
        min_bars=60,
    ),
    "rsi": IndicatorProfile(
        name="rsi",
        get_columns=_rsi_cols,
        signals={
            "oversold": _rsi_oversold,
            "overbought": _rsi_overbought,
        },
        min_bars=30,
    ),
    "bollinger": IndicatorProfile(
        name="bollinger",
        get_columns=_bb_cols,
        signals={
            "touch_lower": _bb_touch_lower,
            "touch_upper": _bb_touch_upper,
            "squeeze": _bb_squeeze,
        },
        min_bars=40,
    ),
    "ma": IndicatorProfile(
        name="ma",
        get_columns=_ma_cols,
        signals={
            "golden_cross": _ma_bullish,
            "death_cross": _ma_bearish,
        },
        min_bars=60,
    ),
    "stochastic": IndicatorProfile(
        name="stochastic",
        get_columns=_stoch_cols,
        signals={
            "golden_cross": _stoch_golden_cross,
            "death_cross": _stoch_death_cross,
            "oversold": _stoch_oversold,
            "overbought": _stoch_overbought,
        },
        min_bars=30,
    ),
    "supertrend": IndicatorProfile(
        name="supertrend",
        get_columns=_supertrend_cols,
        signals={
            "buy": _supertrend_buy,
            "sell": _supertrend_sell,
        },
        min_bars=30,
    ),
    "sar": IndicatorProfile(
        name="sar",
        get_columns=_sar_cols,
        signals={
            "buy": _sar_buy,
            "sell": _sar_sell,
        },
        min_bars=20,
    ),
    "williams_r": IndicatorProfile(
        name="williams_r",
        get_columns=_williams_cols,
        signals={
            "oversold": _williams_oversold,
            "overbought": _williams_overbought,
        },
        min_bars=20,
    ),
    "cci": IndicatorProfile(
        name="cci",
        get_columns=_cci_cols,
        signals={
            "oversold": _cci_oversold,
            "overbought": _cci_overbought,
        },
        min_bars=30,
    ),
    "adx": IndicatorProfile(
        name="adx",
        get_columns=_adx_cols,
        signals={
            "strong_trend": _adx_strong_trend,
            "trend_start": _adx_trend_start,
        },
        min_bars=30,
    ),
    "aroon": IndicatorProfile(
        name="aroon",
        get_columns=_aroon_cols,
        signals={
            "bullish": _aroon_bullish,
            "bearish": _aroon_bearish,
        },
        min_bars=30,
    ),
    "td_sequential": IndicatorProfile(
        name="td_sequential",
        get_columns=_td_cols,
        signals={
            "buy_setup": _td_buy_setup,
            "sell_setup": _td_sell_setup,
        },
        min_bars=20,
    ),
    "roc": IndicatorProfile(
        name="roc",
        get_columns=_roc_cols,
        signals={
            "positive": _roc_positive,
            "negative": _roc_negative,
        },
        min_bars=30,
    ),
    "momentum": IndicatorProfile(
        name="momentum",
        get_columns=_momentum_cols,
        signals={
            "positive": _momentum_positive,
            "negative": _momentum_negative,
        },
        min_bars=30,
    ),
    "atr": IndicatorProfile(
        name="atr",
        get_columns=_atr_cols,
        signals={
            "spike": _atr_spike,
        },
        min_bars=40,
    ),
    "keltner": IndicatorProfile(
        name="keltner",
        get_columns=_keltner_cols,
        signals={
            "breakout_up": _keltner_breakout_up,
            "breakout_down": _keltner_breakout_down,
        },
        min_bars=30,
    ),
    "donchian": IndicatorProfile(
        name="donchian",
        get_columns=_donchian_cols,
        signals={
            "breakout_up": _donchian_breakout_up,
            "breakout_down": _donchian_breakout_down,
        },
        min_bars=30,
    ),
    "std_dev": IndicatorProfile(
        name="std_dev",
        get_columns=_stddev_cols,
        signals={
            "expansion": _stddev_expansion,
        },
        min_bars=40,
    ),
    "trix": IndicatorProfile(
        name="trix",
        get_columns=_trix_cols,
        signals={
            "positive": _trix_positive,
            "negative": _trix_negative,
        },
        min_bars=40,
    ),
    "vortex": IndicatorProfile(
        name="vortex",
        get_columns=_vortex_cols,
        signals={
            "bullish": _vortex_bullish,
            "bearish": _vortex_bearish,
        },
        min_bars=30,
    ),
    "obv": IndicatorProfile(
        name="obv",
        get_columns=_obv_cols,
        signals={
            "positive": _obv_positive,
        },
        min_bars=20,
    ),
    "mfi": IndicatorProfile(
        name="mfi",
        get_columns=_mfi_cols,
        signals={
            "oversold": _mfi_oversold,
            "overbought": _mfi_overbought,
        },
        min_bars=30,
    ),
    "cmf": IndicatorProfile(
        name="cmf",
        get_columns=_cmf_cols,
        signals={
            "positive": _cmf_positive,
            "negative": _cmf_negative,
        },
        min_bars=30,
    ),
    "force_index": IndicatorProfile(
        name="force_index",
        get_columns=_force_cols,
        signals={
            "positive": _force_positive,
            "negative": _force_negative,
        },
        min_bars=30,
    ),
    "ease_of_movement": IndicatorProfile(
        name="ease_of_movement",
        get_columns=_eom_cols,
        signals={
            "positive": _eom_positive,
            "negative": _eom_negative,
        },
        min_bars=30,
    ),
    "volume_roc": IndicatorProfile(
        name="volume_roc",
        get_columns=_vol_roc_cols,
        signals={
            "spike": _vol_roc_spike,
        },
        min_bars=30,
    ),
    "awesome_oscillator": IndicatorProfile(
        name="awesome_oscillator",
        get_columns=_ao_cols,
        signals={
            "positive": _ao_positive,
            "negative": _ao_negative,
        },
        min_bars=40,
    ),
    "ultimate_oscillator": IndicatorProfile(
        name="ultimate_oscillator",
        get_columns=_uo_cols,
        signals={
            "oversold": _uo_oversold,
            "overbought": _uo_overbought,
        },
        min_bars=40,
    ),
    "stochrsi": IndicatorProfile(
        name="stochrsi",
        get_columns=_stochrsi_cols,
        signals={
            "golden_cross": _stochrsi_golden_cross,
            "death_cross": _stochrsi_death_cross,
            "oversold": _stochrsi_oversold,
            "overbought": _stochrsi_overbought,
        },
        min_bars=30,
    ),
    "ichimoku": IndicatorProfile(
        name="ichimoku",
        get_columns=_ichimoku_cols,
        signals={
            "bullish": _ichimoku_bullish,
            "bearish": _ichimoku_bearish,
        },
        min_bars=80,
    ),
    "ema": IndicatorProfile(
        name="ema",
        get_columns=_ema_cols,
        signals={
            "golden_cross": _ema_bullish,
            "death_cross": _ema_bearish,
        },
        min_bars=60,
    ),
    "pivot_points": IndicatorProfile(
        name="pivot_points",
        get_columns=_pivot_cols,
        signals={
            "near_support": _pivot_near_support,
            "near_resistance": _pivot_near_resistance,
        },
        min_bars=5,
    ),
}


# ---------------------------------------------------------------------------
# Analyzer class
# ---------------------------------------------------------------------------


class TdxIndicatorAnalyzer:
    """Analyze indicator performance across a universe of stocks."""

    def __init__(self, query: TdxQuery):
        self.query = query
        self._profiles = INDICATOR_PROFILES

    # ─── introspection ───

    def available_indicators(self) -> List[str]:
        """Return names of indicators supported by the analyzer."""
        return sorted(self._profiles.keys())

    def available_signals(self, indicator: str) -> List[str]:
        """Return signal types available for a given indicator."""
        profile = self._get_profile(indicator)
        return sorted(profile.signals.keys())

    # ─── scan ───

    def scan(
        self,
        codes: List[str],
        indicator: str,
        lookback: int = 120,
        params: Optional[dict] = None,
    ) -> pd.DataFrame:
        """Scan multiple stocks and return the latest indicator values.

        Args:
            codes: list of stock codes.
            indicator: indicator name, e.g. "rsi".
            lookback: minimum bars required for calculation.
            params: optional per-indicator params, e.g. {"period": 14}.

        Returns:
            DataFrame with columns:
                code, latest_date, <indicator columns...>, active_signals
        """
        profile = self._get_profile(indicator)
        params = params or {}
        rows = []

        for code in codes:
            df = self._fetch_and_compute(code, indicator, lookback, params)
            if df is None or len(df) < profile.min_bars:
                continue

            last = df.iloc[-1]
            latest_date = last["trade_date"]
            cols = profile.get_columns(params)
            indicator_vals = {c: last.get(c) for c in cols}

            # detect active signals on the latest bar
            active = [
                sig_name
                for sig_name, detector in profile.signals.items()
                if detector(df, params).iloc[-1]
            ]

            row = {
                "code": code,
                "latest_date": str(latest_date),
                "active_signals": ", ".join(active) if active else None,
            }
            row.update(indicator_vals)
            rows.append(row)

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    # ─── find signals ───

    def find_signals(
        self,
        codes: List[str],
        indicator: str,
        signal_type: str,
        lookback: int = 120,
        params: Optional[dict] = None,
    ) -> pd.DataFrame:
        """Find stocks where a specific signal occurred recently.

        Args:
            codes: list of stock codes.
            indicator: indicator name.
            signal_type: signal name, e.g. "golden_cross".
            lookback: how many recent bars to examine.
            params: optional per-indicator params.

        Returns:
            DataFrame with columns:
                code, signal_date, <indicator columns at signal date>
        """
        profile = self._get_profile(indicator)
        if signal_type not in profile.signals:
            raise ValueError(
                f"Unknown signal '{signal_type}' for {indicator}. "
                f"Available: {list(profile.signals.keys())}"
            )
        detector = profile.signals[signal_type]
        params = params or {}
        rows = []

        for code in codes:
            df = self._fetch_and_compute(code, indicator, lookback, params)
            if df is None or len(df) < profile.min_bars:
                continue

            mask = detector(df, params)
            signal_dates = df.loc[mask, "trade_date"]
            if signal_dates.empty:
                continue

            # Return the most recent signal for this stock
            latest_idx = signal_dates.index[-1]
            signal_date = signal_dates.iloc[-1]
            record = df.loc[latest_idx]
            cols = profile.get_columns(params)

            row = {
                "code": code,
                "signal_date": str(signal_date),
            }
            row.update({c: record.get(c) for c in cols})
            rows.append(row)

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    # ─── backtest ───

    def backtest(
        self,
        codes: List[str],
        indicator: str,
        signal_type: str,
        hold_days: int = 5,
        lookback: int = 252,
        params: Optional[dict] = None,
    ) -> dict:
        """Backtest a signal across multiple stocks.

        Args:
            codes: universe of stocks.
            indicator: indicator name.
            signal_type: signal to backtest.
            hold_days: how many bars to hold after signal.
            lookback: historical bars to fetch per stock.
            params: optional per-indicator params.

        Returns:
            dict with summary statistics and a detail DataFrame.
        """
        profile = self._get_profile(indicator)
        if signal_type not in profile.signals:
            raise ValueError(
                f"Unknown signal '{signal_type}' for {indicator}. "
                f"Available: {list(profile.signals.keys())}"
            )
        detector = profile.signals[signal_type]
        params = params or {}
        trades: List[dict] = []

        for code in codes:
            df = self._fetch_and_compute(code, indicator, lookback, params)
            if df is None or len(df) < profile.min_bars:
                continue

            mask = detector(df, params)
            signal_indices = df[mask].index
            if len(signal_indices) == 0:
                continue

            close = df["close_val"].values
            dates = df["trade_date"].values

            for idx in signal_indices:
                pos = df.index.get_loc(idx)
                if pos >= len(df) - 1:
                    continue
                buy_price = float(close[pos])
                sell_pos = min(pos + hold_days, len(close) - 1)
                sell_price = float(close[sell_pos])
                ret = (sell_price - buy_price) / buy_price * 100.0

                trades.append({
                    "code": code,
                    "buy_date": str(dates[pos]),
                    "sell_date": str(dates[sell_pos]),
                    "buy_price": round(buy_price, 2),
                    "sell_price": round(sell_price, 2),
                    "return_pct": round(ret, 2),
                })

        if not trades:
            return {
                "summary": {"total_signals": 0, "win_rate": None},
                "detail": pd.DataFrame(),
            }

        detail = pd.DataFrame(trades)
        returns = detail["return_pct"]
        wins = (returns > 0).sum()
        total = len(returns)

        summary = {
            "total_signals": total,
            "win_rate": round(wins / total * 100, 2) if total else None,
            "avg_return": round(returns.mean(), 2),
            "median_return": round(returns.median(), 2),
            "max_gain": round(returns.max(), 2),
            "max_loss": round(returns.min(), 2),
            "profit_factor": (
                round(returns[returns > 0].sum() / abs(returns[returns < 0].sum()), 2)
                if returns[returns < 0].sum() != 0 else float("inf")
            ),
            "sharpe_approx": (
                round(returns.mean() / returns.std(), 2) if returns.std() != 0 else 0.0
            ),
        }

        return {"summary": summary, "detail": detail}

    # ─── cross-sectional ranking ───

    def rank(
        self,
        codes: List[str],
        indicator: str,
        column: Optional[str] = None,
        lookback: int = 120,
        params: Optional[dict] = None,
        ascending: bool = True,
    ) -> pd.DataFrame:
        """Rank stocks by a specific indicator column.

        Args:
            codes: stock universe.
            indicator: indicator name.
            column: specific output column to rank by. Defaults to the first column.
            lookback: bars to fetch.
            params: optional per-indicator params.
            ascending: sort order.

        Returns:
            DataFrame sorted by the indicator value.
        """
        profile = self._get_profile(indicator)
        params = params or {}
        df_scan = self.scan(codes, indicator, lookback, params)
        if df_scan.empty:
            return df_scan

        cols = profile.get_columns(params)
        rank_col = column or cols[0]
        if rank_col not in df_scan.columns:
            raise ValueError(
                f"Column '{rank_col}' not found. Available: {cols}"
            )

        df_scan = df_scan.sort_values(by=rank_col, ascending=ascending)
        df_scan["rank"] = range(1, len(df_scan) + 1)
        return df_scan

    # ─── internal helpers ───

    def _get_profile(self, indicator: str) -> IndicatorProfile:
        if indicator not in self._profiles:
            raise ValueError(
                f"Indicator '{indicator}' not supported. "
                f"Available: {self.available_indicators()}"
            )
        return self._profiles[indicator]

    def _fetch_and_compute(
        self,
        code: str,
        indicator: str,
        lookback: int,
        params: dict,
    ) -> Optional[pd.DataFrame]:
        """Fetch daily data and compute indicator."""
        try:
            # Fetch extra bars so rolling windows have enough history
            buffer = lookback + 30
            df = self.query.get_daily(code)
            if df is None or df.empty:
                return None
            if len(df) > buffer:
                df = df.iloc[-buffer:].copy()
            # Ensure date column is string for consistent handling
            df = df.reset_index(drop=True)
            df["trade_date"] = df["trade_date"].astype(str)
            df = TdxIndicators.compute(df, [indicator], **{indicator: params})
            return df
        except Exception as exc:
            logger.debug("Failed to compute %s for %s: %s", indicator, code, exc)
            return None
