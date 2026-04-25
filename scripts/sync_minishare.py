#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""minishare API → 本地数据库 日线同步脚本.

Usage:
    python scripts/sync_minishare.py --codes 515180,159545,000001 --dry-run
    python scripts/sync_minishare.py --watchlist config/watchlist.txt
    python scripts/sync_minishare.py --all-shsz
    python scripts/sync_minishare.py --etf-only --codes 515180,159545
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import List, Optional

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxConfig, TdxDatabase
from tdx_core.minishare_client import MinishareClient, MinishareError

logger = logging.getLogger(__name__)


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def _load_watchlist(path: str) -> List[str]:
    """从文件读取代码列表，每行一个 6 位数字."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"关注列表文件不存在: {path}")
    codes = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and line.isdigit() and len(line) == 6:
            codes.append(line)
    return codes


def _classify_codes(codes: List[str]) -> dict[str, List[str]]:
    """把代码分类为 stock / etf / index.

    启发式规则：
    - 6/0/3/9 开头 且 非 ETF 代码 → stock
    - 5 开头（如 51xxxx, 15xxxx, 56xxxx, 58xxxx, 16xxxx, 51xxxx）→ etf
    - 000001 / 399001 / 399006 / 000688 等 → index
    """
    result: dict[str, List[str]] = {"stock": [], "etf": [], "index": []}
    etf_prefixes = ("5", "15", "16", "51", "56", "58")
    index_codes = {"000001", "000002", "000003", "000004",
                   "399001", "399005", "399006", "399300", "000688"}

    for code in codes:
        if code in index_codes:
            result["index"].append(code)
        elif any(code.startswith(p) for p in etf_prefixes):
            result["etf"].append(code)
        else:
            result["stock"].append(code)
    return result


def _fetch_and_normalize(
    client: MinishareClient,
    codes: List[str],
    code_type: str,
) -> Optional[object]:
    """按类型拉取并返回标准化 DataFrame."""
    if not codes:
        return None

    try:
        if code_type == "stock":
            return client.get_snapshot(codes)
        elif code_type == "etf":
            return client.get_etf_snapshot(codes)
        elif code_type == "index":
            return client.get_index_snapshot(codes)
        else:
            logger.warning("未知代码类型: %s", code_type)
            return None
    except MinishareError as exc:
        logger.error("[%s] 拉取失败: %s", code_type, exc)
        return None


def _get_all_shsz_codes(db: TdxDatabase) -> List[str]:
    """从本地数据库获取所有已有的沪深代码（用于 --all-shsz）."""
    sql = "SELECT DISTINCT code FROM tdx_daily WHERE code LIKE '0%' OR code LIKE '3%' OR code LIKE '6%' ORDER BY code"
    try:
        with db._connect() as conn:
            if db.db_type == "mysql":
                import pymysql
                with conn.cursor() as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
                    return [r[0] for r in rows]
            else:
                rows = conn.execute(sql).fetchall()
                return [r[0] for r in rows]
    except Exception as exc:
        logger.error("读取本地代码列表失败: %s", exc)
        return []


def main():
    parser = argparse.ArgumentParser(description="minishare API 日线同步到本地数据库")
    parser.add_argument("--codes", help="逗号分隔的 6 位代码列表，如 600519,000001")
    parser.add_argument("--watchlist", help="代码列表文件路径，每行一个代码")
    parser.add_argument("--all-shsz", action="store_true",
                        help="同步本地数据库中已有的全部沪深代码（注意 API 限额）")
    parser.add_argument("--etf-only", action="store_true", help="仅同步 ETF")
    parser.add_argument("--mode", choices=["daily", "intraday"], default="daily",
                        help="同步模式: daily=rt_k_ms 日线快照(需权限), intraday=rt_min_daily 分钟线聚合(默认)")
    parser.add_argument("--dry-run", action="store_true",
                        help="预览数据，不写入数据库")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")
    args = parser.parse_args()

    _setup_logging()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ── 收集代码 ──
    codes: List[str] = []
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip().isdigit()]
    elif args.watchlist:
        codes = _load_watchlist(args.watchlist)
    elif args.all_shsz:
        logger.info("--all-shsz 模式：读取本地数据库代码列表...")
        db = TdxDatabase()
        codes = _get_all_shsz_codes(db)
        logger.info("本地共有 %d 支沪深代码待同步", len(codes))
    else:
        parser.print_help()
        sys.exit(1)

    if not codes:
        print("没有可同步的代码", file=sys.stderr)
        sys.exit(1)

    # ── 分类 ──
    classified = _classify_codes(codes)
    total = sum(len(v) for v in classified.values())
    logger.info("代码分类: stock=%d, etf=%d, index=%d, 总计=%d",
                len(classified["stock"]),
                len(classified["etf"]),
                len(classified["index"]),
                total)

    # ── 初始化客户端 ──
    try:
        client = MinishareClient()
    except MinishareError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    # ── 拉取数据 ──
    all_dfs = []
    start_time = time.time()

    for code_type, type_codes in classified.items():
        if args.etf_only and code_type != "etf":
            continue
        if not type_codes:
            continue

        if args.mode == "intraday":
            # Use rt_min_daily aggregation (works with rt_min permission)
            df = client.get_intraday_snapshot(type_codes)
        else:
            df = _fetch_and_normalize(client, type_codes, code_type)

        if df is not None and not df.empty:
            all_dfs.append(df)
            logger.info("[%s] 成功拉取 %d 行 (mode=%s)", code_type, len(df), args.mode)

    if not all_dfs:
        print("没有拉取到任何数据", file=sys.stderr)
        sys.exit(1)

    combined = __import__("pandas", fromlist=["concat"]).concat(all_dfs, ignore_index=True)
    elapsed = time.time() - start_time
    logger.info("拉取完成: %d 行, 耗时 %.1f 秒", len(combined), elapsed)

    # ── 预览 ──
    if args.dry_run:
        print("\n=== DRY RUN 预览 ===")
        print(combined.head(10).to_string(index=False))
        print(f"\n共 {len(combined)} 行，未写入数据库（--dry-run）")
        sys.exit(0)

    # ── 写入数据库 ──
    config = TdxConfig()
    db = TdxDatabase(config)
    rows_written = db.upsert_dataframe(combined, "tdx_daily")
    logger.info("数据库写入完成: %d 行 upserted", rows_written)

    # ── 同步日志 ──
    db.insert_sync_log(
        sync_date=__import__("datetime").date.today().isoformat(),
        mode="minishare_api",
        rows_read=len(combined),
        rows_written=rows_written,
        rows_failed=len(combined) - rows_written,
        duration_sec=round(elapsed, 2),
        status="SUCCESS",
    )

    print(f"\n同步完成: {total} 支代码, {rows_written} 行写入数据库, 耗时 {elapsed:.1f} 秒")


if __name__ == "__main__":
    main()
