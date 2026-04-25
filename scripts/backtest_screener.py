#!/usr/bin/env python3
"""Backtest the tech_screener strategy — 验证形态选股 + 买卖点的历史有效性.

Usage:
    python scripts/backtest_screener.py --codes 600519,000001,300750 --weeks 10 --future-days 5
    python scripts/backtest_screener.py --board 创业板 --weeks 20 --future-days 10 --min-score 60 --top 20
    python scripts/backtest_screener.py --watchlist config/watchlist.txt --weeks 12 --future-days 5 --save
"""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Auto-detect project root
_p = Path(__file__).resolve()
ROOT = str(_p.parent.parent)
for i in range(2, min(8, len(_p.parents))):
    _ancestor = _p.parents[i]
    if (_ancestor / "tdx_core").exists() or (_ancestor / "pyproject.toml").exists():
        ROOT = str(_ancestor)
        break
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxIndicators, TdxQuery, get_name, resolve_codes, by_board, filter_stocks
from scripts.tech_screener import _compute_scores, _generate_trade_plan, TradePlan, WEIGHTS

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

LOOKBACK_BARS = 60
MAX_WORKERS = 12

_REQUIRED_INDICATORS = ["ma", "macd", "rsi"]


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class BacktestTrade:
    code: str
    name: str
    signal_date: str
    buy_date: str | None
    sell_date: str | None
    buy_price: float
    sell_price: float
    return_pct: float
    hold_days: int
    result: str  # "profit" | "loss" | "expired" | "no_trigger"
    score: float
    entry_price: float
    stop_price: float
    target_price: float
    risk_reward: float


# ─── Core backtest logic ──────────────────────────────────────────────────────

def simulate_trade(
    df_future: pd.DataFrame,
    entry: float,
    stop: float,
    target: float,
    max_days: int,
) -> dict[str, Any]:
    """Simulate a pullback trade over future bars.

    New logic (pullback strategy):
    - Buy at next-day open (100% trigger)
    - Stop: close < MA60 (trend broken)
    - Target: close >= recent_20_high (recover pullback)
    - Expire: hold max_days

    Returns dict with keys: triggered, buy_date, sell_date, buy_price,
    sell_price, return_pct, hold_days, result
    """
    if df_future is None or df_future.empty or max_days <= 0:
        return {
            "triggered": False,
            "buy_date": None,
            "sell_date": None,
            "buy_price": 0.0,
            "sell_price": 0.0,
            "return_pct": 0.0,
            "hold_days": 0,
            "result": "no_trigger",
        }

    # Only look at first max_days rows
    df = df_future.head(max_days).copy()
    if df.empty:
        return {
            "triggered": False,
            "buy_date": None,
            "sell_date": None,
            "buy_price": 0.0,
            "sell_price": 0.0,
            "return_pct": 0.0,
            "hold_days": 0,
            "result": "no_trigger",
        }

    # Buy at next-day open (day 1 open)
    day1 = df.iloc[0]
    buy_price = float(day1["open_val"])
    buy_date = str(day1["trade_date"])

    # Sanity check: if open is already wildly off, flag data error
    prev_close = float(day1.get("close_val", buy_price))
    if buy_price > 0 and abs(buy_price - prev_close) / prev_close > 0.5:
        return {
            "triggered": False,
            "buy_date": None,
            "sell_date": None,
            "buy_price": 0.0,
            "sell_price": 0.0,
            "return_pct": 0.0,
            "hold_days": 0,
            "result": "data_error",
        }

    # Subsequent days: check stop (close < MA60) / target (close >= recent high)
    for i in range(1, len(df)):
        row = df.iloc[i]
        close = float(row["close_val"])
        ma_60 = row.get("ma_60", np.nan)

        # Sanity: extreme single-day move = data error
        prev = float(df.iloc[i - 1]["close_val"])
        if prev > 0 and abs(close - prev) / prev > 0.5:
            return {
                "triggered": True,
                "buy_date": buy_date,
                "sell_date": str(row["trade_date"]),
                "buy_price": round(buy_price, 2),
                "sell_price": round(close, 2),
                "return_pct": round((close - buy_price) / buy_price * 100, 2),
                "hold_days": i,
                "result": "data_error",
            }

        # Check target first: recover to recent high
        if close >= target:
            return {
                "triggered": True,
                "buy_date": buy_date,
                "sell_date": str(row["trade_date"]),
                "buy_price": round(buy_price, 2),
                "sell_price": round(close, 2),
                "return_pct": round((close - buy_price) / buy_price * 100, 2),
                "hold_days": i,
                "result": "profit",
            }

        # Check stop: close below MA60 (trend broken)
        if pd.notna(ma_60) and close < ma_60:
            return {
                "triggered": True,
                "buy_date": buy_date,
                "sell_date": str(row["trade_date"]),
                "buy_price": round(buy_price, 2),
                "sell_price": round(close, 2),
                "return_pct": round((close - buy_price) / buy_price * 100, 2),
                "hold_days": i,
                "result": "loss",
            }

    # Expired: sell at close of last day
    last = df.iloc[-1]
    sell_price = float(last["close_val"])
    ret = (sell_price - buy_price) / buy_price * 100
    return {
        "triggered": True,
        "buy_date": buy_date,
        "sell_date": str(last["trade_date"]),
        "buy_price": round(buy_price, 2),
        "sell_price": round(sell_price, 2),
        "return_pct": round(ret, 2),
        "hold_days": len(df) - 1,
        "result": "expired",
    }


