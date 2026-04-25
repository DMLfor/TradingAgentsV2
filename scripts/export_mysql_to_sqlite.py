#!/usr/bin/env python3
"""MySQL tdx_data 导出为 SQLite —— 批量流式优化版

速度优化核心：
1. MySQL SSCursor 流式游标：1次大查询替代 57,875 次逐代码查询
2. SQLite journal_mode=OFF + synchronous=OFF：写入速度 ×3-5
3. 每 10万行批量 executemany：减少事务开销
4. 元组批量转换：避免 DictCursor 逐行对象创建

Usage:
    # 全量导出（默认）
    python scripts/export_mysql_to_sqlite.py

    # 指定输出路径
    python scripts/export_mysql_to_sqlite.py --output data/tdx_data.db

    # 仅导出部分代码（测试用）
    python scripts/export_mysql_to_sqlite.py --codes 515180,159545,000300

    # 跳过验证（更快）
    python scripts/export_mysql_to_sqlite.py --skip-verify
"""
import argparse
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).parent.parent / "sql"


def _load_schema_sql() -> str:
    """读取 schema.sql 和 indexes.sql"""
    parts = []
    for fname in ["schema.sql", "indexes.sql"]:
        fpath = SQL_DIR / fname
        if fpath.exists():
            parts.append(fpath.read_text(encoding="utf-8"))
    return "\n".join(parts)


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


