"""TdxDatabase 单元测试"""
import pandas as pd
import pytest

from tdx_core.db import TdxDatabase
from tdx_core.models import FileInfo


class TestTdxDatabaseInit:
    """数据库初始化测试"""

    def test_init_creates_tables(self, tdx_config):
        db = TdxDatabase(tdx_config)
        import sqlite3
        conn = sqlite3.connect(tdx_config.db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        conn.close()

        assert "tdx_daily" in table_names
        assert "tdx_minute_5" in table_names
        assert "tdx_minute_1" in table_names
        assert "tdx_file_registry" in table_names
        assert "tdx_sync_log" in table_names

    def test_init_creates_indexes(self, tdx_config):
        db = TdxDatabase(tdx_config)
        import sqlite3
        conn = sqlite3.connect(tdx_config.db_path)
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        index_names = {i[0] for i in indexes}
        conn.close()

        assert "idx_daily_date" in index_names
        assert "idx_daily_code_date" in index_names


class TestTdxDatabaseUpsert:
    """数据写入测试"""

    def test_upsert_daily(self, tdx_config):
        db = TdxDatabase(tdx_config)
        df = pd.DataFrame({
            "code": ["000001"] * 3,
            "trade_date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "open_val": [10.0, 10.5, 11.0],
            "high_val": [10.5, 11.0, 11.5],
            "low_val": [9.8, 10.2, 10.5],
            "close_val": [10.2, 10.8, 11.2],
            "volume": [1000, 1200, 1500],
            "amount": [10200, 12960, 16800],
        })

        written = db.upsert_dataframe(df, "tdx_daily")
        assert written == 3
        assert db.get_record_count("tdx_daily") == 3

    def test_upsert_merge_no_duplicate(self, tdx_config):
        db = TdxDatabase(tdx_config)
        df1 = pd.DataFrame({
            "code": ["000001"] * 2,
            "trade_date": ["2024-01-02", "2024-01-03"],
            "open_val": [10.0, 10.5],
            "high_val": [10.5, 11.0],
            "low_val": [9.8, 10.2],
            "close_val": [10.2, 10.8],
            "volume": [1000, 1200],
            "amount": [10200, 12960],
        })
        df2 = pd.DataFrame({
            "code": ["000001"] * 2,
            "trade_date": ["2024-01-03", "2024-01-04"],
            "open_val": [10.6, 11.0],
            "high_val": [11.1, 11.5],
            "low_val": [10.3, 10.5],
            "close_val": [10.9, 11.2],
            "volume": [1300, 1500],
            "amount": [13500, 16800],
        })

        db.upsert_dataframe(df1, "tdx_daily")
        db.upsert_dataframe(df2, "tdx_daily")

        assert db.get_record_count("tdx_daily") == 3

        # 验证 2024-01-03 被更新为 df2 的值
        result = db.query_daily("000001", start_date="2024-01-03", end_date="2024-01-03")
        assert len(result) == 1
        assert result.iloc[0]["close_val"] == 10.9

    def test_upsert_empty_df(self, tdx_config):
        db = TdxDatabase(tdx_config)
        written = db.upsert_dataframe(pd.DataFrame(), "tdx_daily")
        assert written == 0

    def test_upsert_batch_size(self, tdx_config):
        tdx_config.batch_size = 2
        db = TdxDatabase(tdx_config)
        df = pd.DataFrame({
            "code": ["000001"] * 5,
            "trade_date": [f"2024-01-0{i}" for i in range(2, 7)],
            "open_val": [10.0 + i for i in range(5)],
            "high_val": [10.5 + i for i in range(5)],
            "low_val": [9.8 + i for i in range(5)],
            "close_val": [10.2 + i for i in range(5)],
            "volume": [1000 + i * 100 for i in range(5)],
            "amount": [10000 + i * 1000 for i in range(5)],
        })

        written = db.upsert_dataframe(df, "tdx_daily", batch_size=2)
        assert written == 5
        assert db.get_record_count("tdx_daily") == 5

    def test_primary_key_integrity(self, tdx_config):
        db = TdxDatabase(tdx_config)
        df = pd.DataFrame({
            "code": ["000001"] * 3,
            "trade_date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "open_val": [10.0, 10.5, 11.0],
            "high_val": [10.5, 11.0, 11.5],
            "low_val": [9.8, 10.2, 10.5],
            "close_val": [10.2, 10.8, 11.2],
            "volume": [1000, 1200, 1500],
            "amount": [10200, 12960, 16800],
        })
        db.upsert_dataframe(df, "tdx_daily")
        db.upsert_dataframe(df, "tdx_daily")  # 二次写入不应产生重复

        result = db.check_primary_key_integrity("tdx_daily")
        assert result["duplicate_count"] == 0


class TestTdxDatabaseFileRegistry:
    """文件注册表 CRUD 测试"""

    def test_update_and_get_registry(self, tdx_config, sample_file_info):
        db = TdxDatabase(tdx_config)
        db.update_file_registry(sample_file_info, 5)

        registry = db.get_file_registry()
        assert "/tmp/sh000001.day" in registry
        assert registry["/tmp/sh000001.day"].symbol == "000001"
        assert registry["/tmp/sh000001.day"].market == "sh"

    def test_update_registry_overwrite(self, tdx_config, sample_file_info):
        db = TdxDatabase(tdx_config)
        db.update_file_registry(sample_file_info, 5)

        sample_file_info.file_mtime = "2024-01-03T18:00:00"
        db.update_file_registry(sample_file_info, 6)

        registry = db.get_file_registry()
        assert len(registry) == 1
        assert registry["/tmp/sh000001.day"].file_mtime == "2024-01-03T18:00:00"

    def test_get_registry_empty(self, tdx_config):
        db = TdxDatabase(tdx_config)
        registry = db.get_file_registry()
        assert len(registry) == 0


class TestTdxDatabaseSyncLog:
    """同步日志测试"""

    def test_insert_sync_log(self, tdx_config):
        db = TdxDatabase(tdx_config)
        db.insert_sync_log(
            sync_date="2024-01-02",
            mode="full",
            rows_read=100,
            rows_written=100,
            rows_failed=0,
            duration_sec=1.5,
            status="success",
        )

        import sqlite3
        conn = sqlite3.connect(tdx_config.db_path)
        row = conn.execute("SELECT * FROM tdx_sync_log").fetchone()
        conn.close()

        assert row is not None
        assert row[1] == "2024-01-02"
        assert row[4] == 100  # rows_read
        assert row[7] == 1.5  # duration_sec


class TestTdxDatabaseQuery:
    """数据查询测试"""

    def test_query_daily(self, tdx_config):
        db = TdxDatabase(tdx_config)
        df = pd.DataFrame({
            "code": ["000001"] * 3,
            "trade_date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "open_val": [10.0, 10.5, 11.0],
            "high_val": [10.5, 11.0, 11.5],
            "low_val": [9.8, 10.2, 10.5],
            "close_val": [10.2, 10.8, 11.2],
            "volume": [1000, 1200, 1500],
            "amount": [10200, 12960, 16800],
        })
        db.upsert_dataframe(df, "tdx_daily")

        result = db.query_daily("000001")
        assert len(result) == 3

    def test_query_daily_with_date_range(self, tdx_config):
        db = TdxDatabase(tdx_config)
        df = pd.DataFrame({
            "code": ["000001"] * 3,
            "trade_date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "open_val": [10.0, 10.5, 11.0],
            "high_val": [10.5, 11.0, 11.5],
            "low_val": [9.8, 10.2, 10.5],
            "close_val": [10.2, 10.8, 11.2],
            "volume": [1000, 1200, 1500],
            "amount": [10200, 12960, 16800],
        })
        db.upsert_dataframe(df, "tdx_daily")

        result = db.query_daily("000001", start_date="2024-01-03")
        assert len(result) == 2

    def test_query_daily_no_data(self, tdx_config):
        db = TdxDatabase(tdx_config)
        result = db.query_daily("999999")
        assert len(result) == 0

    def test_get_max_trade_date(self, tdx_config):
        db = TdxDatabase(tdx_config)
        df = pd.DataFrame({
            "code": ["000001"] * 3,
            "trade_date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "open_val": [10.0, 10.5, 11.0],
            "high_val": [10.5, 11.0, 11.5],
            "low_val": [9.8, 10.2, 10.5],
            "close_val": [10.2, 10.8, 11.2],
            "volume": [1000, 1200, 1500],
            "amount": [10200, 12960, 16800],
        })
        db.upsert_dataframe(df, "tdx_daily")

        max_date = db.get_max_trade_date("000001")
        assert max_date == "2024-01-04"

    def test_get_max_trade_date_no_data(self, tdx_config):
        db = TdxDatabase(tdx_config)
        assert db.get_max_trade_date("999999") is None

    def test_get_record_count(self, tdx_config):
        db = TdxDatabase(tdx_config)
        df = pd.DataFrame({
            "code": ["000001"] * 3,
            "trade_date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "open_val": [10.0, 10.5, 11.0],
            "high_val": [10.5, 11.0, 11.5],
            "low_val": [9.8, 10.2, 10.5],
            "close_val": [10.2, 10.8, 11.2],
            "volume": [1000, 1200, 1500],
            "amount": [10200, 12960, 16800],
        })
        db.upsert_dataframe(df, "tdx_daily")

        assert db.get_record_count("tdx_daily") == 3
        assert db.get_record_count("tdx_daily", "000001") == 3
        assert db.get_record_count("tdx_daily", "999999") == 0

    def test_query_minute_5(self, tdx_config):
        db = TdxDatabase(tdx_config)
        df = pd.DataFrame({
            "code": ["000001"] * 3,
            "trade_date": ["2024-01-02 09:30", "2024-01-02 09:35", "2024-01-02 09:40"],
            "open_val": [10.0, 10.5, 11.0],
            "high_val": [10.5, 11.0, 11.5],
            "low_val": [9.8, 10.2, 10.5],
            "close_val": [10.2, 10.8, 11.2],
            "volume": [1000, 1200, 1500],
            "amount": [10200, 12960, 16800],
        })
        db.upsert_dataframe(df, "tdx_minute_5")

        result = db.query_minute_5("000001")
        assert len(result) == 3

        result_filtered = db.query_minute_5("000001", trade_date="2024-01-02")
        assert len(result_filtered) == 3

    def test_query_minute_1(self, tdx_config):
        db = TdxDatabase(tdx_config)
        df = pd.DataFrame({
            "code": ["000001"] * 2,
            "trade_date": ["2024-01-02 09:30", "2024-01-02 09:31"],
            "open_val": [10.0, 10.5],
            "high_val": [10.5, 11.0],
            "low_val": [9.8, 10.2],
            "close_val": [10.2, 10.8],
            "volume": [1000, 1200],
            "amount": [10200, 12960],
        })
        db.upsert_dataframe(df, "tdx_minute_1")

        result = db.query_minute_1("000001")
        assert len(result) == 2
