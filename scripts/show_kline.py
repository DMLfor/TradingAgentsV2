#!/usr/bin/env python3
"""在终端打印 ASCII K 线图（含基准对比）.

Usage:
    python scripts/show_kline.py 688018 --benchmark 399006 --start 2026-01-01
    python scripts/show_kline.py 600519 --benchmark 000300
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxQuery


def fetch_data(code: str, start: str, end: str):
    """Fetch daily OHLC data for a stock/index."""
    with TdxQuery() as q:
        df = q.get_daily(code)
    if df is None or df.empty:
        return None
    df = df.sort_values("trade_date").reset_index(drop=True)
    df["trade_date"] = df["trade_date"].astype(str)
    for col in ["open_val", "high_val", "low_val", "close_val", "volume"]:
        if col in df.columns:
            df[col] = df[col].astype(float)
    mask = (df["trade_date"] >= start) & (df["trade_date"] <= end)
    return df[mask].reset_index(drop=True)


def draw_kline(df_stock, df_bench, stock_name: str, bench_name: str, width: int = 80, height: int = 22):
    """Draw ASCII candlestick chart with benchmark overlay."""
    # Align dates
    merged = df_stock.merge(df_bench[["trade_date", "close_val"]], on="trade_date", how="left", suffixes=("", "_bench"))
    merged = merged.dropna(subset=["close_val_bench"]).reset_index(drop=True)
    if len(merged) == 0:
        print("[错误] 股票与基准日期无交集")
        return

    # Normalize both to 100 at start
    s0 = merged["close_val"].iloc[0]
    b0 = merged["close_val_bench"].iloc[0]
    merged["o_n"] = merged["open_val"] / s0 * 100
    merged["h_n"] = merged["high_val"] / s0 * 100
    merged["l_n"] = merged["low_val"] / s0 * 100
    merged["c_n"] = merged["close_val"] / s0 * 100
    merged["b_n"] = merged["close_val_bench"] / b0 * 100

    # Take last `width` days
    data = merged.tail(width).reset_index(drop=True)
    n = len(data)

    # Y range
    all_vals = list(data["h_n"]) + list(data["l_n"]) + list(data["b_n"])
    vmin = min(all_vals) * 0.998
    vmax = max(all_vals) * 1.002
    if vmax == vmin:
        vmax = vmin + 1

    def _price_to_row(v: float) -> int:
        return int((vmax - v) / (vmax - vmin) * (height - 1))

    # Grid
    grid = [[" " for _ in range(n)] for _ in range(height)]

    # Draw candles
    for i in range(n):
        row = data.iloc[i]
        o, h, l, c = row["o_n"], row["h_n"], row["l_n"], row["c_n"]
        y_h = _price_to_row(h)
        y_l = _price_to_row(l)
        y_o = _price_to_row(o)
        y_c = _price_to_row(c)

        # Shadow
        for y in range(min(y_h, y_l), max(y_h, y_l) + 1):
            if 0 <= y < height:
                grid[y][i] = "|"

        # Body
        for y in range(min(y_o, y_c), max(y_o, y_c) + 1):
            if 0 <= y < height:
                if abs(c - o) < 0.01:
                    grid[y][i] = "*"
                elif c > o:
                    grid[y][i] = "+"
                else:
                    grid[y][i] = "-"

    # Draw benchmark line (overwrite shadows but not body)
    b_vals = data["b_n"].values
    for i in range(n):
        y = _price_to_row(b_vals[i])
        if 0 <= y < height and grid[y][i] in (" ", "|"):
            grid[y][i] = "."

    # Header
    start_d = data["trade_date"].iloc[0]
    end_d = data["trade_date"].iloc[-1]
    s_ret = (data["c_n"].iloc[-1] - 100)
    b_ret = (b_vals[-1] - 100)

    print("")
    print(f"  {stock_name}({data['code'].iloc[0] if 'code' in data.columns else ''})  ASCII K线图  {start_d} ~ {end_d}")
    print(f"  股票涨跌: {s_ret:+.2f}%  基准涨跌: {b_ret:+.2f}%  相对强弱: {s_ret - b_ret:+.2f}%")
    print("")

    # Print grid with Y-axis labels
    y_labels = [f"{vmax - y / (height - 1) * (vmax - vmin):6.1f}" for y in range(height)]
    max_label_len = max(len(l) for l in y_labels)

    for y in range(height):
        label = y_labels[y].rjust(max_label_len)
        print(f"{label} |{''.join(grid[y])}|")

    # X-axis
    print(" " * max_label_len + " +" + "-" * n + "+")
    pad = n - len(start_d) - len(end_d)
    pad = max(0, pad)
    x_label = start_d + " " * pad + end_d
    if len(x_label) > n:
        x_label = x_label[:n]
    print(" " * (max_label_len + 1) + " " + x_label)

    # Legend & stats
    print("")
    print("  图例: + = 阳线  - = 阴线  * = 十字星  | = 影线  . = 基准线")
    print("")

    # Recent 5 days OHLC table
    print("  最近5日数据:")
    recent = data.tail(5)
    print(f"  {'日期':12} {'开盘':>10} {'最高':>10} {'最低':>10} {'收盘':>10} {'涨跌':>8} {'基准':>8}")
    for _, row in recent.iterrows():
        dt = row["trade_date"]
        o, h, l, c = row["open_val"], row["high_val"], row["low_val"], row["close_val"]
        chg = (c - row["open_val"]) / row["open_val"] * 100
        bchg = (row["b_n"] - 100)
        print(f"  {dt:12} {o:10.2f} {h:10.2f} {l:10.2f} {c:10.2f} {chg:>+7.2f}% {bchg:>+7.2f}%")
    print("")


def main():
    parser = argparse.ArgumentParser(description="ASCII K-line chart")
    parser.add_argument("code", help="Stock code (e.g. 688018)")
    parser.add_argument("--benchmark", default="399006", help="Benchmark code (default: 399006 创业板指)")
    parser.add_argument("--start", default="2026-01-01", help="Start date (default: 2026-01-01)")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"), help="End date (default: today)")
    parser.add_argument("--width", type=int, default=80, help="Chart width in characters")
    parser.add_argument("--height", type=int, default=22, help="Chart height in rows")
    parser.add_argument("--name", help="Stock name override")
    args = parser.parse_args()

    from tdx_core.names import get_name
    stock_name = args.name or get_name(args.code) or args.code
    bench_name = get_name(args.benchmark) or args.benchmark

    print(f"加载 {stock_name}({args.code}) 数据...")
    df_stock = fetch_data(args.code, args.start, args.end)
    if df_stock is None or df_stock.empty:
        print(f"[错误] 无法获取股票 {args.code} 的数据")
        sys.exit(1)

    print(f"加载 {bench_name}({args.benchmark}) 数据...")
    df_bench = fetch_data(args.benchmark, args.start, args.end)
    if df_bench is None or df_bench.empty:
        print(f"[错误] 无法获取基准 {args.benchmark} 的数据")
        sys.exit(1)

    print(f"股票: {len(df_stock)} 个交易日, 基准: {len(df_bench)} 个交易日")
    draw_kline(df_stock, df_bench, stock_name, bench_name, width=args.width, height=args.height)


if __name__ == "__main__":
    main()
