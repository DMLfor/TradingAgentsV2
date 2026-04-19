"""TDX Data — 通信达行情数据读取与查询包

快速上手:
    from tdx_data import TdxQuery

    with TdxQuery() as q:
        df = q.get_daily("000001")
        codes = q.get_stock_list()
"""
from .config import TdxConfig
from .db import TdxDatabase
from .models import DataType, Market, SyncStatus
from .query import TdxQuery

__all__ = [
    "TdxConfig",
    "TdxDatabase",
    "TdxQuery",
    "Market",
    "DataType",
    "SyncStatus",
]
