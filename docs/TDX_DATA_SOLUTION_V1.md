# 通信达数据解析与自动化更新方案 V1

> 基于目录 `C:\new_tdx_mock`，采用 mootdx 作为解析引擎

---

## 1. 目录结构

```
TradingAgentsV2/
├── docs/
│   └── TDX_DATA_SOLUTION_V1.md          # 本文档
├── tdx_core/
│   ├── __init__.py
│   ├── config.py                         # 全局配置（路径、数据库、批次参数）
│   ├── reader.py                         # TdxReader 封装类（基于 mootdx）
│   ├── db.py                             # 数据库操作层（DDL / CRUD / MERGE）
│   ├── scanner.py                        # 目录扫描与变更检测
│   ├── sync.py                           # 增量同步引擎
│   ├── models.py                         # 数据模型与字段映射
│   └── notify.py                         # 邮件/钉钉通知
├── scripts/
│   ├── tdx_sync.py                       # 定时任务主入口
│   ├── tdx_init_db.py                    # 建库建表脚本
│   └── tdx_full_import.py                # 首次全量导入脚本
├── tests/
│   ├── __init__.py
│   ├── test_reader.py
│   ├── test_db.py
│   ├── test_scanner.py
│   ├── test_sync.py
│   └── conftest.py                       # pytest fixtures & mock 数据
├── sql/
│   ├── schema.sql                        # DDL
│   └── indexes.sql                       # 索引
├── config/
│   ├── tdx_config.yaml                   # 运行配置
│   └── logging.conf                      # 日志配置
├── requirements.txt
├── setup.py
└── README.md
```

---

## 2. 源数据结构分析

### 2.1 实际目录布局

```
C:\new_tdx_mock\vipdoc\
├── sh\lday\      # 沪市日线  sh000001.day ~ sh68XXXXX.day  (4,734 files)
├── sz\lday\      # 深市日线  sz000001.day ~ sz3XXXXXX.day  (4,225 files)
├── bj\lday\      # 北交所日线 bj920000.day ~ ...           (311 files)
├── ds\lday\      # 大宗/外汇  10#AUDUSD.day ~ ...           (51,425 files)
├── sh\fzline\    # 沪市5分钟线 (空)
├── sz\fzline\    # 深市5分钟线 (空)
├── bj\fzline\    # 北交所5分钟线 (空)
├── sh\minline\   # 沪市1分钟线 (空)
├── sz\minline\   # 深市1分钟线 (空)
├── bj\minline\   # 北交所1分钟线 (空)
├── sh\eday\      # 沪市扩展日线 (空)
├── sz\eday\      # 深市扩展日线 (空)
└── bj\eday\      # 北交所扩展日线 (空)
```

### 2.2 文件格式

| 扩展名 | 目录 | 记录长度 | 字段 | 说明 |
|--------|------|---------|------|------|
| `.day` | lday | 32 bytes | date(4)+open(4)+high(4)+low(4)+close(4)+amount(4)+volume(4)+reserved(4) | 日线 |
| `.lc5` | fzline | 32 bytes | date(4)+open(4)+high(4)+low(4)+close(4)+amount(4)+volume(4)+reserved(4) | 5分钟线 |
| `.lc1` | minline | 32 bytes | 同上 | 1分钟线 |

所有数值为 little-endian unsigned int；价格需除以 100 得到真实价格（保留2位小数）；amount 为成交额（元），volume 为成交量（手）。

### 2.3 mootdx 验证结果

```python
from mootdx.reader import Reader
reader = Reader.factory(market='std', tdxdir='C:/new_tdx_mock')
df = reader.daily(symbol='000001')
# columns: ['open', 'high', 'low', 'close', 'amount', 'volume']
# index:   DatetimeIndex (date)
# shape:   (1140, 6)
```

- mootdx `StdReader` 自动解析 `.day` 文件，返回标准 DataFrame
- 北交所(BJ)股票需自定义路径解析（mootdx 不原生支持 bj 前缀）
- 大宗/外汇(ds)需 `ExtReader`，部分 symbol 解析需扩展
- 5分钟/1分钟目录当前为空，预留接口

---

## 3. 数据库设计

### 3.1 技术选型

**SQLite**（默认）——零部署、单文件、满足日均百万级写入。提供 PostgreSQL DDL 作为备选。

### 3.2 ER 图

