#!/usr/bin/env python3
"""Tech Screener — 多因子形态选股 + 交易计划生成器.

基于5个核心维度对股票进行形态评分（满分100），并对入选股票生成
具体的买入价、止损价、目标价、风险收益比和仓位建议。

Usage:
    python scripts/tech_screener.py --codes 000001,600519,688018
    python scripts/tech_screener.py --watchlist config/watchlist.txt
    python scripts/tech_screener.py --board 创业板 --min-score 60 --top 20
    python scripts/tech_screener.py --level1 电子 --min-score 55
    python scripts/tech_screener.py --from-stdin < my_codes.txt
"""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
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

from tdx_core import TdxIndicators, TdxQuery, get_name, resolve_codes, by_board, filter_stocks, get_meta

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

BARS_DEFAULT = 120
MAX_WORKERS = 12
MIN_SCORE_DEFAULT = 60
MIN_RR_DEFAULT = 1.0
TOP_N_DEFAULT = 20

# 5-factor weights (must sum to 100)
WEIGHTS = {
    "trend": 25,
    "pullback": 25,
    "oversold": 20,
    "volume": 15,
    "momentum": 15,
}


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class TradePlan:
    code: str
    name: str
    trend_score: float
    pullback_score: float
    oversold_score: float
    volume_score: float
    momentum_score: float
    total_score: float
    entry_price: float
    stop_price: float
    target_price: float
    risk_reward: float
    position_suggestion: str
    close_price: float
    regime: str


# ─── Scoring Engine ───────────────────────────────────────────────────────────

_REQUIRED_INDICATORS = ["ma", "macd", "rsi"]


def _compute_scores(df: pd.DataFrame) -> dict[str, float]:
    """Compute 5-factor pullback-screener scores (0-100 each before weighting).

    Core logic: reward stocks in an uptrend that have pulled back from recent highs,
    showing oversold RSI and shrinking volume.
    """
    if df is None or df.empty or len(df) < 30:
        return {}

    latest = df.iloc[-1]

    # Ensure we have the required columns
    required_cols = ["ma_5", "ma_20", "ma_60",
                     "macd",
                     "rsi_14",
                     "volume"]
    for col in required_cols:
        if col not in df.columns:
            return {}

    scores: dict[str, float] = {}
    close = latest["close_val"]
    ma_60 = latest["ma_60"]
    ma_5 = latest["ma_5"]

    # ── 1. Trend Score (0-25) ──
    # Must be in a medium-term uptrend: close > MA60 and MA60 is rising
    trend = 0.0
    if pd.notna(ma_60) and close > ma_60:
        trend += 15.0  # above MA60 is the primary filter

    # MA60 slope: compare MA60 today vs 5 days ago
    ma_60_5ago = df["ma_60"].iloc[-6] if len(df) >= 6 else df["ma_60"].iloc[0]
    if pd.notna(ma_60) and pd.notna(ma_60_5ago) and ma_60 > ma_60_5ago:
        trend += 10.0  # MA60 rising = uptrend intact

    scores["trend"] = max(0.0, min(25.0, trend))

    # ── 2. Pullback Score (0-25) ──
    # Reward stocks that have pulled back 5-15% from recent 20-day high
    recent_20_high = df["high_val"].tail(20).max()
    pullback = 0.0
    if recent_20_high > 0:
        pullback_pct = (recent_20_high - close) / recent_20_high * 100
        if 5 <= pullback_pct <= 15:
            pullback = 25.0  # ideal pullback zone
        elif 3 <= pullback_pct < 5:
            pullback = 18.0
        elif 15 < pullback_pct <= 25:
            pullback = 12.0
        elif pullback_pct > 25:
            pullback = 5.0   # too deep, possible downtrend
        elif 0 <= pullback_pct < 3:
            pullback = 8.0   # barely pulled back
        else:
            pullback = 0.0

    # Extra: price below MA5 confirms short-term pullback
    if pd.notna(ma_5) and close < ma_5:
        pullback += 3.0

    scores["pullback"] = max(0.0, min(25.0, pullback))

    # ── 3. Oversold Score (0-20) ──
    # RSI(14) in 30-50 = oversold but not extreme (avoid dying stocks)
    rsi = latest["rsi_14"]
    oversold = 0.0
    if pd.notna(rsi):
        if 30 <= rsi <= 50:
            oversold = 20.0
        elif 50 < rsi <= 55:
            oversold = 12.0
        elif 25 <= rsi < 30:
            oversold = 10.0
        elif rsi < 25:
            oversold = 3.0   # too weak, possibly broken
        elif 55 < rsi <= 65:
            oversold = 5.0
        else:
            oversold = 0.0

    scores["oversold"] = max(0.0, min(20.0, oversold))

    # ── 4. Volume Score (0-15) ──
    # Shrinking volume during pullback = less selling pressure
    vol = latest["volume"]
    vol_ma20 = df["volume"].tail(20).mean()
    volume_score = 0.0
    if vol_ma20 > 0 and pd.notna(vol):
        vol_ratio = vol / vol_ma20
        if vol_ratio < 0.7:
            volume_score = 15.0  # significantly shrunk
        elif vol_ratio < 0.9:
            volume_score = 12.0
        elif vol_ratio < 1.0:
            volume_score = 8.0
        elif vol_ratio < 1.2:
            volume_score = 4.0
        else:
            volume_score = 0.0   # still high volume, panic selling?

    scores["volume"] = max(0.0, min(15.0, volume_score))

    # ── 5. Momentum Score (0-15) ──
    # MACD still above zero = trend momentum not completely lost
    macd_val = latest["macd"]
    momentum = 0.0
    if pd.notna(macd_val):
        if macd_val > 0:
            momentum = 15.0
        elif macd_val > -0.5:
            momentum = 8.0
        else:
            momentum = 3.0

    scores["momentum"] = max(0.0, min(15.0, momentum))

    return scores