def _analyze_at_date(
    code: str,
    name: str,
    df_full: pd.DataFrame,
    signal_date: str,
    future_days: int,
    min_score: float,
    min_rr: float,
    stop_pct: float = 3.0,
    target_pct: float = 5.0,
) -> BacktestTrade | None:
    """Analyze a single stock at a specific historical date."""
    try:
        df_full = df_full.sort_values("trade_date").reset_index(drop=True)

        # Find signal date position
        mask = df_full["trade_date"] == signal_date
        if not mask.any():
            return None
        pos = int(mask.to_numpy().nonzero()[0][0])

        # Need at least LOOKBACK_BARS history before signal date
        if pos < LOOKBACK_BARS:
            return None

        # Need at least 1 future day
        if pos >= len(df_full) - 1:
            return None

        # Slice: signal_date - LOOKBACK_BARS to signal_date (inclusive)
        df_hist = df_full.iloc[pos - LOOKBACK_BARS : pos + 1].copy()

        # Compute indicators on historical slice
        df_hist = TdxIndicators.compute(df_hist, indicators=_REQUIRED_INDICATORS)

        # Compute scores and trade plan
        scores = _compute_scores(df_hist)
        if not scores:
            return None

        plan = _generate_trade_plan(df_hist, scores, code, name, stop_pct, target_pct)
        if plan is None:
            return None

        # Filter
        if plan.total_score < min_score or plan.risk_reward < min_rr:
            return None

        # Slice future data (signal_date + 1 onwards)
        df_future = df_full.iloc[pos + 1 :].copy()

        # Simulate trade
        sim = simulate_trade(df_future, plan.entry_price, plan.stop_price, plan.target_price, future_days)

        return BacktestTrade(
            code=code,
            name=name,
            signal_date=signal_date,
            buy_date=sim["buy_date"],
            sell_date=sim["sell_date"],
            buy_price=sim["buy_price"],
            sell_price=sim["sell_price"],
            return_pct=sim["return_pct"],
            hold_days=sim["hold_days"],
            result=sim["result"],
            score=plan.total_score,
            entry_price=plan.entry_price,
            stop_price=plan.stop_price,
            target_price=plan.target_price,
            risk_reward=plan.risk_reward,
        )
    except Exception:
        logger.debug("Backtest failed for %s at %s: %s", code, signal_date, traceback.format_exc())
        return None


# ─── Report formatting ────────────────────────────────────────────────────────

