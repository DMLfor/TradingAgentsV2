#!/usr/bin/env python3
"""Batch backtest all 515180 strategies and output a ranked summary.

Usage:
    python scripts/batch_backtest.py
"""
from __future__ import annotations

import glob
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core.backtest import BacktestEngine, StrategyConfig
from tdx_core.reporting import ReportManager
from tdx_core.names import get_name


def run_single(strategy_path: Path, start_date: str, end_date: str, benchmark_code: str):
    """Run one strategy backtest."""
    config = StrategyConfig.from_json(strategy_path)
    engine = BacktestEngine(config, max_workers=4)
    result = engine.run(start_date=start_date, end_date=end_date, benchmark_code=benchmark_code)
    return config, result


def main():
    start_date = "2021-08-02"
    end_date = datetime.now().strftime("%Y-%m-%d")
    benchmark_code = "000300"
    code = "515180"
    code_name = get_name(code) or code

    strategy_files = sorted(glob.glob(str(Path(ROOT) / "strategies" / "515180_*.json")))
    if not strategy_files:
        print("[错误] 未找到策略文件，请先运行 scripts/generate_strategies.py")
        sys.exit(1)

    print(f"批量回测: {code_name}({code})")
    print(f"区间: {start_date} ~ {end_date}")
    print(f"基准: {benchmark_code}")
    print(f"策略数: {len(strategy_files)}")
    print("-" * 70)

    mgr = ReportManager()
    rows = []

    for i, path in enumerate(strategy_files, 1):
        path = Path(path)
        sid = path.stem.replace("515180_", "")
        print(f"\n[{i}/{len(strategy_files)}] 回测: {sid} ...", end=" ")

        try:
            config, result = run_single(path, start_date, end_date, benchmark_code)
            m = result.metrics

            row = {
                "strategy": config.name,
                "strategy_id": sid,
                "total_return_pct": round(m.total_return_pct, 2),
                "annualized_return": round(m.annualized_return, 2),
                "max_drawdown_pct": round(m.max_drawdown_pct, 2),
                "sharpe_ratio": round(m.sharpe_ratio, 2),
                "sortino_ratio": round(m.sortino_ratio, 2),
                "win_rate": round(m.win_rate, 1),
                "total_trades": m.total_trades,
                "avg_return_per_trade": round(m.avg_return_per_trade, 2),
                "profit_factor": round(m.profit_factor, 2),
                "benchmark_return": round(m.benchmark_return, 2),
                "alpha": round(m.alpha, 2),
                "beta": round(m.beta, 2),
            }
            rows.append(row)

            # Save individual report
            mgr.save_backtest_report(
                result, config.name, code, code_name,
                benchmark_code, start_date, end_date,
                strategy_id=sid
            )

            print(f"收益率 {m.total_return_pct:+.2f}% | 夏普 {m.sharpe_ratio:.2f} | 回撤 {m.max_drawdown_pct:.2f}% | 交易 {m.total_trades}")

        except Exception as exc:
            print(f"[失败] {exc}")
            rows.append({
                "strategy": sid,
                "strategy_id": sid,
                "total_return_pct": None,
                "sharpe_ratio": None,
                "max_drawdown_pct": None,
                "total_trades": 0,
            })

    # Save batch summary
    summary_path = mgr.save_batch_summary(
        rows, code, code_name, benchmark_code, start_date, end_date
    )
    mgr.update_index()

    # Print ranking table
    print("\n" + "=" * 70)
    print("  策略批量回测排名（按夏普比率降序）")
    print("=" * 70)

    # Sort by sharpe desc, putting None at bottom
    sorted_rows = sorted(rows, key=lambda r: (r.get("sharpe_ratio") is None, - (r.get("sharpe_ratio") or -999)))

    print(f"\n  {'排名':>4} {'策略名称':<20} {'总收益':>8} {'年化':>8} {'回撤':>8} {'夏普':>6} {'胜率':>6} {'交易':>4}")
    print("  " + "-" * 70)
    for rank, r in enumerate(sorted_rows, 1):
        name = r["strategy"][:18]
        ret = f"{r.get('total_return_pct', 0):+.1f}%" if r.get("total_return_pct") is not None else "N/A"
        ann = f"{r.get('annualized_return', 0):+.1f}%" if r.get("annualized_return") is not None else "N/A"
        dd = f"{r.get('max_drawdown_pct', 0):.1f}%" if r.get("max_drawdown_pct") is not None else "N/A"
        sr = f"{r.get('sharpe_ratio', 0):.2f}" if r.get("sharpe_ratio") is not None else "N/A"
        wr = f"{r.get('win_rate', 0):.1f}%" if r.get("win_rate") is not None else "N/A"
        tr = str(r.get("total_trades", 0))
        print(f"  {rank:>4} {name:<20} {ret:>8} {ann:>8} {dd:>8} {sr:>6} {wr:>6} {tr:>4}")

    print("\n" + "=" * 70)
    best = sorted_rows[0]
    btr = best.get('total_return_pct')
    bdd = best.get('max_drawdown_pct')
    bsr = best.get('sharpe_ratio')
    print(f"  最优策略: {best['strategy']}")
    print(f"  总收益率: {btr:+.2f}%" if btr is not None else "  总收益率: N/A")
    print(f"  最大回撤: {bdd:.2f}%" if bdd is not None else "  最大回撤: N/A")
    print(f"  夏普比率: {bsr:.2f}" if bsr is not None else "  夏普比率: N/A")
    print("=" * 70)

    print(f"\n[汇总报告已保存] {summary_path}")
    print(f"[索引已更新] {mgr.base / 'index.md'}")


if __name__ == "__main__":
    main()
