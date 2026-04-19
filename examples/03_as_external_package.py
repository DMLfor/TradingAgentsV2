"""示例3：从其它项目目录当作外部包使用

关键：把 TradingAgentsV2 加入 sys.path 或 PYTHONPATH

方法A — 代码中添加路径（简单直接）:
    import sys
    sys.path.insert(0, r"C:\Users\dblank\code\TradingAgentsV2")
    from tdx_core import TdxQuery

方法B — 设置 PYTHONPATH 环境变量:
    set PYTHONPATH=C:\Users\dblank\\code\\TradingAgentsV2
    然后在任意位置直接 import

方法C — pip install -e（开发模式，推荐长期使用）:
    1. 在 TradingAgentsV2 根目录创建 pyproject.toml（见 README）
    2. pip install -e C:\\Users\\dblank\\code\\TradingAgentsV2
    3. 之后任意位置 from tdx_core import TdxQuery
"""
import sys

# === 这一行是关键 ===
sys.path.insert(0, r"C:\Users\dblank\code\TradingAgentsV2")

from tdx_core import TdxQuery


def main():
    with TdxQuery() as q:
        # 在你的策略/分析代码中直接查询
        df = q.get_daily("000001", start_date="2024-01-01")
        print(f"000001 自 2024-01-01 起共 {len(df)} 条日线")
        print(df.tail())


if __name__ == "__main__":
    main()
