"""Data helper that wraps TdxQuery + TdxIndicators for agent consumption."""

import pandas as pd

from tdx_core.query import TdxQuery
from tdx_core.indicators import TdxIndicators


class AgentDataHelper:
    """Fetches OHLCV + computed indicators for a single stock."""

    def __init__(self, query: TdxQuery | None = None):
        self.query = query or TdxQuery()

    def fetch(self, code: str, bars: int = 120) -> pd.DataFrame | None:
        """Get daily bars + all available indicators with warm-up data."""
        df = self.query.get_daily(code)
        if df is None or df.empty:
            return None

        df = df.sort_values("trade_date").reset_index(drop=True)
        min_required = max(bars, 250) + 260
        if len(df) > min_required:
            df = df.iloc[-min_required:].copy()

        df["trade_date"] = df["trade_date"].astype(str)
        df = TdxIndicators.compute(df, indicators=TdxIndicators.available_indicators())
        return df

    def get_name(self, code: str) -> str:
        """Resolve stock name."""
        try:
            from tdx_core.names import get_name

            return get_name(code) or code
        except Exception:
            return code
