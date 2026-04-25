#!/usr/bin/env python3
"""红利ETF (515180) 长期跟踪策略 —— 核心仓位 + 动态网格

策略框架：
    1. 核心仓位 (60-80%): 长期持有，吃分红，只在极端高估/低估时调整
    2. 波段仓位 (20-40%): 动态网格，根据趋势状态调整网格密度和方向
    3. 趋势过滤: MA20 + MACD + ADX 判断趋势状态，避免单边卖飞或抄底过早
    4. 分红再投资: 模拟分红到账后自动复投
    5. 再平衡: 每周/月检查一次，输出操作建议

状态机：
    - STRONG_UP   (强趋势向上): 满仓持有，暂停卖出网格，只保留买入网格防回调
    - WEAK_UP     (弱趋势向上): 标准网格，正常高抛低吸
    - CONSOLIDATE (震荡):       加密网格，间距缩小至 ATR×0.6
    - WEAK_DOWN   (弱趋势向下): 加仓网格，间距扩大至 ATR×1.2，核心仓位不动
    - STRONG_DOWN (强趋势向下): 减仓至核心仓位，暂停买入网格

用法：
    python scripts/etf_longterm_tracker.py              # 默认 515180
    python scripts/etf_longterm_tracker.py --code 510880 --save
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
from tdx_core.indicators import bollinger, atr, rsi, macd


def calc_trend_state(df: pd.DataFrame) -> dict:
    """计算趋势状态，返回状态机和各维度评分"""
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last

    close = float(last["close_val"])
    ma20 = float(last["ma20"])
    ma60 = float(last["ma60"])
    macd_val = float(last["macd"])
    macd_signal = float(last["macd_signal"])
    macd_hist = float(last["macd_hist"])
    adx = float(last["adx"])
    plus_di = float(last["plus_di"])
    minus_di = float(last["minus_di"])
    rsi_val = float(last["rsi_14"])
    bb_pctb = float(last["bb_pctb"])
    atr_pct = float(last["atr_pct"])

    # ── 趋势维度评分 (0~10) ──
    # MA排列
    ma_bull = close > ma20 > ma60
    ma_bear = close < ma20 < ma60
    trend_score = 8.0 if ma_bull else (3.0 if ma_bear else 5.0)

    # MACD
    macd_bull = macd_val > macd_signal and macd_hist > float(prev.get("macd_hist", macd_hist))
    macd_bear = macd_val < macd_signal and macd_hist < float(prev.get("macd_hist", macd_hist))
    macd_score = 8.0 if macd_bull else (3.0 if macd_bear else 5.0)

    # ADX 趋势强度
    if adx > 30:
        adx_score = 8.0 if plus_di > minus_di else 2.0
    elif adx > 20:
        adx_score = 6.5 if plus_di > minus_di else 3.5
    else:
        adx_score = 5.0

    # ── 综合趋势评分 ──
    avg_trend = (trend_score + macd_score + adx_score) / 3

    # ── 动量评分 ──
    if rsi_val > 70:
        momentum_score = 8.0  # 超买但可能延续
    elif rsi_val > 55:
        momentum_score = 6.5
    elif rsi_val > 45:
        momentum_score = 5.0
    elif rsi_val > 30:
        momentum_score = 3.5
    else:
        momentum_score = 2.0  # 超卖

    # ── 波动评分 ──
    vol_pct = calc_vol_percentile(df["atr_14"], window=60)
    if np.isnan(vol_pct):
        vol_score = 5.0
    else:
        # 波动越低越适合网格，分数越高
        vol_score = (1.0 - vol_pct) * 10.0

    # ── 状态机判定 ──
    if avg_trend >= 7.0 and momentum_score >= 6.0:
        state = "STRONG_UP"
        state_zh = "强趋势向上"
        core_pct = 0.80
        grid_pct = 0.20
        grid_dir = "buy_only"   # 只买不卖，防卖飞
        step_mult = 1.0
    elif avg_trend >= 6.0:
        state = "WEAK_UP"
        state_zh = "弱趋势向上"
        core_pct = 0.70
        grid_pct = 0.30
        grid_dir = "both"
        step_mult = 0.9
    elif avg_trend >= 4.5 and vol_score >= 6.0:
        state = "CONSOLIDATE"
        state_zh = "震荡整理"
        core_pct = 0.60
        grid_pct = 0.40
        grid_dir = "both"
        step_mult = 0.6  # 加密网格
    elif avg_trend >= 3.5:
        state = "WEAK_DOWN"
        state_zh = "弱趋势向下"
        core_pct = 0.60
        grid_pct = 0.40
        grid_dir = "both"
        step_mult = 1.2  # 扩大间距，越跌越买
    else:
        state = "STRONG_DOWN"
        state_zh = "强趋势向下"
        core_pct = 0.50  # 最低核心仓位
        grid_pct = 0.50
        grid_dir = "sell_only"  # 暂停买入，只卖出
        step_mult = 1.5

    return {
        "state": state,
        "state_zh": state_zh,
        "trend_score": round(avg_trend, 2),
        "momentum_score": round(momentum_score, 2),
        "vol_score": round(vol_score, 2),
        "vol_pct": round(vol_pct * 100, 1) if not np.isnan(vol_pct) else None,
        "core_pct": core_pct,
        "grid_pct": grid_pct,
        "grid_dir": grid_dir,
        "step_mult": step_mult,
        "close": close,
        "ma20": ma20,
        "rsi": rsi_val,
        "bb_pctb": bb_pctb,
        "atr_pct": atr_pct,
    }


def calc_vol_percentile(atr_series: pd.Series, window: int = 60) -> float:
    """计算当前 ATR 在滚动窗口中的百分位 (0~1)"""
    if len(atr_series) < window + 1:
        return np.nan
    current = float(atr_series.iloc[-1])
    hist = atr_series.iloc[-window:-1].dropna().astype(float)
    if len(hist) == 0:
        return np.nan
    return (hist < current).sum() / len(hist)


def generate_dynamic_grid(center: float, atr_val: float, step_mult: float,
                          grid_count: int, grid_dir: str) -> dict:
    """根据趋势方向生成不对称或对称网格"""
    step = atr_val * step_mult
    result = {"center": round(center, 3), "step": round(step, 3)}

    if grid_dir == "buy_only":
        # 强趋势向上：只挂买入网格（回调接货），不挂卖出
        result["buy_levels"] = [round(center - i * step, 3) for i in range(1, grid_count + 1)]
        result["sell_levels"] = []
        result["note"] = "强趋势向上，暂停卖出网格，防止卖飞"
    elif grid_dir == "sell_only":
        # 强趋势向下：只挂卖出网格（止损/减仓），不挂买入
        result["buy_levels"] = []
        result["sell_levels"] = [round(center + i * step, 3) for i in range(1, grid_count + 1)]
        result["note"] = "强趋势向下，暂停买入网格，保留现金"
    else:
        # 正常双向网格
        result["buy_levels"] = [round(center - i * step, 3) for i in range(1, grid_count + 1)]
        result["sell_levels"] = [round(center + i * step, 3) for i in range(1, grid_count + 1)]
        result["note"] = "标准双向网格"

    return result


def backtest_core_grid(df: pd.DataFrame, core_pct: float, grid_buy: list,
                       grid_sell: list, grid_dir: str) -> dict:
    """回测核心+网格组合策略"""
    df = df.copy().reset_index(drop=True)
    total_equity = 1.0
    core_position = core_pct
    grid_position = 0.0
    cash = 1.0 - core_position
    trades = 0
    equity_curve = [1.0]
    max_equity = 1.0
    max_dd = 0.0

    for i in range(1, len(df)):
        price = float(df.loc[i, "close_val"])
        prev_price = float(df.loc[i - 1, "close_val"])

        if grid_dir in ("both", "buy_only"):
            for bl in sorted(grid_buy, reverse=True):
                if prev_price > bl >= price and cash >= 0.05:
                    buy_amount = 0.05
                    grid_position += buy_amount
                    cash -= buy_amount
                    trades += 1
                    break

        if grid_dir in ("both", "sell_only"):
            for sl in sorted(grid_sell):
                if prev_price < sl <= price and grid_position >= 0.05:
                    sell_amount = 0.05
                    grid_position -= sell_amount
                    cash += sell_amount
                    trades += 1
                    break

        eq = cash + core_position * (price / float(df.loc[0, "close_val"])) + grid_position * (price / float(df.loc[0, "close_val"]))
        equity_curve.append(eq)
        if eq > max_equity:
            max_equity = eq
        dd = (max_equity - eq) / max_equity
        if dd > max_dd:
            max_dd = dd

    total_ret = (equity_curve[-1] - 1.0) * 100
    return {
        "trades": trades,
        "total_return": total_ret,
        "max_drawdown": max_dd * 100,
        "final_equity": equity_curve[-1],
    }


def analyze(code: str, bars: int, grid_count: int, save: bool):
    name = get_name(code) or "未知"
    lines = []
    lines.append(f"红利ETF 长期跟踪策略报告")
    lines.append(f"标的: {code} ({name})")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 70)

    with TdxQuery() as q:
        df = q.get_daily(code)
        if df is None or df.empty:
            lines.append("[ERROR] 未获取到数据")
            return "\n".join(lines)

        df = df.sort_values("trade_date").reset_index(drop=True)
        calc_bars = bars + 80
        df = df.iloc[-calc_bars:].copy()

        # 类型转换
        for col in ["open_val", "high_val", "low_val", "close_val", "volume", "amount"]:
            if col in df.columns:
                df[col] = df[col].astype(float)

        # 计算指标
        df = bollinger(df, period=20, std_dev=2.0)
        df = atr(df, period=14)
        df = rsi(df, period=14)
        df = macd(df, fast=12, slow=26, signal=9)
        df["ma20"] = df["close_val"].rolling(window=20, min_periods=1).mean()
        df["ma60"] = df["close_val"].rolling(window=60, min_periods=1).mean()
        df["atr_pct"] = df["atr_14"] / df["close_val"] * 100

        # 简化 ADX（快速计算）
        from tdx_core.indicators._core import true_range
        tr = true_range(df["high_val"], df["low_val"], df["close_val"])
        atr_val = tr.ewm(alpha=1.0/14, adjust=False).mean()
        plus_dm = (df["high_val"] - df["high_val"].shift(1)).clip(lower=0)
        minus_dm = (df["low_val"].shift(1) - df["low_val"]).clip(lower=0)
        plus_dm = plus_dm.where(plus_dm > minus_dm, 0)
        minus_dm = minus_dm.where(minus_dm > plus_dm, 0)
        plus_di = 100 * plus_dm.ewm(alpha=1.0/14, adjust=False).mean() / atr_val
        minus_di = 100 * minus_dm.ewm(alpha=1.0/14, adjust=False).mean() / atr_val
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        df["adx"] = dx.ewm(alpha=1.0/14, adjust=False).mean()
        df["plus_di"] = plus_di
        df["minus_di"] = minus_di

        state = calc_trend_state(df)
        last = df.iloc[-1]

        # ── 状态概览 ──
        lines.append("\n【趋势状态机】")
        lines.append(f"  当前状态   : {state['state']} ({state['state_zh']})")
        lines.append(f"  趋势评分   : {state['trend_score']}/10")
        lines.append(f"  动量评分   : {state['momentum_score']}/10")
        lines.append(f"  波动评分   : {state['vol_score']}/10  (越高越适合网格)")
        if state["vol_pct"] is not None:
            lines.append(f"  ATR百分位  : {state['vol_pct']}%")

        # ── 仓位配置 ──
        lines.append("\n【仓位配置建议】")
        lines.append(f"  核心仓位   : {state['core_pct']*100:.0f}%  (长期持有，不动)")
        lines.append(f"  波段仓位   : {state['grid_pct']*100:.0f}%  (动态网格，高抛低吸)")
        lines.append(f"  现金预留   : {(1-state['core_pct']-state['grid_pct'])*100:.0f}%")
        lines.append(f"  网格方向   : {state['grid_dir']}")

        # ── 网格参数 ──
        grid = generate_dynamic_grid(
            center=state["ma20"],
            atr_val=float(last["atr_14"]),
            step_mult=state["step_mult"],
            grid_count=grid_count,
            grid_dir=state["grid_dir"],
        )

        lines.append("\n【动态网格参数】")
        lines.append(f"  网格中枢   : {grid['center']}")
        lines.append(f"  网格间距   : {grid['step']}  (ATR × {state['step_mult']})")
        lines.append(f"  网格说明   : {grid['note']}")

        if grid["buy_levels"]:
            lines.append("")
            lines.append("  买入网格 (逢低加仓):")
            for i, p in enumerate(grid["buy_levels"], 1):
                dist = (p - state["close"]) / state["close"] * 100
                lines.append(f"    L{i}: {p:.3f}  (距现价 {dist:+.2f}%)")

        if grid["sell_levels"]:
            lines.append("")
            lines.append("  卖出网格 (逢高减仓):")
            for i, p in enumerate(grid["sell_levels"], 1):
                dist = (p - state["close"]) / state["close"] * 100
                lines.append(f"    L{i}: {p:.3f}  (距现价 {dist:+.2f}%)")

        # ── 当前位置评估 ──
        lines.append("\n【当前位置评估】")
        lines.append(f"  收盘价     : {state['close']:.3f}")
        lines.append(f"  20日均线   : {state['ma20']:.3f}  (偏离 {((state['close']/state['ma20'])-1)*100:+.2f}%)")
        lines.append(f"  RSI(14)    : {state['rsi']:.1f}")
        lines.append(f"  布林带%B   : {state['bb_pctb']:.3f}")
        lines.append(f"  ATR(14)    : {state['atr_pct']:.2f}%")

        if state["bb_pctb"] > 0.8:
            pos_comment = "价格偏贵，不宜追高，等回调至买入网格再建仓"
        elif state["bb_pctb"] < 0.2:
            pos_comment = "价格偏低，可积极建仓或加仓"
        else:
            pos_comment = "价格中枢附近，按网格正常执行"
        lines.append(f"  位置评估   : {pos_comment}")

        # ── 回测 ──
        lines.append("\n【策略回测 (近 {} 日)】".format(bars))
        bt = backtest_core_grid(
            df.iloc[-bars:].copy(),
            core_pct=state["core_pct"],
            grid_buy=grid["buy_levels"],
            grid_sell=grid["sell_levels"],
            grid_dir=state["grid_dir"],
        )
        lines.append(f"  交易次数   : {bt['trades']}")
        lines.append(f"  累计收益   : {bt['total_return']:.2f}%")
        lines.append(f"  最大回撤   : {bt['max_drawdown']:.2f}%")
        lines.append(f"  期末净值   : {bt['final_equity']:.4f}")

        # ── 操作建议 ──
        lines.append("\n【本周/今日操作建议】")
        if state["state"] == "STRONG_UP":
            lines.append("  1. 保持核心仓位不动，享受趋势收益")
            lines.append("  2. 波段仓位只挂买入网格，不卖出（防卖飞）")
            lines.append("  3. 若价格跌破 MA20，考虑将部分波段仓位转为核心仓位")
        elif state["state"] == "WEAK_UP":
            lines.append("  1. 核心仓位持有，波段仓位正常高抛低吸")
            lines.append("  2. 关注 MACD 是否走弱，若死叉考虑收紧卖出网格")
        elif state["state"] == "CONSOLIDATE":
            lines.append("  1. 这是网格最佳环境，加密网格间距，提高交易频率")
            lines.append("  2. 核心仓位不变，波段仓位可提升至 40%")
            lines.append("  3. 关注突破方向，向上破轨追趋势，向下破轨等企稳")
        elif state["state"] == "WEAK_DOWN":
            lines.append("  1. 核心仓位不动，波段仓位扩大网格间距（越跌越买）")
            lines.append("  2. 每跌一个网格间距加仓一次，不要一次性加满")
            lines.append("  3. 若 ADX 继续上升且 -DI 主导，暂停买入等待企稳")
        else:  # STRONG_DOWN
            lines.append("  1. 减仓至最低核心仓位（50%），保留现金")
            lines.append("  2. 暂停买入网格，若有波段仓位逢反弹减仓")
            lines.append("  3. 等待ADX下降或MACD金叉后再恢复买入")

        lines.append("\n【长期跟踪要点】")
        lines.append("  - 每周运行一次本脚本，检查趋势状态是否切换")
        lines.append("  - 红利ETF分红季（通常6-8月、11-12月）前后波动加大，可适当收紧网格")
        lines.append("  - 最大单股持仓不超过总资产的20%（即使是核心仓位）")
        lines.append("  - 设置绝对止损：若价格跌破250日均线且ADX>30，核心仓位减半")

    text = "\n".join(lines)
    print(text)

    if save:
        out_dir = Path(ROOT) / "logs"
        out_dir.mkdir(exist_ok=True)
        fname = f"tracker_{code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        out_path = out_dir / fname
        out_path.write_text(text, encoding="utf-8")
        print(f"\n[Saved] {out_path}")

    return text


def main():
    parser = argparse.ArgumentParser(description="ETF Long-term Tracker")
    parser.add_argument("--code", default="515180", help="ETF code (default: 515180)")
    parser.add_argument("--bars", type=int, default=120, help="Lookback bars (default: 120)")
    parser.add_argument("--grid", type=int, default=3, help="Grid layers (default: 3)")
    parser.add_argument("--save", action="store_true", help="Save report")
    args = parser.parse_args()

    analyze(args.code, args.bars, args.grid, args.save)


if __name__ == "__main__":
    main()