```
┌──────────────────┐       ┌──────────────────────┐       ┌──────────────────────┐
│    tdx_daily      │       │    tdx_minute_5       │       │    tdx_minute_1      │
├──────────────────┤       ├──────────────────────┤       ├──────────────────────┤
│ PK code  TEXT     │       │ PK code  TEXT         │       │ PK code  TEXT        │
│ PK trade_date DATE│       │ PK trade_date DATETIME│       │ PK trade_date DATETIME│
│    open   REAL    │       │    open   REAL        │       │    open   REAL       │
│    high   REAL    │       │    high   REAL        │       │    high   REAL       │
│    low    REAL    │       │    low    REAL        │       │    low    REAL       │
│    close  REAL    │       │    close  REAL        │       │    close  REAL       │
│    volume REAL    │       │    volume REAL        │       │    volume REAL       │
│    amount REAL    │       │    amount REAL        │       │    amount REAL       │
│    adj_factor REAL│       │    adj_factor REAL    │       │    adj_factor REAL   │
│    is_suspended INT│      │    is_suspended INT   │       │    is_suspended INT  │
│    created_at TEXT │       │    created_at TEXT    │       │    created_at TEXT   │
│    updated_at TEXT │       │    updated_at TEXT    │       │    updated_at TEXT   │
└──────────────────┘       └──────────────────────┘       └──────────────────────┘

┌──────────────────────┐       ┌──────────────────────┐
│    tdx_sync_log      │       │    tdx_file_registry │
├──────────────────────┤       ├──────────────────────┤
│ PK id        INTEGER │       │ PK file_path TEXT     │
│    sync_date TEXT     │       │    market    TEXT     │
│    market    TEXT     │       │    symbol    TEXT     │
│    data_type  TEXT    │       │    data_type  TEXT    │
│    rows_read  INT     │       │    file_size  INT     │
│    rows_written INT   │       │    file_mtime TEXT    │
│    rows_failed INT    │       │    record_count INT   │
│    duration_sec REAL  │       │    last_synced TEXT   │
│    status    TEXT     │       │    md5_hash   TEXT    │
│    error_msg  TEXT    │       │    created_at TEXT    │
│    created_at TEXT    │       │    updated_at TEXT    │
└──────────────────────┘       └──────────────────────┘
```

### 3.3 DDL 脚本

```sql
-- sql/schema.sql

-- 日线主表
CREATE TABLE IF NOT EXISTS tdx_daily (
    code        TEXT    NOT NULL,
    trade_date  DATE    NOT NULL,
    open        REAL    NOT NULL,
    high        REAL    NOT NULL,
    low         REAL    NOT NULL,
    close       REAL    NOT NULL,
    volume      REAL    NOT NULL,
    amount      REAL    NOT NULL,
    adj_factor  REAL    DEFAULT 1.0,
    is_suspended INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (code, trade_date)
) WITHOUT ROWID;

-- 5分钟线
CREATE TABLE IF NOT EXISTS tdx_minute_5 (
    code        TEXT    NOT NULL,
    trade_date  DATETIME NOT NULL,
    open        REAL    NOT NULL,
    high        REAL    NOT NULL,
    low         REAL    NOT NULL,
    close       REAL    NOT NULL,
    volume      REAL    NOT NULL,
    amount      REAL    NOT NULL,
    adj_factor  REAL    DEFAULT 1.0,
    is_suspended INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (code, trade_date)
) WITHOUT ROWID;

-- 1分钟线
CREATE TABLE IF NOT EXISTS tdx_minute_1 (
    code        TEXT    NOT NULL,
    trade_date  DATETIME NOT NULL,
    open        REAL    NOT NULL,
    high        REAL    NOT NULL,
    low         REAL    NOT NULL,
    close       REAL    NOT NULL,
    volume      REAL    NOT NULL,
    amount      REAL    NOT NULL,
    adj_factor  REAL    DEFAULT 1.0,
    is_suspended INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (code, trade_date)
) WITHOUT ROWID;

-- 文件注册表（增量更新依据）
CREATE TABLE IF NOT EXISTS tdx_file_registry (
    file_path   TEXT    PRIMARY KEY,
    market      TEXT    NOT NULL,
    symbol      TEXT    NOT NULL,
    data_type   TEXT    NOT NULL,  -- 'daily' / 'minute_5' / 'minute_1'
    file_size   INTEGER NOT NULL,
    file_mtime  TEXT    NOT NULL,
    record_count INTEGER DEFAULT 0,
    last_synced TEXT,
    md5_hash    TEXT,
    created_at  TEXT    DEFAULT (datetime('now')),
    updated_at  TEXT    DEFAULT (datetime('now'))
);

-- 同步日志
CREATE TABLE IF NOT EXISTS tdx_sync_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_date   TEXT    NOT NULL,
    market      TEXT,
    data_type   TEXT,
    rows_read   INTEGER DEFAULT 0,
    rows_written INTEGER DEFAULT 0,
    rows_failed INTEGER DEFAULT 0,
    duration_sec REAL   DEFAULT 0.0,
    status      TEXT    NOT NULL,  -- 'success' / 'partial' / 'failed'
    error_msg   TEXT,
    created_at  TEXT    DEFAULT (datetime('now'))
);
```

