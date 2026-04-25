#!/usr/bin/env python3
"""Generate strategy JSON files for 515180 (and reusable for other ETFs).

Usage:
    python scripts/generate_strategies.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Base config shared by all ETF strategies
ETF_BASE = {
    "universe": {"codes": "515180", "min_price": 0.1, "max_price": 10000, "exclude_st": False},
    "lookback": 120,
    "initial_capital": 1_000_000,
    "position": {"max_holding": 1, "per_position": 1.0, "weight_by": "equal"},
    "rebalance": {"frequency": "daily"},
    "costs": {
        "commission_buy": 0.00025,
        "commission_sell": 0.00025,
        "tax_sell": 0.0,  # ETF 免印花税
        "slippage": 0.0001,
    },
}

STRATEGIES = [
    # ── 流派1: 均线趋势跟踪 ──
    {
        "id": "ma5_20_trend",
        "name": "MA5/20 趋势跟踪",
        "description": "MA5 上穿 MA20 买入，下穿卖出",
        "entry": [{"indicator": "ma_5", "op": ">", "value": "ma_20"}],
        "exit": [{"indicator": "ma_5", "op": "<", "value": "ma_20"}],
        "stop_loss": -0.08,
        "max_hold_days": 60,
    },
    {
        "id": "ma20_60_trend",
        "name": "MA20/60 趋势跟踪",
        "description": "MA20 上穿 MA60 买入，下穿卖出",
        "entry": [{"indicator": "ma_20", "op": ">", "value": "ma_60"}],
        "exit": [{"indicator": "ma_20", "op": "<", "value": "ma_60"}],
        "stop_loss": -0.08,
        "max_hold_days": 60,
    },
    {
        "id": "ma60_120_trend",
        "name": "MA60/120 趋势跟踪",
        "description": "MA60 上穿 MA120 买入，下穿卖出（长线）",
        "entry": [{"indicator": "ma_60", "op": ">", "value": "ma_120"}],
        "exit": [{"indicator": "ma_60", "op": "<", "value": "ma_120"}],
        "stop_loss": -0.10,
        "max_hold_days": 90,
    },
    {
        "id": "ema12_26_trend",
        "name": "EMA12/26 趋势跟踪",
        "description": "EMA12 上穿 EMA26 买入，下穿卖出",
        "entry": [{"indicator": "ema_12", "op": ">", "value": "ema_26"}],
        "exit": [{"indicator": "ema_12", "op": "<", "value": "ema_26"}],
        "stop_loss": -0.08,
        "max_hold_days": 60,
    },
    {
        "id": "price_above_ma20",
        "name": "价格突破 MA20",
        "description": "收盘价站上 MA20 买入，跌破卖出",
        "entry": [{"indicator": "close_val", "op": ">", "value": "ma_20"}],
        "exit": [{"indicator": "close_val", "op": "<", "value": "ma_20"}],
        "stop_loss": -0.05,
        "max_hold_days": 40,
    },
    # ── 流派2: MACD 动量 ──
    {
        "id": "macd_golden",
        "name": "MACD 金叉策略",
        "description": "MACD 金叉买入，死叉卖出",
        "entry": [{"indicator": "macd", "signal": "golden_cross"}],
        "exit": [{"indicator": "macd", "signal": "death_cross"}],
        "stop_loss": -0.08,
        "take_profit": 0.20,
        "max_hold_days": 60,
    },
    {
        "id": "macd_hist_turn",
        "name": "MACD 柱转正",
        "description": "MACD 柱状图由负转正买入，转负卖出",
        "entry": [{"indicator": "macd_hist", "op": ">", "value": 0}],
        "exit": [{"indicator": "macd_hist", "op": "<", "value": 0}],
        "stop_loss": -0.08,
        "take_profit": 0.15,
        "max_hold_days": 40,
    },
    {
        "id": "macd_rsi_combo",
        "name": "MACD+RSI 复合",
        "description": "MACD 金叉且 RSI<65 买入，MACD 死叉或 RSI>80 卖出",
        "entry": [
            {"indicator": "macd", "signal": "golden_cross"},
            {"indicator": "rsi", "op": "<", "value": 65},
        ],
        "exit": [
            {"indicator": "macd", "signal": "death_cross"},
            {"indicator": "rsi", "op": ">", "value": 80},
        ],
        "stop_loss": -0.08,
        "take_profit": 0.20,
        "max_hold_days": 60,
    },
    # ── 流派3: RSI 均值回归 ──
    {
        "id": "rsi30_bounce",
        "name": "RSI30 反弹",
        "description": "RSI<30 超卖买入，RSI>70 卖出",
        "entry": [{"indicator": "rsi", "op": "<", "value": 30}],
        "exit": [{"indicator": "rsi", "op": ">", "value": 70}],
        "stop_loss": -0.05,
        "take_profit": 0.15,
        "max_hold_days": 40,
    },
    {
        "id": "rsi35_bounce",
        "name": "RSI35 反弹",
        "description": "RSI<35 超卖买入，RSI>65 卖出",
        "entry": [{"indicator": "rsi", "op": "<", "value": 35}],
        "exit": [{"indicator": "rsi", "op": ">", "value": 65}],
        "stop_loss": -0.05,
        "take_profit": 0.12,
        "max_hold_days": 40,
    },
    {
        "id": "rsi40_bounce",
        "name": "RSI40 反弹",
        "description": "RSI<40 买入，RSI>60 卖出",
        "entry": [{"indicator": "rsi", "op": "<", "value": 40}],
        "exit": [{"indicator": "rsi", "op": ">", "value": 60}],
        "stop_loss": -0.05,
        "take_profit": 0.10,
        "max_hold_days": 30,
    },
    {
        "id": "rsi_williams_combo",
        "name": "RSI+威廉 复合",
        "description": "RSI<35 且威廉指标<-80 买入，RSI>65 或威廉>-20 卖出",
        "entry": [
            {"indicator": "rsi", "op": "<", "value": 35},
            {"indicator": "williams_r", "op": "<", "value": -80},
        ],
        "exit": [
            {"indicator": "rsi", "op": ">", "value": 65},
            {"indicator": "williams_r", "op": ">", "value": -20},
        ],
        "stop_loss": -0.05,
        "take_profit": 0.12,
        "max_hold_days": 40,
    },
    # ── 流派4: 布林带 ──
    {
        "id": "bb_lower_bounce",
        "name": "布林带下轨反弹",
        "description": "BB%<0.1 买入，BB%>0.9 卖出",
        "entry": [{"indicator": "bb_pctb", "op": "<", "value": 0.1}],
        "exit": [{"indicator": "bb_pctb", "op": ">", "value": 0.9}],
        "stop_loss": -0.05,
        "take_profit": 0.12,
        "max_hold_days": 40,
    },
    {
        "id": "bb_mean_reversion",
        "name": "布林带均值回归",
        "description": "价格跌破下轨买入，突破上轨卖出",
        "entry": [{"indicator": "close_val", "op": "<", "value": "bb_lower"}],
        "exit": [{"indicator": "close_val", "op": ">", "value": "bb_upper"}],
        "stop_loss": -0.05,
        "take_profit": 0.10,
        "max_hold_days": 30,
    },
    {
        "id": "bb_rsi_combo",
        "name": "布林带+RSI 复合",
        "description": "BB%<0.1 且 RSI<40 买入，BB%>0.8 或 RSI>70 卖出",
        "entry": [
            {"indicator": "bb_pctb", "op": "<", "value": 0.1},
            {"indicator": "rsi", "op": "<", "value": 40},
        ],
        "exit": [
            {"indicator": "bb_pctb", "op": ">", "value": 0.8},
            {"indicator": "rsi", "op": ">", "value": 70},
        ],
        "stop_loss": -0.05,
        "take_profit": 0.12,
        "max_hold_days": 40,
    },
    # ── 流派5: 动量 ──
    {
        "id": "roc_positive",
        "name": "ROC 正向",
        "description": "ROC>0 买入，ROC<0 卖出",
        "entry": [{"indicator": "roc", "op": ">", "value": 0}],
        "exit": [{"indicator": "roc", "op": "<", "value": 0}],
        "stop_loss": -0.05,
        "max_hold_days": 40,
    },
    {
        "id": "momentum_positive",
        "name": "动量正向",
        "description": "Momentum>0 买入，<0 卖出",
        "entry": [{"indicator": "momentum", "op": ">", "value": 0}],
        "exit": [{"indicator": "momentum", "op": "<", "value": 0}],
        "stop_loss": -0.05,
        "max_hold_days": 40,
    },
    {
        "id": "adx_trend_follow",
        "name": "ADX 趋势跟踪",
        "description": "ADX>25 且价格>MA20 买入，ADX<20 或价格<MA20 卖出",
        "entry": [
            {"indicator": "adx", "op": ">", "value": 25},
            {"indicator": "close_val", "op": ">", "value": "ma_20"},
        ],
        "exit": [
            {"indicator": "adx", "op": "<", "value": 20},
            {"indicator": "close_val", "op": "<", "value": "ma_20"},
        ],
        "stop_loss": -0.08,
        "max_hold_days": 60,
    },
    # ── 流派6: 多指标复合 ──
    {
        "id": "ma_rsi_combo",
        "name": "MA+RSI 复合",
        "description": "MA20>MA60 且 RSI<60 买入，MA20<MA60 或 RSI>75 卖出",
        "entry": [
            {"indicator": "ma_20", "op": ">", "value": "ma_60"},
            {"indicator": "rsi", "op": "<", "value": 60},
        ],
        "exit": [
            {"indicator": "ma_20", "op": "<", "value": "ma_60"},
            {"indicator": "rsi", "op": ">", "value": 75},
        ],
        "stop_loss": -0.08,
        "max_hold_days": 60,
    },
    {
        "id": "triple_filter",
        "name": "三指标过滤",
        "description": "价格>MA20 + RSI>50 + MACD>0 买入，价格<MA20 或 RSI>80 卖出",
        "entry": [
            {"indicator": "close_val", "op": ">", "value": "ma_20"},
            {"indicator": "rsi", "op": ">", "value": 50},
            {"indicator": "macd", "op": ">", "value": 0},
        ],
        "exit": [
            {"indicator": "close_val", "op": "<", "value": "ma_20"},
            {"indicator": "rsi", "op": ">", "value": 80},
        ],
        "stop_loss": -0.08,
        "max_hold_days": 60,
    },
    {
        "id": "supertrend_follow",
        "name": "超级趋势跟踪",
        "description": "SuperTrend 多头买入，空头卖出",
        "entry": [{"indicator": "supertrend", "signal": "buy"}],
        "exit": [{"indicator": "supertrend", "signal": "sell"}],
        "stop_loss": -0.08,
        "max_hold_days": 60,
    },
    {
        "id": "sar_follow",
        "name": "SAR 抛物线",
        "description": "SAR 多头买入，空头卖出",
        "entry": [{"indicator": "sar", "signal": "buy"}],
        "exit": [{"indicator": "sar", "signal": "sell"}],
        "stop_loss": -0.08,
        "max_hold_days": 60,
    },
    # ── 流派7: 基准 ──
    {
        "id": "buy_and_hold",
        "name": "买入并持有",
        "description": "首日买入后一直持有，不择时",
        "entry": [],  # 空条件表示首日买入
        "exit": [{"indicator": "rsi", "op": "<", "value": -999}],  # 永不可能触发
        "stop_loss": None,
        "take_profit": None,
        "max_hold_days": None,
    },
    {
        "id": "trailing_stop_trend",
        "name": "移动止损趋势",
        "description": "MA20>MA60 买入，8%回撤移动止损卖出",
        "entry": [{"indicator": "ma_20", "op": ">", "value": "ma_60"}],
        "exit": [],
        "stop_loss": None,
        "take_profit": None,
        "max_hold_days": None,
        "trailing_stop": 0.08,
    },
]


def build_config(s: dict) -> dict:
    """Build a full strategy config dict from a strategy definition."""
    cfg = {
        "name": s["name"],
        "description": s["description"],
        **ETF_BASE,
        "entry": {"conditions": s["entry"]},
        "exit": {
            "conditions": s["exit"],
            "stop_loss": s.get("stop_loss"),
            "take_profit": s.get("take_profit"),
            "max_hold_days": s.get("max_hold_days"),
        },
    }
    if "trailing_stop" in s:
        cfg["exit"]["trailing_stop"] = s["trailing_stop"]
    return cfg


def main():
    out_dir = Path(ROOT) / "strategies"
    out_dir.mkdir(exist_ok=True)

    generated = []
    for s in STRATEGIES:
        cfg = build_config(s)
        path = out_dir / f"515180_{s['id']}.json"
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        generated.append(path.name)
        print(f"[已生成] {path.name}")

    print(f"\n共生成 {len(generated)} 个策略文件到 strategies/")


if __name__ == "__main__":
    main()
