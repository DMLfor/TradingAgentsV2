#!/usr/bin/env python3
"""创业板全量股票技术分析排名 — 120日数据批量评分.

Usage:
    python scripts/rank_growth_board.py
    python scripts/rank_growth_board.py --bars 120 --top 100
    python scripts/rank_growth_board.py --save
"""

from __future__ import annotations

import argparse
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Auto-detect project root (works from both scripts/ and skill/scripts/)
_p = Path(__file__).resolve()
# Try to find project root by looking for tdx_core or pyproject.toml
ROOT = str(_p.parent.parent)  # default: 2 levels up
for i in range(2, min(8, len(_p.parents))):
    _ancestor = _p.parents[i]
    if (_ancestor / "tdx_core").exists() or (_ancestor / "pyproject.toml").exists():
        ROOT = str(_ancestor)
        break
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Import the analysis engine from technical_master
from scripts.technical_master import fetch_and_compute, calc_period_scores, detect_market_regime, _calc_raw_volatility
from tdx_core.metadata import by_board, get_meta


BARS_DEFAULT = 120
TOP_N_DEFAULT = 100
MAX_WORKERS = 12


def phase1_fetch(code: str, bars: int) -> dict[str, Any] | None:
    """Phase 1: fetch data + raw volatility + regime detection."""
    try:
        df = fetch_and_compute(code, bars)
        if df is None or df.empty or len(df) < bars * 0.8:
            return None
        raw_vol = _calc_raw_volatility(df)
        regime, weights = detect_market_regime(df)
        return {
            "code": code,
            "df": df,
            "raw_vol": raw_vol,
            "regime": regime,
            "weights": weights,
        }
    except Exception:
        return None


def phase2_score(item: dict[str, Any], vol_percentile: float) -> dict[str, Any] | None:
    """Phase 2: final scoring with relative volatility."""
    try:
        scores, _ = calc_period_scores(
            item["df"], weights_override=item["weights"], vol_percentile=vol_percentile
        )
        meta = get_meta(item["code"])
        name = meta["name"] if meta else item["code"]
        return {
            "code": item["code"],
            "name": name,
            "level1": meta["level1"] if meta else "",
            "level2": meta["level2"] if meta else "",
            "regime": item["regime"],
            "overall": scores["overall"],
            "trend": scores["trend"],
            "momentum": scores["momentum"],
            "volatility": scores["volatility"],
            "volume": scores["volume"],
            "bars": len(item["df"]),
        }
    except Exception:
        return None


def run_analysis(codes: list[str], bars: int, top_n: int) -> list[dict]:
    """Run concurrent analysis with relative volatility scoring."""
    # ── Phase 1 ──
    items: list[dict] = []
    total = len(codes)
    processed = 0
    success = 0

    print(f"▌创业板技术分析排名 ({bars}日数据)")
    print(f"  总股票数: {total}  |  并发线程: {MAX_WORKERS}")
    print(f"  Phase1 开始: {datetime.now().strftime('%H:%M:%S')}")
    print()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(phase1_fetch, code, bars): code for code in codes}
        for future in as_completed(future_map):
            processed += 1
            item = future.result()
            if item:
                items.append(item)
                success += 1

            if processed % 100 == 0 or processed == total:
                print(f"  Phase1: {processed}/{total}  成功: {success}  ({success / processed * 100:.1f}%)", end="\r")

    print()
    print(f"  Phase1 完成: {datetime.now().strftime('%H:%M:%S')} | 成功: {success}/{total}")

    if not items:
        return []

    # ── Relative volatility percentiles ──
    raw_vols = [it["raw_vol"] for it in items]
    raw_vols_sorted = sorted(raw_vols)
    n_peers = len(raw_vols_sorted)

    def _percentile(val: float) -> float:
        below = sum(1 for v in raw_vols_sorted if v < val)
        equal = sum(1 for v in raw_vols_sorted if v == val)
        return (below + equal / 2) / n_peers

    for it in items:
        it["vol_pct"] = _percentile(it["raw_vol"])

    vol_range = raw_vols_sorted[-1] - raw_vols_sorted[0]
    print(f"  原始波动范围: {raw_vols_sorted[0]:.2f} ~ {raw_vols_sorted[-1]:.2f} (跨度 {vol_range:.2f})")

    # ── Phase 2: score (parallel) ──
    results: list[dict] = []
    print(f"  Phase2 开始: {datetime.now().strftime('%H:%M:%S')}")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(phase2_score, it, it["vol_pct"]): it for it in items}
        for future in as_completed(future_map):
            r = future.result()
            if r:
                results.append(r)

    print(f"  Phase2 完成: {datetime.now().strftime('%H:%M:%S')} | 成功: {len(results)}/{len(items)}")
    print()

    results.sort(key=lambda x: x["overall"], reverse=True)
    return results


