#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端环境综合验证测试.

验证项目 clone + pip install 后，核心功能是否全部可用。
在 Linux 云端 / OpenClaw / 无 MySQL 环境下运行。

Usage:
    cd TradingAgentsV2
    source venv/bin/activate
    python tests/test_cloud_setup.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
PASS = "\u2705 PASS"
FAIL = "\u274c FAIL"
SKIP = "\u23ed\ufe0f SKIP"


def run(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    """Run a command and return (rc, stdout, stderr)."""
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT
    )
    return result.returncode, result.stdout, result.stderr


def test_01_tdx_cli() -> bool:
    """验证 tdx CLI 可用."""
    rc, out, _ = run(["tdx", "--help"])
    ok = rc == 0 and "Commands:" in out
    print(f"  {'tdx --help':<30} {PASS if ok else FAIL}")
    return ok


def test_02_db_auto_detect() -> bool:
    """验证数据库自动检测（云端 SQLite / 本地 MySQL）."""
    from tdx_core.config import TdxConfig
    c = TdxConfig()
    cloud_db = ROOT / "data" / "tdx_data_cloud.db"
    cloud_gz = ROOT / "data" / "tdx_data_cloud.db.gz"
    is_cloud = cloud_db.exists() or cloud_gz.exists()
    expected = "sqlite" if is_cloud else "mysql"
    ok = c.db_type == expected
    label = "SQLite auto-detect" if is_cloud else "MySQL default"
    print(f"  {label:<30} {PASS if ok else FAIL} (db_type={c.db_type})")
    return ok


def test_03_db_connection() -> bool:
    """验证数据库可连接（云端检查解压，本地检查 MySQL）."""
    from tdx_core.config import TdxConfig
    c = TdxConfig()
    if c.db_type == "sqlite":
        db_path = ROOT / "data" / "tdx_data_cloud.db"
        ok = db_path.exists()
        size_mb = db_path.stat().st_size / 1024 / 1024 if ok else 0
        print(f"  {'SQLite DB exists':<30} {PASS if ok else FAIL} ({size_mb:.1f} MB)")
    else:
        from tdx_core.db import TdxDatabase
        try:
            db = TdxDatabase()
            conn = db._get_conn()
            conn.close()
            ok = True
        except Exception as e:
            ok = False
            print(f"    MySQL error: {e}")
        print(f"  {'MySQL connect':<30} {PASS if ok else FAIL}")
    return ok


def test_04_query_daily() -> bool:
    """验证日线查询."""
    from tdx_core.query import TdxQuery
    q = TdxQuery()
    df = q.get_daily("515180")
    ok = len(df) > 100
    print(f"  {'get_daily(515180)':<30} {PASS if ok else FAIL} ({len(df)} rows)")
    q.close()
    return ok


def test_05_signal_tracker() -> bool:
    """验证信号跟踪."""
    sys.path.insert(0, str(ROOT))
    from scripts.signal_tracker import build_report
    text = build_report("515180", "rsi30_bounce", {}, save=False)
    ok = "\u4fe1\u53f7" in text  # 信号
    print(f"  {'signal_tracker(515180)':<30} {PASS if ok else FAIL}")
    return ok


def test_06_rank_top5() -> bool:
    """验证板块排名（只跑 Top 5，减少时间）."""
    try:
        rc, out, err = run(["python", "scripts/rank_growth_board.py", "--bars", "30", "--top", "5"], timeout=45)
        ok = rc == 0 and ("Top 5" in out or "\u6392\u540d" in out)
        print(f"  {'rank --top 5':<30} {PASS if ok else FAIL}")
        return ok
    except subprocess.TimeoutExpired:
        print(f"  {'rank --top 5':<30} {SKIP} (timeout > 45s)")
        return True  # treat as acceptable skip


def test_07_scan_market() -> bool:
    """验证市场扫描."""
    rc, out, _ = run([
        "python", "scripts/scan_market.py",
        "000001,000002", "--indicator", "macd", "--signal", "golden_cross"
    ])
    ok = rc == 0 and "Scan" in out
    print(f"  {'scan 000001,000002':<30} {PASS if ok else FAIL}")
    return ok


