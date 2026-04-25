"""高层查询 API — 从其它项目直接 import 即可使用

典型用法:
    from tdx_core import TdxQuery

    q = TdxQuery()                       # 默认读 config/tdx_config.yaml
    df = q.get_daily("000001")            # 日线
    df = q.get_daily("000001", start_date="2024-01-01", end_date="2024-12-31")
    df = q.get_minute_5("000001")         # 5分钟线
    df = q.get_minute_1("000001")         # 1分钟线
    codes = q.get_stock_list()            # 所有有数据的股票代码
    q.close()
"""
import logging
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .config import TdxConfig
from .db import TdxDatabase
from .minishare_client import MinishareClient, MinishareError

logger = logging.getLogger(__name__)


class TdxQuery:
    """高层查询接口，封装 TdxDatabase 的常用读取操作"""

    def __init__(self, config: Optional[TdxConfig] = None,
                 yaml_path: Optional[str] = None,
                 minishare_client: Optional[MinishareClient] = None):
        if config:
            self.config = config
        elif yaml_path:
            self.config = TdxConfig.from_yaml(yaml_path)
        else:
            # 自动查找 config/tdx_config.yaml
            default_yaml = Path(__file__).parent.parent / "config" / "tdx_config.yaml"
            if default_yaml.exists():
                self.config = TdxConfig.from_yaml(str(default_yaml))
            else:
                self.config = TdxConfig()
        self.db = TdxDatabase(self.config)
        self._ms_client = minishare_client
        if self._ms_client is None and self.config.minishare_token:
            try:
                self._ms_client = MinishareClient(self.config.minishare_token)
            except MinishareError:
                self._ms_client = None

    # ─── 日线 ───

    def get_daily(self, code: str,
                  start_date: Optional[str] = None,
                  end_date: Optional[str] = None) -> pd.DataFrame:
        """查询日线数据

        Args:
            code: 股票代码，如 "000001"
            start_date: 起始日期 "YYYY-MM-DD"，可选
            end_date: 结束日期 "YYYY-MM-DD"，可选
        Returns:
            DataFrame with columns: code, trade_date, open_val, high_val, low_val, close_val, volume, amount, adj_factor
        """
        return self.db.query_daily(code, start_date, end_date)

    # ─── 分钟线 ───

    def get_minute_5(self, code: str,
                     trade_date: Optional[str] = None) -> pd.DataFrame:
        """查询5分钟线

        Args:
            code: 股票代码
            trade_date: 交易日期 "YYYY-MM-DD"，可选，不传则返回全部
        """
        return self.db.query_minute_5(code, trade_date)

    def get_minute_1(self, code: str,
                     trade_date: Optional[str] = None) -> pd.DataFrame:
        """查询1分钟线

        Args:
            code: 股票代码
            trade_date: 交易日期 "YYYY-MM-DD"，可选
        """
        return self.db.query_minute_1(code, trade_date)

    # ─── 列表查询 ───

    def get_stock_list(self, table: str = "tdx_daily") -> List[str]:
        """获取指定表中有数据的全部股票代码"""
        with self.db._connect() as conn:
            if self.config.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute(f"SELECT DISTINCT code FROM {table} ORDER BY code")
                    return [row[0] for row in cur.fetchall()]
            else:
                rows = conn.execute(
                    f"SELECT DISTINCT code FROM {table} ORDER BY code"
                ).fetchall()
                return [row[0] for row in rows]

    def get_trade_dates(self, code: str, table: str = "tdx_daily") -> List[str]:
        """获取某只股票的全部交易日期"""
        with self.db._connect() as conn:
            if self.config.db_type == "mysql":
                with conn.cursor() as cur:
                    cur.execute(
                        f"SELECT DISTINCT trade_date FROM {table} WHERE code = %s ORDER BY trade_date",
                        (code,)
                    )
                    return [str(row[0]) for row in cur.fetchall()]
            else:
                rows = conn.execute(
                    f"SELECT DISTINCT trade_date FROM {table} WHERE code = ? ORDER BY trade_date",
                    (code,)
                ).fetchall()
                return [row[0] for row in rows]

    def get_max_date(self, code: str, table: str = "tdx_daily") -> Optional[str]:
        """获取某只股票的最新交易日期"""
        return self.db.get_max_trade_date(code, table)

    def get_record_count(self, table: str, code: Optional[str] = None) -> int:
        """获取记录数"""
        return self.db.get_record_count(table, code)

    # ─── 通用 SQL 查询 ───

    def execute(self, sql: str, params: Optional[tuple] = None) -> pd.DataFrame:
        """执行自定义 SQL 并返回 DataFrame

        注意：仅用于查询(SELECT)，不要用于写操作。
        """
        with self.db._connect() as conn:
            if self.config.db_type == "mysql":
                import pymysql
                with conn.cursor(pymysql.cursors.DictCursor) as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
                return pd.DataFrame(rows)
            else:
                return pd.read_sql_query(sql, conn, params=params)

    # ─── 生命周期 ───

    def refresh_live(self, codes: List[str]) -> int:
        """从 minishare API 拉取实时快照并写入本地数据库.

        Args:
            codes: 6 位纯数字代码列表
        Returns:
            成功写入的行数
        """
        if self._ms_client is None:
            logger.warning("refresh_live: MinishareClient 未初始化，跳过")
            return 0

        import pandas as pd
        all_dfs = []
        classified = {"stock": [], "etf": [], "index": []}
        index_codes = {"000001", "000002", "000003", "000004",
                       "399001", "399005", "399006", "399300", "000688"}
        for code in codes:
            if code in index_codes:
                classified["index"].append(code)
            elif code.startswith(("5", "15", "16")):
                classified["etf"].append(code)
            else:
                classified["stock"].append(code)

        for code_type, type_codes in classified.items():
            if not type_codes:
                continue
            try:
                if code_type == "stock":
                    df = self._ms_client.get_snapshot(type_codes)
                elif code_type == "etf":
                    df = self._ms_client.get_etf_snapshot(type_codes)
                elif code_type == "index":
                    df = self._ms_client.get_index_snapshot(type_codes)
                else:
                    continue
                if df is not None and not df.empty:
                    all_dfs.append(df)
            except MinishareError as exc:
                logger.error("refresh_live [%s] 失败: %s", code_type, exc)

        if not all_dfs:
            return 0

        combined = pd.concat(all_dfs, ignore_index=True)
        rows = self.db.upsert_dataframe(combined, "tdx_daily")
        logger.info("refresh_live: %d 行数据已更新到数据库", rows)
        return rows

    def close(self):
        """TdxQuery 本身不持有长连接，此方法为接口一致性保留"""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
