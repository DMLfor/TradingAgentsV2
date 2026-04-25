#!/usr/bin/env python3
"""
Ablation Study — 批量回测各种策略改进方向（预计算优化版）

优化点：
1. 数据预加载：12线程并行加载 1400 只股票
2. 预计算：所有股票所有 signal dates 的 pos / sector_strength / volume_ratio 只算一次
3. 实验级并行：8个实验同时跑
"""
from __future__ import annotations

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

_p = Path(__file__).resolve()
ROOT = str(_p.parent.parent)
for i in range(2, min(8, len(_p.parents))):
    _ancestor = _p.parents[i]
    if (_ancestor / "tdx_core").exists() or (_ancestor / "pyproject.toml").exists():
        ROOT = str(_ancestor)
        break
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxIndicators, TdxQuery, get_name, by_board
from scripts.backtest_screener import (
    simulate_trade, BacktestTrade, _generate_signal_dates,
    LOOKBACK_BARS, _REQUIRED_INDICATORS,
)
from scripts.tech_screener import _compute_scores, _generate_trade_plan, TradePlan


@dataclass
class Experiment:
    name: str
    filters: dict[str, Any]
    future_days: int = 5


# ─── Filter helpers ───────────────────────────────────────────────────────────

def _is_st(name: str) -> bool:
    return "ST" in name or "*ST" in name


def _is_suspended(df_full: pd.DataFrame, pos: int) -> bool:
    for i in range(pos, min(pos + 3, len(df_full))):
        if df_full.iloc[i].get("is_suspended", 0) == 1:
            return True
    return False


def _sector_strength(df_full: pd.DataFrame, pos: int, lookback: int = 5) -> float:
    if pos < lookback:
        return 0.0
    hist = df_full.iloc[pos - lookback : pos + 1]
    if len(hist) < 2:
        return 0.0
    start_price = hist.iloc[0]["close_val"]
    end_price = hist.iloc[-1]["close_val"]
    if start_price > 0:
        return (end_price - start_price) / start_price * 100
    return 0.0


def _volume_confirm(df_full: pd.DataFrame, pos: int, lookback: int = 5) -> tuple[float, float]:
    if pos < lookback:
        return 1.0, 1.0
    signal_vol = df_full.iloc[pos]["volume"]
    signal_amt = df_full.iloc[pos]["amount"]
    hist = df_full.iloc[pos - lookback : pos]
    avg_vol = hist["volume"].mean()
    avg_amt = hist["amount"].mean()
    vol_ratio = signal_vol / avg_vol if avg_vol > 0 else 1.0
    amt_ratio = signal_amt / avg_amt if avg_amt > 0 else 1.0
    return vol_ratio, amt_ratio


def _price_filter(df_full: pd.DataFrame, pos: int, min_price: float = 2.0) -> bool:
    return df_full.iloc[pos]["close_val"] >= min_price


# ─── Parallel data loading ────────────────────────────────────────────────────

def _load_one_stock(code: str, future_days: int):
    try:
        with TdxQuery() as q:
            df = q.get_daily(code)
        if df is not None and not df.empty and len(df) >= LOOKBACK_BARS + future_days + 2:
            df = df.sort_values("trade_date").reset_index(drop=True)
            df = TdxIndicators.compute(df, indicators=_REQUIRED_INDICATORS)
            return code, df, get_name(code) or code
    except Exception:
        pass
    return None


def preload_data_parallel(codes: list[str], future_days: int, max_workers: int = 12):
    code_data = {}
    code_names = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = executor.map(lambda c: _load_one_stock(c, future_days), codes)
        for r in results:
            if r:
                code, df, name = r
                code_data[code] = df
                code_names[code] = name
    return code_data, code_names


# ─── Pre-compute all reusable metrics ─────────────────────────────────────────

