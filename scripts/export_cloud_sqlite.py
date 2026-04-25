#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出云端 SQLite 数据包（sz/sh 近1年日线）.

Usage:
    python scripts/export_cloud_sqlite.py
    python scripts/export_cloud_sqlite.py --output data/tdx_data_cloud.db
"""
from __future__ import annotations

import argparse
import gzip
import logging
import sqlite3
import sys
import time
from pathlib import Path

import pymysql

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core.config import TdxConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).parent.parent / "sql"

MARKET_PREFIXES = {
    "sh": ("60", "68", "51", "000"),
    "sz": ("00", "30", "15", "39"),
}


def get_mysql_conn(config: TdxConfig, cursorclass=pymysql.cursors.DictCursor):
    return pymysql.connect(
        host=config.mysql_host,
        port=config.mysql_port,
        user=config.mysql_user,
        password=config.mysql_password,
        database=config.mysql_database,
        charset="utf8mb4",
        cursorclass=cursorclass,
    )


def _load_schema_sql() -> str:
    parts = []
    for fname in ["schema.sql", "indexes.sql"]:
        fpath = SQL_DIR / fname
        if fpath.exists():
            parts.append(fpath.read_text(encoding="utf-8"))
    return "\n".join(parts)


def init_sqlite(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    if Path(db_path).exists():
        Path(db_path).unlink()
    conn = sqlite3.connect(db_path)
    schema_sql = _load_schema_sql()
    schema_lines = []
    for line in schema_sql.split(";"):
        stripped = line.strip()
        if stripped and not stripped.upper().startswith("CREATE INDEX"):
            schema_lines.append(stripped)
    conn.executescript(";".join(schema_lines))
    conn.commit()
    conn.close()
    logger.info("[SQLite] Init done: %s", db_path)


def build_index_sql() -> str:
    schema_sql = _load_schema_sql()
    indexes = []
    for stmt in schema_sql.split(";"):
        stripped = stmt.strip()
        if stripped.upper().startswith("CREATE INDEX"):
            indexes.append(stripped)
    return ";".join(indexes) + ";"


def get_codes(config: TdxConfig) -> list[str]:
    """Query all distinct codes from tdx_daily for sz + sh markets."""
    conn = get_mysql_conn(config)
    try:
        with conn.cursor() as cur:
            # Build prefix conditions
            conditions = []
            for prefix in MARKET_PREFIXES["sh"]:
                conditions.append(f"code LIKE '{prefix}%'")
            for prefix in MARKET_PREFIXES["sz"]:
                conditions.append(f"code LIKE '{prefix}%'")
            where = " OR ".join(conditions)
            sql = f"SELECT DISTINCT code FROM tdx_daily WHERE {where} ORDER BY code"
            cur.execute(sql)
            rows = cur.fetchall()
            codes = [r["code"] for r in rows]
            logger.info("[MySQL] Found %d codes for sz+sh markets", len(codes))
            return codes
    finally:
        conn.close()


def export_daily(config: TdxConfig, sqlite_path: str, codes: list[str]):
    """Stream export tdx_daily for given codes, last 1 year only."""
    init_sqlite(sqlite_path)

    # Stats
    stats_conn = get_mysql_conn(config)
    try:
        with stats_conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(codes))
            cur.execute(
                f"""SELECT COUNT(*) FROM tdx_daily
                   WHERE code IN ({placeholders})
                   AND trade_date >= DATE_SUB(CURDATE(), INTERVAL 1 YEAR)""",
                tuple(codes),
            )
            total_expected = cur.fetchone()["COUNT(*)"]
            cur.execute(
                f"""SELECT MIN(trade_date), MAX(trade_date) FROM tdx_daily
                   WHERE code IN ({placeholders})
                   AND trade_date >= DATE_SUB(CURDATE(), INTERVAL 1 YEAR)""",
                tuple(codes),
            )
            min_date, max_date = cur.fetchone().values()
    finally:
        stats_conn.close()

    logger.info("[MySQL] Expected rows: %d, date range: %s ~ %s",
                total_expected, min_date, max_date)

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.execute("PRAGMA journal_mode=OFF")
    sqlite_conn.execute("PRAGMA synchronous=OFF")
    sqlite_conn.execute("PRAGMA cache_size=-100000")
    sqlite_conn.execute("PRAGMA temp_store=MEMORY")
    sqlite_conn.commit()

    stream_conn = get_mysql_conn(config, cursorclass=pymysql.cursors.SSCursor)

    columns = ["code", "trade_date", "open_val", "high_val", "low_val",
               "close_val", "volume", "amount", "adj_factor", "is_suspended"]
    col_str = ",".join(columns)
    placeholders = ",".join(["%s"] * len(codes))

    sql = f"""SELECT {col_str} FROM tdx_daily
              WHERE code IN ({placeholders})
              AND trade_date >= DATE_SUB(CURDATE(), INTERVAL 1 YEAR)
              ORDER BY code, trade_date"""

    total_rows = 0
    batch = []
    BATCH_SIZE = 50000
    COMMIT_EVERY = 100000
    last_commit = 0
    start_time = time.time()

    try:
        with stream_conn.cursor() as cur:
            cur.execute(sql, tuple(codes))
            logger.info("[Export] Streaming started...")
            while True:
                rows = cur.fetchmany(BATCH_SIZE)
                if not rows:
                    break
                sqlite_rows = []
                for row in rows:
                    sqlite_rows.append(tuple(
                        float(v) if isinstance(v, (int, float)) and i >= 2 else
                        str(v) if i in (0, 1) else
                        float(v) if v is not None else None
                        for i, v in enumerate(row)
                    ))
                sqlite_conn.executemany(
                    f"""INSERT INTO tdx_daily
                        ({col_str}, created_at, updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?, datetime('now'), datetime('now'))""",
                    sqlite_rows,
                )
                total_rows += len(sqlite_rows)
                if total_rows - last_commit >= COMMIT_EVERY:
                    sqlite_conn.commit()
                    elapsed = time.time() - start_time
                    logger.info("[Export] %d rows, %.1f sec, %.0f rows/sec",
                                total_rows, elapsed, total_rows / elapsed)
                    last_commit = total_rows
    finally:
        stream_conn.close()

    sqlite_conn.commit()

    # Build indexes
    logger.info("[SQLite] Building indexes...")
    index_sql = build_index_sql()
    if index_sql.strip():
        sqlite_conn.executescript(index_sql)
    sqlite_conn.commit()

    # Stats
    row = sqlite_conn.execute("SELECT COUNT(*) FROM tdx_daily").fetchone()
    actual_rows = row[0] if row else 0
    row = sqlite_conn.execute("SELECT COUNT(DISTINCT code) FROM tdx_daily").fetchone()
    actual_codes = row[0] if row else 0
    sqlite_conn.close()

    elapsed = time.time() - start_time
    logger.info("[Export] Done: %d rows, %d codes in %.1f sec",
                actual_rows, actual_codes, elapsed)
    return actual_rows


def compress_db(db_path: str) -> str:
    """Gzip compress the db file, return gz path."""
    gz_path = db_path + ".gz"
    logger.info("[Compress] %s -> %s", db_path, gz_path)
    with open(db_path, "rb") as f_in:
        with gzip.open(gz_path, "wb", compresslevel=6) as f_out:
            f_out.writelines(f_in)
    original = Path(db_path).stat().st_size
    compressed = Path(gz_path).stat().st_size
    ratio = compressed / original * 100
    logger.info("[Compress] Original: %.1f MB, Compressed: %.1f MB (%.1f%%)",
                original / 1024 / 1024, compressed / 1024 / 1024, ratio)
    return gz_path


def main():
    parser = argparse.ArgumentParser(description="Export cloud SQLite (sz+sh, last 1 year)")
    parser.add_argument("--output", default="data/tdx_data_cloud.db", help="Output SQLite path")
    parser.add_argument("--skip-compress", action="store_true", help="Skip gzip compression")
    args = parser.parse_args()

    config = TdxConfig()
    codes = get_codes(config)
    if not codes:
        logger.error("No codes found for sz+sh markets")
        sys.exit(1)

    export_daily(config, args.output, codes)

    if not args.skip_compress:
        compress_db(args.output)
        logger.info("[Done] Output: %s.gz", args.output)
    else:
        logger.info("[Done] Output: %s", args.output)


if __name__ == "__main__":
    main()