def init_sqlite(db_path: str):
    """初始化 SQLite（建表，不建索引——索引最后统一建）"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    if Path(db_path).exists():
        Path(db_path).unlink()
    conn = sqlite3.connect(db_path)
    # 先执行 schema（建表）
    schema_sql = _load_schema_sql()
    # 去掉索引创建（最后统一建，导入期间索引会拖慢写入）
    schema_lines = []
    for line in schema_sql.split(";"):
        stripped = line.strip()
        if stripped and not stripped.upper().startswith("CREATE INDEX"):
            schema_lines.append(stripped)
    conn.executescript(";".join(schema_lines))
    conn.commit()
    conn.close()
    logger.info("[SQLite] 数据库初始化完成（表已建，索引延后）: %s", db_path)


def build_index_sql() -> str:
    """从 schema.sql 中提取 CREATE INDEX 语句"""
    schema_sql = _load_schema_sql()
    indexes = []
    for stmt in schema_sql.split(";"):
        stripped = stmt.strip()
        if stripped.upper().startswith("CREATE INDEX"):
            indexes.append(stripped)
    return ";".join(indexes) + ";"


def export_daily_fast(config: TdxConfig, sqlite_path: str, codes_filter: list = None):
    """批量流式导出 tdx_daily"""

    # ── 1. 统计信息（普通连接） ──
    stats_conn = get_mysql_conn(config)
    with stats_conn.cursor() as cur:
        where_clause = ""
        params = ()
        if codes_filter:
            placeholders = ",".join(["%s"] * len(codes_filter))
            where_clause = f"WHERE code IN ({placeholders})"
            params = tuple(codes_filter)

        cur.execute(f"SELECT COUNT(*) FROM tdx_daily {where_clause}", params)
        total_expected = cur.fetchone()["COUNT(*)"]

        cur.execute(f"SELECT MIN(trade_date), MAX(trade_date) FROM tdx_daily {where_clause}", params)
        min_date, max_date = cur.fetchone().values()
    stats_conn.close()

    logger.info("[MySQL] 待导出: %d 行, 日期范围: %s ~ %s", total_expected, min_date, max_date)

    # ── 2. 流式读取 + 批量写入 ──
    sqlite_conn = sqlite3.connect(sqlite_path)
    # 极速写入模式（导入完成后恢复）
    sqlite_conn.execute("PRAGMA journal_mode=OFF")
    sqlite_conn.execute("PRAGMA synchronous=OFF")
    sqlite_conn.execute("PRAGMA cache_size=-100000")  # 100MB 缓存
    sqlite_conn.execute("PRAGMA temp_store=MEMORY")
    sqlite_conn.commit()

    # MySQL 流式游标连接
    stream_conn = get_mysql_conn(config, cursorclass=pymysql.cursors.SSCursor)

    columns = ["code", "trade_date", "open_val", "high_val", "low_val",
               "close_val", "volume", "amount", "adj_factor", "is_suspended"]
    col_str = ",".join(columns)

    where_clause = ""
    params = ()
    if codes_filter:
        placeholders = ",".join(["%s"] * len(codes_filter))
        where_clause = f"WHERE code IN ({placeholders})"
        params = tuple(codes_filter)

    sql = f"SELECT {col_str} FROM tdx_daily {where_clause} ORDER BY code, trade_date"

    total_rows = 0
    batch = []
    BATCH_SIZE = 50000  # 每 5万行写入一次 SQLite
    COMMIT_EVERY = 100000  # 每 10万行 commit 一次
    last_commit = 0
    start_time = time.time()

    try:
        with stream_conn.cursor() as cur:
            cur.execute(sql, params)

            logger.info("[导出] 开始流式读取...")

            while True:
                # fetchmany 避免一次性加载全部到内存
                rows = cur.fetchmany(BATCH_SIZE)
                if not rows:
                    break

                # 转换为 SQLite 元组（Decimal → float）
                sqlite_rows = []
                for row in rows:
                    sqlite_rows.append(tuple(
                        float(v) if isinstance(v, (int, float, type(row[4]))) and i >= 2 else
                        str(v) if i == 1 else  # trade_date
                        str(v) if i == 0 else  # code
                        float(v) if v is not None else None
                        for i, v in enumerate(row)
                    ))

                sqlite_conn.executemany(
                    f"""
                    INSERT INTO tdx_daily ({col_str}, created_at, updated_at)
                    VALUES ({','.join(['?'] * len(columns))}, datetime('now'), datetime('now'))
                    """,
                    sqlite_rows
                )
                total_rows += len(sqlite_rows)
                batch.extend(sqlite_rows)

                # 批量 commit
                if total_rows - last_commit >= COMMIT_EVERY:
                    sqlite_conn.commit()
                    elapsed = time.time() - start_time
                    rate = total_rows / elapsed if elapsed > 0 else 0
                    pct = total_rows / total_expected * 100 if total_expected > 0 else 0
                    logger.info(
                        "[进度] %d/%d 行 (%.1f%%), 耗时 %.1fs, 速率 %.0f 行/s",
                        total_rows, total_expected, pct, elapsed, rate
                    )
                    last_commit = total_rows
                    batch = []

        # 最后一批 commit
        if batch:
            sqlite_conn.commit()

    finally:
        stream_conn.close()

    # ── 3. 恢复 SQLite 设置 ──
    logger.info("[SQLite] 导入完成，重建索引...")
    sqlite_conn.execute("PRAGMA journal_mode=WAL")
    sqlite_conn.execute("PRAGMA synchronous=NORMAL")
    sqlite_conn.executescript(build_index_sql())
    sqlite_conn.commit()

    # VACUUM 整理空间
    logger.info("[SQLite] 执行 VACUUM...")
    sqlite_conn.execute("VACUUM")
    sqlite_conn.commit()
    sqlite_conn.close()

    elapsed = time.time() - start_time
    rate = total_rows / elapsed if elapsed > 0 else 0
    logger.info("[完成] 共导出 %d 行, 耗时 %.1fs, 平均速率 %.0f 行/s",
                total_rows, elapsed, rate)

    return total_rows


def export_metadata_fast(config: TdxConfig, sqlite_path: str):
    """导出元数据表（数据量小，保持简单）"""
    mysql_conn = get_mysql_conn(config)
    sqlite_conn = sqlite3.connect(sqlite_path)

    tables = ["tdx_file_registry", "tdx_sync_log"]
    for table in tables:
        with mysql_conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {table}")
            rows = cur.fetchall()

        if not rows:
            logger.info("[元数据] %s 无数据，跳过", table)
            continue

        columns = list(rows[0].keys())
        placeholders = ",".join(["?"] * len(columns))
        col_names = ",".join(columns)

        sqlite_rows = []
        for row in rows:
            sqlite_rows.append(tuple(
                str(row.get(c, "")) if row.get(c) is not None else None
                for c in columns
            ))

        sqlite_conn.executemany(
            f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})",
            sqlite_rows
        )
        logger.info("[元数据] %s 导出 %d 行", table, len(sqlite_rows))

    sqlite_conn.commit()
    sqlite_conn.close()
    mysql_conn.close()


def verify_export(sqlite_path: str, expected_rows: int = None):
    """验证导出结果"""
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()

    checks = {
        "总代码数": "SELECT COUNT(DISTINCT code) FROM tdx_daily",
        "总行数": "SELECT COUNT(*) FROM tdx_daily",
        "最早日期": "SELECT MIN(trade_date) FROM tdx_daily",
        "最新日期": "SELECT MAX(trade_date) FROM tdx_daily",
    }

    logger.info("=" * 50)
    logger.info("[验证] SQLite 导出结果")
    for name, sql in checks.items():
        cur.execute(sql)
        val = cur.fetchone()[0]
        logger.info("  %s: %s", name, val)
        if name == "总行数" and expected_rows and val != expected_rows:
            logger.warning("  [警告] 行数不匹配! 期望 %d, 实际 %d", expected_rows, val)

    # 性能测试
    t0 = time.time()
    cur.execute("SELECT * FROM tdx_daily WHERE code='515180' ORDER BY trade_date")
    rows = cur.fetchall()
    t1 = time.time()
    logger.info("  单代码查询(515180): %d 行, %.3fs", len(rows), t1 - t0)

    # 索引检查
    cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tdx_daily'")
    idx_names = [r[0] for r in cur.fetchall()]
    logger.info("  索引: %s", ", ".join(idx_names))

    conn.close()
    logger.info("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="MySQL → SQLite 极速导出")
    parser.add_argument("--output", "-o", default="data/tdx_data.db",
                        help="SQLite 输出路径 (默认: data/tdx_data.db)")
    parser.add_argument("--codes", help="仅导出指定代码，逗号分隔")
    parser.add_argument("--skip-verify", action="store_true", help="跳过验证")
    parser.add_argument("--config", help="配置文件路径")
    args = parser.parse_args()

    config = TdxConfig()
    if args.config:
        config = TdxConfig.from_yaml(args.config)

    codes_filter = None
    if args.codes:
        codes_filter = [c.strip() for c in args.codes.split(",")]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 如果已存在，删除
    if output_path.exists():
        logger.info("[清理] 删除旧的 SQLite 文件: %s", output_path)
        output_path.unlink()

    logger.info("[开始] MySQL → SQLite 极速导出")
    logger.info("  MySQL: %s:%d/%s", config.mysql_host, config.mysql_port, config.mysql_database)
    logger.info("  SQLite: %s", output_path)
    if codes_filter:
        logger.info("  筛选代码: %s", ", ".join(codes_filter))

    overall_start = time.time()

    # 1. 初始化 SQLite
    init_sqlite(str(output_path))

    # 2. 导出日线数据（批量流式）
    total_rows = export_daily_fast(config, str(output_path), codes_filter)

    # 3. 导出元数据
    export_metadata_fast(config, str(output_path))

    overall_elapsed = time.time() - overall_start

    # 4. 验证
    if not args.skip_verify:
        verify_export(str(output_path), expected_rows=total_rows)

    # 5. 文件大小
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info("[完成] SQLite 文件: %s (%.1f MB)", output_path, file_size_mb)
    logger.info("[完成] 共导出 %d 行数据, 总耗时 %.1fs", total_rows, overall_elapsed)


if __name__ == "__main__":
    main()