def build_precomputed_cache(
    code_data: dict[str, pd.DataFrame],
    signal_dates: list[str],
) -> dict[str, dict[str, Any]]:
    """
    Pre-compute for every (code, signal_date) pair:
      - pos: index in df_full
      - valid: whether pos >= LOOKBACK_BARS and pos < len(df) - 1
      - rs_5: sector strength (5-day lookback)
      - rs_10: sector strength (10-day lookback)
      - vol_ratio_5, amt_ratio_5: volume confirmation (5-day lookback)
      - suspended: whether suspended at/near signal date
      - price_ok: whether close >= 2.0
    """
    cache: dict[str, dict[str, Any]] = {}
    total = len(code_data) * len(signal_dates)
    processed = 0

    for code, df_full in code_data.items():
        cache[code] = {}
        for signal_date in signal_dates:
            processed += 1
            mask = df_full["trade_date"] == signal_date
            if not mask.any():
                cache[code][signal_date] = None
                continue

            pos = int(mask.to_numpy().nonzero()[0][0])
            valid = pos >= LOOKBACK_BARS and pos < len(df_full) - 1

            if not valid:
                cache[code][signal_date] = {
                    "pos": pos, "valid": False,
                    "rs_5": 0.0, "rs_10": 0.0,
                    "vol_ratio_5": 1.0, "amt_ratio_5": 1.0,
                    "suspended": False, "price_ok": True,
                }
                continue

            # Pre-compute all metrics
            rs_5 = _sector_strength(df_full, pos, lookback=5)
            rs_10 = _sector_strength(df_full, pos, lookback=10)
            vol_ratio_5, amt_ratio_5 = _volume_confirm(df_full, pos, lookback=5)
            suspended = _is_suspended(df_full, pos)
            price_ok = _price_filter(df_full, pos, min_price=2.0)

            cache[code][signal_date] = {
                "pos": pos, "valid": True,
                "rs_5": rs_5, "rs_10": rs_10,
                "vol_ratio_5": vol_ratio_5, "amt_ratio_5": amt_ratio_5,
                "suspended": suspended, "price_ok": price_ok,
            }

        if processed % 5000 == 0 or processed == total:
            print(f"  Pre-computing: {processed}/{total}", end="\r")

    print(f"  Pre-computing: {total}/{total} done")
    return cache


# ─── Single experiment runner (with precomputed cache) ────────────────────────

def run_single_experiment_cached(
    code_data: dict[str, pd.DataFrame],
    code_names: dict[str, str],
    signal_dates: list[str],
    cache: dict[str, dict[str, Any]],
    experiment: Experiment,
    min_score: float,
    min_rr: float,
    top_n: int,
) -> tuple[str, list[BacktestTrade]]:
    fcfg = experiment.filters
    all_trades: list[BacktestTrade] = []

    for signal_date in signal_dates:
        plans: list[TradePlan] = []

        # Compute sector avg for this date (if needed)
        sector_avg_return = 0.0
        if fcfg.get("relative_strength"):
            lookback = fcfg.get("rs_lookback", 5)
            key = f"rs_{lookback}"
            sector_returns = []
            for code in code_data:
                c = cache[code].get(signal_date)
                if c and c["valid"]:
                    sector_returns.append(c[key])
            sector_avg_return = sum(sector_returns) / len(sector_returns) if sector_returns else 0.0

        for code, df_full in code_data.items():
            c = cache[code].get(signal_date)
            if c is None or not c["valid"]:
                continue

            name = code_names[code]

            if fcfg.get("exclude_st") and _is_st(name):
                continue
            if fcfg.get("exclude_suspended") and c["suspended"]:
                continue
            if fcfg.get("min_price") is not None and not c["price_ok"]:
                continue
            if fcfg.get("relative_strength"):
                key = f"rs_{fcfg.get('rs_lookback', 5)}"
                if c[key] < sector_avg_return:
                    continue
            if fcfg.get("volume_confirm"):
                max_vol_ratio = fcfg.get("max_vol_ratio", 1.5)
                if c["vol_ratio_5"] > max_vol_ratio or c["amt_ratio_5"] > max_vol_ratio:
                    continue

            pos = c["pos"]
            df_hist = df_full.iloc[pos - LOOKBACK_BARS : pos + 1].copy()
            scores = _compute_scores(df_hist)
            if not scores:
                continue

            plan = _generate_trade_plan(df_hist, scores, code, name)
            if plan and plan.total_score >= min_score and plan.risk_reward >= min_rr:
                plans.append(plan)

        plans.sort(key=lambda x: x.total_score, reverse=True)
        selected = plans[:top_n]

        for plan in selected:
            df_full = code_data[plan.code]
            pos = cache[plan.code][signal_date]["pos"]
            df_future = df_full.iloc[pos + 1 :].copy()

            sim = simulate_trade(
                df_future, plan.entry_price, plan.stop_price,
                plan.target_price, experiment.future_days,
            )

            all_trades.append(BacktestTrade(
                code=plan.code, name=plan.name, signal_date=signal_date,
                buy_date=sim["buy_date"], sell_date=sim["sell_date"],
                buy_price=sim["buy_price"], sell_price=sim["sell_price"],
                return_pct=sim["return_pct"], hold_days=sim["hold_days"],
                result=sim["result"], score=plan.total_score,
                entry_price=plan.entry_price, stop_price=plan.stop_price,
                target_price=plan.target_price, risk_reward=plan.risk_reward,
            ))

    return experiment.name, all_trades


