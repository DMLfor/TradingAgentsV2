"""示例1：基本查询 — 日线、分钟线、股票列表

用法:
    cd TradingAgentsV2
    python -m examples.01_basic_query
"""
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_data import TdxQuery


def main():
    # 默认自动加载 config/tdx_config.yaml
    with TdxQuery() as q:

        # 1. 查询日线
        print("=== 日线查询: 000001 ===")
        df = q.get_daily("000001", start_date="2024-01-01", end_date="2024-01-10")
        print(df.head())
        print()

        # 2. 查询5分钟线
        print("=== 5分钟线: 000001 ===")
        df5 = q.get_minute_5("000001", trade_date="2024-01-02")
        print(df5.head())
        print()

        # 3. 查询1分钟线
        print("=== 1分钟线: 000001 ===")
        df1 = q.get_minute_1("000001", trade_date="2024-01-02")
        print(df1.head())
        print()

        # 4. 获取股票列表
        print("=== 有日线数据的股票代码（前20）===")
        codes = q.get_stock_list()
        print(f"共 {len(codes)} 只: {codes[:20]}")
        print()

        # 5. 获取最新交易日期
        print("=== 000001 最新交易日期 ===")
        max_date = q.get_max_date("000001")
        print(max_date)


if __name__ == "__main__":
    main()