```sql
-- sql/indexes.sql

CREATE INDEX IF NOT EXISTS idx_daily_date ON tdx_daily(trade_date);
CREATE INDEX IF NOT EXISTS idx_daily_code_date ON tdx_daily(code, trade_date);
CREATE INDEX IF NOT EXISTS idx_min5_date ON tdx_minute_5(trade_date);
CREATE INDEX IF NOT EXISTS idx_min5_code ON tdx_minute_5(code);
CREATE INDEX IF NOT EXISTS idx_min1_date ON tdx_minute_1(trade_date);
CREATE INDEX IF NOT EXISTS idx_min1_code ON tdx_minute_1(code);
CREATE INDEX IF NOT EXISTS idx_registry_mtime ON tdx_file_registry(file_mtime);
CREATE INDEX IF NOT EXISTS idx_registry_symbol ON tdx_file_registry(symbol);
CREATE INDEX IF NOT EXISTS idx_synclog_date ON tdx_sync_log(sync_date);
```

---

## 4. 核心流程图

### 4.1 全量导入流程

```
┌─────────────┐
│   启动脚本    │
└──────┬──────┘
       ▼
┌─────────────────┐
│ 扫描 vipdoc 目录 │──── 获取所有 .day/.lc5/.lc1 文件列表
└──────┬──────────┘
       ▼
┌──────────────────┐
│ 文件分类与排序    │──── 按 market → data_type 分组
└──────┬───────────┘
       ▼
┌───────────────────┐
│ 逐文件调用 mootdx │──── Reader.daily / minute / fzline
│   解析为 DataFrame │
└──────┬────────────┘
       ▼
┌───────────────────┐
│  字段标准化        │──── 统一列名、类型、精度
│  + 股票代码提取    │
└──────┬────────────┘
       ▼
┌───────────────────┐
│ 批量写入临时表     │──── stg_tdx_daily (无 PK 约束)
│  batch_size=5000  │
└──────┬────────────┘
       ▼
┌───────────────────┐
│ MERGE 到主表       │──── INSERT OR REPLACE / UPSERT
└──────┬────────────┘
       ▼
┌───────────────────┐
│ 更新 file_registry │──── 记录 mtime / md5 / record_count
└──────┬────────────┘
       ▼
┌───────────────────┐
│ 写入 sync_log      │
└──────┬────────────┘
       ▼
┌───────────────────┐
│ 发送通知摘要       │
└───────────────────┘
```

### 4.2 增量更新流程

```
┌──────────────┐
│ 定时任务触发   │
└──────┬───────┘
       ▼
┌──────────────────────┐
│ 读取 tdx_file_registry│──── 获取已知文件的 mtime/size
└──────┬───────────────┘
       ▼
┌──────────────────────┐
│ 扫描 vipdoc 目录      │──── 获取当前文件 mtime/size
└──────┬───────────────┘
       ▼
┌────────────────────────────┐
│ Diff：对比 mtime/size 变化  │
│ - 新增文件 → 全量解析       │
│ - 变更文件 → 全量解析+MERGE │
│ - 无变化   → 跳过           │
└──────┬─────────────────────┘
       ▼
┌──────────────────────┐
│ 仅处理变更集          │──── 调用 mootdx 解析
└──────┬───────────────┘
       ▼
┌──────────────────────┐
│ 临时表 → MERGE 主表   │
└──────┬───────────────┘
       ▼
┌──────────────────────┐
│ 更新 registry + log  │
└──────┬───────────────┘
       ▼
┌──────────────────────┐
│ 通知（有变更时）      │
└──────────────────────┘
```

---

## 5. 关键模块伪代码

