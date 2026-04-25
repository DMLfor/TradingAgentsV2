#!/usr/bin/env python3
"""Multi-factor strategy backtest CLI.

Usage:
    # Run with a JSON strategy file
    python scripts/strategy_backtest.py --strategy strategies/trend_momentum.json --start 2024-01-01 --end 2025-12-31 --save

    # Run with a built-in template
    python scripts/strategy_backtest.py --template trend_momentum --board 创业板 --start 2024-01-01 --end 2025-12-31 --save

    # Quick test with inline strategy JSON
    python scripts/strategy_backtest.py --inline '{"name":"test","entry":{"conditions":[{"indicator":"composite_score","op":">=","value":7.0}]}}' --start 2024-06-01 --end 2025-06-01
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core.backtest import BacktestEngine, StrategyConfig


BUILTIN_TEMPLATES = {
    "trend_momentum": {
        "name": "趋势动量策略",
        "description": "MACD 金叉买入，MACD 死叉或趋势转弱卖出",
        "universe": {"board": "创业板", "min_price": 5, "max_price": 500, "exclude_st": True},
        "lookback": 60,
        "initial_capital": 1000000,
        "position": {"max_holding": 10, "per_position": 0.1, "weight_by": "equal"},
        "entry": {
            "conditions": [
                {"indicator": "macd", "signal": "golden_cross"},
                {"indicator": "rsi", "op": "<", "value": 70},
            ],
            "rank_by": "composite_score",
            "direction": "desc",
            "limit": 10,
        },
        "exit": {
            "conditions": [
                {"indicator": "macd", "signal": "death_cross"},
            ],
            "stop_loss": -0.10,
            "take_profit": 0.30,
            "max_hold_days": 30,
        },
        "rebalance": {"frequency": "daily"},
        "costs": {
            "commission_buy": 0.00025,
            "commission_sell": 0.00025,
            "tax_sell": 0.001,
            "slippage": 0.0001,
        },
    },
    "high_score_breakout": {
        "name": "高分突破策略",
        "description": "选择综合评分 Top 20 且突破布林上轨的股票，跌破中轨或评分低于 6 时卖出",
        "universe": {"board": "创业板", "min_price": 5, "max_price": 500, "exclude_st": True},
        "lookback": 60,
        "initial_capital": 1000000,
        "position": {"max_holding": 15, "per_position": 0.067, "weight_by": "equal"},
        "entry": {
            "conditions": [
                {"indicator": "composite_score", "op": ">=", "value": 7.5},
                {"indicator": "bollinger", "signal": "touch_upper"},
            ],
            "rank_by": "composite_score",
            "direction": "desc",
            "limit": 15,
        },
        "exit": {
            "conditions": [
                {"indicator": "composite_score", "op": "<", "value": 6.0},
                {"indicator": "bollinger", "signal": "touch_lower"},
            ],
            "stop_loss": -0.10,
            "take_profit": 0.25,
            "max_hold_days": 15,
        },
        "rebalance": {"frequency": "daily"},
        "costs": {
            "commission_buy": 0.00025,
            "commission_sell": 0.00025,
            "tax_sell": 0.001,
            "slippage": 0.0001,
        },
    },
    "low_vol_trend": {
        "name": "低波动趋势策略",
        "description": "选择趋势强但波动低（ATR 百分位低）的股票，适合稳健持仓",
        "universe": {"board": "沪市主板", "min_price": 5, "max_price": 500, "exclude_st": True},
        "lookback": 120,
        "initial_capital": 1000000,
        "position": {"max_holding": 8, "per_position": 0.125, "weight_by": "equal"},
        "entry": {
            "conditions": [
                {"indicator": "trend_score", "op": ">=", "value": 7.0},
                {"indicator": "volatility_score", "op": "<=", "value": 3.0},
                {"indicator": "rsi", "op": ">=", "value": 50},
            ],
            "rank_by": "trend_score",
            "direction": "desc",
            "limit": 8,
        },
        "exit": {
            "conditions": [
                {"indicator": "trend_score", "op": "<", "value": 5.0},
            ],
            "stop_loss": -0.05,
            "take_profit": 0.15,
            "max_hold_days": 30,
        },
        "rebalance": {"frequency": "daily"},
        "costs": {
            "commission_buy": 0.00025,
            "commission_sell": 0.00025,
            "tax_sell": 0.001,
            "slippage": 0.0001,
        },
    },
    "rsi_bounce": {
        "name": "RSI 超卖反弹策略",
        "description": "选择 RSI 超卖后反弹的股票，RSI 回到中性区或触及止损时卖出",
        "universe": {"board": "创业板", "min_price": 5, "max_price": 500, "exclude_st": True},
        "lookback": 60,
        "initial_capital": 1000000,
        "position": {"max_holding": 10, "per_position": 0.1, "weight_by": "equal"},
        "entry": {
            "conditions": [
                {"indicator": "rsi", "op": "<", "value": 35},
                {"indicator": "composite_score", "op": ">=", "value": 5.0},
            ],
            "rank_by": "composite_score",
            "direction": "desc",
            "limit": 10,
        },
        "exit": {
            "conditions": [
                {"indicator": "rsi", "op": ">", "value": 65},
            ],
            "stop_loss": -0.06,
            "take_profit": 0.12,
            "max_hold_days": 10,
        },
        "rebalance": {"frequency": "daily"},
        "costs": {
            "commission_buy": 0.00025,
            "commission_sell": 0.00025,
            "tax_sell": 0.001,
            "slippage": 0.0001,
        },
    },
}


def load_config(args) -> StrategyConfig:
    """Load strategy config from various sources."""
    if args.strategy:
        path = Path(args.strategy)
        if not path.exists():
            # Try strategies/ subdir
            path = Path(ROOT) / "strategies" / args.strategy
            if not path.exists() and not str(args.strategy).endswith(".json"):
                path = Path(ROOT) / "strategies" / f"{args.strategy}.json"
        if not path.exists():
            print(f"[ERROR] Strategy file not found: {args.strategy}")
            sys.exit(1)
        return StrategyConfig.from_json(path)

    if args.template:
        name = args.template
        if name not in BUILTIN_TEMPLATES:
            print(f"[ERROR] Unknown template: {name}")
            print(f"Available: {', '.join(BUILTIN_TEMPLATES.keys())}")
            sys.exit(1)
        config = StrategyConfig.from_dict(BUILTIN_TEMPLATES[name])
        # Override universe from CLI args
        if args.codes:
            # Explicit codes override everything else
            config.universe = {"codes": args.codes}
        else:
            if args.board:
                config.universe["board"] = args.board
            if args.level1:
                config.universe["level1"] = args.level1
            if args.level2:
                config.universe["level2"] = args.level2
        return config

    if args.inline:
        try:
            data = json.loads(args.inline)
            return StrategyConfig.from_dict(data)
        except json.JSONDecodeError as exc:
            print(f"[ERROR] Invalid inline JSON: {exc}")
            sys.exit(1)

    print("[ERROR] Must provide --strategy, --template, or --inline")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Multi-factor strategy backtest")
    parser.add_argument("--strategy", "-s", help="Path to strategy JSON file")
    parser.add_argument("--template", "-t", help=f"Built-in template ({', '.join(BUILTIN_TEMPLATES.keys())})")
    parser.add_argument("--inline", help="Inline strategy JSON string")
    today = datetime.now().strftime("%Y-%m-%d")
    parser.add_argument("--start", required=True, help="开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", default=today, help=f"结束日期 (YYYY-MM-DD), 默认今天 ({today})")
    parser.add_argument("--capital", type=float, default=1_000_000, help="Initial capital (default: 1,000,000)")
    parser.add_argument("--board", help="Override universe board")
    parser.add_argument("--level1", help="Override universe level1 industry")
    parser.add_argument("--level2", help="Override universe level2 industry")
    parser.add_argument("--codes", help="Override universe with comma-separated codes")
    parser.add_argument("--workers", type=int, default=8, help="Parallel workers for data loading (default: 8)")
    parser.add_argument("--save", action="store_true", help="Save report to logs/")
    parser.add_argument("--export-trades", action="store_true", help="导出交易明细到 CSV")
    parser.add_argument("--export-nav", action="store_true", help="导出资金曲线到 CSV")
    parser.add_argument("--benchmark", help="基准指数代码 (如 000300 沪深300, 399006 创业板指)")
    parser.add_argument("--plot", action="store_true", help="生成资金曲线对比图 PNG")
    args = parser.parse_args()

    config = load_config(args)
    config.initial_capital = args.capital

    print(f"策略名称: {config.name}")
    print(f"回测区间: {args.start} ~ {args.end}")
    print(f"初始资金: {config.initial_capital:,.0f}")
    print("-" * 70)

    engine = BacktestEngine(config, max_workers=args.workers)
    result = engine.run(start_date=args.start, end_date=args.end, benchmark_code=args.benchmark)

    # Print report
    print("\n" + result.summary_text())

    # Save
    if args.save:
        log_dir = Path(ROOT) / "logs"
        log_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = config.name.replace(" ", "_").replace("/", "_")

        # Main report
        report_path = log_dir / f"bt_{safe_name}_{args.start}_{args.end}_{ts}.txt"
        report_path.write_text(result.summary_text(), encoding="utf-8")
        print(f"\n[已保存报告] {report_path}")

        # Metrics JSON
        metrics_path = log_dir / f"bt_{safe_name}_{ts}_metrics.json"
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(result.metrics.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"[已保存指标] {metrics_path}")

    if args.export_trades:
        log_dir = Path(ROOT) / "logs"
        log_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = config.name.replace(" ", "_").replace("/", "_")
        trades_path = log_dir / f"bt_{safe_name}_{ts}_trades.csv"
        result.trade_log().to_csv(trades_path, index=False, encoding="utf-8-sig")
        print(f"[已保存交易明细] {trades_path}")

    if args.export_nav:
        log_dir = Path(ROOT) / "logs"
        log_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = config.name.replace(" ", "_").replace("/", "_")
        nav_path = log_dir / f"bt_{safe_name}_{ts}_nav.csv"
        result.nav_df().to_csv(nav_path, index=False, encoding="utf-8-sig")
        print(f"[已保存资金曲线] {nav_path}")

    if args.plot:
        _plot_nav(result, config.name, args.start, args.end)



def _plot_nav(result, strategy_name: str, start_date: str, end_date: str):
    """Plot NAV curve with benchmark using ASCII art in terminal."""
    try:
        df = result.nav_df()
        if df.empty:
            print("[画图] 无净值数据，跳过")
            return

        has_bench = "benchmark" in df.columns and df["benchmark"].notna().any()
        vals = df["total_value"].values
        bench_vals = df["benchmark"].values if has_bench else None
        dates = df["date"].values

        # Chart dimensions
        width = 70
        height = 18
        vmin = min(vals.min(), bench_vals.min() if has_bench else vals.min())
        vmax = max(vals.max(), bench_vals.max() if has_bench else vals.max())
        if vmin == vmax:
            vmin -= 1
            vmax += 1

        def _y_to_row(v):
            return height - 1 - int((v - vmin) / (vmax - vmin) * (height - 1))

        # Build grid
        grid = [[" " for _ in range(width)] for _ in range(height)]

        # Draw benchmark first (so strategy line overlays)
        if has_bench:
            for i in range(len(bench_vals) - 1):
                x0 = int(i / (len(bench_vals) - 1) * (width - 1))
                x1 = int((i + 1) / (len(bench_vals) - 1) * (width - 1))
                y0 = _y_to_row(bench_vals[i])
                y1 = _y_to_row(bench_vals[i + 1])
                for x in range(x0, min(x1 + 1, width)):
                    t = (x - x0) / max(x1 - x0, 1)
                    y = int(y0 + t * (y1 - y0))
                    if 0 <= y < height:
                        grid[y][x] = "."

        # Draw strategy
        for i in range(len(vals) - 1):
            x0 = int(i / (len(vals) - 1) * (width - 1))
            x1 = int((i + 1) / (len(vals) - 1) * (width - 1))
            y0 = _y_to_row(vals[i])
            y1 = _y_to_row(vals[i + 1])
            for x in range(x0, min(x1 + 1, width)):
                t = (x - x0) / max(x1 - x0, 1)
                y = int(y0 + t * (y1 - y0))
                if 0 <= y < height:
                    grid[y][x] = "#"

        # Build output
        lines = []
        lines.append("")
        lines.append(f"  {strategy_name} 资金曲线 ({start_date} ~ {end_date})")
        lines.append("")

        # Y-axis labels
        y_labels = [f"{vmin + (height - 1 - i) / (height - 1) * (vmax - vmin):,.0f}" for i in range(height)]
        max_label_len = max(len(l) for l in y_labels)

        for i, row in enumerate(grid):
            label = y_labels[i].rjust(max_label_len)
            lines.append(f"{label} |{''.join(row)}|")

        # X-axis
        lines.append(" " * (max_label_len + 1) + "+" + "-" * width + "+")
        start_label = str(dates[0])[:10]
        end_label = str(dates[-1])[:10]
        x_line = start_label + " " * (width - len(start_label) - len(end_label)) + end_label
        lines.append(" " * (max_label_len + 1) + " " + x_line)

        # Legend
        lines.append("")
        lines.append("  图例: #=策略净值  .=基准净值")
        lines.append("")

        print("\n".join(lines))
    except Exception as exc:
        print(f"[画图失败] {exc}")


if __name__ == "__main__":
    main()
