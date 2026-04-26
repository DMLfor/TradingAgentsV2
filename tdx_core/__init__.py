"""TDX Data — 通信达行情数据读取与查询包

快速上手:
    from tdx_core import TdxQuery

    with TdxQuery() as q:
        df = q.get_daily("000001")
        codes = q.get_stock_list()
"""
from .config import TdxConfig
from .db import TdxDatabase
from .models import DataType, Market, SyncStatus
from .query import TdxQuery
from .indicators.facade import TdxIndicators
from .analyzer import TdxIndicatorAnalyzer
from .names import (
    get_name,
    get_code,
    resolve_code,
    resolve_codes,
    fuzzy_search,
    reload as reload_names,
)
from .metadata import (
    get_meta,
    get_level1,
    get_level2,
    get_level3,
    get_board,
    by_level1,
    by_level2,
    by_level3,
    by_board,
    filter_stocks,
    list_level1,
    list_level2,
    list_level3,
    list_boards,
    sector_stats,
)
from .watchlist import WatchlistManager

__all__ = [
    "TdxConfig",
    "TdxDatabase",
    "TdxQuery",
    "Market",
    "DataType",
    "SyncStatus",
    "TdxIndicators",
    "TdxIndicatorAnalyzer",
    "get_name",
    "get_code",
    "resolve_code",
    "resolve_codes",
    "fuzzy_search",
    "reload_names",
    "get_meta",
    "get_level1",
    "get_level2",
    "get_level3",
    "get_board",
    "by_level1",
    "by_level2",
    "by_level3",
    "by_board",
    "filter_stocks",
    "list_level1",
    "list_level2",
    "list_level3",
    "list_boards",
    "sector_stats",
]