### 5.1 config.py

```python
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class TdxConfig:
    tdx_dir: str = r"C:\new_tdx_mock"
    db_path: str = "tdx_data.db"
    batch_size: int = 5000
    max_retries: int = 3
    retry_delay: float = 1.0
    log_dir: str = "logs"
    log_retention_days: int = 30

    # 通知配置
    dingtalk_webhook: str = ""
    smtp_host: str = ""
    smtp_port: int = 465
    notify_email: str = ""

    # 目录映射
    MARKET_MAP = {
        "sh": "std",   # 沪市 → StdReader
        "sz": "std",   # 深市 → StdReader
        "bj": "std",   # 北交所 → StdReader (需自定义路径)
        "ds": "ext",   # 大宗/外汇 → ExtReader
    }

    DATA_TYPE_MAP = {
        "lday":    {"suffix": "day", "table": "tdx_daily",     "reader": "daily"},
        "fzline":  {"suffix": "lc5", "table": "tdx_minute_5", "reader": "fzline"},
        "minline": {"suffix": "lc1", "table": "tdx_minute_1", "reader": "minute"},
    }
```

### 5.2 reader.py — TdxReader

```python
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Optional
import pandas as pd
from mootdx.reader import Reader
from .config import TdxConfig

logger = logging.getLogger(__name__)

class TdxReader:
    """通信达数据读取器，基于 mootdx 封装"""

    STANDARD_COLUMNS = ["open", "high", "low", "close", "volume", "amount"]

    def __init__(self, config: Optional[TdxConfig] = None):
        self.config = config or TdxConfig()
        self._std_reader = Reader.factory(
            market="std", tdxdir=self.config.tdx_dir
        )
        self._ext_reader = Reader.factory(
            market="ext", tdxdir=self.config.tdx_dir
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def read_daily(self, code: str, market: str = "auto") -> pd.DataFrame:
        """读取日线数据
        Args:
            code: 股票代码，如 '000001'、'920000'、'10#AUDUSD'
            market: 'sh'/'sz'/'bj'/'ds'/'auto'
        Returns:
            DataFrame with columns: [open, high, low, close, volume, amount]
            index: DatetimeIndex (trade_date)
        """
        try:
            reader = self._get_reader(code, market)
            df = reader.daily(symbol=code)
            return self._normalize(df, code)
        except FileNotFoundError:
            logger.warning(f"File not found for code={code}")
            return pd.DataFrame(columns=self.STANDARD_COLUMNS)
        except Exception as e:
            logger.error(f"Failed to read daily code={code}: {e}")
            raise TdxReadError(f"Read daily failed: {code}") from e

    def read_minute(self, code: str, market: str = "auto") -> pd.DataFrame:
        """读取1分钟线"""
        try:
            reader = self._get_reader(code, market)
            df = reader.minute(symbol=code)
            return self._normalize(df, code)
        except Exception as e:
            logger.error(f"Failed to read minute code={code}: {e}")
            raise TdxReadError(f"Read minute failed: {code}") from e

    def read_fzline(self, code: str, market: str = "auto") -> pd.DataFrame:
        """读取5分钟线"""
        try:
            reader = self._get_reader(code, market)
            df = reader.fzline(symbol=code)
            return self._normalize(df, code)
        except Exception as e:
            logger.error(f"Failed to read fzline code={code}: {e}")
            raise TdxReadError(f"Read fzline failed: {code}") from e

    def read_daily_by_file(self, file_path: str) -> pd.DataFrame:
        """直接按文件路径读取（兼容 BJ/DS 等非标准路径）"""
        path = Path(file_path)
        # 从文件名提取 code 和 market
        stem = path.stem          # e.g. 'sh000001', 'bj920000'
        market = stem[:2]         # 'sh', 'sz', 'bj', 'ds'
        code = stem[2:]           # '000001', '920000'

        try:
            reader = MooTdxDailyBarReader()
            df = reader.get_df(str(path))
            return self._normalize(df, code)
        except Exception as e:
            logger.error(f"Failed to read file={file_path}: {e}")
            raise TdxReadError(f"Read file failed: {file_path}") from e

    def _get_reader(self, code: str, market: str):
        if market == "ds" or "#" in code:
            return self._ext_reader
        return self._std_reader

    def _normalize(self, df: pd.DataFrame, code: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=self.STANDARD_COLUMNS)
        df = df.copy()
        df["code"] = code
        # 确保列名标准化
        df = df.rename(columns={
            "amount": "amount",
            "volume": "volume",
        })
        # 确保数值精度
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df[col] = df[col].round(2)
        return df

class TdxReadError(Exception):
    pass
```