def _bar(percent: float, width: int = 12) -> str:
    filled = int(round(percent / 10 * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def print_top(results: list[dict], top_n: int) -> str:
    """Print and return the top-N ranking table."""
    lines = []
    lines.append("╔" + "═" * 108 + "╗")
    lines.append(f"║  创业板技术分析排名 Top {top_n:<3} (120日综合评分){' ' * 60}║")
    lines.append("╠" + "═" * 108 + "╣")
    header = f"  {'排名':<4} {'代码':<8} {'名称':<10} {'一级行业':<8} {'二级行业':<8} {'趋势':>5} {'动量':>5} {'波动':>5} {'量价':>5} {'综合':>5} {'研判':<8}"
    lines.append(f"║{header:<108}║")
    lines.append(f"║  {'─'*104}  ║")

    for i, r in enumerate(results, 1):
        ov = r["overall"]
        label = (
        "🔥强烈偏多" if ov >= 7.8 else
        "📈谨慎偏多" if ov >= 7.0 else
        "➡️中性偏强" if ov >= 6.0 else
        "➖中性" if ov >= 5.0 else
        "⚠️中性偏弱" if ov >= 4.0 else
        "📉谨慎偏空"
    )
        row = (
            f"  {i:<4} {r['code']:<8} {r['name']:<10} {r['level1']:<8} {r['level2']:<8}"
            f" {r['trend']:>5.1f} {r['momentum']:>5.1f} {r['volatility']:>5.1f} {r['volume']:>5.1f}"
            f" {ov:>5.1f} {label:<8}"
        )
        lines.append(f"║{row:<108}║")

    lines.append("╚" + "═" * 108 + "╝")
    text = "\n".join(lines)
    print(text)
    return text


def print_distribution(results: list[dict]) -> None:
    """Print score distribution histogram."""
    if not results:
        return
    scores = [r["overall"] for r in results]
    print("▌评分分布")
    bins = [(0, 3), (3, 4.5), (4.5, 5.5), (5.5, 6.5), (6.5, 8), (8, 10)]
    for lo, hi in bins:
        count = sum(1 for s in scores if lo <= s < hi)
        pct = count / len(scores) * 100
        bar = "█" * int(pct / 2)
        print(f"  {lo:>4.1f}~{hi:<4.1f}: {bar:<50} {count:>4}只 ({pct:>5.1f}%)")
    print(f"  平均分: {sum(scores)/len(scores):.2f}  最高分: {max(scores):.2f}  最低分: {min(scores):.2f}")
    print()


def main():
    parser = argparse.ArgumentParser(description="创业板全量股票技术分析排名")
    parser.add_argument("--bars", type=int, default=BARS_DEFAULT, help="分析窗口天数 (default: 120)")
    parser.add_argument("--top", type=int, default=TOP_N_DEFAULT, help="输出Top N (default: 100)")
    parser.add_argument("--save", action="store_true", help="保存结果到 reports/rankings/")
    args = parser.parse_args()

    # Get all 创业板 codes
    codes = by_board("创业板")
    if not codes:
        print("[ERROR] 未找到创业板股票，请确认 metadata 已生成")
        print("Run: python scripts/update_stock_metadata.py")
        sys.exit(1)

    print(f"  创业板股票数: {len(codes)}")
    print()

    # Run analysis
    all_results = run_analysis(codes, args.bars, args.top)

    if not all_results:
        print("[ERROR] 没有成功分析任何股票")
        sys.exit(1)

    # Print distribution of ALL successful analyses
    print_distribution(all_results)

    # Print top table
    top_results = all_results[:args.top]
    text = print_top(top_results, args.top)

    # Save
    if args.save:
        out_dir = Path(ROOT) / "reports" / "rankings"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"growth_board_rank_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        out_path.write_text(text, encoding="utf-8")
        print(f"\n[Saved] {out_path}")


if __name__ == "__main__":
    main()
