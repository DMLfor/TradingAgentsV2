#!/usr/bin/env python3
"""红利ETF (515180) 波动率自适应网格策略

核心逻辑：
    1. 布林带(20,2) 确定价格通道与相对位置
    2. ATR(14) 衡量绝对波动，动态调整网格间距
    3. RSI(14) 过滤超买超卖信号
    4. 波动率百分位评估当前是否适合开网格

用法：
    python scripts/etf_volatility_strategy.py          # 默认分析 515180
    python scripts/etf_volatility_strategy.py --code 510880 --bars 120
    python scripts/etf_volatility_strategy.py --grid 3 --step 0.8 --save
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxQuery, get_name
from tdx_core.indicators import bollinger, atr, rsi


def calc_vol_percentile(atr_series: pd.Series, window: int = 60) -> float:
    """计算当前 ATR 在滚动窗口中的百分位 (0~1)"""
    if len(atr_series) < window:
        return np.nan
    current = atr_series.iloc[-1]
    hist = atr_series.iloc[-window:-1].dropna()
    if len(hist) == 0:
        return np.nan
    return (hist < current).sum() / len(hist)


def generate_grid(center: float, step: float, grid_count: int) -> dict:
    """生成对称网格价位"""
    buys = [round(center - i * step, 3) for i in range(1, grid_count + 1)]
    sells = [round(center + i * step, 3) for i in range(1, grid_count + 1)]
    return {
        "center": round(center, 3),
        "buy_levels": buys,
        "sell_levels": sells,
    }


def analyze_etf(code: str, bars: int, grid_count: int, step_mult: float,
                rsi_buy_th: float, rsi_sell_th: float, save: bool):
    name = get_name(code) or "未知"
    lines = []
    lines.append(f"红利ETF 波动策略报告")
    lines.append(f"代码: {code}  ({name})")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 70)

    with TdxQuery() as q:
        df = q.get_daily(code)
        if df is None or df.empty:
            lines.append("[ERROR] 未获取到数据")
            return "\n".join(lines)

        # 保留最近 bars+60 条用于指标计算
        df = df.sort_values("trade_date").reset_index(drop=True)
        calc_bars = bars + 60
        df = df.iloc[-calc_bars:].copy()

        # 确保数值列为 float（数据库可能返回 Decimal）
        for col in ["open_val", "high_val", "low_val", "close_val", "volume", "amount"]:
            if col in df.columns:
                df[col] = df[col].astype(float)

        # 计算指标
        df = bollinger(df, period=20, std_dev=2.0)
        df = atr(df, period=14)
        df = rsi(df, period=14)
        df["ma20"] = df["close_val"].rolling(window=20, min_periods=1).mean()
        df["atr_pct"] = df["atr_14"] / df["close_val"] * 100

        # 取最新一条
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else last

        close = float(last["close_val"])
        bb_upper = float(last["bb_upper"])
        bb_middle = float(last["bb_middle"])
        bb_lower = float(last["bb_lower"])
        bb_pctb = float(last["bb_pctb"])
        bb_width = float(last["bb_bandwidth"])
        atr_val = float(last["atr_14"])
        atr_pct = float(last["atr_pct"])
        rsi_val = float(last["rsi_14"])
        ma20 = float(last["ma20"])

        # 波动率百分位
        vol_pct = calc_vol_percentile(df["atr_14"], window=60)

        # ── 价格状态 ──
        lines.append("\n【价格状态】")
        lines.append(f"  最新收盘价 : {close:.3f}")
        lines.append(f"  20日均线   : {ma20:.3f}")
        lines.append(f"  布林上轨   : {bb_upper:.3f}")
        lines.append(f"  布林中轨   : {bb_middle:.3f}")
        lines.append(f"  布林下轨   : {bb_lower:.3f}")
        lines.append(f"  %B 位置    : {bb_pctb:.3f}  (0=下轨, 1=上轨)")
        lines.append(f"  带宽       : {bb_width*100:.2f}%")

        # ── 波动率评估 ──
        lines.append("\n【波动率评估】")
        lines.append(f"  ATR(14)    : {atr_val:.3f}  ({atr_pct:.2f}%)")
        if not np.isnan(vol_pct):
            lines.append(f"  ATR 百分位 : {vol_pct*100:.1f}%  (近60日)")
            if vol_pct < 0.3:
                vol_comment = "低波动 → 适合开网格"
            elif vol_pct > 0.7:
                vol_comment = "高波动 → 网格易被突破，谨慎"
            else:
                vol_comment = "中等波动 → 可开网格，注意止损"
            lines.append(f"  评估       : {vol_comment}")
        else:
            lines.append("  ATR 百分位 : 数据不足")

        # ── 动量过滤 ──
        lines.append("\n【动量过滤】")
        lines.append(f"  RSI(14)    : {rsi_val:.1f}")
        if rsi_val < rsi_buy_th:
            rsi_comment = "超卖区间 → 倾向买入"
        elif rsi_val > rsi_sell_th:
            rsi_comment = "超买区间 → 倾向卖出/减仓"
        else:
            rsi_comment = "中性区间 → 按网格执行"
        lines.append(f"  评估       : {rsi_comment}")

        # ── 策略信号 ──
        lines.append("\n【策略信号】")
        signal = "观望"
        if close <= bb_lower and rsi_val < rsi_buy_th:
            signal = "[BUY] 买入信号 (触及下轨+RSI超卖)"
        elif close >= bb_upper and rsi_val > rsi_sell_th:
            signal = "[SELL] 卖出信号 (触及上轨+RSI超买)"
        elif close < bb_middle and rsi_val < 45:
            signal = "[WATCH] 偏空观望 (价格在中轨下方)"
        elif close > bb_middle and rsi_val > 55:
            signal = "[WATCH] 偏多观望 (价格在中轨上方)"
        else:
            signal = "[NEUTRAL] 中性观望"
        lines.append(f"  综合信号   : {signal}")

        # ── 网格参数 ──
        grid_step = atr_val * step_mult
        grid = generate_grid(ma20, grid_step, grid_count)

        lines.append("\n【网格交易建议】")
        lines.append(f"  网格中枢   : {grid['center']}")
        lines.append(f"  网格间距   : {round(grid_step, 3)}  (ATR × {step_mult})")
        lines.append(f"  网格层数   : {grid_count}")
        lines.append("")
        lines.append("  买入网格 (逢低分批建仓):")
        for i, p in enumerate(grid["buy_levels"], 1):
            dist = (p - close) / close * 100
            lines.append(f"    L{i}: {p:.3f}  (距现价 {dist:+.2f}%)")
        lines.append("")
        lines.append("  卖出网格 (逢高分批减仓):")
        for i, p in enumerate(grid["sell_levels"], 1):
            dist = (p - close) / close * 100
            lines.append(f"    L{i}: {p:.3f}  (距现价 {dist:+.2f}%)")

        # ── 近期触发统计 ──
        lines.append("\n【近 {} 日触发统计】".format(bars))
        touch_lower = (df["close_val"] <= df["bb_lower"]).sum()
        touch_upper = (df["close_val"] >= df["bb_upper"]).sum()
        touch_mid_below = (df["close_val"] < df["bb_middle"]).sum()
        touch_mid_above = (df["close_val"] > df["bb_middle"]).sum()
        lines.append(f"  触及下轨次数 : {touch_lower}")
        lines.append(f"  触及上轨次数 : {touch_upper}")
        lines.append(f"  中轨下方天数 : {touch_mid_below} ({touch_mid_below/len(df)*100:.1f}%)")
        lines.append(f"  中轨上方天数 : {touch_mid_above} ({touch_mid_above/len(df)*100:.1f}%)")

        # ── 回测简单网格 ──
        lines.append("\n【简单网格回测 (近 {} 日)】".format(bars))
        bt_result = backtest_grid(df, grid["buy_levels"], grid["sell_levels"])
        lines.append(f"  总交易次数   : {bt_result['trades']}")
        lines.append(f"  胜率         : {bt_result['win_rate']:.1f}%")
        lines.append(f"  累计收益率   : {bt_result['total_return']:.2f}%")
        lines.append(f"  最大回撤     : {bt_result['max_drawdown']:.2f}%")

    text = "\n".join(lines)
    print(text)

    if save:
        out_dir = Path(ROOT) / "logs"
        out_dir.mkdir(exist_ok=True)
        fname = f"etf_grid_{code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        out_path = out_dir / fname
        out_path.write_text(text, encoding="utf-8")
        print(f"\n[Saved] {out_path}")

    return text


def backtest_grid(df: pd.DataFrame, buy_levels: list, sell_levels: list,
                  initial_pos: float = 0.5) -> dict:
    """极简网格回测：持半仓起步，触碰买入线加仓，触碰卖出线减仓"""
    df = df.copy().reset_index(drop=True)
    position = initial_pos  # 0~1
    cash = 1.0 - position
    trades = 0
    wins = 0
    equity = [1.0]
    max_equity = 1.0
    max_dd = 0.0
    buy_levels = sorted(buy_levels, reverse=True)  # 高到低
    sell_levels = sorted(sell_levels)              # 低到高

    for i in range(1, len(df)):
        price = float(df.loc[i, "close_val"])
        prev_price = float(df.loc[i - 1, "close_val"])

        # 买入触发：价格下穿买入线
        for bl in buy_levels:
            if prev_price > bl >= price and cash >= 0.1:
                invest = 0.1
                position += invest
                cash -= invest
                trades += 1
                break

        # 卖出触发：价格上穿卖出线
        for sl in sell_levels:
            if prev_price < sl <= price and position >= 0.1:
                sell = 0.1
                position -= sell
                cash += sell
                trades += 1
                wins += 1  # 简化：每次卖出都记为盈利（网格卖出总在买入之上）
                break

        # 每日估值
        eq = cash + position
        equity.append(eq)
        if eq > max_equity:
            max_equity = eq
        dd = (max_equity - eq) / max_equity
        if dd > max_dd:
            max_dd = dd

    total_ret = (equity[-1] - 1.0) * 100
    win_rate = (wins / trades * 100) if trades > 0 else 0
    return {
        "trades": trades,
        "win_rate": win_rate,
        "total_return": total_ret,
        "max_drawdown": max_dd * 100,
    }


def main():
    parser = argparse.ArgumentParser(description="ETF Volatility Grid Strategy")
    parser.add_argument("--code", default="515180", help="ETF code (default: 515180)")
    parser.add_argument("--bars", type=int, default=120, help="Analysis bars (default: 120)")
    parser.add_argument("--grid", type=int, default=3, help="Grid layers per side (default: 3)")
    parser.add_argument("--step", type=float, default=0.8, help="Grid step = ATR * step (default: 0.8)")
    parser.add_argument("--rsi-buy", type=float, default=35.0, help="RSI oversold threshold (default: 35)")
    parser.add_argument("--rsi-sell", type=float, default=65.0, help="RSI overbought threshold (default: 65)")
    parser.add_argument("--save", action="store_true", help="Save report to logs/")
    args = parser.parse_args()

    analyze_etf(
        code=args.code,
        bars=args.bars,
        grid_count=args.grid,
        step_mult=args.step,
        rsi_buy_th=args.rsi_buy,
        rsi_sell_th=args.rsi_sell,
        save=args.save,
    )


if __name__ == "__main__":
    main()