### 5.3 scanner.py — 目录扫描与变更检测

```python
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import List
from .config import TdxConfig

logger = logging.getLogger(__name__)

@dataclass
class FileInfo:
    file_path: str
    market: str          # sh / sz / bj / ds
    symbol: str          # 000001
    data_type: str       # daily / minute_5 / minute_1
    suffix: str          # day / lc5 / lc1
    file_size: int
    file_mtime: str      # ISO format
    md5_hash: str = ""

class TdxScanner:
    SUPPORTED_SUFFIXES = {"day", "lc5", "lc1"}
    SUBDIR_MAP = {
        "lday":    ("daily",     "day"),
        "fzline":  ("minute_5",  "lc5"),
        "minline": ("minute_1",  "lc1"),
    }

    def __init__(self, config: TdxConfig = None):
        self.config = config or TdxConfig()

    def scan_all(self) -> List[FileInfo]:
        """递归扫描 vipdoc 下所有数据文件"""
        vipdoc = Path(self.config.tdx_dir) / "vipdoc"
        results = []
        for market_dir in vipdoc.iterdir():
            if not market_dir.is_dir():
                continue
            market = market_dir.name  # sh / sz / bj / ds
            for subdir in market_dir.iterdir():
                if not subdir.is_dir():
                    continue
                subdir_name = subdir.name  # lday / fzline / minline
                if subdir_name not in self.SUBDIR_MAP:
                    continue
                data_type, suffix = self.SUBDIR_MAP[subdir_name]
                for f in subdir.glob(f"*.{suffix}"):
                    results.append(FileInfo(
                        file_path=str(f),
                        market=market,
                        symbol=self._extract_symbol(f.name, market),
                        data_type=data_type,
                        suffix=suffix,
                        file_size=f.stat().st_size,
                        file_mtime=self._mtime_iso(f),
                    ))
        return results

    def detect_changes(self, known: dict, current: List[FileInfo]) -> dict:
        """对比已知文件与当前文件，返回变更集
        Args:
            known: {file_path: FileInfo} from db
            current: [FileInfo] from scan
        Returns:
            {"new": [...], "modified": [...], "unchanged": [...]}
        """
        new, modified, unchanged = [], [], []
        current_map = {f.file_path: f for f in current}

        for fi in current:
            if fi.file_path not in known:
                new.append(fi)
            elif (fi.file_mtime != known[fi.file_path].file_mtime
                  or fi.file_size != known[fi.file_path].file_size):
                modified.append(fi)
            else:
                unchanged.append(fi)

        return {"new": new, "modified": modified, "unchanged": unchanged}

    @staticmethod
    def _extract_symbol(filename: str, market: str) -> str:
        stem = Path(filename).stem
        if market in ("sh", "sz", "bj"):
            return stem[2:]  # sh000001 → 000001
        return stem           # 10#AUDUSD → 10#AUDUSD

    @staticmethod
    def _mtime_iso(path: Path) -> str:
        from datetime import datetime
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts).isoformat()
```

### 5.4 sync.py — 增量同步引擎

