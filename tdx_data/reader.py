"""通信达数据读取器，基于 mootdx 封装"""
import logging
import struct
from pathlib import Path
from typing import Optional

import pandas as pd

from .config import TdxConfig
from .models import STANDARD_COLUMNS

logger = logging.getLogger(__name__)


class TdxReadError(Exception):
    """通信达数据读取异常"""


class TdxReader:
    """通信达数据读取器

    基于 mootdx 的 Reader 封装，支持：
    - read_daily(code) 日线读取
    - read_minute(code) 1分钟线读取
    - read_fzline(code) 5分钟线读取
    - read_daily_by_file(path) 直接按文件路径读取
    - with 上下文管理
    """

    RECORD_SIZE = 32  # 每条记录 32 字节
    PRICE_SCALE = 100.0  # 价格缩放因子

    def __init__(self, config: Optional[TdxConfig] = None):
        self.config = config or TdxConfig()
        self._std_reader = None
        self._ext_reader = None
        try:
            from mootdx.reader import Reader
            self._std_reader = Reader.factory(
                market="std", tdxdir=self.config.tdx_dir
            )
            self._ext_reader = Reader.factory(
                market="ext", tdxdir=self.config.tdx_dir
            )
        except Exception as exc:
            logger.warning("mootdx Reader init failed: %s", exc)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def read_daily(self, code: str, market: str = "auto") -> pd.DataFrame:
        """读取日线数据

        Args:
            code: 股票代码，如 '000001'、'920000'
            market: 'sh'/'sz'/'bj'/'ds'/'auto'
        Returns:
            DataFrame，列: [code, open, high, low, close, volume, amount]
            索引: trade_date (DatetimeIndex)
        """
        try:
            reader = self._get_reader(code, market)
            df = reader.daily(symbol=code)
            return self._normalize(df, code)
        except FileNotFoundError:
            logger.warning("File not found for code=%s", code)
            return self._empty_df()
        except Exception as exc:
            logger.error("Failed to read daily code=%s: %s", code, exc)
            raise TdxReadError(f"Read daily failed: {code}") from exc

    def read_minute(self, code: str, market: str = "auto") -> pd.DataFrame:
        """读取1分钟线"""
        try:
            reader = self._get_reader(code, market)
            df = reader.minute(symbol=code)
            return self._normalize(df, code)
        except FileNotFoundError:
            logger.warning("File not found for code=%s", code)
            return self._empty_df()
        except Exception as exc:
            logger.error("Failed to read minute code=%s: %s", code, exc)
            raise TdxReadError(f"Read minute failed: {code}") from exc

    def read_fzline(self, code: str, market: str = "auto") -> pd.DataFrame:
        """读取5分钟线"""
        try:
            reader = self._get_reader(code, market)
            df = reader.fzline(symbol=code)
            return self._normalize(df, code)
        except FileNotFoundError:
            logger.warning("File not found for code=%s", code)
            return self._empty_df()
        except Exception as exc:
            logger.error("Failed to read fzline code=%s: %s", code, exc)
            raise TdxReadError(f"Read fzline failed: {code}") from exc

    def read_daily_by_file(self, file_path: str) -> pd.DataFrame:
        """直接按文件路径读取（兼容 BJ/DS 等非标准路径）

        使用 struct 直接解析二进制，不依赖 mootdx 路径解析逻辑。
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning("File not found: %s", file_path)
            return self._empty_df()

        stem = path.stem
        market = stem[:2]
        code = stem[2:]

        try:
            df = self._parse_day_file(path)
            return self._normalize(df, code)
        except Exception as exc:
            logger.error("Failed to read file=%s: %s", file_path, exc)
            raise TdxReadError(f"Read file failed: {file_path}") from exc

    def read_lc_file(self, file_path: str) -> pd.DataFrame:
        """解析 .lc1/.lc5 分钟线文件（直接二进制解析）"""
        path = Path(file_path)
        if not path.exists():
            logger.warning("File not found: %s", file_path)
            return self._empty_df()

        stem = path.stem
        market = stem[:2]
        code = stem[2:]

        try:
            df = self._parse_lc_file(path)
            return self._normalize(df, code)
        except Exception as exc:
            logger.error("Failed to read lc file=%s: %s", file_path, exc)
            raise TdxReadError(f"Read lc file failed: {file_path}") from exc

    def _get_reader(self, code: str, market: str):
        if market == "ds" or "#" in code:
            return self._ext_reader
        return self._std_reader

    def _normalize(self, df: Optional[pd.DataFrame], code: str) -> pd.DataFrame:
        if df is None or df.empty:
            return self._empty_df()
        df = df.copy()
        df["code"] = code
        # 重命名列：open→open_val 等（避免 MySQL 保留字）
        rename_map = {"open": "open_val", "high": "high_val",
                      "low": "low_val", "close": "close_val"}
        for old, new in rename_map.items():
            if old in df.columns:
                df = df.rename(columns={old: new})
        for col in ["open_val", "high_val", "low_val", "close_val"]:
            if col in df.columns:
                df[col] = df[col].round(2)
        cols = ["code"] + [c for c in STANDARD_COLUMNS if c in df.columns]
        return df[cols]

    @staticmethod
    def _empty_df() -> pd.DataFrame:
        return pd.DataFrame(columns=["code"] + STANDARD_COLUMNS)

    def _parse_day_file(self, path: Path) -> pd.DataFrame:
        """直接解析 .day 二进制文件

        格式：每条记录 32 字节
        date(4) + open(4) + high(4) + low(4) + close(4)
        + amount(4) + volume(4) + reserved(4)
        全部为 little-endian unsigned int
        """
        raw = path.read_bytes()
        if len(raw) % self.RECORD_SIZE != 0:
            logger.warning("File size not aligned: %s (%d bytes)", path, len(raw))

        n = len(raw) // self.RECORD_SIZE
        records = struct.unpack(f"<{n * 8}I", raw[:n * self.RECORD_SIZE])

        dates, opens, highs, lows, closes, amounts, volumes = [], [], [], [], [], [], []
        for i in range(n):
            base = i * 8
            date_int = records[base]
            opens.append(records[base + 1] / self.PRICE_SCALE)
            highs.append(records[base + 2] / self.PRICE_SCALE)
            lows.append(records[base + 3] / self.PRICE_SCALE)
            closes.append(records[base + 4] / self.PRICE_SCALE)
            amounts.append(records[base + 5])
            volumes.append(records[base + 6])
            dates.append(self._int_to_date(date_int))

        return pd.DataFrame({
            "open": opens, "high": highs, "low": lows, "close": closes,
            "amount": amounts, "volume": volumes,
        }, index=pd.DatetimeIndex(dates, name="date"))

    def _parse_lc_file(self, path: Path) -> pd.DataFrame:
        """解析 .lc1/.lc5 分钟线二进制文件

        格式：每条记录 32 字节
        date(2) + time(2) + open(4f) + high(4f) + low(4f)
        + close(4f) + amount(4f) + volume(4) + reserved(4)
        date 编码: year=num//2048+2004, month=(num%2048)//100, day=(num%2048)%100
        time 编码: hour=num//60, minute=num%60
        """
        raw = path.read_bytes()
        if len(raw) % self.RECORD_SIZE != 0:
            logger.warning("File size not aligned: %s (%d bytes)", path, len(raw))

        n = len(raw) // self.RECORD_SIZE
        record_fmt = struct.Struct("<HHfffffII")

        dates, opens, highs, lows, closes, amounts, volumes = [], [], [], [], [], [], []
        for i in range(n):
            offset = i * self.RECORD_SIZE
            row = record_fmt.unpack_from(raw, offset)
            year, month, day = self._parse_lc_date(row[0])
            hour, minute = self._parse_lc_time(row[1])
            dates.append(f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}")
            opens.append(round(row[2], 2))
            highs.append(round(row[3], 2))
            lows.append(round(row[4], 2))
            closes.append(round(row[5], 2))
            amounts.append(row[6])
            volumes.append(row[7])

        return pd.DataFrame({
            "open": opens, "high": highs, "low": lows, "close": closes,
            "amount": amounts, "volume": volumes,
        }, index=pd.DatetimeIndex(dates, name="date"))

    @staticmethod
    def _parse_lc_date(num: int):
        year = num // 2048 + 2004
        month = (num % 2048) // 100
        day = (num % 2048) % 100
        return year, month, day

    @staticmethod
    def _parse_lc_time(num: int):
        return num // 60, num % 60

    @staticmethod
    def _int_to_date(val: int) -> str:
        """将整数日期转为 ISO 格式字符串，如 20240102 → '2024-01-02'"""
        s = str(val)
        if len(s) == 8:
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return s

    @staticmethod
    def _int_to_datetime(val: int) -> str:
        """将整数日期时间转为 ISO 格式字符串，如 202401020930 → '2024-01-02 09:30'"""
        s = str(val)
        if len(s) == 12:
            return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
        if len(s) == 8:
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return s