def _generate_trade_plan(
    df: pd.DataFrame,
    scores: dict[str, float],
    code: str,
    name: str,
    stop_pct: float = 3.0,
    target_pct: float = 5.0,
) -> TradePlan | None:
    """Generate entry/stop/target prices and position suggestion.

    Pullback strategy:
    - Entry: next-day open (or today's close for planning)
    - Stop: MA60 (lose the medium-term trend = exit)
    - Target: recent 20-day high (recover the pullback)
    """
    if not scores or df is None or df.empty:
        return None

    latest = df.iloc[-1]
    close = latest["close_val"]
    ma_60 = latest.get("ma_60", np.nan)

    recent_20_high = df["high_val"].tail(20).max()

    # Entry: next-day open (use today's close as proxy for planning)
    entry = close

    # Stop: MA60 or recent low -3%, whichever is higher
    recent_20_low = df["low_val"].tail(20).min()
    stop_from_low = recent_20_low * (1.0 - stop_pct / 100.0)
    if pd.notna(ma_60):
        stop = max(ma_60, stop_from_low)
    else:
        stop = stop_from_low

    # Target: recent 20-day high (recover the pullback)
    target = recent_20_high

    # Risk-reward ratio
    if entry > stop and target > entry:
        risk_reward = (target - entry) / (entry - stop)
    else:
        risk_reward = 0.0

    # Total score
    total = sum(scores.get(k, 0) for k in WEIGHTS)

    # Position suggestion
    if total >= 80 and risk_reward >= 2.0:
        pos = "重仓 60-80%"
    elif total >= 65 and risk_reward >= 1.5:
        pos = "中等 30-50%"
    elif total >= 55 and risk_reward >= 1.2:
        pos = "轻仓 10-20%"
    else:
        pos = "观望"

    # Regime label
    if total >= 80:
        regime = "🔥强烈偏多"
    elif total >= 70:
        regime = "📈谨慎偏多"
    elif total >= 60:
        regime = "➡️中性偏强"
    elif total >= 50:
        regime = "➖中性"
    elif total >= 40:
        regime = "⚠️中性偏弱"
    else:
        regime = "📉谨慎偏空"

    return TradePlan(
        code=code,
        name=name or code,
        trend_score=round(scores.get("trend", 0), 1),
        pullback_score=round(scores.get("pullback", 0), 1),
        oversold_score=round(scores.get("oversold", 0), 1),
        volume_score=round(scores.get("volume", 0), 1),
        momentum_score=round(scores.get("momentum", 0), 1),
        total_score=round(total, 1),
        entry_price=round(entry, 2),
        stop_price=round(stop, 2),
        target_price=round(target, 2),
        risk_reward=round(risk_reward, 2),
        position_suggestion=pos,
        close_price=round(close, 2),
        regime=regime,
    )


