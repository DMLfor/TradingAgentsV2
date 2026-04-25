"""Technical indicator library for tdx_core.

Usage patterns:

1. Low-level functions (work on any DataFrame):
    from tdx_core.indicators import ma, macd, rsi, bollinger
    df = ma(df, periods=[5, 10, 20])

2. High-level facade (integrates with TdxQuery):
    from tdx_core import TdxQuery, TdxIndicators
    query = TdxQuery()
    indicators = TdxIndicators(query)
    df = indicators.calc("000001", indicators=["ma", "rsi"])
"""

# Core utilities
from ._core import normalize_ohlcv, restore_ohlcv, validate_ohlcv, true_range, IndicatorError

# Trend indicators
from .trend import (ma, ema, sma, wma, dema, tema, macd, adx, aroon,
                    ichimoku, sar, supertrend, trix, vortex)

# Momentum indicators
from .momentum import (rsi, stochastic, williams_r, cci, roc, momentum as momentum_ind,
                       stochrsi, ultimate_oscillator, awesome_oscillator)

# Volatility indicators
from .volatility import (bollinger, atr, keltner, donchian, std_dev,
                         chaikin_volatility)

# Volume indicators
from .volume import (obv, vwap, mfi, ad_line, chaikin_money_flow,
                     force_index, ease_of_movement, volume_roc, nvi)

# Composite indicators
from .composite import pivot_points, fibonacci_retracement, td_sequential

# Facade
from .facade import TdxIndicators

__all__ = [
    # Core
    "normalize_ohlcv", "restore_ohlcv", "validate_ohlcv", "true_range",
    "IndicatorError",
    # Trend
    "ma", "ema", "sma", "wma", "dema", "tema", "macd", "adx", "aroon",
    "ichimoku", "sar", "supertrend", "trix", "vortex",
    # Momentum
    "rsi", "stochastic", "williams_r", "cci", "roc", "momentum_ind",
    "stochrsi", "ultimate_oscillator", "awesome_oscillator",
    # Volatility
    "bollinger", "atr", "keltner", "donchian", "std_dev", "chaikin_volatility",
    # Volume
    "obv", "vwap", "mfi", "ad_line", "chaikin_money_flow", "force_index",
    "ease_of_movement", "volume_roc", "nvi",
    # Composite
    "pivot_points", "fibonacci_retracement", "td_sequential",
    # Facade
    "TdxIndicators",
]