# ─── Stats & reporting ────────────────────────────────────────────────────────

def compute_stats(trades: list[BacktestTrade]) -> dict[str, Any]:
    valid = [t for t in trades if t.result not in ("no_trigger", "data_error")]
    if not valid:
        return {"n": 0, "win_rate": 0, "avg_return": 0, "median_return": 0,
                "profit_factor": 0, "max_gain": 0, "max_loss": 0, "avg_hold": 0,
                "trigger_rate": 0, "profit_count": 0, "loss_count": 0, "expired_count": 0}

    returns = [t.return_pct for t in valid]
    wins = [t for t in valid if t.return_pct > 0]
    losses = [t for t in valid if t.return_pct <= 0]

    triggered = [t for t in trades if t.result != "no_trigger"]
    trigger_rate = len(triggered) / len(trades) * 100 if trades else 0

    win_rate = len(wins) / len(valid) * 100
    avg_return = sum(returns) / len(returns)
    median_return = sorted(returns)[len(returns) // 2]
    max_gain = max(returns)
    max_loss = min(returns)
    avg_hold = sum(t.hold_days for t in valid) / len(valid)

    profit_factor = (
        sum(t.return_pct for t in wins) / abs(sum(t.return_pct for t in losses))
        if losses and sum(t.return_pct for t in losses) != 0 else float("inf")
    )

    return {
        "n": len(trades), "triggered": len(triggered), "trigger_rate": trigger_rate,
        "win_rate": win_rate, "avg_return": avg_return, "median_return": median_return,
        "profit_factor": profit_factor, "max_gain": max_gain, "max_loss": max_loss,
        "avg_hold": avg_hold,
        "profit_count": sum(1 for t in valid if t.result == "profit"),
        "loss_count": sum(1 for t in valid if t.result == "loss"),
        "expired_count": sum(1 for t in valid if t.result == "expired"),
    }


def print_comparison(results: list[tuple[str, dict[str, Any]]]) -> None:
    print("\n" + "=" * 130)
    print("  Ablation Study Comparison")
    print("=" * 130)
    header = (
        f"  {'Experiment':<30} {'Signals':>6} {'Trig':>6} {'Trig%':>6} "
        f"{'Win%':>6} {'AvgRet':>8} {'Median':>8} {'PF':>6} "
        f"{'Prof':>5} {'Loss':>5} {'Exp':>5} {'Max+':>7} {'Max-':>7}"
    )
    print(header)
    print("  " + "-" * 126)
    for name, stats in results:
        if stats["n"] == 0:
            print(f"  {name:<30} (no data)")
            continue
        print(
            f"  {name:<30} "
            f"{stats['n']:>6} {stats['triggered']:>6} {stats['trigger_rate']:>5.1f}% "
            f"{stats['win_rate']:>5.1f}% {stats['avg_return']:>+7.2f}% {stats['median_return']:>+7.2f}% "
            f"{stats['profit_factor']:>6.2f} "
            f"{stats['profit_count']:>5} {stats['loss_count']:>5} {stats['expired_count']:>5} "
            f"{stats['max_gain']:>+6.1f}% {stats['max_loss']:>+6.1f}%"
        )
    print()


def main():
    t0 = datetime.now()
    print(f"Ablation Study — Precomputed Cache + Parallel")
    print(f"Start: {t0.strftime('%H:%M:%S')}")
    print()

    codes = by_board("创业板")
    print(f"创业板股票数: {len(codes)}")

    weeks = 20
    top_n = 20
    min_score = 55
    min_rr = 0.5

    # Parallel pre-load
    print("Parallel pre-loading all stock data...")
    code_data, code_names = preload_data_parallel(codes, future_days=20, max_workers=12)
    print(f"Loaded: {len(code_data)}/{len(codes)} stocks")

    first_df = next(iter(code_data.values()))
    signal_dates = _generate_signal_dates(first_df, weeks)
    print(f"Signal dates: {len(signal_dates)}")
    print()

    # Pre-compute all reusable metrics once
    print("Pre-computing reusable metrics for all (stock, date) pairs...")
    t_cache = datetime.now()
    cache = build_precomputed_cache(code_data, signal_dates)
    print(f"Cache built in {(datetime.now() - t_cache).total_seconds():.1f}s")
    print()

    experiments = [
        Experiment("Baseline (5d)", {}),
        Experiment("+ Exclude ST", {"exclude_st": True}),
        Experiment("+ Exclude ST+Suspended", {"exclude_st": True, "exclude_suspended": True}),
        Experiment("+ Relative Strength(5d)", {"relative_strength": True, "rs_lookback": 5}),
        Experiment("+ Volume Confirm", {"volume_confirm": True, "vol_lookback": 5, "max_vol_ratio": 1.5}),
        Experiment("+ Combo C (All filters)", {
            "exclude_st": True, "exclude_suspended": True,
            "min_price": 2.0, "relative_strength": True, "rs_lookback": 5,
            "volume_confirm": True, "vol_lookback": 5, "max_vol_ratio": 1.5,
        }),
        Experiment("Baseline (10d)", {}, future_days=10),
        Experiment("Baseline (20d)", {}, future_days=20),
    ]

    # Run all experiments in parallel
    results = []
    with ThreadPoolExecutor(max_workers=len(experiments)) as executor:
        futures = {
            executor.submit(
                run_single_experiment_cached,
                code_data, code_names, signal_dates, cache, exp,
                min_score, min_rr, top_n,
            ): exp.name
            for exp in experiments
        }
        for future in as_completed(futures):
            name, trades = future.result()
            stats = compute_stats(trades)
            results.append((name, stats))
            print(f"  Done: {name:<30} signals={stats['n']:>3} avg={stats['avg_return']:>+6.2f}% win={stats['win_rate']:>5.1f}%")

    name_order = {e.name: i for i, e in enumerate(experiments)}
    results.sort(key=lambda x: name_order[x[0]])

    print_comparison(results)

    total_elapsed = (datetime.now() - t0).total_seconds()
    print(f"Total elapsed: {total_elapsed:.1f}s")

    # Save
    out_dir = Path(ROOT) / "reports" / "backtests"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"ablation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    lines = []
    lines.append("=" * 130)
    lines.append("  Ablation Study Comparison")
    lines.append("=" * 130)
    header = (
        f"  {'Experiment':<30} {'Signals':>6} {'Trig':>6} {'Trig%':>6} "
        f"{'Win%':>6} {'AvgRet':>8} {'Median':>8} {'PF':>6} "
        f"{'Prof':>5} {'Loss':>5} {'Exp':>5} {'Max+':>7} {'Max-':>7}"
    )
    lines.append(header)
    lines.append("  " + "-" * 126)
    for name, stats in results:
        if stats["n"] == 0:
            lines.append(f"  {name:<30} (no data)")
            continue
        lines.append(
            f"  {name:<30} "
            f"{stats['n']:>6} {stats['triggered']:>6} {stats['trigger_rate']:>5.1f}% "
            f"{stats['win_rate']:>5.1f}% {stats['avg_return']:>+7.2f}% {stats['median_return']:>+7.2f}% "
            f"{stats['profit_factor']:>6.2f} "
            f"{stats['profit_count']:>5} {stats['loss_count']:>5} {stats['expired_count']:>5} "
            f"{stats['max_gain']:>+6.1f}% {stats['max_loss']:>+6.1f}%"
        )
    lines.append(f"\nTotal elapsed: {total_elapsed:.1f}s")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[Saved] {out_path}")


if __name__ == "__main__":
    main()
