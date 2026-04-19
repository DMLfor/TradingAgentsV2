"""pytest 共享 fixtures"""
import os
import struct
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from tdx_core.config import TdxConfig
from tdx_core.models import FileInfo


@pytest.fixture
def tmp_dir(tmp_path):
    """临时目录，模拟 TDX 根目录"""
    return tmp_path


@pytest.fixture
def tdx_config(tmp_dir):
    """测试用配置，指向临时目录"""
    return TdxConfig(
        tdx_dir=str(tmp_dir / "tdx"),
        db_type="sqlite",
        db_path=str(tmp_dir / "test.db"),
        batch_size=100,
        max_retries=2,
        retry_delay=0.01,
        markets=("sh", "sz", "bj"),
        data_types=("daily", "minute_5", "minute_1"),
        log_dir=str(tmp_dir / "logs"),
    )


@pytest.fixture
def mock_tdx_dir(tmp_dir):
    """创建模拟的 TDX 目录结构"""
    tdx_root = tmp_dir / "tdx"
    for market in ["sh", "sz", "bj", "ds"]:
        for subdir in ["lday", "fzline", "minline"]:
            (tdx_root / "vipdoc" / market / subdir).mkdir(parents=True, exist_ok=True)

    # 创建模拟 .day 文件（沪市 2 个，深市 1 个）
    _create_day_file(tdx_root / "vipdoc" / "sh" / "lday" / "sh000001.day", 5)
    _create_day_file(tdx_root / "vipdoc" / "sh" / "lday" / "sh600000.day", 3)
    _create_day_file(tdx_root / "vipdoc" / "sz" / "lday" / "sz000001.day", 4)
    _create_day_file(tdx_root / "vipdoc" / "bj" / "lday" / "bj920000.day", 2)

    # 创建模拟 .lc5 文件
    _create_lc_file(tdx_root / "vipdoc" / "sh" / "fzline" / "sh000001.lc5", 3)

    # 创建模拟 .lc1 文件
    _create_lc_file(tdx_root / "vipdoc" / "sh" / "minline" / "sh000001.lc1", 3)

    return tdx_root


def _create_day_file(path: Path, n_records: int):
    """创建模拟 .day 二进制文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = b""
    base_date = 20240102
    for i in range(n_records):
        date_int = base_date + i
        open_v = 1000 + i * 10
        high_v = 1050 + i * 10
        low_v = 980 + i * 10
        close_v = 1020 + i * 10
        amount = 10000000 + i * 1000000
        volume = 100000 + i * 10000
        reserved = 0
        data += struct.pack("<IIIIIIII",
                            date_int, open_v, high_v, low_v,
                            close_v, amount, volume, reserved)
    path.write_bytes(data)


def _create_lc_file(path: Path, n_records: int):
    """创建模拟 .lc5/.lc1 二进制文件

    TDX 分钟线格式（32字节/记录）:
    date(2) + time(2) + open(4f) + high(4f) + low(4f)
    + close(4f) + amount(4f) + volume(4) + reserved(4)
    date 编码: year=num//2048+2004, month=(num%2048)//100, day=(num%2048)%100
    time 编码: 从0点开始的分钟数
    """
    import struct as _struct
    path.parent.mkdir(parents=True, exist_ok=True)
    data = b""
    # 2024-01-02 的 date 编码: (2024-2004)*2048 + 1*100 + 2 = 41062
    base_date_num = (2024 - 2004) * 2048 + 1 * 100 + 2  # = 41062
    base_minutes = 9 * 60 + 30  # 9:30 = 570 分钟
    for i in range(n_records):
        date_num = base_date_num  # 同一天
        time_num = base_minutes + i * 5  # 每5分钟
        open_v = 10.0 + i * 0.5
        high_v = 10.5 + i * 0.5
        low_v = 9.8 + i * 0.5
        close_v = 10.2 + i * 0.5
        amount = 5000000.0 + i * 500000.0
        volume = 50000 + i * 5000
        reserved = 0
        data += _struct.pack("<HHfffffII",
                             date_num, time_num,
                             open_v, high_v, low_v,
                             close_v, amount, volume, reserved)
    path.write_bytes(data)


@pytest.fixture
def mock_daily_df():
    """模拟 mootdx 返回的日线 DataFrame"""
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    return pd.DataFrame({
        "open":   [10.0, 10.5, 11.0, 10.8, 11.2],
        "high":   [10.5, 11.0, 11.5, 11.0, 11.5],
        "low":    [9.8,  10.2, 10.5, 10.3, 10.8],
        "close":  [10.2, 10.8, 11.2, 10.5, 11.0],
        "volume": [1000.0, 1200.0, 1500.0, 800.0,  1100.0],
        "amount": [10200.0, 12960.0, 16800.0, 8400.0, 12100.0],
    }, index=pd.DatetimeIndex(dates, name="date"))


@pytest.fixture
def sample_file_info():
    """模拟 FileInfo"""
    return FileInfo(
        file_path="/tmp/sh000001.day",
        market="sh",
        symbol="000001",
        data_type="daily",
        suffix="day",
        file_size=160,
        file_mtime="2024-01-02T18:00:00",
    )