```python
import logging
import time
from typing import List
from .config import TdxConfig
from .reader import TdxReader
from .scanner import TdxScanner, FileInfo
from .db import TdxDatabase

logger = logging.getLogger(__name__)

class TdxSyncEngine:
    def __init__(self, config: TdxConfig = None):
        self.config = config or TdxConfig()
        self.reader = TdxReader(self.config)
        self.scanner = TdxScanner(self.config)
        self.db = TdxDatabase(self.config)

    def full_import(self):
        """首次全量导入"""
        start = time.time()
        all_files = self.scanner.scan_all()
        logger.info(f"Full import: found {len(all_files)} files")

        results = self._process_files(all_files, is_full=True)
        duration = time.time() - start
        self._log_sync("full", results, duration)
        return results

    def incremental_sync(self):
        """增量同步"""
        start = time.time()
        current_files = self.scanner.scan_all()
        known_files = self.db.get_file_registry()

        changes = self.scanner.detect_changes(known_files, current_files)
        to_process = changes["new"] + changes["modified"]
        logger.info(
            f"Incremental sync: new={len(changes['new'])}, "
            f"modified={len(changes['modified'])}, "
            f"unchanged={len(changes['unchanged'])}"
        )

        if not to_process:
            logger.info("No changes detected")
            return None

        results = self._process_files(to_process, is_full=False)
        duration = time.time() - start
        self._log_sync("incremental", results, duration)
        return results

    def _process_files(self, files: List[FileInfo], is_full: bool) -> dict:
        total_read, total_written, total_failed = 0, 0, 0
        failed_files = []

        for fi in files:
            for attempt in range(1, self.config.max_retries + 1):
                try:
                    df = self._read_file(fi)
                    if df.empty:
                        continue
                    rows_read = len(df)
                    total_read += rows_read

                    rows_written = self.db.upsert_dataframe(
                        df, table=self._table_name(fi),
                        batch_size=self.config.batch_size
                    )
                    total_written += rows_written

                    self.db.update_file_registry(fi, rows_read)
                    break

                except Exception as e:
                    logger.warning(
                        f"Attempt {attempt}/{self.config.max_retries} "
                        f"failed for {fi.file_path}: {e}"
                    )
                    if attempt == self.config.max_retries:
                        total_failed += 1
                        failed_files.append(fi.file_path)
                        logger.error(
                            f"All retries exhausted: {fi.file_path}"
                        )
                    else:
                        time.sleep(self.config.retry_delay)

        return {
            "rows_read": total_read,
            "rows_written": total_written,
            "rows_failed": total_failed,
            "failed_files": failed_files,
        }

    def _read_file(self, fi: FileInfo):
        if fi.data_type == "daily":
            return self.reader.read_daily_by_file(fi.file_path)
        elif fi.data_type == "minute_5":
            return self.reader.read_fzline(fi.symbol, fi.market)
        elif fi.data_type == "minute_1":
            return self.reader.read_minute(fi.symbol, fi.market)
        raise ValueError(f"Unknown data_type: {fi.data_type}")

    def _table_name(self, fi: FileInfo) -> str:
        return {
            "daily": "tdx_daily",
            "minute_5": "tdx_minute_5",
            "minute_1": "tdx_minute_1",
        }[fi.data_type]

    def _log_sync(self, mode, results, duration):
        self.db.insert_sync_log(
            sync_date=time.strftime("%Y-%m-%d"),
            mode=mode,
            rows_read=results["rows_read"],
            rows_written=results["rows_written"],
            rows_failed=results["rows_failed"],
            duration_sec=duration,
            status="success" if not results["failed_files"] else "partial",
        )
```

### 5.5 db.py — 数据库操作层

```python
import logging
import sqlite3
from pathlib import Path
from typing import Dict, Optional
import pandas as pd
from .config import TdxConfig
from .scanner import FileInfo

logger = logging.getLogger(__name__)

class TdxDatabase:
    def __init__(self, config: TdxConfig = None):
        self.config = config or TdxConfig()
        self.db_path = self.config.db_path
        self._init_schema()

    def _init_schema(self):
        sql_dir = Path(__file__).parent.parent / "sql"
        with sqlite3.connect(self.db_path) as conn:
            for sql_file in ["schema.sql", "indexes.sql"]:
                path = sql_dir / sql_file
                if path.exists():
                    conn.executescript(path.read_text(encoding="utf-8"))

    def upsert_dataframe(self, df: pd.DataFrame, table: str,
                         batch_size: int = 5000) -> int:
        """MERGE 模式写入：INSERT OR REPLACE"""
        total = 0
        with sqlite3.connect(self.db_path) as conn:
            for start in range(0, len(df), batch_size):
                batch = df.iloc[start:start + batch_size]
                batch.to_sql(
                    f"stg_{table}", conn,
                    if_exists="replace", index=True,
                    index_label="trade_date"
                )
                # MERGE from staging
                conn.execute(f"""
                    INSERT OR REPLACE INTO {table}
                        (code, trade_date, open, high, low, close,
                         volume, amount, updated_at)
                    SELECT code, trade_date, open, high, low, close,
                           volume, amount, datetime('now')
                    FROM stg_{table}
                """)
                conn.execute(f"DROP TABLE IF EXISTS stg_{table}")
                total += len(batch)
        return total

    def get_file_registry(self) -> Dict[str, FileInfo]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM tdx_file_registry"
            ).fetchall()
        return {
            r["file_path"]: FileInfo(
                file_path=r["file_path"],
                market=r["market"],
                symbol=r["symbol"],
                data_type=r["data_type"],
                suffix="",
                file_size=r["file_size"],
                file_mtime=r["file_mtime"],
            )
            for r in rows
        }

    def update_file_registry(self, fi: FileInfo, record_count: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tdx_file_registry
                    (file_path, market, symbol, data_type,
                     file_size, file_mtime, record_count,
                     last_synced, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """, (fi.file_path, fi.market, fi.symbol, fi.data_type,
                  fi.file_size, fi.file_mtime, record_count))

    def insert_sync_log(self, **kwargs):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO tdx_sync_log
                    (sync_date, market, data_type, rows_read,
                     rows_written, rows_failed, duration_sec,
                     status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (kwargs.get("sync_date"), kwargs.get("mode"),
                  None, kwargs.get("rows_read"),
                  kwargs.get("rows_written"), kwargs.get("rows_failed"),
                  kwargs.get("duration_sec"), kwargs.get("status")))
```