def format_backtest_report(
    trades: list[BacktestTrade],
    params: dict[str, Any],
) -> str:
    """Format backtest results as an ASCII table."""
    lines = []
    lines.append("╔" + "═" * 110 + "╗")
    lines.append(f"║  技术形态选股策略回测报告{' ' * 85}║")
    lines.append("╠" + "═" * 110 + "╣")
    lines.append(f"║  参数: 股票池={params['universe']}  回测周数={params['weeks']}  持有天数={params['future_days']}  min_score={params['min_score']}  min_rr={params['min_rr']}  top={params['top_n']}{' ' * 20}║")
    lines.append("╚" + "═" * 110 + "╝")
    lines.append("")

    if not trades:
        lines.append("[INFO] 没有生成任何交易记录")
        return "\n".join(lines)

    # ── Summary ──
    valid_trades = [t for t in trades if t.result not in ("no_trigger", "data_error")]
    triggered = [t for t in trades if t.result != "no_trigger"]
    no_trigger = [t for t in trades if t.result == "no_trigger"]
    data_errors = [t for t in trades if t.result == "data_error"]

    total = len(trades)
    triggered_count = len(triggered)
    trigger_rate = triggered_count / total * 100 if total else 0

    if valid_trades:
        returns = [t.return_pct for t in valid_trades]
        wins = [t for t in valid_trades if t.return_pct > 0]
        losses = [t for t in valid_trades if t.return_pct <= 0]

        win_rate = len(wins) / len(valid_trades) * 100
        avg_return = sum(returns) / len(returns)
        median_return = sorted(returns)[len(returns) // 2] if returns else 0
        max_gain = max(returns)
        max_loss = min(returns)

        profit_factor = (
            sum(t.return_pct for t in wins) / abs(sum(t.return_pct for t in losses))
            if losses and sum(t.return_pct for t in losses) != 0 else float("inf")
        )

        avg_hold = sum(t.hold_days for t in valid_trades) / len(valid_trades)

        profit_count = sum(1 for t in valid_trades if t.result == "profit")
        loss_count = sum(1 for t in valid_trades if t.result == "loss")
        expired_count = sum(1 for t in valid_trades if t.result == "expired")
    else:
        win_rate = avg_return = median_return = max_gain = max_loss = profit_factor = avg_hold = 0
        profit_count = loss_count = expired_count = 0

    lines.append("▌交易统计")
    lines.append(f"  总信号数:      {total}")
    lines.append(f"  触发买入:      {triggered_count} ({trigger_rate:.1f}%)")
    lines.append(f"  未触发买入:    {len(no_trigger)}")
    if data_errors:
        lines.append(f"  数据异常过滤:  {len(data_errors)}")
    lines.append(f"")
    lines.append("▌绩效指标（排除数据异常）")
    lines.append(f"  胜率:          {win_rate:.1f}%")
    lines.append(f"  平均收益率:    {avg_return:+.2f}%")
    lines.append(f"  中位数收益率:  {median_return:+.2f}%")
    lines.append(f"  最大单笔盈利:  {max_gain:+.2f}%")
    lines.append(f"  最大单笔亏损:  {max_loss:+.2f}%")
    lines.append(f"  盈亏比:        {profit_factor:.2f}")
    lines.append(f"  平均持仓天数:  {avg_hold:.1f}")
    lines.append(f"")
    lines.append("▌结果分布")
    lines.append(f"  止盈 (触及目标价): {profit_count} 笔")
    lines.append(f"  止损 (触及止损价): {loss_count} 笔")
    lines.append(f"  到期 (持有到期):   {expired_count} 笔")
    lines.append(f"")

    # ── Score tier analysis ──
    if trades:
        lines.append("▌评分分层收益分析（全部信号，含未触发）")
        scores = [t.score for t in trades]
        sorted_trades = sorted(trades, key=lambda x: x.score)
        n = len(sorted_trades)
        tiers = [
            ("最低20%", sorted_trades[: max(1, n // 5)]),
            ("20-40%", sorted_trades[max(1, n // 5) : max(1, n * 2 // 5)]),
            ("40-60%", sorted_trades[max(1, n * 2 // 5) : max(1, n * 3 // 5)]),
            ("60-80%", sorted_trades[max(1, n * 3 // 5) : max(1, n * 4 // 5)]),
            ("最高20%", sorted_trades[max(1, n * 4 // 5) :]),
        ]
        for label, tier_trades in tiers:
            if not tier_trades:
                continue
            triggered_tier = [t for t in tier_trades if t.result != "no_trigger"]
            if triggered_tier:
                tier_returns = [t.return_pct for t in triggered_tier]
                tier_avg = sum(tier_returns) / len(tier_returns)
                tier_win = sum(1 for t in triggered_tier if t.return_pct > 0) / len(triggered_tier) * 100
            else:
                tier_avg = 0
                tier_win = 0
            tier_score_avg = sum(t.score for t in tier_trades) / len(tier_trades)
            lines.append(
                f"  {label:<8}  评分均值:{tier_score_avg:>5.1f}  样本:{len(tier_trades):>3}  "
                f"触发:{len(triggered_tier):>3}  平均收益:{tier_avg:>+6.2f}%  胜率:{tier_win:>5.1f}%"
            )
        lines.append("")

    # ── Detail table ──
    if triggered:
        lines.append("▌交易明细（按收益率排序）")
        lines.append("")
        lines.append(
            f"  {'代码':<8} {'名称':<10} {'信号日':<12} {'买入日':<12} {'卖出日':<12} "
            f"{'买入价':>8} {'卖出价':>8} {'收益%':>7} {'天数':>4} {'结果':<8} {'评分':>5}"
        )
        lines.append("  " + "-" * 108)
        for t in sorted(triggered, key=lambda x: x.return_pct, reverse=True):
            lines.append(
                f"  {t.code:<8} {t.name:<10} {t.signal_date:<12} {t.buy_date or '-':<12} {t.sell_date or '-':<12} "
                f"{t.buy_price:>8.2f} {t.sell_price:>8.2f} {t.return_pct:>+7.2f} {t.hold_days:>4} {t.result:<8} {t.score:>5.1f}"
            )

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def _load_codes_from_file(path: str) -> list[str]:
    codes = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            first = line.split(",")[0].strip()
            if first:
                codes.append(first)
    return codes


def _generate_signal_dates(df: pd.DataFrame, weeks: int) -> list[str]:
    """Generate weekly signal dates (Fridays) from the DataFrame's trade dates."""
    dates = pd.to_datetime(df["trade_date"]).sort_values().drop_duplicates()
    # Pick Fridays
    fridays = dates[dates.dt.dayofweek == 4]
    if len(fridays) == 0:
        # Fallback: pick every 5th trading day
        fridays = dates.iloc[::5]
    # Take the last 'weeks' dates, but leave room for future_days
    available = fridays.iloc[:-1]  # ensure at least 1 future day
    if len(available) > weeks:
        available = available.iloc[-weeks:]
    return [d.strftime("%Y-%m-%d") for d in available]


def run_backtest(
    codes: list[str],
    weeks: int,
    future_days: int,
    min_score: float,
    min_rr: float,
    top_n: int,
    stop_pct: float,
    target_pct: float,
) -> tuple[list[BacktestTrade], dict[str, Any]]:
    """Run the backtest across all codes and signal dates."""

    # Fetch all data first
    print("▌数据准备")
    code_data: dict[str, pd.DataFrame] = {}
    code_names: dict[str, str] = {}

    for code in codes:
        try:
            with TdxQuery() as q:
                df = q.get_daily(code)
            if df is not None and not df.empty and len(df) >= LOOKBACK_BARS + future_days + 2:
                df = df.sort_values("trade_date").reset_index(drop=True)
                # Pre-compute indicators on full history (more efficient than per-slice)
                df = TdxIndicators.compute(df, indicators=_REQUIRED_INDICATORS)
                code_data[code] = df
                code_names[code] = get_name(code) or code
        except Exception:
            logger.debug("Failed to fetch %s: %s", code, traceback.format_exc())

    if not code_data:
        print("[ERROR] 没有获取到有效数据")
        return [], {}

    print(f"  成功加载: {len(code_data)}/{len(codes)} 只股票")

    # Generate signal dates from the first stock's dates
    first_df = next(iter(code_data.values()))
    signal_dates = _generate_signal_dates(first_df, weeks)
    print(f"  回测日期数: {len(signal_dates)} 个")
    print()

    # Run backtest for each signal date
    all_trades: list[BacktestTrade] = []

    for signal_date in signal_dates:
        print(f"  回测日期: {signal_date}", end="\r")

        # Analyze all stocks at this date
        plans: list[TradePlan] = []
        for code, df_full in code_data.items():
            # Find signal date position
            mask = df_full["trade_date"] == signal_date
            if not mask.any():
                continue
            pos = int(mask.to_numpy().nonzero()[0][0])
            if pos < LOOKBACK_BARS or pos >= len(df_full) - 1:
                continue

            # Slice historical data
            df_hist = df_full.iloc[pos - LOOKBACK_BARS : pos + 1].copy()
            scores = _compute_scores(df_hist)
            if not scores:
                continue

            plan = _generate_trade_plan(df_hist, scores, code, code_names[code], stop_pct, target_pct)
            if plan and plan.total_score >= min_score and plan.risk_reward >= min_rr:
                plans.append(plan)

        # Sort by score and take top_n
        plans.sort(key=lambda x: x.total_score, reverse=True)
        selected = plans[:top_n]

        # Simulate trades for selected stocks
        for plan in selected:
            df_full = code_data[plan.code]
            mask = df_full["trade_date"] == signal_date
            pos = int(mask.to_numpy().nonzero()[0][0])
            df_future = df_full.iloc[pos + 1 :].copy()

            sim = simulate_trade(df_future, plan.entry_price, plan.stop_price, plan.target_price, future_days)

            all_trades.append(BacktestTrade(
                code=plan.code,
                name=plan.name,
                signal_date=signal_date,
                buy_date=sim["buy_date"],
                sell_date=sim["sell_date"],
                buy_price=sim["buy_price"],
                sell_price=sim["sell_price"],
                return_pct=sim["return_pct"],
                hold_days=sim["hold_days"],
                result=sim["result"],
                score=plan.total_score,
                entry_price=plan.entry_price,
                stop_price=plan.stop_price,
                target_price=plan.target_price,
                risk_reward=plan.risk_reward,
            ))

    print()
    print(f"  总信号数: {len(all_trades)}")
    print()

    params = {
        "universe": len(code_data),
        "weeks": weeks,
        "future_days": future_days,
        "min_score": min_score,
        "min_rr": min_rr,
        "top_n": top_n,
    }
    return all_trades, params


def main():
    parser = argparse.ArgumentParser(description="技术形态选股策略回测")
    parser.add_argument("--codes", "-c", help="逗号分隔的股票代码")
    parser.add_argument("--watchlist", "-w", help="关注列表文件路径")
    parser.add_argument("--board", "-b", help="板块名称，如 创业板")
    parser.add_argument("--level1", help="一级行业，如 电子")
    parser.add_argument("--weeks", type=int, default=10, help="回测周数 (default: 10)")
    parser.add_argument("--future-days", "-d", type=int, default=5, help="持有天数 (default: 5)")
    parser.add_argument("--min-score", type=float, default=60, help="最低形态分 (default: 60)")
    parser.add_argument("--min-rr", type=float, default=1.0, help="最低风报比 (default: 1.0)")
    parser.add_argument("--top", "-n", type=int, default=20, help="每周选股数量 (default: 20)")
    parser.add_argument("--save", action="store_true", help="保存报告")
    parser.add_argument("--stop-pct", type=float, default=3.0, help="止损百分比 (default: 3)")
    parser.add_argument("--target-pct", type=float, default=5.0, help="目标百分比 (default: 5)")
    args = parser.parse_args()

    # Resolve codes
    codes: list[str] = []
    if args.codes:
        codes = resolve_codes(args.codes)
    elif args.watchlist:
        codes = _load_codes_from_file(args.watchlist)
    elif args.board:
        codes = by_board(args.board)
        if not codes:
            print(f"[ERROR] 未找到板块 '{args.board}' 的股票")
            sys.exit(1)
    elif args.level1:
        codes = filter_stocks(level1=args.level1)
        if not codes:
            print(f"[ERROR] 未找到行业 '{args.level1}' 的股票")
            sys.exit(1)
    else:
        print("[ERROR] 请至少指定一个输入源: --codes, --watchlist, --board, --level1")
        parser.print_help()
        sys.exit(1)

    codes = list(dict.fromkeys(c for c in codes if c and len(c) == 6 and c.isdigit()))
    if not codes:
        print("[ERROR] 没有可分析的股票")
        sys.exit(1)

    print(f"▌策略回测")
    print(f"  股票池: {len(codes)} 只")
    print(f"  参数: {args.weeks}周 × 持有{args.future_days}天  min_score={args.min_score}  min_rr={args.min_rr}  top={args.top}")
    print()

    trades, params = run_backtest(
        codes=codes,
        weeks=args.weeks,
        future_days=args.future_days,
        min_score=args.min_score,
        min_rr=args.min_rr,
        top_n=args.top,
        stop_pct=args.stop_pct,
        target_pct=args.target_pct,
    )

    report = format_backtest_report(trades, params)
    print(report)

    if args.save:
        out_dir = Path(ROOT) / "reports" / "backtests"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"screener_bt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        out_path.write_text(report, encoding="utf-8")
        print(f"\n[Saved] {out_path}")


if __name__ == "__main__":
    main()
