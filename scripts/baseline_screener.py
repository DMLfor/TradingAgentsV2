#!/usr/bin/env python
"""
基线回测：对比 tech_screener 策略 vs 随机买入 / 等权指数
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from tdx_core import TdxQuery, by_board
from datetime import datetime


def get_fridays(start="2025-11-21", end="2026-04-17"):
    """从 tdx_daily 表中获取回测期间的周五列表"""
    q = TdxQuery()
    # 用任意一只创业板股票获取交易日期
    codes = by_board("创业板")
    if not codes:
        return []
    
    df = q.get_daily(codes[0], start_date=start, end_date=end)
    if df.empty:
        return []
    
    fridays = []
    for d in df["trade_date"]:
        if isinstance(d, str):
            dt = datetime.strptime(d, "%Y-%m-%d").date()
        else:
            dt = d.date() if hasattr(d, "date") else d
        if dt.weekday() == 4:
            fridays.append(str(dt))
    return fridays


def baseline_all_stocks(fridays, hold_days=5):
    """
    基线1：每个周五，所有创业板股票次日开盘买入，持有hold_days天
    返回全部样本的收益率列表
    """
    q = TdxQuery()
    codes = by_board("创业板")
    all_returns = []
    
    for signal_date in fridays:
        for code in codes:
            df = q.get_daily(code, start_date=signal_date)
            if df.empty or len(df) < 2:
                continue
            
            # 次日开盘买入（和策略一致）
            buy_price = df.iloc[1]["open_val"]
            if buy_price is None or buy_price == 0:
                continue
            
            # 持有 hold_days 个交易日
            sell_idx = min(hold_days, len(df) - 1)
            if sell_idx <= 0:
                continue
            sell_price = df.iloc[sell_idx]["close_val"]
            if sell_price is None:
                continue
            
            ret = (sell_price - buy_price) / buy_price * 100
            all_returns.append(ret)
    
    return all_returns


def baseline_equal_weight_index(fridays, hold_days=5):
    """
    基线2：创业板等权指数（每周五买入全部创业板股票，等权平均收益）
    """
    q = TdxQuery()
    codes = by_board("创业板")
    all_returns = []
    
    for signal_date in fridays:
        daily_returns = []
        for code in codes:
            df = q.get_daily(code, start_date=signal_date)
            if df.empty or len(df) < 2:
                continue
            
            buy_price = df.iloc[1]["open_val"]
            if buy_price is None or buy_price == 0:
                continue
            
            sell_idx = min(hold_days, len(df) - 1)
            if sell_idx <= 0:
                continue
            sell_price = df.iloc[sell_idx]["close_val"]
            if sell_price is None:
                continue
            
            ret = (sell_price - buy_price) / buy_price * 100
            daily_returns.append(ret)
        
        if daily_returns:
            all_returns.append(sum(daily_returns) / len(daily_returns))
    
    return all_returns


def print_stats(label, returns):
    if not returns:
        print(f"  {label}: no data")
        return
    
    n = len(returns)
    avg = sum(returns) / n
    sorted_r = sorted(returns)
    median = sorted_r[n // 2]
    win_rate = sum(1 for r in returns if r > 0) / n * 100
    
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    win_avg = sum(wins) / len(wins) if wins else 0
    loss_avg = sum(losses) / len(losses) if losses else 0
    profit_factor = abs(win_avg / loss_avg) if loss_avg != 0 else float("inf")
    
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  样本数:     {n}")
    print(f"  平均收益:   {avg:+.2f}%")
    print(f"  中位数收益: {median:+.2f}%")
    print(f"  胜率:       {win_rate:.1f}%")
    print(f"  盈亏比:     {profit_factor:.2f}")
    print(f"  平均盈利:   {win_avg:+.2f}%")
    print(f"  平均亏损:   {loss_avg:+.2f}%")
    print(f"  最大盈利:   {max(returns):+.2f}%")
    print(f"  最大亏损:   {min(returns):+.2f}%")


def main():
    fridays = get_fridays()
    print(f"回测周五数: {len(fridays)}")
    for f in fridays:
        print(f"  {f}")
    
    # 基线1：全部创业板股票
    returns_all = baseline_all_stocks(fridays, hold_days=5)
    print_stats("基线1：全部创业板股票（次日开盘买，持有5天）", returns_all)
    
    # 基线2：等权指数
    returns_index = baseline_equal_weight_index(fridays, hold_days=5)
    print_stats("基线2：创业板等权指数（次日开盘买，持有5天）", returns_index)
    
    # 策略数据（从之前回测报告中提取）
    print("\n" + "="*60)
    print("  策略：tech_screener 回调低吸（top20，持有5天）")
    print("="*60)
    print("  样本数:     400")
    print("  平均收益:   +0.35%")
    print("  中位数收益: -0.93%")
    print("  胜率:       43.5%")
    print("  盈亏比:     1.17")
    print("  最大盈利:   +30.29%")
    print("  最大亏损:   -13.33%")


if __name__ == "__main__":
    main()
