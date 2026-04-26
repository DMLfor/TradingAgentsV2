"""关注池每日扫描 — 对关注池股票进行快速技术面检查.

Usage:
    python scripts/watchlist_scan.py --pool default --save
    python scripts/watchlist_scan.py --pool tech --date 2026-04-24 --save
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pandas as pd

from tdx_core import TdxIndicators, TdxQuery, get_name
from tdx_core.watchlist import WatchlistManager
from tdx_core.reporting import ReportManager


def _scan_one(code: str, query: TdxQuery, end_date: str) -> dict | None:
    """扫描单只股票，返回技术面摘要."""
    try:
        df = query.get_daily(code, end_date=end_date)
        if df is None or len(df) < 30:
            return None
        df = df.sort_values("trade_date").reset_index(drop=True)
        for col in ["open_val", "high_val", "low_val", "close_val", "volume"]:
            if col in df.columns:
                df[col] = df[col].astype(float)

        df = TdxIndicators.compute(df, indicators=["ma", "macd", "rsi"])
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else last

        close = float(last["close_val"])
        prev_close = float(prev["close_val"])
        change_pct = (close - prev_close) / prev_close * 100

        # 均线状态
        ma5 = last.get("ma_5")
        ma10 = last.get("ma_10")
        ma20 = last.get("ma_20")
        ma60 = last.get("ma_60")
        try:
            if close > ma5 > ma10 > ma20 > ma60:
                ma_state = "多头排列"
            elif close < ma5 < ma10 < ma20 < ma60:
                ma_state = "空头排列"
            else:
                ma_state = "震荡整理"
        except Exception:
            ma_state = "未知"

        # MACD
        macd_val = float(last.get("macd", 0))
        macd_sig = float(last.get("macd_signal", 0))
        macd_hist = float(last.get("macd_hist", 0))
        if macd_val > macd_sig:
            macd_state = "金叉/多头" if macd_hist > 0 else "金叉收敛"
        else:
            macd_state = "死叉/空头" if macd_hist < 0 else "死叉收敛"

        # RSI
        rsi = float(last.get("rsi_14", 50))

        # 成交量（量比近5日）
        vol = float(last.get("volume", 0))
        vol_ma5 = df["volume"].tail(5).mean()
        vol_ratio = vol / vol_ma5 if vol_ma5 and vol_ma5 > 0 else 1.0

        return {
            "code": code,
            "name": get_name(code) or code,
            "close": round(close, 2),
            "change_pct": round(change_pct, 2),
            "macd_state": macd_state,
            "rsi": round(rsi, 1),
            "ma_state": ma_state,
            "vol_ratio": round(vol_ratio, 2),
        }
    except Exception:
        return None


def run_scan(pool: str, date: str | None, save: bool) -> list[dict]:
    """运行关注池扫描."""
    wm = WatchlistManager()
    codes = wm.get_codes(pool)
    if not codes:
        print(f"[提示] 关注池 '{pool}' 为空")
        return []

    effective_date = date or datetime.now().strftime("%Y-%m-%d")

    print(f"\n[关注池扫描] 池: {pool} | 股票数: {len(codes)} | 日期: {effective_date}")
    print("数据加载中...")

    results = []
    with TdxQuery() as q:
        for i, code in enumerate(codes, 1):
            print(f"  ({i}/{len(codes)}) {code} ...", end="\r")
            r = _scan_one(code, q, effective_date)
            if r:
                results.append(r)

    print(f"\n扫描完成: {len(results)}/{len(codes)} 只成功")
    return results


def _print_results(results: list[dict], pool: str, date: str) -> None:
    if not results:
        return
    print(f"\n{'=' * 90}")
    print(f"关注池扫描报告 — {pool} ({len(results)}只) — {date}")
    print(f"{'=' * 90}")
    header = (
        f"{'代码':<10}{'名称':<12}{'收盘价':<10}{'涨跌':<10}"
        f"{'MACD':<12}{'RSI':<8}{'均线':<10}{'量比':<8}"
    )
    print(header)
    print("-" * 90)
    for r in results:
        change_str = f"{r['change_pct']:+.2f}%"
        print(
            f"{r['code']:<10}{r['name']:<12}{r['close']:<10.2f}{change_str:<10}"
            f"{r['macd_state']:<12}{r['rsi']:<8.1f}{r['ma_state']:<10}{r['vol_ratio']:<8.2f}"
        )
    print(f"{'=' * 90}\n")


def _save_results(results: list[dict], pool: str, date: str) -> str | None:
    """保存扫描结果为 Markdown 报告."""
    if not results:
        return None
    rm = ReportManager()
    dir_path = rm.base / "watchlist" / date
    dir_path.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# 关注池扫描报告 — {pool} — {date}",
        "",
        f"**扫描数量**: {len(results)} 只",
        "",
        "| 代码 | 名称 | 收盘价 | 涨跌 | MACD | RSI | 均线 | 量比 |",
        "|------|------|--------|------|------|-----|------|------|",
    ]
    for r in results:
        change_str = f"{r['change_pct']:+.2f}%"
        lines.append(
            f"| {r['code']} | {r['name']} | {r['close']:.2f} | {change_str} | "
            f"{r['macd_state']} | {r['rsi']:.1f} | {r['ma_state']} | {r['vol_ratio']:.2f} |"
        )
    lines.append("")
    lines.append("---")
    lines.append(f"*生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

    path = dir_path / f"{pool}_scan.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def main():
    parser = argparse.ArgumentParser(description="关注池每日扫描")
    parser.add_argument("--pool", default="default", help="关注池名称")
    parser.add_argument("--date", help="扫描日期 YYYY-MM-DD")
    parser.add_argument("--save", action="store_true", help="保存报告")
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    results = run_scan(args.pool, args.date, args.save)
    _print_results(results, args.pool, date_str)

    if args.save and results:
        path = _save_results(results, args.pool, date_str)
        if path:
            print(f"[已保存报告] {path}")


if __name__ == "__main__":
    main()
