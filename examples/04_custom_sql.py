"""示例4：自定义 SQL 查询

当高层 API 不够用时，可以直接写 SQL
"""
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_data import TdxQuery


def main():
    with TdxQuery() as q:

        # 涨幅前10的交易日
        print("=== 000001 涨幅最大的10天 ===")
        df = q.execute("""
            SELECT trade_date,
                   close_val - open_val AS day_change,
                   ROUND((close_val - open_val) / open_val * 100, 2) AS pct_change
            FROM tdx_daily
            WHERE code = %s
            ORDER BY pct_change DESC
            LIMIT 10
        """, ("000001",))
        print(df)
        print()

        # 成交量突破 — 是20日均量2倍以上的日期
        print("=== 000001 放量日期（量 > 20日均量2倍）===")
        df = q.execute("""
            SELECT d.trade_date, d.volume, avg.v20,
                   ROUND(d.volume / avg.v20, 2) AS ratio
            FROM tdx_daily d
            JOIN (
                SELECT trade_date,
                       AVG(volume) OVER (ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS v20
                FROM tdx_daily WHERE code = %s
            ) avg ON d.trade_date = avg.trade_date
            WHERE d.code = %s AND d.volume > avg.v20 * 2
            ORDER BY d.trade_date DESC
            LIMIT 10
        """, ("000001", "000001"))
        print(df)


if __name__ == "__main__":
    main()