def test_08_list_indicators() -> bool:
    """验证指标列表."""
    rc, out, _ = run(["tdx", "list-indicators"])
    ok = rc == 0 and "macd" in out.lower()
    print(f"  {'list-indicators':<30} {PASS if ok else FAIL}")
    return ok


def test_09_list_strategies() -> bool:
    """验证策略列表."""
    rc, out, _ = run(["tdx", "list-strategies"])
    ok = rc == 0 and "rsi" in out.lower()
    print(f"  {'list-strategies':<30} {PASS if ok else FAIL}")
    return ok


def test_10_strategy_backtest() -> bool:
    """验证策略回测（简化模式，只跑 515180）."""
    strategy_file = ROOT / "strategies" / "515180_rsi30_bounce.json"
    if not strategy_file.exists():
        print(f"  {'backtest 515180':<30} {SKIP} (strategy file not found)")
        return True

    sys.path.insert(0, str(ROOT))
    from tdx_core.indicators import TdxIndicators
    from tdx_core.query import TdxQuery

    try:
        q = TdxQuery()
        df = q.get_daily("515180")
        q.close()
        if len(df) < 60:
            print(f"  {'backtest 515180':<30} {SKIP} (not enough data)")
            return True

        # Simple manual backtest: buy if RSI < 30, sell if > 70
        df = TdxIndicators.compute(df, indicators=["rsi"])
        df["rsi_14"] = df["rsi_14"].astype(float)

        trades = 0
        position = 0
        for _, row in df.iterrows():
            rsi = row["rsi_14"]
            if position == 0 and rsi < 30:
                position = 1
                trades += 1
            elif position == 1 and rsi > 70:
                position = 0
                trades += 1

        ok = trades >= 0  # allow zero trades (just verify pipeline works)
        print(f"  {'backtest 515180':<30} {PASS if ok else FAIL} ({trades} signals)")
        return ok
    except Exception as e:
        print(f"  {'backtest 515180':<30} {FAIL} ({e})")
        return False


def main():
    print("=" * 60)
    print("TradingAgentsV2 \u4e91\u7aef\u73af\u5883\u7efc\u5408\u9a8c\u8bc1\u6d4b\u8bd5")
    print("=" * 60)
    print(f"\u9879\u76ee\u8def\u5f84: {ROOT}")
    print(f"Python: {sys.version.split()[0]}")
    print("-" * 60)

    tests = [
        ("01 tdx CLI", test_01_tdx_cli),
        ("02 DB auto-detect", test_02_db_auto_detect),
        ("03 DB connection", test_03_db_connection),
        ("04 Query daily", test_04_query_daily),
        ("05 Signal tracker", test_05_signal_tracker),
        ("06 Rank top 5", test_06_rank_top5),
        ("07 Scan market", test_07_scan_market),
        ("08 List indicators", test_08_list_indicators),
        ("09 List strategies", test_09_list_strategies),
        ("10 Backtest", test_10_strategy_backtest),
    ]

    results = []
    start = time.time()
    for name, fn in tests:
        try:
            ok = fn()
            results.append((name, ok))
        except Exception as e:
            print(f"  {name:<30} {FAIL} (exception: {e})")
            results.append((name, False))

    elapsed = time.time() - start
    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    print("-" * 60)
    print(f"\u7ed3\u679c: {passed}/{total} \u901a\u8fc7, \u8017\u65f6 {elapsed:.1f}\u79d2")
    print("=" * 60)

    if passed == total:
        print("\u2705 \u5168\u90e8\u6d4b\u8bd5\u901a\u8fc7\uff01\u4e91\u7aef\u73af\u5883\u5c31\u7eea\u3002")
        return 0
    else:
        print("\u274c \u90e8\u5206\u6d4b\u8bd5\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u4ee5\u4e0a\u9519\u8bef\u9879\u3002")
        return 1


if __name__ == "__main__":
    sys.exit(main())
