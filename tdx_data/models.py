"""数据模型与字段映射"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Market(Enum):
    SH = "sh"
    SZ = "sz"
    BJ = "bj"
    DS = "ds"


class DataType(Enum):
    DAILY = "daily"
    MINUTE_5 = "minute_5"
    MINUTE_1 = "minute_1"


class SyncStatus(Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class FileInfo:
    file_path: str
    market: str
    symbol: str
    data_type: str
    suffix: str
    file_size: int
    file_mtime: str
    md5_hash: Optional[str] = None


@dataclass
class SyncResult:
    rows_read: int = 0
    rows_written: int = 0
    rows_failed: int = 0
    failed_files: Optional[list] = None

    def __post_init__(self):
        if self.failed_files is None:
            self.failed_files = []

    @property
    def status(self) -> SyncStatus:
        if self.rows_failed == 0:
            return SyncStatus.SUCCESS
        if self.rows_written > 0:
            return SyncStatus.PARTIAL
        return SyncStatus.FAILED


# mootdx 列名 → 数据库列名映射（避免 MySQL 保留字）
COLUMN_MAP = {
    "open": "open_val",
    "high": "high_val",
    "low": "low_val",
    "close": "close_val",
    "volume": "volume",
    "amount": "amount",
}

STANDARD_COLUMNS = list(COLUMN_MAP.values())

# 数据类型 → 目标表名
TABLE_MAP = {
    "daily": "tdx_daily",
    "minute_5": "tdx_minute_5",
    "minute_1": "tdx_minute_1",
}
