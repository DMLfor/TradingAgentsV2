"""TdxReader 单元测试"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tdx_core.reader import TdxReadError, TdxReader


class TestTdxReaderReadDaily:
    """read_daily 方法测试"""

    def test_read_daily_success(self, mock_daily_df, tdx_config):
        with patch.object(TdxReader, "__init__", lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            reader._std_reader = MagicMock()
            reader._ext_reader = MagicMock()
            reader._std_reader.daily.return_value = mock_daily_df

            result = reader.read_daily("000001")
            assert len(result) == 5
            assert "code" in result.columns
            assert result["code"].iloc[0] == "000001"
            assert "open_val" in result.columns
            assert "close_val" in result.columns

    def test_read_daily_returns_none(self, tdx_config):
        with patch.object(TdxReader, "__init__", lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            reader._std_reader = MagicMock()
            reader._ext_reader = MagicMock()
            reader._std_reader.daily.return_value = None

            result = reader.read_daily("000001")
            assert result.empty
            assert "code" in result.columns

    def test_read_daily_file_not_found(self, tdx_config):
        with patch.object(TdxReader, "__init__", lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            reader._std_reader = MagicMock()
            reader._ext_reader = MagicMock()
            reader._std_reader.daily.side_effect = FileNotFoundError

            result = reader.read_daily("999999")
            assert result.empty

    def test_read_daily_format_error_raises(self, tdx_config):
        with patch.object(TdxReader, "__init__", lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            reader._std_reader = MagicMock()
            reader._ext_reader = MagicMock()
            reader._std_reader.daily.side_effect = Exception("corrupt")

            with pytest.raises(TdxReadError):
                reader.read_daily("000001")

    def test_read_daily_ext_market(self, mock_daily_df, tdx_config):
        with patch.object(TdxReader, "__init__", lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            reader._std_reader = MagicMock()
            reader._ext_reader = MagicMock()
            reader._ext_reader.daily.return_value = mock_daily_df

            result = reader.read_daily("AUDUSD", market="ds")
            assert len(result) == 5
            reader._ext_reader.daily.assert_called_once()

    def test_read_daily_hash_in_code_uses_ext(self, mock_daily_df, tdx_config):
        with patch.object(TdxReader, "__init__", lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            reader._std_reader = MagicMock()
            reader._ext_reader = MagicMock()
            reader._ext_reader.daily.return_value = mock_daily_df

            result = reader.read_daily("10#AUDUSD")
            reader._ext_reader.daily.assert_called_once()
            reader._std_reader.daily.assert_not_called()


class TestTdxReaderByFile:
    """read_daily_by_file 方法测试"""

    def test_read_day_file(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        reader = TdxReader(tdx_config)
        day_file = mock_tdx_dir / "vipdoc" / "sh" / "lday" / "sh000001.day"

        result = reader.read_daily_by_file(str(day_file))
        assert len(result) == 5
        assert "code" in result.columns
        assert result["code"].iloc[0] == "000001"
        assert result["open_val"].iloc[0] == 10.0
        assert result["close_val"].iloc[0] == 10.2

    def test_read_day_file_not_found(self, tdx_config):
        reader = TdxReader(tdx_config)
        result = reader.read_daily_by_file("/nonexistent/sh000001.day")
        assert result.empty

    def test_read_bj_day_file(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        reader = TdxReader(tdx_config)
        day_file = mock_tdx_dir / "vipdoc" / "bj" / "lday" / "bj920000.day"

        result = reader.read_daily_by_file(str(day_file))
        assert len(result) == 2
        assert result["code"].iloc[0] == "920000"

    def test_read_lc_file(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        reader = TdxReader(tdx_config)
        lc_file = mock_tdx_dir / "vipdoc" / "sh" / "fzline" / "sh000001.lc5"

        result = reader.read_lc_file(str(lc_file))
        assert len(result) == 3
        assert "code" in result.columns


class TestTdxReaderNormalize:
    """_normalize 方法测试"""

    def test_normalize_precision(self, tdx_config):
        df = pd.DataFrame({
            "open": [10.123456], "high": [11.789012],
            "low": [9.111111], "close": [10.555555],
            "volume": [1000.0], "amount": [10000.0],
        }, index=pd.DatetimeIndex(["2024-01-02"], name="date"))

        with patch.object(TdxReader, "__init__", lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            result = reader._normalize(df, "000001")
            assert result["open_val"].iloc[0] == 10.12
            assert result["high_val"].iloc[0] == 11.79
            assert result["low_val"].iloc[0] == 9.11
            assert result["close_val"].iloc[0] == 10.56

    def test_normalize_none_returns_empty(self, tdx_config):
        with patch.object(TdxReader, "__init__", lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            result = reader._normalize(None, "000001")
            assert result.empty

    def test_normalize_empty_df_returns_empty(self, tdx_config):
        with patch.object(TdxReader, "__init__", lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            result = reader._normalize(pd.DataFrame(), "000001")
            assert result.empty


class TestTdxReaderContextManager:
    """with 上下文管理测试"""

    def test_context_manager(self, tdx_config):
        with TdxReader(tdx_config) as reader:
            assert reader is not None
            assert reader.config == tdx_config

    def test_context_manager_no_exception(self, tdx_config):
        with TdxReader(tdx_config) as reader:
            pass
        # 不应抛出异常


class TestTdxReaderIntToDate:
    """_int_to_date / _parse_lc_date / _parse_lc_time 测试"""

    def test_int_to_date(self):
        assert TdxReader._int_to_date(20240102) == "2024-01-02"

    def test_int_to_date_short(self):
        assert TdxReader._int_to_date(123) == "123"

    def test_parse_lc_date(self):
        # (2024-2004)*2048 + 1*100 + 2 = 41062
        year, month, day = TdxReader._parse_lc_date(41062)
        assert year == 2024
        assert month == 1
        assert day == 2

    def test_parse_lc_time(self):
        hour, minute = TdxReader._parse_lc_time(570)
        assert hour == 9
        assert minute == 30


class TestTdxReaderMinute:
    """read_minute / read_fzline 测试"""

    def test_read_minute_returns_none(self, tdx_config):
        with patch.object(TdxReader, "__init__", lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            reader._std_reader = MagicMock()
            reader._ext_reader = MagicMock()
            reader._std_reader.minute.return_value = None

            result = reader.read_minute("000001")
            assert result.empty

    def test_read_fzline_returns_none(self, tdx_config):
        with patch.object(TdxReader, "__init__", lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            reader._std_reader = MagicMock()
            reader._ext_reader = MagicMock()
            reader._std_reader.fzline.return_value = None

            result = reader.read_fzline("000001")
            assert result.empty

    def test_read_minute_file_not_found(self, tdx_config):
        with patch.object(TdxReader, "__init__", lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            reader._std_reader = MagicMock()
            reader._ext_reader = MagicMock()
            reader._std_reader.minute.side_effect = FileNotFoundError

            result = reader.read_minute("000001")
            assert result.empty

    def test_read_minute_error_raises(self, tdx_config):
        with patch.object(TdxReader, "__init__", lambda self, c: None):
            reader = TdxReader.__new__(TdxReader)
            reader.config = tdx_config
            reader._std_reader = MagicMock()
            reader._ext_reader = MagicMock()
            reader._std_reader.minute.side_effect = Exception("corrupt")

            with pytest.raises(TdxReadError):
                reader.read_minute("000001")