### 5.6 tdx_sync.py — 主入口

```python
#!/usr/bin/env python
"""通信达数据同步主脚本

Usage:
    python tdx_sync.py                     # 增量同步
    python tdx_sync.py --full              # 全量导入
    python tdx_sync.py --date 2024-01-15   # 指定日期
    python tdx_sync.py --force             # 忽略变更检测，强制重跑
    python tdx_sync.py --config my.yaml    # 自定义配置
"""
import argparse
import logging
import sys
import time
from tdx_core.config import TdxConfig
from tdx_core.sync import TdxSyncEngine
from tdx_core.notify import send_notification

def setup_logging(config: TdxConfig):
    log_dir = Path(config.log_dir)
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(
                log_dir / f"tdx_sync_{time.strftime('%Y%m%d')}.log",
                encoding="utf-8"
            ),
            logging.StreamHandler(),
        ],
    )

def main():
    parser = argparse.ArgumentParser(description="TDX Data Sync")
    parser.add_argument("--full", action="store_true", help="全量导入")
    parser.add_argument("--date", type=str, help="指定同步日期")
    parser.add_argument("--force", action="store_true", help="强制重跑")
    parser.add_argument("--config", type=str, help="配置文件路径")
    args = parser.parse_args()

    config = TdxConfig()
    setup_logging(config)
    logger = logging.getLogger(__name__)
    logger.info(f"Sync started: full={args.full}, date={args.date}, force={args.force}")

    engine = TdxSyncEngine(config)
    start = time.time()

    try:
        if args.full:
            results = engine.full_import()
        elif args.force:
            results = engine.full_import()
        else:
            results = engine.incremental_sync()

        duration = time.time() - start
        logger.info(f"Sync completed in {duration:.1f}s: {results}")

        send_notification(results, duration, config)

    except Exception as e:
        logger.exception(f"Sync failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

---

## 6. 定时任务配置

### 6.1 Windows 任务计划

```xml
<!-- tdx_sync_task.xml - 导入到 Windows 任务计划程序 -->
<Task version="1.2">
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2024-01-01T18:00:00</StartBoundary>
      <DaysOfWeek>Monday Tuesday Wednesday Thursday Friday</DaysOfWeek>
    </CalendarTrigger>
  </Triggers>
  <Actions>
    <Exec>
      <Command>python</Command>
      <Arguments>C:\TradingAgentsV2\scripts\tdx_sync.py --config C:\TradingAgentsV2\config\tdx_config.yaml</Arguments>
      <WorkingDirectory>C:\TradingAgentsV2</WorkingDirectory>
    </Exec>
  </Actions>
  <Settings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <RestartOnFailure>
      <Interval>PT5M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
</Task>
```

注册命令：
```cmd
schtasks /Create /TN "TDX_DailySync" /XML tdx_sync_task.xml
```

### 6.2 Linux Crontab

```cron
# 每个交易日 18:05 执行增量同步（跳过周末）
5 18 * * 1-5 /opt/TradingAgentsV2/venv/bin/python /opt/TradingAgentsV2/scripts/tdx_sync.py --config /opt/TradingAgentsV2/config/tdx_config.yaml >> /var/log/tdx_sync/cron.log 2>&1
```

---

## 7. 单元测试策略

```python
# tests/conftest.py
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_daily_df():
    """模拟 mootdx 返回的日线 DataFrame"""
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    return pd.DataFrame({
        "open":   [10.0, 10.5, 11.0, 10.8, 11.2],
        "high":   [10.5, 11.0, 11.5, 11.0, 11.5],
        "low":    [9.8,  10.2, 10.5, 10.3, 10.8],
        "close":  [10.2, 10.8, 11.2, 10.5, 11.0],
        "volume": [1000, 1200, 1500, 800,  1100],
        "amount": [10200, 12960, 16800, 8400, 12100],
    }, index=dates)

