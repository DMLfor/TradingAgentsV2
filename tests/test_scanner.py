"""TdxScanner 单元测试"""
import struct
from pathlib import Path

import pytest

from tdx_core.models import FileInfo
from tdx_core.scanner import TdxScanner


class TestTdxScannerScanAll:
    """scan_all 方法测试"""

    def test_scan_all_finds_files(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        scanner = TdxScanner(tdx_config)
        files = scanner.scan_all()

        assert len(files) >= 5  # sh000001, sh600000, sz000001, bj920000 + lc5 + lc1
        symbols = {f.symbol for f in files}
        assert "000001" in symbols
        assert "600000" in symbols
        assert "920000" in symbols

    def test_scan_all_correct_market(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        scanner = TdxScanner(tdx_config)
        files = scanner.scan_all()

        by_market = {}
        for f in files:
            by_market.setdefault(f.market, []).append(f)

        assert "sh" in by_market
        assert "sz" in by_market
        assert "bj" in by_market

    def test_scan_all_correct_data_type(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        scanner = TdxScanner(tdx_config)
        files = scanner.scan_all()

        by_type = {}
        for f in files:
            by_type.setdefault(f.data_type, []).append(f)

        assert "daily" in by_type
        assert "minute_5" in by_type
        assert "minute_1" in by_type

    def test_scan_all_nonexistent_dir(self, tdx_config):
        tdx_config.tdx_dir = "/nonexistent/path"
        scanner = TdxScanner(tdx_config)
        files = scanner.scan_all()
        assert files == []

    def test_scan_all_file_info_fields(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        scanner = TdxScanner(tdx_config)
        files = scanner.scan_all()

        for fi in files:
            assert fi.file_path
            assert fi.market in ("sh", "sz", "bj", "ds")
            assert fi.symbol
            assert fi.data_type in ("daily", "minute_5", "minute_1")
            assert fi.suffix in ("day", "lc5", "lc1")
            assert fi.file_size > 0
            assert fi.file_mtime


class TestTdxScannerScanMarket:
    """scan_market 方法测试"""

    def test_scan_market_sh(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        scanner = TdxScanner(tdx_config)
        files = scanner.scan_market("sh")

        assert all(f.market == "sh" for f in files)
        symbols = {f.symbol for f in files}
        assert "000001" in symbols
        assert "600000" in symbols

    def test_scan_market_with_data_type(self, mock_tdx_dir, tdx_config):
        tdx_config.tdx_dir = str(mock_tdx_dir)
        scanner = TdxScanner(tdx_config)
        files = scanner.scan_market("sh", data_type="daily")

        assert all(f.data_type == "daily" for f in files)

    def test_scan_market_nonexistent(self, tdx_config):
        tdx_config.tdx_dir = "/nonexistent"
        scanner = TdxScanner(tdx_config)
        files = scanner.scan_market("xx")
        assert files == []


class TestTdxScannerDetectChanges:
    """detect_changes 方法测试"""

    def test_detect_new_files(self, tdx_config):
        scanner = TdxScanner(tdx_config)
        current = [
            FileInfo("a.day", "sh", "000001", "daily", "day", 160, "2024-01-01T00:00:00"),
            FileInfo("b.day", "sz", "000002", "daily", "day", 320, "2024-01-01T00:00:00"),
        ]
        known = {}

        changes = scanner.detect_changes(known, current)
        assert len(changes["new"]) == 2
        assert len(changes["modified"]) == 0
        assert len(changes["unchanged"]) == 0

    def test_detect_modified_files(self, tdx_config):
        scanner = TdxScanner(tdx_config)
        current = [
            FileInfo("a.day", "sh", "000001", "daily", "day", 160, "2024-01-02T00:00:00"),
        ]
        known = {
            "a.day": FileInfo("a.day", "sh", "000001", "daily", "day", 160, "2024-01-01T00:00:00"),
        }

        changes = scanner.detect_changes(known, current)
        assert len(changes["new"]) == 0
        assert len(changes["modified"]) == 1
        assert len(changes["unchanged"]) == 0

    def test_detect_modified_by_size(self, tdx_config):
        scanner = TdxScanner(tdx_config)
        current = [
            FileInfo("a.day", "sh", "000001", "daily", "day", 200, "2024-01-01T00:00:00"),
        ]
        known = {
            "a.day": FileInfo("a.day", "sh", "000001", "daily", "day", 160, "2024-01-01T00:00:00"),
        }

        changes = scanner.detect_changes(known, current)
        assert len(changes["modified"]) == 1

    def test_detect_unchanged_files(self, tdx_config):
        scanner = TdxScanner(tdx_config)
        fi = FileInfo("a.day", "sh", "000001", "daily", "day", 160, "2024-01-01T00:00:00")
        current = [fi]
        known = {"a.day": fi}

        changes = scanner.detect_changes(known, current)
        assert len(changes["new"]) == 0
        assert len(changes["modified"]) == 0
        assert len(changes["unchanged"]) == 1

    def test_detect_mixed_changes(self, tdx_config):
        scanner = TdxScanner(tdx_config)
        current = [
            FileInfo("a.day", "sh", "000001", "daily", "day", 160, "2024-01-01T00:00:00"),
            FileInfo("b.day", "sz", "000002", "daily", "day", 320, "2024-01-02T00:00:00"),
            FileInfo("c.day", "bj", "920000", "daily", "day", 64, "2024-01-01T00:00:00"),
        ]
        known = {
            "a.day": FileInfo("a.day", "sh", "000001", "daily", "day", 160, "2024-01-01T00:00:00"),
            "b.day": FileInfo("b.day", "sz", "000002", "daily", "day", 320, "2024-01-01T00:00:00"),
        }

        changes = scanner.detect_changes(known, current)
        assert len(changes["new"]) == 1  # c.day
        assert len(changes["modified"]) == 1  # b.day (mtime changed)
        assert len(changes["unchanged"]) == 1  # a.day


class TestTdxScannerExtractSymbol:
    """_extract_symbol 测试"""

    def test_extract_sh(self):
        assert TdxScanner._extract_symbol("sh000001.day", "sh") == "000001"

    def test_extract_sz(self):
        assert TdxScanner._extract_symbol("sz399001.day", "sz") == "399001"

    def test_extract_bj(self):
        assert TdxScanner._extract_symbol("bj920000.day", "bj") == "920000"

    def test_extract_ds(self):
        assert TdxScanner._extract_symbol("10#AUDUSD.day", "ds") == "10#AUDUSD"


class TestTdxScannerMd5:
    """compute_md5 测试"""

    def test_compute_md5(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        md5 = TdxScanner.compute_md5(str(f))
        assert len(md5) == 32
        assert md5 == "5eb63bbbe01eeed093cb22bb8f5acdc3"