def _analyze_one(
    code: str,
    bars: int,
    stop_pct: float = 3.0,
    target_pct: float = 5.0,
) -> TradePlan | None:
    """Analyze a single stock: fetch data, compute indicators, score, generate plan."""
    try:
        with TdxQuery() as q:
            df = q.get_daily(code)
        if df is None or df.empty or len(df) < bars * 0.6:
            return None

        df = df.sort_values("trade_date").reset_index(drop=True)
        if len(df) > bars + 30:
            df = df.iloc[-(bars + 30):].copy()

        # Compute core indicators
        df = TdxIndicators.compute(df, indicators=_REQUIRED_INDICATORS)

        scores = _compute_scores(df)
        if not scores:
            return None

        name = get_name(code) or code
        plan = _generate_trade_plan(df, scores, code, name, stop_pct, target_pct)
        return plan
    except Exception:
        logger.debug("Failed to analyze %s: %s", code, traceback.format_exc())
        return None


# ─── Output formatting ────────────────────────────────────────────────────────

def _bar(percent: float, width: int = 10) -> str:
    filled = int(round(percent / 10 * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def format_report(plans: list[TradePlan], min_score: float, min_rr: float) -> str:
    """Format the screener results as an ASCII table."""
    lines = []
    lines.append("╔" + "═" * 118 + "╗")
    lines.append(f"║  技术形态选股 + 交易计划  (min_score={min_score}, min_rr={min_rr}){' ' * 56}║")
    lines.append("╠" + "═" * 118 + "╣")
    header = (
        f"  {'排名':<4} {'代码':<8} {'名称':<10} {'趋势':>5} {'回调':>5} {'超卖':>5} "
        f"{'量能':>5} {'动量':>5} {'总分':>5} {'研判':<8}"
    )
    lines.append(f"║{header:<118}║")
    lines.append(f"║  {'─'*114}  ║")

    for i, p in enumerate(plans, 1):
        row1 = (
            f"  {i:<4} {p.code:<8} {p.name:<10}"
            f" {p.trend_score:>5.1f} {p.pullback_score:>5.1f} {p.oversold_score:>5.1f}"
            f" {p.volume_score:>5.1f} {p.momentum_score:>5.1f}"
            f" {p.total_score:>5.1f} {p.regime:<8}"
        )
        lines.append(f"║{row1:<118}║")

        # Trade plan line
        entry_pct = (p.entry_price - p.close_price) / p.close_price * 100 if p.close_price else 0
        stop_pct = (p.stop_price - p.close_price) / p.close_price * 100 if p.close_price else 0
        target_pct = (p.target_price - p.close_price) / p.close_price * 100 if p.close_price else 0

        row2 = (
            f"       现价:{p.close_price:>8.2f}  买入:{p.entry_price:>8.2f}({entry_pct:+.1f}%)  "
            f"止损:{p.stop_price:>8.2f}({stop_pct:+.1f}%)  目标:{p.target_price:>8.2f}({target_pct:+.1f}%)  "
            f"RR:{p.risk_reward:>4.1f}  {p.position_suggestion}"
        )
        lines.append(f"║{row2:<118}║")
        lines.append(f"║{' '*118}║")

    lines.append("╚" + "═" * 118 + "╝")
    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def _load_codes_from_file(path: str) -> list[str]:
    codes = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Handle CSV-like lines: code,name,... or just code
            first = line.split(",")[0].strip()
            if first:
                codes.append(first)
    return codes


def _load_codes_from_stdin() -> list[str]:
    codes = []
    for line in sys.stdin:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        first = line.split(",")[0].strip()
        if first:
            codes.append(first)
    return codes


def run_screener(
    codes: list[str],
    bars: int,
    min_score: float,
    min_rr: float,
    top_n: int,
    stop_pct: float = 3.0,
    target_pct: float = 5.0,
) -> list[TradePlan]:
    """Run the screener on a list of codes."""
    total = len(codes)
    processed = 0
    success = 0
    plans: list[TradePlan] = []

    print(f"▌技术形态选股 ({bars}日数据)")
    print(f"  总股票数: {total}  |  并发线程: {MAX_WORKERS}")
    print(f"  过滤条件: 总分 ≥ {min_score}, 风报比 ≥ {min_rr}")
    print(f"  开始: {datetime.now().strftime('%H:%M:%S')}")
    print()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(_analyze_one, code, bars, stop_pct, target_pct): code
            for code in codes
        }
        for future in as_completed(future_map):
            processed += 1
            plan = future.result()
            if plan and plan.total_score >= min_score and plan.risk_reward >= min_rr:
                plans.append(plan)
                success += 1

            if processed % 50 == 0 or processed == total:
                print(
                    f"  进度: {processed}/{total}  入选: {success}  ({success / max(processed, 1) * 100:.1f}%)",
                    end="\r",
                )

    print()
    print(f"  完成: {datetime.now().strftime('%H:%M:%S')} | 入选: {success}/{total}")
    print()

    # Sort by total score descending
    plans.sort(key=lambda x: x.total_score, reverse=True)
    return plans[:top_n]


def print_distribution(plans: list[TradePlan]) -> None:
    """Print score distribution histogram."""
    if not plans:
        return
    scores = [p.total_score for p in plans]
    print("▌评分分布")
    bins = [(0, 40), (40, 50), (50, 60), (60, 70), (70, 80), (80, 100)]
    for lo, hi in bins:
        count = sum(1 for s in scores if lo <= s < hi)
        pct = count / len(scores) * 100
        bar = "█" * int(pct / 2)
        print(f"  {lo:>3}~{hi:<3}: {bar:<50} {count:>4}只 ({pct:>5.1f}%)")
    print(f"  平均分: {sum(scores)/len(scores):.1f}  最高分: {max(scores):.1f}  最低分: {min(scores):.1f}")
    print()


def main():
    parser = argparse.ArgumentParser(description="技术形态选股 + 交易计划生成器")
    parser.add_argument("--codes", "-c", help="逗号分隔的股票代码")
    parser.add_argument("--watchlist", "-w", help="关注列表文件路径")
    parser.add_argument("--board", "-b", help="按板块筛选，如 创业板/科创板/主板")
    parser.add_argument("--level1", help="按一级行业筛选，如 电子")
    parser.add_argument("--from-stdin", action="store_true", help="从标准输入读取代码列表")
    parser.add_argument("--bars", type=int, default=BARS_DEFAULT, help=f"分析窗口天数 (default: {BARS_DEFAULT})")
    parser.add_argument("--min-score", type=float, default=MIN_SCORE_DEFAULT, help=f"最低形态分 (default: {MIN_SCORE_DEFAULT})")
    parser.add_argument("--min-rr", type=float, default=MIN_RR_DEFAULT, help=f"最低风报比 (default: {MIN_RR_DEFAULT})")
    parser.add_argument("--top", type=int, default=TOP_N_DEFAULT, help=f"输出Top N (default: {TOP_N_DEFAULT})")
    parser.add_argument("--save", action="store_true", help="保存结果到 reports/picks/")
    parser.add_argument("--stop-pct", type=float, default=3.0, help="止损距离近期低点的百分比 (default: 3)")
    parser.add_argument("--target-pct", type=float, default=5.0, help="目标距离近期高点的百分比 (default: 5)")
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
    elif args.from_stdin:
        codes = _load_codes_from_stdin()
    else:
        print("[ERROR] 请至少指定一个输入源: --codes, --watchlist, --board, --level1, --from-stdin")
        parser.print_help()
        sys.exit(1)

    if not codes:
        print("[ERROR] 没有可分析的股票")
        sys.exit(1)

    # Deduplicate and filter invalid codes
    codes = list(dict.fromkeys(c for c in codes if c and len(c) == 6 and c.isdigit()))
    print(f"  去重后股票数: {len(codes)}")
    print()

    # Run screener
    plans = run_screener(
        codes=codes,
        bars=args.bars,
        min_score=args.min_score,
        min_rr=args.min_rr,
        top_n=args.top,
        stop_pct=args.stop_pct,
        target_pct=args.target_pct,
    )

    if not plans:
        print("[INFO] 没有股票满足筛选条件")
        sys.exit(0)

    # Print distribution
    print_distribution(plans)

    # Print report
    report = format_report(plans, args.min_score, args.min_rr)
    print(report)

    # Save
    if args.save:
        out_dir = Path(ROOT) / "reports" / "picks"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"tech_screener_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        out_path.write_text(report, encoding="utf-8")
        print(f"\n[Saved] {out_path}")


if __name__ == "__main__":
    main()
