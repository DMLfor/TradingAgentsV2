"""TdxSyncEngine 单元测试"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tdx_data.models import FileInfo, SyncResult, SyncStatus
from tdx_data.sync import TdxSyncEngine


class TestSyncEngineFullImport:
    """full_import 测试"""

    def test_full_import_with_mock(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        engine = TdxSyncEngine(tdx_config)
        result = engine.full_import()

        assert result.rows_read > 0
        assert result.rows_written > 0
        assert result.rows_failed == 0
        assert result.status == SyncStatus.SUCCESS

        # 验证数据库有数据
        count = engine.db.get_record_count("tdx_daily")
        assert count > 0

        # 验证 file_registry 有记录
        registry = engine.db.get_file_registry()
        assert len(registry) > 0

    def test_full_import_logs_sync(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        engine = TdxSyncEngine(tdx_config)
        engine.full_import()

        # 验证 sync_log 有记录
        import sqlite3
        conn = sqlite3.connect(tdx_config.db_path)
        row = conn.execute("SELECT * FROM tdx_sync_log").fetchone()
        conn.close()
        assert row is not None
        assert row[1] is not None  # sync_date


class TestSyncEngineIncremental:
    """incremental_sync 测试"""

    def test_incremental_no_changes(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        engine = TdxSyncEngine(tdx_config)

        # 先全量导入
        engine.full_import()

        # 再次增量，无变更
        result = engine.incremental_sync()
        assert result is None

    def test_incremental_detects_new_file(self, mock_tdx_dir, tdx_config):
        import struct
        tdx_config.tdx_dir = str(mock_tdx_dir)
        engine = TdxSyncEngine(tdx_config)

        # 先全量导入
        engine.full_import()
        initial_count = engine.db.get_record_count("tdx_daily")

        # 添加新文件
        new_file = mock_tdx_dir / "vipdoc" / "sh" / "lday" / "sh601000.day"
        data = b""
        for i in range(2):
            data += struct.pack("<IIIIIIII",
                                20240110 + i, 1000, 1050, 980,
                                1020, 10000000, 100000, 0)
        new_file.write_bytes(data)

        # 增量同步
        result = engine.incremental_sync()
        assert result is not None
        assert result.rows_written > 0

        new_count = engine.db.get_record_count("tdx_daily")
        assert new_count > initial_count


class TestSyncEngineProcessFiles:
    """_process_files 测试"""

    def test_process_empty_file_list(self, tdx_config):
        engine = TdxSyncEngine(tdx_config)
        result = engine._process_files([])
        assert result.rows_read == 0
        assert result.rows_written == 0
        assert result.rows_failed == 0

    def test_process_file_with_retry(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        tdx_config.max_retries = 3
        engine = TdxSyncEngine(tdx_config)

        # 构造一个不存在的文件路径
        # read_daily_by_file 对不存在文件返回空 DataFrame（不抛异常）
        # 所以不会触发重试，只是 0 行写入
        bad_fi = FileInfo(
            file_path="/nonexistent/sh999999.day",
            market="sh",
            symbol="999999",
            data_type="daily",
            suffix="day",
            file_size=0,
            file_mtime="2024-01-01T00:00:00",
        )

        result = engine._process_files([bad_fi])
        assert result.rows_read == 0
        assert result.rows_written == 0
        assert result.rows_failed == 0  # empty file 不算失败

    def test_process_file_read_exception_retries(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        tdx_config.max_retries = 2
        tdx_config.retry_delay = 0.01
        engine = TdxSyncEngine(tdx_config)

        # Mock read_daily_by_file to raise exception → 触发重试
        fi = FileInfo(
            file_path=str(mock_tdx_dir / "vipdoc" / "sh" / "lday" / "sh000001.day"),
            market="sh",
            symbol="000001",
            data_type="daily",
            suffix="day",
            file_size=160,
            file_mtime="2024-01-01T00:00:00",
        )
        with patch.object(engine.reader, "read_daily_by_file", side_effect=Exception("parse error")):
            result = engine._process_files([fi])
        assert result.rows_failed == 1
        assert fi.file_path in result.failed_files


class TestSyncResult:
    """SyncResult 模型测试"""

    def test_sync_result_success(self):
        r = SyncResult(rows_read=10, rows_written=10, rows_failed=0)
        assert r.status == SyncStatus.SUCCESS

    def test_sync_result_partial(self):
        r = SyncResult(rows_read=10, rows_written=8, rows_failed=2)
        assert r.status == SyncStatus.PARTIAL

    def test_sync_result_failed(self):
        r = SyncResult(rows_read=10, rows_written=0, rows_failed=10)
        assert r.status == SyncStatus.FAILED

    def test_sync_result_default_failed_files(self):
        r = SyncResult()
        assert r.failed_files == []

    def test_sync_result_custom_failed_files(self):
        r = SyncResult(failed_files=["a.day", "b.day"])
        assert len(r.failed_files) == 2


class TestSyncEngineByMarket:
    """sync_by_market 测试"""

    def test_sync_sh_market(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        engine = TdxSyncEngine(tdx_config)
        result = engine.sync_by_market("sh")

        assert result.rows_read > 0
        assert result.rows_written > 0

    def test_sync_sh_daily_only(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        engine = TdxSyncEngine(tdx_config)
        result = engine.sync_by_market("sh", data_type="daily")

        assert result.rows_read > 0
