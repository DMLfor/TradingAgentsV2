#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多策略共振回测验证 — 对比单策略 vs 组合策略.

在历史数据上逐日跑策略，统计胜率、收益、回撤，验证组合是否更优.

Usage:
    python scripts/backtest_multi_signal.py --code 515180 --start 2021-08-02
    python scripts/backtest_multi_signal.py --code 159545 --start 2024-04-15
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxQuery
from tdx_core.indicators import bollinger, macd, rsi as rsi_ind


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算所有需要的指标."""
    df = df.sort_values("trade_date").reset_index(drop=True)
    for col in ["open_val", "high_val", "low_val", "close_val", "volume", "amount"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = rsi_ind(df, period=14)
    df = bollinger(df, period=20, std_dev=2.0)
    df = macd(df, fast=12, slow=26, signal=9)
    df["ma5"] = df["close_val"].rolling(window=5, min_periods=1).mean()
    df["ma10"] = df["close_val"].rolling(window=10, min_periods=1).mean()
    df["ma20"] = df["close_val"].rolling(window=20, min_periods=1).mean()
    return df


def backtest_single_rsi(df: pd.DataFrame, rsi_buy: float = 30, rsi_sell: float = 70) -> list[dict]:
    """回测单一 RSI30 策略，返回交易列表."""
    trades = []
    position = 0  # 0=空仓, 1=持仓
    buy_price = None
    buy_date = None
    max_hold_days = 40

    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        date = str(curr["trade_date"])

        rsi_curr = float(curr["rsi_14"])
        rsi_prev = float(prev["rsi_14"])
        price = float(curr["close_val"])

        # BUY: RSI 从下向上突破买入阈值
        if position == 0 and rsi_prev < rsi_buy and rsi_curr >= rsi_buy:
            position = 1
            buy_price = price
            buy_date = date
            buy_idx = i

        # SELL 条件
        if position == 1:
            hold_days = i - buy_idx
            # 1. RSI 跌破卖出阈值
            rsi_sell_trigger = rsi_prev > rsi_sell and rsi_curr <= rsi_sell
            # 2. 最大持有期
            max_hold_trigger = hold_days >= max_hold_days

            if rsi_sell_trigger or max_hold_trigger:
                reason = "RSI_sell" if rsi_sell_trigger else "max_hold"
                pnl_pct = (price - buy_price) / buy_price * 100
                trades.append({
                    "buy_date": buy_date, "sell_date": date,
                    "buy_price": buy_price, "sell_price": price,
                    "pnl_pct": pnl_pct, "hold_days": hold_days,
                    "reason": reason,
                })
                position = 0
                buy_price = None

    return trades


def backtest_single_macd(df: pd.DataFrame) -> list[dict]:
    """回测单一 MACD 金叉策略."""
    trades = []
    position = 0
    buy_price = None
    buy_date = None

    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        date = str(curr["trade_date"])
        price = float(curr["close_val"])

        macd_prev = float(prev["macd"])
        macd_sig_prev = float(prev["macd_signal"])
        macd_curr = float(curr["macd"])
        macd_sig_curr = float(curr["macd_signal"])

        golden = macd_prev <= macd_sig_prev and macd_curr > macd_sig_curr
        death = macd_prev >= macd_sig_prev and macd_curr < macd_sig_curr

        if position == 0 and golden:
            position = 1
            buy_price = price
            buy_date = date
            buy_idx = i

        if position == 1 and death:
            pnl_pct = (price - buy_price) / buy_price * 100
            hold_days = i - buy_idx
            trades.append({
                "buy_date": buy_date, "sell_date": date,
                "buy_price": buy_price, "sell_price": price,
                "pnl_pct": pnl_pct, "hold_days": hold_days,
                "reason": "macd_death",
            })
            position = 0
            buy_price = None

    return trades


def backtest_combined(df: pd.DataFrame, code: str) -> list[dict]:
    """回测组合策略（RSI30 + 布林带 + 趋势），2/3 共识才交易."""
    trades = []
    position = 0
    buy_price = None
    buy_date = None

    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        date = str(curr["trade_date"])
        price = float(curr["close_val"])

        # --- 各策略信号计算 ---
        # RSI
        rsi_prev = float(prev["rsi_14"])
        rsi_curr = float(curr["rsi_14"])
        rsi_buy = 30
        rsi_sell = 70
        rsi_buy_signal = rsi_prev < rsi_buy and rsi_curr >= rsi_buy
        rsi_sell_signal = rsi_prev > rsi_sell and rsi_curr <= rsi_sell

        # Bollinger
        close_prev = float(prev["close_val"])
        close_curr = float(curr["close_val"])
        bb_lower_prev = float(prev["bb_lower"])
        bb_lower_curr = float(curr["bb_lower"])
        bb_upper_prev = float(prev["bb_upper"])
        bb_upper_curr = float(curr["bb_upper"])
        bb_buy = close_prev <= bb_lower_prev and close_curr > bb_lower_curr
        bb_sell = close_prev >= bb_upper_prev and close_curr < bb_upper_curr

        # Trend (MA排列)
        ma5_prev = float(prev["ma5"])
        ma10_prev = float(prev["ma10"])
        ma20_prev = float(prev["ma20"])
        ma5_curr = float(curr["ma5"])
        ma10_curr = float(curr["ma10"])
        ma20_curr = float(curr["ma20"])
        bull_prev = close_prev > ma5_prev > ma10_prev > ma20_prev
        bull_curr = close_curr > ma5_curr > ma10_curr > ma20_curr
        bear_prev = close_prev < ma5_prev < ma10_prev < ma20_prev
        bear_curr = close_curr < ma5_curr < ma10_curr < ma20_curr
        trend_buy = bull_curr and not bull_prev
        trend_sell = bear_curr and not bear_prev

        # --- 多数投票共识（2/3 策略支持才交易）---
        buy_votes = sum([rsi_buy_signal, bb_buy, trend_buy])
        sell_votes = sum([rsi_sell_signal, bb_sell, trend_sell])

        # 159545 把 RSI 替换为 MACD
        if code == "159545":
            macd_prev = float(prev["macd"])
            macd_sig_prev = float(prev["macd_signal"])
            macd_curr = float(curr["macd"])
            macd_sig_curr = float(curr["macd_signal"])
            macd_buy = macd_prev <= macd_sig_prev and macd_curr > macd_sig_curr
            macd_sell = macd_prev >= macd_sig_prev and macd_curr < macd_sig_curr
            buy_votes = sum([macd_buy, trend_buy, bb_buy])
            sell_votes = sum([macd_sell, trend_sell, bb_sell])

        # 2/3 多数投票
        if position == 0 and buy_votes >= 2:
            position = 1
            buy_price = price
            buy_date = date
            buy_idx = i

        if position == 1 and sell_votes >= 2:
            pnl_pct = (price - buy_price) / buy_price * 100
            hold_days = i - buy_idx
            trades.append({
                "buy_date": buy_date, "sell_date": date,
                "buy_price": buy_price, "sell_price": price,
                "pnl_pct": pnl_pct, "hold_days": hold_days,
                "reason": f"consensus_{sell_votes}/3",
            })
            position = 0
            buy_price = None

    return trades


def calc_stats(trades: list[dict]) -> dict:
    """计算交易统计."""
    if not trades:
        return {"trades": 0}
    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    total_return = sum(t["pnl_pct"] for t in trades)
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "total_return_pct": round(total_return, 2),
        "avg_pnl": round(total_return / len(trades), 2),
        "avg_win": round(sum(t["pnl_pct"] for t in wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0,
        "avg_hold": round(sum(t["hold_days"] for t in trades) / len(trades), 1),
        "max_pnl": round(max(t["pnl_pct"] for t in trades), 2),
        "min_pnl": round(min(t["pnl_pct"] for t in trades), 2),
    }


def print_report(code: str, single_name: str, single_trades: list, combo_trades: list):
    """打印对比报告."""
    s = calc_stats(single_trades)
    c = calc_stats(combo_trades)

    lines = []
    lines.append("=" * 70)
    lines.append(f"  多策略共振回测验证 — {code}")
    lines.append(f"  回测区间: {single_trades[0]['buy_date'] if single_trades else 'N/A'} ~ {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("=" * 70)
    lines.append("")

    lines.append(f"【单一 {single_name} 策略】")
    if s["trades"] > 0:
        lines.append(f"  交易次数 : {s['trades']} 笔")
        lines.append(f"  胜率     : {s['win_rate']:.1f}% ({s['wins']} 盈 {s['losses']} 亏)")
        lines.append(f"  累计收益 : {s['total_return_pct']:+.2f}%")
        lines.append(f"  单笔平均 : {s['avg_pnl']:+.2f}%")
        lines.append(f"  平均盈利 : +{s['avg_win']:.2f}%")
        lines.append(f"  平均亏损 : {s['avg_loss']:.2f}%")
        lines.append(f"  最大单笔 : {s['max_pnl']:+.2f}% / {s['min_pnl']:+.2f}%")
        lines.append(f"  平均持有 : {s['avg_hold']:.1f} 天")
    else:
        lines.append("  无交易")
    lines.append("")

    lines.append(f"【组合策略（多策略共振）】")
    if c["trades"] > 0:
        lines.append(f"  交易次数 : {c['trades']} 笔")
        lines.append(f"  胜率     : {c['win_rate']:.1f}% ({c['wins']} 盈 {c['losses']} 亏)")
        lines.append(f"  累计收益 : {c['total_return_pct']:+.2f}%")
        lines.append(f"  单笔平均 : {c['avg_pnl']:+.2f}%")
        lines.append(f"  平均盈利 : +{c['avg_win']:.2f}%")
        lines.append(f"  平均亏损 : {c['avg_loss']:.2f}%")
        lines.append(f"  最大单笔 : {c['max_pnl']:+.2f}% / {c['min_pnl']:+.2f}%")
        lines.append(f"  平均持有 : {c['avg_hold']:.1f} 天")
    else:
        lines.append("  无交易")
    lines.append("")

    lines.append("【对比结论】")
    if s["trades"] > 0 and c["trades"] > 0:
        win_delta = c["win_rate"] - s["win_rate"]
        return_delta = c["total_return_pct"] - s["total_return_pct"]
        trade_delta = c["trades"] - s["trades"]

        lines.append(f"  交易次数变化: {trade_delta:+d} 笔 ({s['trades']} → {c['trades']})")
        lines.append(f"  胜率变化    : {win_delta:+.1f}% ({s['win_rate']:.1f}% → {c['win_rate']:.1f}%)")
        lines.append(f"  累计收益变化: {return_delta:+.2f}% ({s['total_return_pct']:+.2f}% → {c['total_return_pct']:+.2f}%)")

        if c["win_rate"] > s["win_rate"] and c["total_return_pct"] >= s["total_return_pct"] * 0.8:
            lines.append("  ✅ 组合策略更优: 胜率提升，收益未大幅下降")
        elif c["win_rate"] > s["win_rate"]:
            lines.append("  ⚠️ 组合策略胜率更高，但收益有所下降（交易次数减少）")
        else:
            lines.append("  ❌ 组合策略未优于单一策略，需调整参数")
    else:
        lines.append("  数据不足，无法对比")

    lines.append("=" * 70)
    text = "\n".join(lines)
    print(text)
    return text


def main():
    parser = argparse.ArgumentParser(description="Multi-signal backtest validation")
    parser.add_argument("--code", required=True, help="Stock/ETF code")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--save", action="store_true", help="Save report")
    args = parser.parse_args()

    with TdxQuery() as q:
        df = q.get_daily(args.code, start_date=args.start)
        if df is None or df.empty or len(df) < 60:
            print(f"[ERROR] 数据不足: {args.code}")
            sys.exit(1)

        df = compute_indicators(df)

        if args.code == "515180":
            single_trades = backtest_single_rsi(df, rsi_buy=30, rsi_sell=70)
            combo_trades = backtest_combined(df, args.code)
            report = print_report(args.code, "RSI30", single_trades, combo_trades)
        elif args.code == "159545":
            single_trades = backtest_single_macd(df)
            combo_trades = backtest_combined(df, args.code)
            report = print_report(args.code, "MACD金叉", single_trades, combo_trades)
        else:
            # 默认 RSI
            single_trades = backtest_single_rsi(df)
            combo_trades = backtest_combined(df, args.code)
            report = print_report(args.code, "RSI30", single_trades, combo_trades)

    if args.save:
        out_dir = Path(ROOT) / "logs"
        out_dir.mkdir(exist_ok=True)
        fname = f"backtest_multi_{args.code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        (out_dir / fname).write_text(report, encoding="utf-8")
        print(f"\n[Saved] {out_dir / fname}")


if __name__ == "__main__":
    main()
