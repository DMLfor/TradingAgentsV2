"""关注池每日复盘 — 对关注池股票进行技术面复盘和信号检测.

Usage:
    python scripts/watchlist_review.py --pool default --save
    python scripts/watchlist_review.py --pool tech --date 2026-04-24 --save
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

from tdx_core import TdxIndicators, TdxQuery, get_name, get_meta
from tdx_core.watchlist import WatchlistManager
from tdx_core.reporting import ReportManager


def _review_one(code: str, query: TdxQuery, end_date: str) -> dict | None:
    """复盘单只股票，返回技术面摘要和信号判断."""
    try:
        df = query.get_daily(code, end_date=end_date)
        if df is None or len(df) < 60:
            return None
        df = df.sort_values("trade_date").reset_index(drop=True)
        for col in ["open_val", "high_val", "low_val", "close_val", "volume"]:
            if col in df.columns:
                df[col] = df[col].astype(float)

        # 数据清洗：过滤单日跳变>50% 和 混入的个股数据（如000001混入平安银行）
        df["change_pct"] = df["close_val"].pct_change() * 100
        df = df[df["change_pct"].abs() <= 50].copy()
        tail5 = df.tail(5)
        if len(tail5) >= 3 and tail5["close_val"].min() < 1000 and tail5["close_val"].max() > 3000:
            df = df[df["close_val"] > 1000].copy()
        if len(df) < 30:
            return None

        df = TdxIndicators.compute(df, indicators=["ma", "macd", "rsi", "bollinger"])
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else last
        prev3 = df.iloc[-3] if len(df) >= 3 else prev

        close = float(last["close_val"])
        prev_close = float(prev["close_val"])
        change_pct = (close - prev_close) / prev_close * 100

        # 均线
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
        prev_hist = float(prev.get("macd_hist", macd_hist))
        if macd_val > macd_sig and macd_hist > prev_hist:
            macd_state = "金叉+扩张"
        elif macd_val > macd_sig:
            macd_state = "金叉"
        elif macd_val < macd_sig and macd_hist < prev_hist:
            macd_state = "死叉+扩张"
        else:
            macd_state = "死叉"

        # RSI
        rsi = float(last.get("rsi_14", 50))
        if rsi > 80:
            rsi_state = "严重超买"
        elif rsi > 70:
            rsi_state = "超买"
        elif rsi < 20:
            rsi_state = "严重超卖"
        elif rsi < 30:
            rsi_state = "超卖"
        else:
            rsi_state = "中性"

        # 布林带
        bb_upper = float(last.get("bb_upper", close))
        bb_lower = float(last.get("bb_lower", close))
        bb_pctb = (close - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5
        if bb_pctb > 0.95:
            bb_state = "突破上轨"
        elif bb_pctb > 0.8:
            bb_state = "接近上轨"
        elif bb_pctb < 0.05:
            bb_state = "跌破下轨"
        elif bb_pctb < 0.2:
            bb_state = "接近下轨"
        else:
            bb_state = "中轨附近"

        # 成交量
        vol = float(last.get("volume", 0))
        vol_ma5 = df["volume"].tail(5).mean()
        vol_ratio = vol / vol_ma5 if vol_ma5 and vol_ma5 > 0 else 1.0

        # 信号判断
        signals = []
        if macd_state.startswith("金叉") and rsi < 50:
            signals.append("MACD金叉")
        if rsi_state in ("严重超卖", "超卖"):
            signals.append("RSI超卖")
        if bb_state in ("跌破下轨", "接近下轨") and change_pct > -3:
            signals.append("布林带下轨")
        if ma_state == "多头排列" and close > ma5:
            signals.append("均线多头")
        if not signals:
            signals.append("无明确信号")

        # 操作建议
        if "MACD金叉" in signals or "RSI超卖" in signals:
            action = "关注买入"
        elif "均线多头" in signals:
            action = "持有"
        elif macd_state.startswith("死叉") and rsi > 60:
            action = "关注卖出"
        else:
            action = "观望"

        # 20日涨跌幅
        price_20ago = float(df.iloc[-20]["close_val"]) if len(df) >= 20 else close
        ret_20d = (close / price_20ago - 1) * 100

        meta = get_meta(code) or {}

        return {
            "code": code,
            "name": get_name(code) or code,
            "close": round(close, 2),
            "change_pct": round(change_pct, 2),
            "ret_20d": round(ret_20d, 2),
            "ma_state": ma_state,
            "macd_state": macd_state,
            "rsi": round(rsi, 1),
            "rsi_state": rsi_state,
            "bb_state": bb_state,
            "vol_ratio": round(vol_ratio, 2),
            "signals": signals,
            "action": action,
            "board": meta.get("board", ""),
            "level1": meta.get("level1", ""),
            "level2": meta.get("level2", ""),
        }
    except Exception:
        return None


def run_review(pool: str, date: str | None, save: bool) -> list[dict]:
    """运行关注池复盘."""
    wm = WatchlistManager()
    codes = wm.get_codes(pool)
    if not codes:
        print(f"[提示] 关注池 '{pool}' 为空")
        return []

    effective_date = date or datetime.now().strftime("%Y-%m-%d")

    print(f"\n[关注池复盘] 池: {pool} | 股票数: {len(codes)} | 日期: {effective_date}")
    print("数据加载中...")

    results = []
    with TdxQuery() as q:
        for i, code in enumerate(codes, 1):
            print(f"  ({i}/{len(codes)}) {code} ...", end="\r")
            r = _review_one(code, q, effective_date)
            if r:
                results.append(r)

    print(f"\n复盘完成: {len(results)}/{len(codes)} 只成功")
    return results


def _print_summary(results: list[dict], pool: str, date: str) -> None:
    if not results:
        return

    # 统计
    up = sum(1 for r in results if r["change_pct"] > 0)
    down = sum(1 for r in results if r["change_pct"] < 0)
    avg_change = sum(r["change_pct"] for r in results) / len(results)

    # 信号统计
    sig_count = {}
    for r in results:
        for s in r["signals"]:
            sig_count[s] = sig_count.get(s, 0) + 1

    print(f"\n{'=' * 100}")
    print(f"关注池每日复盘报告 — {pool} ({len(results)}只) — {date}")
    print(f"{'=' * 100}")
    print(f"今日涨跌: {up}涨 / {down}跌 / 平均 {avg_change:+.2f}%")
    if sig_count:
        sig_str = " | ".join([f"{k}:{v}" for k, v in sorted(sig_count.items(), key=lambda x: -x[1])])
        print(f"信号统计: {sig_str}")
    print("")

    header = (
        f"{'代码':<10}{'名称':<12}{'涨跌':<10}{'20日':<10}"
        f"{'MACD':<12}{'RSI':<8}{'均线':<10}{'布林带':<10}{'操作建议':<10}"
    )
    print(header)
    print("-" * 100)
    for r in results:
        change_str = f"{r['change_pct']:+.2f}%"
        ret_str = f"{r['ret_20d']:+.1f}%"
        print(
            f"{r['code']:<10}{r['name']:<12}{change_str:<10}{ret_str:<10}"
            f"{r['macd_state']:<12}{r['rsi']:<8.1f}{r['ma_state']:<10}"
            f"{r['bb_state']:<10}{r['action']:<10}"
        )
    print(f"{'=' * 100}\n")


def _save_report(results: list[dict], pool: str, date: str) -> str | None:
    if not results:
        return None

    rm = ReportManager()
    dir_path = rm.base / "watchlist" / date
    dir_path.mkdir(parents=True, exist_ok=True)

    up = sum(1 for r in results if r["change_pct"] > 0)
    down = sum(1 for r in results if r["change_pct"] < 0)
    avg_change = sum(r["change_pct"] for r in results) / len(results)

    lines = [
        f"# 关注池每日复盘报告 — {pool} — {date}",
        "",
        f"**股票数量**: {len(results)} 只",
        f"**今日涨跌**: {up}涨 / {down}跌 / 平均 {avg_change:+.2f}%",
        "",
        "| 代码 | 名称 | 板块 | 涨跌 | 20日收益 | MACD | RSI | 均线 | 布林带 | 操作建议 |",
        "|------|------|------|------|----------|------|-----|------|--------|----------|",
    ]
    for r in results:
        change_str = f"{r['change_pct']:+.2f}%"
        ret_str = f"{r['ret_20d']:+.1f}%"
        lines.append(
            f"| {r['code']} | {r['name']} | {r['board']} | {change_str} | {ret_str} | "
            f"{r['macd_state']} | {r['rsi']:.1f} | {r['ma_state']} | {r['bb_state']} | {r['action']} |"
        )
    lines.append("")
    lines.append("---")
    lines.append(f"*生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

    path = dir_path / f"{pool}_review.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def main():
    parser = argparse.ArgumentParser(description="关注池每日复盘")
    parser.add_argument("--pool", default="default", help="关注池名称")
    parser.add_argument("--date", help="复盘日期 YYYY-MM-DD")
    parser.add_argument("--save", action="store_true", help="保存报告")
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    results = run_review(args.pool, args.date, args.save)
    _print_summary(results, args.pool, date_str)

    if args.save and results:
        path = _save_report(results, args.pool, date_str)
        if path:
            print(f"[已保存报告] {path}")


if __name__ == "__main__":
    main()
