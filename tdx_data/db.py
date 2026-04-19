"""数据库操作层（MySQL / SQLite 双模式）"""
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .config import TdxConfig
from .models import FileInfo, SyncStatus

logger = logging.getLogger(__name__)


class TdxDatabase:
    """数据库操作层

    支持 MySQL 和 SQLite，通过 config.db_type 切换。
    MySQL 使用 INSERT ... ON DUPLICATE KEY UPDATE。
    SQLite 使用 INSERT OR REPLACE。
    """

    def __init__(self, config: Optional[TdxConfig] = None):
        self.config = config or TdxConfig()
        self.db_type = self.config.db_type
        self._init_schema()

    def _get_conn(self):
        if self.db_type == "mysql":
            import pymysql
            return pymysql.connect(
                host=self.config.mysql_host,
                port=self.config.mysql_port,
                user=self.config.mysql_user,
                password=self.config.mysql_password,
                database=self.config.mysql_database,
                charset="utf8mb4",
                autocommit=False,
            )
        else:
            import sqlite3
            conn = sqlite3.connect(self.config.db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            return conn

    @contextmanager
    def _connect(self):
        """上下文管理器：自动 commit/rollback + close 连接"""
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        if self.db_type == "mysql":
            self._init_mysql_schema()
        else:
            self._init_sqlite_schema()

    def _init_mysql_schema(self):
        sql_path = Path(__file__).parent.parent / "sql" / "schema_mysql.sql"
        if sql_path.exists():
            sql = sql_path.read_text(encoding="utf-8")
            with self._connect() as conn:
                with conn.cursor() as cur:
                    for stmt in sql.split(";"):
                        stmt = stmt.strip()
                        if stmt and not stmt.startswith("--"):
                            try:
                                cur.execute(stmt)
                            except Exception as e:
                                if "already exists" not in str(e).lower():
                                    logger.debug("Schema init skip: %s", e)

    def _init_sqlite_schema(self):
        sql_dir = Path(__file__).parent.parent / "sql"
        with self._connect() as conn:
            for sql_file in ["schema.sql", "indexes.sql"]:
                path = sql_dir / sql_file
                if path.exists():
                    conn.executescript(path.read_text(encoding="utf-8"))

    # ─── 数据写入 ───

    def upsert_dataframe(self, df: pd.DataFrame, table: str,
                         batch_size: int = 5000) -> int:
        """MERGE 写入"""
        if df.empty:
            return 0

        # 确保 trade_date 列存在
        if "trade_date" not in df.columns and "date" not in df.columns:
            if df.index.name in ("date", "trade_date"):
                df = df.reset_index()
            else:
                logger.error("upsert_dataframe: no date/trade_date column found, columns=%s",
                             list(df.columns))
                return 0

        total = 0
        with self._connect() as conn:
            for start in range(0, len(df), batch_size):
                batch = df.iloc[start:start + batch_size].copy()

                # 如果 date 在索引中，移到列
                if "trade_date" not in batch.columns and "date" not in batch.columns:
                    if batch.index.name in ("date", "trade_date"):
                        batch = batch.reset_index()

                if "trade_date" not in batch.columns and "date" in batch.columns:
                    batch = batch.rename(columns={"date": "trade_date"})

                if "trade_date" in batch.columns:
                    batch["trade_date"] = batch["trade_date"].astype(str)
                    # 过滤无效日期
                    batch = batch[batch["trade_date"].str.strip().astype(bool)]
                    batch = batch[batch["trade_date"] != "NaT"]

                if batch.empty:
                    continue

                # 统一列名：open → open_val（MySQL 保留字）
                col_map = {"open": "open_val", "high": "high_val",
                           "low": "low_val", "close": "close_val"}
                for old, new in col_map.items():
                    if old in batch.columns:
                        batch = batch.rename(columns={old: new})

                if self.db_type == "mysql":
                    total += self._upsert_mysql(conn, batch, table)
                else:
                    total += self._upsert_sqlite(conn, batch, table)

        return total

    def _upsert_mysql(self, conn, batch: pd.DataFrame, table: str) -> int:
        codes = batch["code"].astype(str).tolist()
        dates = batch["trade_date"].astype(str).tolist()
        rows = list(zip(
            codes, dates,
            batch["open_val"].tolist(),
            batch["high_val"].tolist(),
            batch["low_val"].tolist(),
            batch["close_val"].tolist(),
            batch["volume"].tolist(),
            batch["amount"].tolist(),
        ))

        with conn.cursor() as cur:
            cur.executemany(f"""
                INSERT INTO {table}
                    (code, trade_date, open_val, high_val, low_val, close_val,
                     volume, amount, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    open_val=VALUES(open_val), high_val=VALUES(high_val),
                    low_val=VALUES(low_val), close_val=VALUES(close_val),
                    volume=VALUES(volume), amount=VALUES(amount),
                    updated_at=NOW()
            """, rows)
        return len(batch)

    def _upsert_sqlite(self, conn, batch: pd.DataFrame, table: str) -> int:
        codes = batch["code"].astype(str).tolist()
        dates = batch["trade_date"].astype(str).tolist()
        rows = list(zip(
            codes, dates,
            batch["open_val"].tolist(),
            batch["high_val"].tolist(),
            batch["low_val"].tolist(),
            batch["close_val"].tolist(),
            batch["volume"].tolist(),
            batch["amount"].tolist(),
        ))

        conn.executemany(f"""
            INSERT OR REPLACE INTO {table}
                (code, trade_date, open_val, high_val, low_val, close_val,
                 volume, amount, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, rows)
        return len(batch)

    # ─── 文件注册表 ───

    def get_file_registry(self) -> Dict[str, FileInfo]:
        with self._connect() as conn:
            if self.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM tdx_file_registry")
                    columns = [d[0] for d in cur.description]
                    rows = [dict(zip(columns, r)) for r in cur.fetchall()]
            else:
                conn.row_factory = self._sqlite_row_factory
                rows = conn.execute(
                    "SELECT * FROM tdx_file_registry"
                ).fetchall()

        return {
            r["file_path"]: FileInfo(
                file_path=r["file_path"],
                market=r["market"],
                symbol=r["symbol"],
                data_type=r["data_type"],
                suffix="",
                file_size=r["file_size"],
                file_mtime=str(r["file_mtime"]),
                md5_hash=r.get("md5_hash"),
            )
            for r in rows
        }

    @staticmethod
    def _sqlite_row_factory(cursor, row):
        columns = [d[0] for d in cursor.description]
        return dict(zip(columns, row))

    def update_file_registry(self, fi: FileInfo, record_count: int):
        with self._connect() as conn:
            if self.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO tdx_file_registry
                            (file_path, market, symbol, data_type,
                             file_size, file_mtime, record_count,
                             last_synced, md5_hash, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s, NOW())
                        ON DUPLICATE KEY UPDATE
                            file_size=%s, file_mtime=%s, record_count=%s,
                            last_synced=NOW(), md5_hash=%s, updated_at=NOW()
                    """, (fi.file_path, fi.market, fi.symbol, fi.data_type,
                          fi.file_size, fi.file_mtime, record_count, fi.md5_hash,
                          fi.file_size, fi.file_mtime, record_count, fi.md5_hash))
            else:
                conn.execute("""
                    INSERT OR REPLACE INTO tdx_file_registry
                        (file_path, market, symbol, data_type,
                         file_size, file_mtime, record_count,
                         last_synced, md5_hash, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, datetime('now'))
                """, (fi.file_path, fi.market, fi.symbol, fi.data_type,
                      fi.file_size, fi.file_mtime, record_count, fi.md5_hash))

    # ─── 同步日志 ───

    def insert_sync_log(self, sync_date: str, mode: str,
                        rows_read: int, rows_written: int,
                        rows_failed: int, duration_sec: float,
                        status: str, error_msg: str = None):
        with self._connect() as conn:
            if self.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO tdx_sync_log
                            (sync_date, market, data_type, rows_read,
                             rows_written, rows_failed, duration_sec,
                             status, error_msg)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (sync_date, mode, None, rows_read, rows_written,
                          rows_failed, duration_sec, status, error_msg))
            else:
                conn.execute("""
                    INSERT INTO tdx_sync_log
                        (sync_date, market, data_type, rows_read,
                         rows_written, rows_failed, duration_sec,
                         status, error_msg, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """, (sync_date, mode, None, rows_read, rows_written,
                      rows_failed, duration_sec, status, error_msg))

    # ─── 查询 API ───

    def get_max_trade_date(self, code: str, table: str = "tdx_daily") -> Optional[str]:
        with self._connect() as conn:
            if self.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute(
                        f"SELECT MAX(trade_date) FROM {table} WHERE code = %s",
                        (code,)
                    )
                    row = cur.fetchone()
                    val = row[0] if row else None
                    return str(val) if val else None
            else:
                row = conn.execute(
                    f"SELECT MAX(trade_date) FROM {table} WHERE code = ?",
                    (code,)
                ).fetchone()
                return row[0] if row and row[0] else None

    def get_record_count(self, table: str, code: str = None) -> int:
        with self._connect() as conn:
            if self.db_type == "mysql":
                with conn.cursor() as cur:
                    if code:
                        cur.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE code = %s",
                            (code,)
                        )
                    else:
                        cur.execute(f"SELECT COUNT(*) FROM {table}")
                    return cur.fetchone()[0]
            else:
                if code:
                    row = conn.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE code = ?",
                        (code,)
                    ).fetchone()
                else:
                    row = conn.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()
                return row[0] if row else 0

    def query_daily(self, code: str, start_date: str = None,
                    end_date: str = None) -> pd.DataFrame:
        with self._connect() as conn:
            if self.db_type == "mysql":
                return self._query_mysql(conn, "tdx_daily", code,
                                         start_date, end_date)
            sql = "SELECT * FROM tdx_daily WHERE code = ?"
            params = [code]
            if start_date:
                sql += " AND trade_date >= ?"
                params.append(start_date)
            if end_date:
                sql += " AND trade_date <= ?"
                params.append(end_date)
            sql += " ORDER BY trade_date"
            return pd.read_sql_query(sql, conn, params=params)

    def query_minute_5(self, code: str, trade_date: str = None) -> pd.DataFrame:
        with self._connect() as conn:
            if self.db_type == "mysql":
                return self._query_mysql(conn, "tdx_minute_5", code,
                                         trade_date, None)
            sql = "SELECT * FROM tdx_minute_5 WHERE code = ?"
            params = [code]
            if trade_date:
                sql += " AND trade_date LIKE ?"
                params.append(f"{trade_date}%")
            sql += " ORDER BY trade_date"
            return pd.read_sql_query(sql, conn, params=params)

    def query_minute_1(self, code: str, trade_date: str = None) -> pd.DataFrame:
        with self._connect() as conn:
            if self.db_type == "mysql":
                return self._query_mysql(conn, "tdx_minute_1", code,
                                         trade_date, None)
            sql = "SELECT * FROM tdx_minute_1 WHERE code = ?"
            params = [code]
            if trade_date:
                sql += " AND trade_date LIKE ?"
                params.append(f"{trade_date}%")
            sql += " ORDER BY trade_date"
            return pd.read_sql_query(sql, conn, params=params)

    def _query_mysql(self, conn, table: str, code: str,
                      start_date: str = None, end_date: str = None) -> pd.DataFrame:
        sql = f"SELECT * FROM {table} WHERE code = %s"
        params = [code]
        if start_date:
            sql += " AND trade_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND trade_date <= %s"
            params.append(end_date)
        sql += " ORDER BY trade_date"

        import pymysql
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return pd.DataFrame(rows)

    def check_primary_key_integrity(self, table: str) -> Dict[str, int]:
        with self._connect() as conn:
            if self.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute(f"""
                        SELECT COUNT(*) - COUNT(DISTINCT code, trade_date)
                        FROM {table}
                    """)
                    dup = cur.fetchone()[0]
            else:
                row = conn.execute(f"""
                    SELECT COUNT(*) - COUNT(*)
                    FROM (SELECT DISTINCT code, trade_date FROM {table})
                """).fetchone()
                dup = row[0] if row else 0
        return {"duplicate_count": dup}