@pytest.fixture
def tdx_config(tmp_path):
    from tdx_core.config import TdxConfig
    return TdxConfig(
        tdx_dir=str(tmp_path / "tdx"),
        db_path=str(tmp_path / "test.db"),
        batch_size=100,
    )
```

```python
# tests/test_reader.py
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from tdx_core.reader import TdxReader, TdxReadError

class TestTdxReader:
    def test_read_daily_success(self, mock_daily_df, tdx_config):
        with patch.object(TdxReader, '__init__', lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            reader._std_reader = MagicMock()
            reader._ext_reader = MagicMock()
            reader._std_reader.daily.return_value = mock_daily_df

            result = reader.read_daily("000001")
            assert len(result) == 5
            assert "code" in result.columns
            assert result["code"].iloc[0] == "000001"

    def test_read_daily_file_not_found(self, tdx_config):
        with patch.object(TdxReader, '__init__', lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            reader._std_reader = MagicMock()
            reader._ext_reader = MagicMock()
            reader._std_reader.daily.return_value = None

            result = reader.read_daily("999999")
            assert result.empty

    def test_read_daily_format_error(self, tdx_config):
        with patch.object(TdxReader, '__init__', lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            reader._std_reader = MagicMock()
            reader._ext_reader = MagicMock()
            reader._std_reader.daily.side_effect = Exception("corrupt")

            with pytest.raises(TdxReadError):
                reader.read_daily("000001")

    def test_context_manager(self, tdx_config):
        with TdxReader(tdx_config) as reader:
            assert reader is not None

    def test_normalize_precision(self, tdx_config):
        df = pd.DataFrame({
            "open": [10.123456], "high": [11.789012],
            "low": [9.111111], "close": [10.555555],
            "volume": [1000], "amount": [10000],
        }, index=pd.date_range("2024-01-02", periods=1))
        with patch.object(TdxReader, '__init__', lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            result = reader._normalize(df, "000001")
            assert result["open"].iloc[0] == 10.12
            assert result["close"].iloc[0] == 10.56
```

---

## 8. 风险列表

| # | 风险 | 概率 | 影响 | 缓解措施 |
|---|------|------|------|----------|
| R1 | mootdx 对 BJ/DS 市场解析不完整 | 高 | 中 | 备选：直接 struct.unpack 二进制解析 |
| R2 | 5分钟/1分钟目录为空，接口未经实测 | 中 | 低 | 保留接口，待数据到位后验证 |
| R3 | 通信达软件写入文件与同步任务并发冲突 | 低 | 高 | 错开定时任务至收盘后 18:00+ |
| R4 | 日增量 500+ 文件时 SQLite 写入瓶颈 | 中 | 中 | WAL 模式 + 批量事务 + 预留 PostgreSQL 切换 |
| R5 | 文件 mtime 被非内容变更触发（拷贝等） | 低 | 中 | 补充 md5 校验作为二次确认 |
| R6 | 大宗/外汇 symbol 含 `#`，路径解析特殊 | 中 | 低 | 统一路径编码函数处理特殊字符 |

---

## 9. 时间计划表

| 阶段 | 里程碑 | 交付物 | 工期 |
|------|--------|--------|------|
| **阶段一** | 方案文档 | 本文档 + 架构图 + 时序图 + 风险列表 | W1 (当前) |
| **阶段二** | 原型开发 | reader.py + db.py + scanner.py + sync.py + 单元测试 + DDL | W2-W3 |
| **阶段三** | 性能压测 | 压测报告（1万条<1s，500文件<5min）+ 调优 | W4 |
| **阶段四** | 部署上线 | 部署手册 + 回滚方案 + 定时任务配置 + 通知集成 | W5 |

---

## 10. 技术依赖

```
# requirements.txt
mootdx>=0.11.7
pandas>=2.0
sqlite-utils>=3.35
pyyaml>=6.0
requests>=2.28        # 钉钉/邮件通知
pytest>=7.0
pytest-cov>=4.0
pylint>=2.17
```
