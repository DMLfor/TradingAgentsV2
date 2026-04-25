#!/usr/bin/env python3
"""Technical Analysis Master Panel — 全量指标深度解析.

Usage:
    python scripts/technical_master.py 688018
    python scripts/technical_master.py 688018 --bars 120
    python scripts/technical_master.py 688018 --save
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Force UTF-8 output on Windows to avoid UnicodeEncodeError with box-drawing chars
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tdx_core import TdxIndicators, TdxQuery, resolve_code, get_name

# ─── 指标元数据：技术分析大师视角的优先级与解读规则 ────────────────────────────

INDICATOR_LAYERS = [
    {
        "title": "一、趋势结构层 (Trend Architecture)",
        "desc": "判断市场方向、趋势强度与结构完整性",
        "indicators": [
            {
                "key": "macd",
                "name": "MACD",
                "name_zh": "指数平滑异同平均线",
                "cols": [("macd", "DIF"), ("macd_signal", "DEA"), ("macd_hist", "HIST")],
                "format": "{macd:.4f}  {macd_signal:.4f}  {macd_hist:+.4f}",
                "state_fn": lambda r: (
                    "零轴上方·多头动能" if r["macd"] > 0 else "零轴下方·空头动能"
                ) + (
                    "·金叉维持" if r["macd"] > r["macd_signal"] else "·死叉维持"
                ) + (
                    "·HIST扩张" if abs(r["macd_hist"]) > abs(r["macd_hist_shift1"]) * 0.9 else "·HIST收缩"
                ),
                "priority": 1,
            },
            {
                "key": "supertrend",
                "name": "Supertrend",
                "name_zh": "超级趋势",
                "cols": [("supertrend", "ST线"), ("supertrend_direction", "方向")],
                "format": "{supertrend:.2f}  {direction}",
                "state_fn": lambda r: (
                    "价格在ST之上·UP趋势" if r["supertrend_direction"] == -1 else "价格在ST之下·DOWN趋势"
                ),
                "priority": 2,
            },
            {
                "key": "adx",
                "name": "ADX",
                "name_zh": "平均趋向指数",
                "cols": [("adx", "ADX"), ("plus_di", "+DI"), ("minus_di", "-DI")],
                "format": "{adx:.2f}  +DI:{plus_di:.2f}  -DI:{minus_di:.2f}",
                "state_fn": lambda r: (
                    ("强趋势(" + ("买方主导" if r["plus_di"] > r["minus_di"] else "卖方主导") + ")")
                    if r["adx"] > 25 else ("弱趋势/震荡(" + ("买方略强" if r["plus_di"] > r["minus_di"] else "卖方略强") + ")")
                ),
                "priority": 3,
            },
            {
                "key": "ichimoku",
                "name": "Ichimoku",
                "name_zh": "一目均衡表",
                "cols": [("tenkan_sen", "转换"), ("kijun_sen", "基准"), ("senkou_span_a", "云A"), ("senkou_span_b", "云B")],
                "format": "转:{tenkan_sen:.2f} 基:{kijun_sen:.2f} 云A:{senkou_span_a:.2f} 云B:{senkou_span_b:.2f}",
                "state_fn": lambda r: (
                    "价格在云上方·强多头" if r["close_val"] > max(r["senkou_span_a"], r["senkou_span_b"]) else
                    "价格在云下方·强空头" if r["close_val"] < min(r["senkou_span_a"], r["senkou_span_b"]) else
                    "价格在云中·震荡/转折"
                ),
                "priority": 4,
            },
            {
                "key": "ma",
                "name": "MA",
                "name_zh": "均线系统",
                "cols": [("ma_5", "MA5"), ("ma_10", "MA10"), ("ma_20", "MA20"), ("ma_60", "MA60"), ("ma_120", "MA120"), ("ma_250", "MA250")],
                "format": "MA5:{ma_5:.2f} MA10:{ma_10:.2f} MA20:{ma_20:.2f} MA60:{ma_60:.2f} MA120:{ma_120:.2f} MA250:{ma_250:.2f}",
                "state_fn": lambda r: _ma_state(r),
                "priority": 5,
            },
            {
                "key": "ema",
                "name": "EMA",
                "name_zh": "指数移动平均线",
                "cols": [("ema_12", "EMA12"), ("ema_26", "EMA26")],
                "format": "EMA12:{ema_12:.2f}  EMA26:{ema_26:.2f}",
                "state_fn": lambda r: (
                    "EMA12>EMA26·金叉维持" if r["ema_12"] > r["ema_26"] else "EMA12<EMA26·死叉维持"
                ),
                "priority": 6,
            },
            {
                "key": "sar",
                "name": "SAR",
                "name_zh": "抛物线转向",
                "cols": [("sar", "SAR")],
                "format": "SAR:{sar:.2f}",
                "state_fn": lambda r: (
                    "价格在SAR之上·多头" if r["close_val"] > r["sar"] else "价格在SAR之下·空头"
                ),
                "priority": 7,
            },
            {
                "key": "trix",
                "name": "TRIX",
                "name_zh": "三重指数平滑",
                "cols": [("trix", "TRIX")],
                "format": "TRIX:{trix:.4f}",
                "state_fn": lambda r: (
                    "正值·中期趋势向上" if r["trix"] > 0 else "负值·中期趋势向下"
                ),
                "priority": 8,
            },
            {
                "key": "aroon",
                "name": "Aroon",
                "name_zh": "阿隆指标",
                "cols": [("aroon_up", "Up"), ("aroon_down", "Down"), ("aroon_osc", "Osc")],
                "format": "Up:{aroon_up:.1f}  Down:{aroon_down:.1f}  Osc:{aroon_osc:.1f}",
                "state_fn": lambda r: (
                    "强势多头·接近高点" if r["aroon_up"] > 70 and r["aroon_down"] < 30 else
                    "强势空头·接近低点" if r["aroon_down"] > 70 and r["aroon_up"] < 30 else
                    "趋势转换中/震荡"
                ),
                "priority": 9,
            },
            {
                "key": "vortex",
                "name": "Vortex",
                "name_zh": "涡旋指标",
                "cols": [("vortex_pos", "VI+"), ("vortex_neg", "VI-")],
                "format": "VI+:{vortex_pos:.4f}  VI-:{vortex_neg:.4f}",
                "state_fn": lambda r: (
                    "上升动能占优" if r["vortex_pos"] > r["vortex_neg"] else "下降动能占优"
                ),
                "priority": 10,
            },
        ],
    },
    {
        "title": "二、动量与时机层 (Momentum & Timing)",
        "desc": "判断超买超卖、入场时机与动能衰竭",
        "indicators": [
            {
                "key": "rsi",
                "name": "RSI",
                "name_zh": "相对强弱指标(14日)",
                "cols": [("rsi_14", "RSI")],
                "format": "RSI:{rsi_14:.2f}",
                "state_fn": lambda r: _rsi_state(r["rsi_14"]),
                "priority": 11,
            },
            {
                "key": "stochastic",
                "name": "Stochastic",
                "name_zh": "随机指标",
                "cols": [("stoch_k", "%K"), ("stoch_d", "%D")],
                "format": "%K:{stoch_k:.2f}  %D:{stoch_d:.2f}",
                "state_fn": lambda r: (
                    ("超买区·" + ("死叉风险" if r["stoch_k"] < r["stoch_d"] else "维持强势")) if r["stoch_k"] > 80 else
                    ("超卖区·" + ("金叉机会" if r["stoch_k"] > r["stoch_d"] else "维持弱势")) if r["stoch_k"] < 20 else
                    ("中性区·" + ("%K>%D·偏多" if r["stoch_k"] > r["stoch_d"] else "%K<%D·偏空"))
                ),
                "priority": 12,
            },
            {
                "key": "stochrsi",
                "name": "StochRSI",
                "name_zh": "随机相对强弱",
                "cols": [("stochrsi_k", "K"), ("stochrsi_d", "D")],
                "format": "K:{stochrsi_k:.2f}  D:{stochrsi_d:.2f}",
                "state_fn": lambda r: (
                    ("超买·" + ("死叉" if r["stochrsi_k"] < r["stochrsi_d"] else "强势")) if r["stochrsi_k"] > 80 else
                    ("超卖·" + ("金叉" if r["stochrsi_k"] > r["stochrsi_d"] else "弱势")) if r["stochrsi_k"] < 20 else
                    "中性"
                ),
                "priority": 13,
            },
            {
                "key": "cci",
                "name": "CCI",
                "name_zh": "商品通道指数(20日)",
                "cols": [("cci_20", "CCI")],
                "format": "CCI:{cci_20:.2f}",
                "state_fn": lambda r: (
                    "超买区(>+100)" if r["cci_20"] > 100 else
                    "超卖区(<-100)" if r["cci_20"] < -100 else
                    "中性区"
                ),
                "priority": 14,
            },
            {
                "key": "williams_r",
                "name": "Williams %R",
                "name_zh": "威廉指标(14日)",
                "cols": [("williams_r", "%R")],
                "format": "%R:{williams_r:.2f}",
                "state_fn": lambda r: (
                    "超买区(>-20)" if r["williams_r"] > -20 else
                    "超卖区(<-80)" if r["williams_r"] < -80 else
                    "中性区"
                ),
                "priority": 15,
            },
            {
                "key": "ultimate_oscillator",
                "name": "Ultimate Osc",
                "name_zh": "终极振荡器",
                "cols": [("ultimate_osc", "UO")],
                "format": "UO:{ultimate_osc:.2f}",
                "state_fn": lambda r: _rsi_state(r["ultimate_osc"]),  # 同RSI阈值
                "priority": 16,
            },
            {
                "key": "awesome_oscillator",
                "name": "Awesome Osc",
                "name_zh": "动量震荡指标",
                "cols": [("awesome_osc", "AO")],
                "format": "AO:{awesome_osc:.4f}",
                "state_fn": lambda r: (
                    "正值·多头动能" if r["awesome_osc"] > 0 else "负值·空头动能"
                ) + ("·增强中" if r["awesome_osc"] > r["awesome_osc_shift1"] else "·减弱中"),
                "priority": 17,
            },
            {
                "key": "roc",
                "name": "ROC",
                "name_zh": "变动率(12日)",
                "cols": [("roc_12", "ROC")],
                "format": "ROC:{roc_12:.2f}%",
                "state_fn": lambda r: (
                    "正动量" if r["roc_12"] > 0 else "负动量"
                ) + ("·加速" if abs(r["roc_12"]) > abs(r["roc_12_shift1"]) else "·减速"),
                "priority": 18,
            },
            {
                "key": "momentum",
                "name": "Momentum",
                "name_zh": "动量(10日)",
                "cols": [("momentum_10", "MOM")],
                "format": "MOM:{momentum_10:.2f}",
                "state_fn": lambda r: (
                    "正向动量" if r["momentum_10"] > 0 else "负向动量"
                ),
                "priority": 19,
            },
        ],
    },
    {
        "title": "三、波动率与价格结构层 (Volatility & Structure)",
        "desc": "衡量风险、支撑阻力与价格极端状态",
        "indicators": [
            {
                "key": "bollinger",
                "name": "Bollinger Bands",
                "name_zh": "布林带(20,2)",
                "cols": [("bb_upper", "上轨"), ("bb_middle", "中轨"), ("bb_lower", "下轨"), ("bb_pctb", "%B")],
                "format": "上:{bb_upper:.2f} 中:{bb_middle:.2f} 下:{bb_lower:.2f}  %B:{bb_pctb:.3f}",
                "state_fn": lambda r: (
                    "触及上轨·超买压力" if r["bb_pctb"] > 1.0 else
                    "触及下轨·超卖支撑" if r["bb_pctb"] < 0.0 else
                    ("强势区(>0.8)" if r["bb_pctb"] > 0.8 else
                     "弱势区(<0.2)" if r["bb_pctb"] < 0.2 else "中轨附近·震荡")
                ),
                "priority": 20,
            },
            {
                "key": "atr",
                "name": "ATR",
                "name_zh": "真实波幅(14日)",
                "cols": [("atr_14", "ATR")],
                "format": "ATR:{atr_14:.2f} ({atr_pct:.2f}%)",
                "state_fn": lambda r: (
                    "高波动" if r["atr_pct"] > 3.0 else "中等波动" if r["atr_pct"] > 1.5 else "低波动"
                ),
                "priority": 21,
            },
            {
                "key": "keltner",
                "name": "Keltner",
                "name_zh": "肯特纳通道",
                "cols": [("keltner_upper", "上轨"), ("keltner_middle", "中轨"), ("keltner_lower", "下轨")],
                "format": "上:{keltner_upper:.2f} 中:{keltner_middle:.2f} 下:{keltner_lower:.2f}",
                "state_fn": lambda r: (
                    "突破上轨·强势" if r["close_val"] > r["keltner_upper"] else
                    "跌破下轨·弱势" if r["close_val"] < r["keltner_lower"] else "通道内"
                ),
                "priority": 22,
            },
            {
                "key": "donchian",
                "name": "Donchian",
                "name_zh": "唐奇安通道(20日)",
                "cols": [("donchian_upper", "上轨"), ("donchian_middle", "中轨"), ("donchian_lower", "下轨")],
                "format": "上:{donchian_upper:.2f} 中:{donchian_middle:.2f} 下:{donchian_lower:.2f}",
                "state_fn": lambda r: (
                    "突破新高" if r["close_val"] >= r["donchian_upper"] else
                    "跌破新低" if r["close_val"] <= r["donchian_lower"] else "区间内"
                ),
                "priority": 23,
            },
            {
                "key": "std_dev",
                "name": "StdDev",
                "name_zh": "标准差(20日)",
                "cols": [("stddev_20", "StdDev")],
                "format": "StdDev:{stddev_20:.2f}",
                "state_fn": lambda r: (
                    "波动扩张" if r["stddev_20"] > r["stddev_20_shift5"] * 1.2 else
                    "波动收缩" if r["stddev_20"] < r["stddev_20_shift5"] * 0.8 else "波动正常"
                ),
                "priority": 24,
            },
            {
                "key": "chaikin_volatility",
                "name": "Chaikin Vol",
                "name_zh": "蔡金波动率",
                "cols": [("chaikin_vol", "CV")],
                "format": "CV:{chaikin_vol:.2f}",
                "state_fn": lambda r: (
                    "波动放大" if r["chaikin_vol"] > 0 else "波动收窄"
                ),
                "priority": 25,
            },
        ],
    },
    {
        "title": "四、量价确认层 (Volume Confirmation)",
        "desc": "通过成交量验证价格行为的可信度",
        "indicators": [
            {
                "key": "obv",
                "name": "OBV",
                "name_zh": "能量潮",
                "cols": [("obv", "OBV")],
                "format": "OBV:{obv:,.0f}",
                "state_fn": lambda r: (
                    "上升·量能配合价格" if r["obv"] > r["obv_shift1"] else "下降·量价背离风险"
                ),
                "priority": 26,
            },
            {
                "key": "mfi",
                "name": "MFI",
                "name_zh": "资金流量指数(14日)",
                "cols": [("mfi_14", "MFI")],
                "format": "MFI:{mfi_14:.2f}",
                "state_fn": lambda r: _rsi_state(r["mfi_14"]),
                "priority": 27,
            },
            {
                "key": "vwap",
                "name": "VWAP",
                "name_zh": "成交量加权均价",
                "cols": [("vwap", "VWAP")],
                "format": "VWAP:{vwap:.2f}",
                "state_fn": lambda r: (
                    "价格在VWAP上方·偏强" if r["close_val"] > r["vwap"] else "价格在VWAP下方·偏弱"
                ),
                "priority": 28,
            },
            {
                "key": "chaikin_money_flow",
                "name": "CMF",
                "name_zh": "蔡金资金流量(20日)",
                "cols": [("cmf_20", "CMF")],
                "format": "CMF:{cmf_20:.4f}",
                "state_fn": lambda r: (
                    "资金流入" if r["cmf_20"] > 0 else "资金流出"
                ) + ("·增强" if abs(r["cmf_20"]) > abs(r["cmf_20_shift1"]) else ""),
                "priority": 29,
            },
            {
                "key": "force_index",
                "name": "Force Index",
                "name_zh": "力量指数(13日)",
                "cols": [("force_index_13", "FI")],
                "format": "FI:{force_index_13:,.0f}",
                "state_fn": lambda r: (
                    "多头力量" if r["force_index_13"] > 0 else "空头力量"
                ),
                "priority": 30,
            },
            {
                "key": "ease_of_movement",
                "name": "EOM",
                "name_zh": "简易波动指标(14日)",
                "cols": [("eom_14", "EOM")],
                "format": "EOM:{eom_14:.4f}",
                "state_fn": lambda r: (
                    "上升阻力小" if r["eom_14"] > 0 else "下降阻力小"
                ),
                "priority": 31,
            },
            {
                "key": "volume_roc",
                "name": "Volume ROC",
                "name_zh": "成交量变动率(12日)",
                "cols": [("vol_roc_12", "VROC")],
                "format": "VROC:{vol_roc_12:.2f}%",
                "state_fn": lambda r: (
                    "放量" if r["vol_roc_12"] > 20 else "缩量" if r["vol_roc_12"] < -20 else "量平"
                ),
                "priority": 32,
            },
            {
                "key": "ad_line",
                "name": "A/D Line",
                "name_zh": "累积派发线",
                "cols": [("ad_line", "AD")],
                "format": "AD:{ad_line:,.0f}",
                "state_fn": lambda r: (
                    "累积为主·资金流入" if r["ad_line"] > r["ad_line_shift1"] else "派发为主·资金流出"
                ),
                "priority": 33,
            },
            {
                "key": "nvi",
                "name": "NVI",
                "name_zh": "负量指标",
                "cols": [("nvi", "NVI")],
                "format": "NVI:{nvi:,.2f}",
                "state_fn": lambda r: (
                    "NVI上升·主力资金潜伏" if r["nvi"] > r["nvi_shift5"] else "NVI走平/下降"
                ),
                "priority": 34,
            },
        ],
    },
    {
        "title": "五、价格目标与特殊系统 (Targets & Special Systems)",
        "desc": "支撑阻力位识别与特殊计数系统",
        "indicators": [
            {
                "key": "pivot_points",
                "name": "Pivot Points",
                "name_zh": "枢纽点(标准)",
                "cols": [("pp", "PP"), ("r1", "R1"), ("s1", "S1"), ("r2", "R2"), ("s2", "S2")],
                "format": "PP:{pp:.2f} R1:{r1:.2f} S1:{s1:.2f} R2:{r2:.2f} S2:{s2:.2f}",
                "state_fn": lambda r: _pivot_state(r),
                "priority": 35,
            },
            {
                "key": "fibonacci_retracement",
                "name": "Fibonacci",
                "name_zh": "斐波那契回撤",
                "cols": [("fib_0", "0%"), ("fib_236", "23.6%"), ("fib_382", "38.2%"), ("fib_500", "50%"), ("fib_618", "61.8%"), ("fib_1000", "100%")],
                "format": "0%:{fib_0:.2f} 23.6%:{fib_236:.2f} 38.2%:{fib_382:.2f} 50%:{fib_500:.2f} 61.8%:{fib_618:.2f}",
                "state_fn": lambda r: _fib_state(r),
                "priority": 36,
            },
            {
                "key": "td_sequential",
                "name": "TD Sequential",
                "name_zh": "TD序列",
                "cols": [("td_setup", "Setup")],
                "format": "Setup:{td_setup}",
                "state_fn": lambda r: (
                    (f"买入Setup计数中({min(r['td_setup'], 9)}/9)" if r["td_setup"] > 0 else "") +
                    (f"卖出Setup计数中({min(abs(r['td_setup']), 9)}/9)" if r["td_setup"] < 0 else "") +
                    ("无活跃Setup" if r["td_setup"] == 0 else "")
                ),
                "priority": 37,
            },
        ],
    },
]


# ─── 状态辅助函数 ──────────────────────────────────────────────────────────────

def _rsi_state(val: float) -> str:
    if val > 80:
        return "严重超买"
    if val > 70:
        return "超买区"
    if val < 20:
        return "严重超卖"
    if val < 30:
        return "超卖区"
    if val > 55:
        return "中性偏强"
    if val < 45:
        return "中性偏弱"
    return "中性区"


def _ma_state(r: dict) -> str:
    close = r["close_val"]
    mas = [(r.get(f"ma_{p}"), p) for p in [5, 10, 20, 60, 120, 250] if f"ma_{p}" in r]
    mas = [(v, p) for v, p in mas if pd.notna(v)]
    if len(mas) < 2:
        return "数据不足"
    sorted_mas = sorted(mas, key=lambda x: x[0], reverse=True)
    if all(sorted_mas[i][0] >= sorted_mas[i + 1][0] for i in range(len(sorted_mas) - 1)):
        trend = "多头排列"
    elif all(sorted_mas[i][0] <= sorted_mas[i + 1][0] for i in range(len(sorted_mas) - 1)):
        trend = "空头排列"
    else:
        trend = "均线纠缠/整理"
    above_all = all(close > v for v, _ in mas)
    below_all = all(close < v for v, _ in mas)
    pos = "价格在所有均线上方" if above_all else ("价格在所有均线下方" if below_all else "价格在均线间")
    return f"{trend} | {pos}"


def _pivot_state(r: dict) -> str:
    c = r["close_val"]
    if c > r["r2"]:
        return f"突破R2·极强 | 距R3: {((r.get('r3', c) - c) / c * 100):.1f}%"
    if c > r["r1"]:
        return f"R1-R2区间·偏强 | 距R2: {((r['r2'] - c) / c * 100):.1f}%"
    if c > r["pp"]:
        return f"PP-R1区间·偏多 | 距R1: {((r['r1'] - c) / c * 100):.1f}%"
    if c > r["s1"]:
        return f"S1-PP区间·偏空 | 距S1: {((c - r['s1']) / c * 100):.1f}%"
    if c > r["s2"]:
        return f"S2-S1区间·偏弱 | 距S2: {((c - r['s2']) / c * 100):.1f}%"
    return f"跌破S2·极弱 | 距S3: {((c - r.get('s3', c)) / c * 100):.1f}%"


def _fib_state(r: dict) -> str:
    c = r["close_val"]
    levels = [
        ("0%", r["fib_0"]), ("23.6%", r["fib_236"]), ("38.2%", r["fib_382"]),
        ("50%", r["fib_500"]), ("61.8%", r["fib_618"]), ("100%", r["fib_1000"]),
    ]
    for i in range(len(levels) - 1):
        l1_name, l1 = levels[i]
        l2_name, l2 = levels[i + 1]
        if min(l1, l2) <= c <= max(l1, l2):
            return f"位于{l2_name}~{l1_name}区间 | 关键位: {l2_name if abs(c - l2) < abs(c - l1) else l1_name}"
    return "位于区间外"


# ─── 核心逻辑 ──────────────────────────────────────────────────────────────────

ALL_INDICATOR_KEYS = []
for layer in INDICATOR_LAYERS:
    for ind in layer["indicators"]:
        ALL_INDICATOR_KEYS.append(ind["key"])


def fetch_and_compute(code: str, bars: int = 250) -> pd.DataFrame | None:
    """Fetch enough history for multi-timeframe analysis, compute all indicators, return full df.

    The returned DataFrame contains at least max(bars, 250) + 260 rows of warm-up data,
    allowing the caller to slice arbitrary windows (short/medium/long) for cross-timeframe analysis.
    """
    with TdxQuery() as q:
        df = q.get_daily(code)
        if df is None or df.empty:
            return None
        df = df.sort_values("trade_date").reset_index(drop=True)

        # Ensure enough history for the longest window (250) + warm-up
        min_required = max(bars, 250) + 260
        if len(df) > min_required:
            df = df.iloc[-min_required:].copy()

        # Compute ALL indicators on the full history
        df = TdxIndicators.compute(df, indicators=ALL_INDICATOR_KEYS)

        return df


def _format_value(v: Any) -> str:
    if pd.isna(v):
        return "N/A"
    if isinstance(v, (int, np.integer)):
        return f"{v}"
    if isinstance(v, (float, np.floating)):
        return f"{v:.4f}" if abs(v) < 10 else f"{v:.2f}"
    return str(v)


def _count_crosses(df: pd.DataFrame, col_a: str, col_b: str, direction: str) -> int:
    """Count crossovers in the analysis period."""
    if direction == "above":
        mask = (df[col_a] > df[col_b]) & (df[col_a].shift(1) <= df[col_b].shift(1))
    else:
        mask = (df[col_a] < df[col_b]) & (df[col_a].shift(1) >= df[col_b].shift(1))
    return int(mask.sum())


def _build_period_summary(df: pd.DataFrame, scores: dict, period_return: float, max_dd: float) -> str:
    """Generate a natural-language summary of the period's technical profile."""
    n = len(df)
    parts = []

    # Price action
    trend_word = "上涨" if period_return > 0 else "下跌"
    parts.append(f"区间走势: {trend_word}{abs(period_return):.1f}%, 最大回撤{abs(max_dd):.1f}%")

    # MACD dynamics
    if "macd" in df.columns and "macd_signal" in df.columns:
        start_gold = df["macd"].iloc[0] > df["macd_signal"].iloc[0]
        end_gold = df["macd"].iloc[-1] > df["macd_signal"].iloc[-1]
        if not start_gold and end_gold:
            parts.append("MACD: 区间内发生金叉，动能由负转正")
        elif start_gold and not end_gold:
            parts.append("MACD: 区间内发生死叉，动能由正转负")
        elif end_gold:
            parts.append("MACD: 金叉维持，多头动能持续")
        else:
            parts.append("MACD: 死叉维持，空头动能持续")

    # RSI trajectory
    if "rsi_14" in df.columns:
        rsi_start = df["rsi_14"].iloc[0]
        rsi_end = df["rsi_14"].iloc[-1]
        if rsi_end > rsi_start + 10:
            parts.append(f"RSI: 从{rsi_start:.0f}升至{rsi_end:.0f}，动能走强")
        elif rsi_end < rsi_start - 10:
            parts.append(f"RSI: 从{rsi_start:.0f}降至{rsi_end:.0f}，动能走弱")
        else:
            parts.append(f"RSI: 维持在{rsi_end:.0f}附近，动能平稳")

    # Volume
    if "obv" in df.columns:
        obv_change = df["obv"].iloc[-1] - df["obv"].iloc[0]
        parts.append(f"量价: OBV{'上升·资金流入' if obv_change > 0 else '下降·资金流出'}")

    return " | ".join(parts)


def build_signal_radar(df: pd.DataFrame, max_signals: int = 15) -> list[tuple]:
    """Scan the entire analysis period for signals, return the most recent ones."""
    signals: list[tuple] = []
    close = df["close_val"]
    n = len(df)

    def _add(mask: pd.Series, label: str, desc: str):
        for pos in mask.to_numpy().nonzero()[0]:
            if 0 <= pos < n:
                signals.append((str(df.iloc[pos]["trade_date"]), label, desc))

    # MACD crosses
    if len(df) >= 2 and "macd" in df.columns and "macd_signal" in df.columns:
        mg = (df["macd"] > df["macd_signal"]) & (df["macd"].shift(1) <= df["macd_signal"].shift(1))
        md = (df["macd"] < df["macd_signal"]) & (df["macd"].shift(1) >= df["macd_signal"].shift(1))
        _add(mg, "MACD", "金叉")
        _add(md, "MACD", "死叉")

    # Supertrend flips
    if "supertrend_direction" in df.columns:
        st_buy = (df["supertrend_direction"] == -1) & (df["supertrend_direction"].shift(1) == 1)
        st_sell = (df["supertrend_direction"] == 1) & (df["supertrend_direction"].shift(1) == -1)
        _add(st_buy, "Supertrend", "买入")
        _add(st_sell, "Supertrend", "卖出")

    # MA5/MA10 crosses
    if "ma_5" in df.columns and "ma_10" in df.columns:
        ma_gold = (df["ma_5"] > df["ma_10"]) & (df["ma_5"].shift(1) <= df["ma_10"].shift(1))
        ma_death = (df["ma_5"] < df["ma_10"]) & (df["ma_5"].shift(1) >= df["ma_10"].shift(1))
        _add(ma_gold, "MA", "MA5上穿MA10")
        _add(ma_death, "MA", "MA5下穿MA10")

    # RSI thresholds
    if "rsi_14" in df.columns:
        rsi_buy = (df["rsi_14"] < 30) & (df["rsi_14"].shift(1) >= 30)
        rsi_sell = (df["rsi_14"] > 70) & (df["rsi_14"].shift(1) <= 70)
        _add(rsi_buy, "RSI", "进入超卖区")
        _add(rsi_sell, "RSI", "进入超买区")

    # Bollinger touch
    if "bb_lower" in df.columns:
        bb_low = df["close_val"] <= df["bb_lower"]
        bb_high = df["close_val"] >= df["bb_upper"]
        _add(bb_low, "Bollinger", "触及下轨")
        _add(bb_high, "Bollinger", "触及上轨")

    # SAR flips
    if "sar" in df.columns:
        sar_buy = (close > df["sar"]) & (close.shift(1) <= df["sar"].shift(1))
        sar_sell = (close < df["sar"]) & (close.shift(1) >= df["sar"].shift(1))
        _add(sar_buy, "SAR", "转多")
        _add(sar_sell, "SAR", "转空")

    signals.sort(key=lambda x: x[0], reverse=True)
    return signals[:max_signals]


def _calc_raw_volatility(df: pd.DataFrame) -> float:
    """Calculate raw volatility value (unbounded) for percentile ranking.

    Returns a raw score where higher = more volatile.  Used by batch analyzers
    to compute relative volatility percentiles across a peer group.
    """
    cummax = df["close_val"].cummax()
    max_dd = ((df["close_val"] - cummax) / cummax * 100).min()

    vol_raw = abs(max_dd) / 10.0

    if "atr_14" in df.columns:
        atr_pct_mean = (df["atr_14"] / df["close_val"] * 100).mean()
        if pd.notna(atr_pct_mean):
            vol_raw += atr_pct_mean * 0.8

    if "bb_bandwidth" in df.columns:
        bbw = df["bb_bandwidth"].dropna()
        if len(bbw) > 1:
            bb_chg = bbw.iloc[-1] - bbw.iloc[0]
            if pd.notna(bb_chg):
                vol_raw += bb_chg * 15.0

    return vol_raw


def calc_period_scores(
    df: pd.DataFrame,
    weights_override: dict[str, float] | None = None,
    vol_percentile: float | None = None,
) -> tuple[dict[str, float], str]:
    """Calculate a period-driven multi-factor score based on the entire analysis window.

    Args:
        df: Analysis window DataFrame.
        weights_override: Optional dict with keys "trend"/"momentum"/"volatility"/"volume"
            to override the default scoring weights.
        vol_percentile: Optional 0-1 float. When provided (e.g. from batch ranking),
            volatility score = percentile * 10, enabling relative risk ranking within
            a peer group.  When None, absolute volatility calibration is used.

    Returns (scores_dict, period_summary_string).
    """
    n = len(df)
    scores: dict[str, float] = {}

    # ── Pre-compute common metrics ──
    period_return = (df["close_val"].iloc[-1] - df["close_val"].iloc[0]) / df["close_val"].iloc[0] * 100
    cummax = df["close_val"].cummax()
    max_dd = ((df["close_val"] - cummax) / cummax * 100).min()

    # ── 1. Trend Direction (0-10) ──
    # Recalibrated: base lowered, sensitivity reduced for better discrimination
    trend_score = 4.0

    # Period return contribution: ±30% → ±2.5 pts (was ±20%→±3)
    trend_score += max(-2.5, min(2.5, period_return / 30.0 * 2.5))

    # MA alignment persistence (was +2.0 max, now +1.5)
    if "ma_5" in df.columns and "ma_10" in df.columns and "ma_20" in df.columns:
        bull_mask = (df["ma_5"] > df["ma_10"]) & (df["ma_10"] > df["ma_20"])
        trend_score += (bull_mask.sum() / n) * 1.5

    # MACD: crossovers + HIST net change
    if "macd" in df.columns and "macd_signal" in df.columns:
        gold = _count_crosses(df, "macd", "macd_signal", "above")
        death = _count_crosses(df, "macd", "macd_signal", "below")
        trend_score += gold * 0.4 - death * 0.4
        if "macd_hist" in df.columns:
            hist_chg = df["macd_hist"].iloc[-1] - df["macd_hist"].iloc[0]
            trend_score += 0.4 if hist_chg > 0 else -0.4

    # Supertrend consistency (was ±1.0, now ±0.8)
    if "supertrend_direction" in df.columns:
        up_days = (df["supertrend_direction"] == -1).sum()
        trend_score += (up_days / n - 0.5) * 1.6

    # ADX strong-trend persistence (was ±0.5, now ±0.4)
    if "adx" in df.columns:
        strong_days = (df["adx"] > 25).sum()
        trend_score += (strong_days / n - 0.5) * 0.8

    scores["trend"] = max(0.0, min(10.0, trend_score))

    # ── 2. Momentum State (0-10) ──
    mom_score = 5.0

    if "rsi_14" in df.columns:
        rsi_mean = df["rsi_14"].mean()
        mom_score += (rsi_mean - 50.0) / 15.0  # relaxed from /20.0 for wider score distribution
        rsi_chg = df["rsi_14"].iloc[-1] - df["rsi_14"].iloc[0]
        if rsi_chg > 10:
            mom_score += 0.4
        elif rsi_chg < -10:
            mom_score -= 0.4

    if "stoch_k" in df.columns:
        stoch_mean = df["stoch_k"].mean()
        mom_score += (stoch_mean - 50.0) / 25.0  # relaxed from /30.0

    if "awesome_osc" in df.columns:
        ao_mean = df["awesome_osc"].mean()
        mom_score += 0.4 if ao_mean > 0 else -0.4

    if "roc_12" in df.columns:
        roc_mean = df["roc_12"].mean()
        mom_score += 0.4 if roc_mean > 0 else -0.4

    scores["momentum"] = max(0.0, min(10.0, mom_score))

    # ── 3. Volatility Risk (0=low risk, 10=high risk) ──
    if vol_percentile is not None:
        # Relative scoring: percentile within peer group (batch ranking)
        # This solves cross-sector saturation — a high-vol stock in a high-vol
        # sector can still score ~5 if it's median-volatile for its peers.
        vol_score = vol_percentile * 10.0
    else:
        # Absolute scoring: standalone calibration (single-stock analysis)
        vol_score = 2.5
        vol_score += abs(max_dd) / 10.0
        if "atr_14" in df.columns:
            atr_pct_mean = (df["atr_14"] / df["close_val"] * 100).mean()
            if pd.notna(atr_pct_mean):
                vol_score += atr_pct_mean * 0.8
        if "bb_bandwidth" in df.columns:
            bbw = df["bb_bandwidth"].dropna()
            if len(bbw) > 1:
                bb_chg = bbw.iloc[-1] - bbw.iloc[0]
                if pd.notna(bb_chg):
                    vol_score += bb_chg * 15.0

    scores["volatility"] = max(0.0, min(10.0, vol_score))

    # ── 4. Volume Confirmation (0-10) ──
    vol_conf = 5.0

    if "obv" in df.columns:
        obv_chg = df["obv"].iloc[-1] - df["obv"].iloc[0]
        vol_conf += 1.5 if obv_chg > 0 else -1.5

    if "cmf_20" in df.columns:
        pos_days = (df["cmf_20"] > 0).sum()
        vol_conf += (pos_days / n - 0.5) * 2.0

    if "mfi_14" in df.columns:
        mfi_mean = df["mfi_14"].mean()
        vol_conf += (mfi_mean - 50.0) / 15.0

    scores["volume"] = max(0.0, min(10.0, vol_conf))

    # ── Overall (adaptive weights) ──
    if weights_override:
        w = weights_override
    else:
        w = {"trend": 0.35, "momentum": 0.25, "volatility": 0.15, "volume": 0.25}
    scores["overall"] = (
        scores["trend"] * w["trend"] +
        scores["momentum"] * w["momentum"] +
        (10.0 - scores["volatility"]) * w["volatility"] +
        scores["volume"] * w["volume"]
    )

    # ── Period Summary ──
    summary = _build_period_summary(df, scores, period_return, max_dd)

    return scores, summary


# ─── Multi-Timeframe Fusion Engine ─────────────────────────────────────────────

TF_CONFIG = [
    ("short", 10, "短期(10日)"),
    ("medium", 60, "中期(60日)"),
    ("long", 250, "长期(250日)"),
]


def calc_multi_timeframe_scores(df: pd.DataFrame, primary_bars: int, weights_override: dict[str, float] | None = None) -> dict[str, dict]:
    """Calculate scores for short/medium/long windows from the same full df.

    Returns {"short": {...}, "medium": {...}, "long": {...}, "primary": {...}}
    where each value is {"scores": dict, "summary": str, "window": df_slice}.
    """
    result: dict[str, dict] = {}
    for key, window_size, label in TF_CONFIG:
        if len(df) >= window_size:
            window_df = df.iloc[-window_size:].copy()
        else:
            window_df = df.copy()
        scores, summary = calc_period_scores(window_df, weights_override)
        result[key] = {
            "scores": scores,
            "summary": summary,
            "window": window_df,
            "label": label,
            "bars": len(window_df),
        }
    # Also score the user's primary window explicitly
    primary_df = df.iloc[-primary_bars:].copy() if len(df) > primary_bars else df.copy()
    p_scores, p_summary = calc_period_scores(primary_df, weights_override)
    result["primary"] = {
        "scores": p_scores,
        "summary": p_summary,
        "window": primary_df,
        "label": f"主窗口({primary_bars}日)",
        "bars": len(primary_df),
    }
    return result


def detect_timeframe_divergence(tf_scores: dict[str, dict]) -> list[str]:
    """Detect divergences across timeframes.

    Returns a list of human-readable divergence warnings.
    """
    alerts: list[str] = []
    s = tf_scores.get("short", {}).get("scores", {})
    m = tf_scores.get("medium", {}).get("scores", {})
    l = tf_scores.get("long", {}).get("scores", {})
    p = tf_scores.get("primary", {}).get("scores", {})

    if not s or not m or not l:
        return alerts

    # 1. Short-term strength vs long-term weakness (bull trap warning)
    if s.get("trend", 5) >= 7 and l.get("trend", 5) <= 4:
        alerts.append("⚠️ 周期背离：短期趋势强势 vs 长期趋势弱势 — 警惕反弹诱多")

    # 2. Short-term weakness vs long-term strength (accumulation zone)
    if s.get("trend", 5) <= 4 and l.get("trend", 5) >= 7:
        alerts.append("🔥 周期背离：短期回调 vs 长期趋势完好 — 关注低吸机会")

    # 3. Momentum divergence across timeframes
    if s.get("momentum", 5) >= 7 and m.get("momentum", 5) <= 4:
        alerts.append("⚠️ 动量背离：短期动量过热，中期动量不足 — 上涨持续性存疑")

    if s.get("momentum", 5) <= 4 and m.get("momentum", 5) >= 7:
        alerts.append("🔥 动量背离：短期动能衰竭，中期动能储备充足 — 或为一脚踩空")

    # 4. Volume divergence
    if s.get("volume", 5) >= 7 and m.get("volume", 5) <= 4:
        alerts.append("⚠️ 量价背离：短期放量但中期量能不足 — 需确认资金持续性")

    # 5. All timeframes aligned
    trends = [s.get("trend", 5), m.get("trend", 5), l.get("trend", 5)]
    if all(t >= 7 for t in trends):
        alerts.append("✅ 周期共振：短/中/长期趋势全部强势 — 顺大势做多")
    elif all(t <= 4 for t in trends):
        alerts.append("❌ 周期共振：短/中/长期趋势全部弱势 — 顺大势做空/空仓")

    # 6. Primary vs consensus
    if p.get("overall", 5) >= 7 and m.get("overall", 5) <= 4.5:
        alerts.append("⚠️ 窗口偏差：主窗口偏强，但中期背景偏弱 — 不宜追高")
    elif p.get("overall", 5) <= 4 and m.get("overall", 5) >= 7:
        alerts.append("🔥 窗口偏差：主窗口偏弱，但中期背景强势 — 或为主升浪起点")

    return alerts


def _build_multitimeframe_block(tf_scores: dict[str, dict], divergences: list[str]) -> list[str]:
    """Build the multi-timeframe fusion panel."""
    lines = []
    lines.append("╔" + "═" * 78 + "╗")
    lines.append(f"║  多周期融合分析{' ' * 62}║")
    lines.append("╠" + "═" * 78 + "╣")

    # Header row
    header = f"  {'周期':<12} {'趋势':>6} {'动量':>6} {'波动':>6} {'量价':>6} {'综合':>6} {'研判':<8}"
    lines.append(f"║{header:<78}║")
    lines.append(f"║  {'─'*74}  ║")

    order = ["short", "medium", "long", "primary"]
    for key in order:
        if key not in tf_scores:
            continue
        info = tf_scores[key]
        sc = info["scores"]
        label = info["label"]
        ov = sc.get("overall", 0)
        ov_label = _score_label(ov)
        row = f"  {label:<12} {sc.get('trend', 0):>6.1f} {sc.get('momentum', 0):>6.1f} {sc.get('volatility', 0):>6.1f} {sc.get('volume', 0):>6.1f} {ov:>6.1f} {ov_label:<8}"
        lines.append(f"║{row:<78}║")

    # Divergence alerts
    if divergences:
        lines.append("╠" + "═" * 78 + "╣")
        lines.append(f"║  周期背离检测{' ' * 62}║")
        lines.append(f"║  {'─'*74}  ║")
        for alert in divergences[:6]:  # max 6 alerts
            lines.append(f"║  {alert:<76}║")
    else:
        lines.append("╠" + "═" * 78 + "╣")
        lines.append(f"║  周期状态：各周期方向一致，无显著背离{' ' * 37}║")

    lines.append("╚" + "═" * 78 + "╝")
    return lines


# ─── Phase 2: Resonance Radar + Divergence Detection ─────────────────────────

def _indicator_bias(r: pd.Series) -> dict[str, dict[str, int]]:
    """Score each indicator as bull(+1), bear(-1), or neutral(0) based on latest values.

    Returns {"trend": {"bull": n, "bear": n, "neutral": n}, ...} for all 4 dimensions.
    """
    bias: dict[str, dict[str, int]] = {
        "trend": {"bull": 0, "bear": 0, "neutral": 0},
        "momentum": {"bull": 0, "bear": 0, "neutral": 0},
        "volatility": {"bull": 0, "bear": 0, "neutral": 0},
        "volume": {"bull": 0, "bear": 0, "neutral": 0},
    }
    c = r.get("close_val", np.nan)
    if pd.isna(c):
        return bias

    # ── Trend Layer ──
    # MACD
    if "macd" in r and "macd_signal" in r:
        if r["macd"] > 0 and r["macd"] > r["macd_signal"]:
            bias["trend"]["bull"] += 1
        elif r["macd"] < 0 and r["macd"] < r["macd_signal"]:
            bias["trend"]["bear"] += 1
        else:
            bias["trend"]["neutral"] += 1

    # Supertrend
    if "supertrend_direction" in r:
        if r["supertrend_direction"] == -1:
            bias["trend"]["bull"] += 1
        else:
            bias["trend"]["bear"] += 1

    # ADX
    if "adx" in r and "plus_di" in r and "minus_di" in r:
        if r["adx"] > 25:
            if r["plus_di"] > r["minus_di"]:
                bias["trend"]["bull"] += 1
            else:
                bias["trend"]["bear"] += 1
        else:
            bias["trend"]["neutral"] += 1

    # Ichimoku
    if "senkou_span_a" in r and "senkou_span_b" in r:
        cloud_top = max(r["senkou_span_a"], r["senkou_span_b"])
        cloud_bot = min(r["senkou_span_a"], r["senkou_span_b"])
        if c > cloud_top:
            bias["trend"]["bull"] += 1
        elif c < cloud_bot:
            bias["trend"]["bear"] += 1
        else:
            bias["trend"]["neutral"] += 1

    # MA alignment
    ma_cols = [f"ma_{p}" for p in [5, 10, 20, 60, 120, 250] if f"ma_{p}" in r]
    if len(ma_cols) >= 3:
        vals = [r[col] for col in ma_cols if pd.notna(r[col])]
        if len(vals) >= 3:
            if all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1)):
                bias["trend"]["bull"] += 1
            elif all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1)):
                bias["trend"]["bear"] += 1
            else:
                bias["trend"]["neutral"] += 1

    # EMA
    if "ema_12" in r and "ema_26" in r:
        if r["ema_12"] > r["ema_26"]:
            bias["trend"]["bull"] += 1
        else:
            bias["trend"]["bear"] += 1

    # SAR
    if "sar" in r:
        if c > r["sar"]:
            bias["trend"]["bull"] += 1
        else:
            bias["trend"]["bear"] += 1

    # TRIX
    if "trix" in r:
        if r["trix"] > 0:
            bias["trend"]["bull"] += 1
        else:
            bias["trend"]["bear"] += 1

    # Aroon
    if "aroon_up" in r and "aroon_down" in r:
        if r["aroon_up"] > 70 and r["aroon_down"] < 30:
            bias["trend"]["bull"] += 1
        elif r["aroon_down"] > 70 and r["aroon_up"] < 30:
            bias["trend"]["bear"] += 1
        else:
            bias["trend"]["neutral"] += 1

    # Vortex
    if "vortex_pos" in r and "vortex_neg" in r:
        if r["vortex_pos"] > r["vortex_neg"]:
            bias["trend"]["bull"] += 1
        else:
            bias["trend"]["bear"] += 1

    # ── Momentum Layer ──
    # RSI
    if "rsi_14" in r:
        if r["rsi_14"] > 55:
            bias["momentum"]["bull"] += 1
        elif r["rsi_14"] < 45:
            bias["momentum"]["bear"] += 1
        else:
            bias["momentum"]["neutral"] += 1

    # Stochastic
    if "stoch_k" in r and "stoch_d" in r:
        if r["stoch_k"] > r["stoch_d"] and r["stoch_k"] > 50:
            bias["momentum"]["bull"] += 1
        elif r["stoch_k"] < r["stoch_d"] and r["stoch_k"] < 50:
            bias["momentum"]["bear"] += 1
        else:
            bias["momentum"]["neutral"] += 1

    # StochRSI
    if "stochrsi_k" in r and "stochrsi_d" in r:
        if r["stochrsi_k"] > r["stochrsi_d"] and r["stochrsi_k"] > 50:
            bias["momentum"]["bull"] += 1
        elif r["stochrsi_k"] < r["stochrsi_d"] and r["stochrsi_k"] < 50:
            bias["momentum"]["bear"] += 1
        else:
            bias["momentum"]["neutral"] += 1

    # CCI
    if "cci_20" in r:
        if r["cci_20"] > 0:
            bias["momentum"]["bull"] += 1
        elif r["cci_20"] < 0:
            bias["momentum"]["bear"] += 1
        else:
            bias["momentum"]["neutral"] += 1

    # Williams %R
    if "williams_r" in r:
        if r["williams_r"] > -50:
            bias["momentum"]["bull"] += 1
        elif r["williams_r"] < -50:
            bias["momentum"]["bear"] += 1

    # Ultimate Oscillator
    if "ultimate_osc" in r:
        if r["ultimate_osc"] > 50:
            bias["momentum"]["bull"] += 1
        elif r["ultimate_osc"] < 50:
            bias["momentum"]["bear"] += 1
        else:
            bias["momentum"]["neutral"] += 1

    # Awesome Oscillator
    if "awesome_osc" in r:
        if r["awesome_osc"] > 0:
            bias["momentum"]["bull"] += 1
        else:
            bias["momentum"]["bear"] += 1

    # ROC
    if "roc_12" in r:
        if r["roc_12"] > 0:
            bias["momentum"]["bull"] += 1
        else:
            bias["momentum"]["bear"] += 1

    # Momentum
    if "momentum_10" in r:
        if r["momentum_10"] > 0:
            bias["momentum"]["bull"] += 1
        else:
            bias["momentum"]["bear"] += 1

    # ── Volatility Layer (bull = low risk / stable, bear = high risk / extreme) ──
    # Bollinger %B
    if "bb_pctb" in r:
        bb = r["bb_pctb"]
        if 0.2 <= bb <= 0.8:
            bias["volatility"]["bull"] += 1  # stable zone
        elif bb > 1 or bb < 0:
            bias["volatility"]["bear"] += 1  # extreme
        else:
            bias["volatility"]["neutral"] += 1

    # ATR
    if "atr_14" in r:
        atr_pct = r["atr_14"] / c * 100 if c else 0
        if atr_pct < 1.5:
            bias["volatility"]["bull"] += 1
        elif atr_pct > 3.0:
            bias["volatility"]["bear"] += 1
        else:
            bias["volatility"]["neutral"] += 1

    # Keltner
    if "keltner_upper" in r and "keltner_lower" in r:
        if r["keltner_lower"] <= c <= r["keltner_upper"]:
            bias["volatility"]["bull"] += 1
        else:
            bias["volatility"]["bear"] += 1

    # Donchian
    if "donchian_upper" in r and "donchian_lower" in r:
        if r["donchian_lower"] <= c <= r["donchian_upper"]:
            bias["volatility"]["bull"] += 1
        else:
            bias["volatility"]["bear"] += 1

    # StdDev
    if "stddev_20" in r and "stddev_20_shift5" in r:
        if r["stddev_20"] < r["stddev_20_shift5"] * 0.8:
            bias["volatility"]["bull"] += 1
        elif r["stddev_20"] > r["stddev_20_shift5"] * 1.2:
            bias["volatility"]["bear"] += 1
        else:
            bias["volatility"]["neutral"] += 1

    # Chaikin Volatility
    if "chaikin_vol" in r:
        if r["chaikin_vol"] < 0:
            bias["volatility"]["bull"] += 1
        else:
            bias["volatility"]["bear"] += 1

    # ── Volume Layer ──
    # OBV
    if "obv" in r and "obv_shift1" in r:
        if r["obv"] > r["obv_shift1"]:
            bias["volume"]["bull"] += 1
        else:
            bias["volume"]["bear"] += 1

    # MFI
    if "mfi_14" in r:
        if r["mfi_14"] > 50:
            bias["volume"]["bull"] += 1
        elif r["mfi_14"] < 50:
            bias["volume"]["bear"] += 1
        else:
            bias["volume"]["neutral"] += 1

    # VWAP
    if "vwap" in r:
        if c > r["vwap"]:
            bias["volume"]["bull"] += 1
        else:
            bias["volume"]["bear"] += 1

    # CMF
    if "cmf_20" in r:
        if r["cmf_20"] > 0:
            bias["volume"]["bull"] += 1
        else:
            bias["volume"]["bear"] += 1

    # Force Index
    if "force_index_13" in r:
        if r["force_index_13"] > 0:
            bias["volume"]["bull"] += 1
        else:
            bias["volume"]["bear"] += 1

    # EOM
    if "eom_14" in r:
        if r["eom_14"] > 0:
            bias["volume"]["bull"] += 1
        else:
            bias["volume"]["bear"] += 1

    # Volume ROC
    if "vol_roc_12" in r:
        vroc = r["vol_roc_12"]
        if -20 <= vroc <= 20:
            bias["volume"]["neutral"] += 1
        elif vroc > 20:
            bias["volume"]["bull"] += 1  # 放量配合
        else:
            bias["volume"]["bear"] += 1  # 缩量

    # A/D Line
    if "ad_line" in r and "ad_line_shift1" in r:
        if r["ad_line"] > r["ad_line_shift1"]:
            bias["volume"]["bull"] += 1
        else:
            bias["volume"]["bear"] += 1

    # NVI
    if "nvi" in r and "nvi_shift5" in r:
        if r["nvi"] > r["nvi_shift5"]:
            bias["volume"]["bull"] += 1
        else:
            bias["volume"]["bear"] += 1

    return bias


def build_resonance_radar(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Aggregate bull/bear/neutral counts across all 4 dimensions."""
    latest = df.iloc[-1]
    # Build a row with shifted values for one-bar-ago comparison
    r = latest.copy()
    if len(df) >= 2:
        prev = df.iloc[-2]
        for col in prev.index:
            r[f"{col}_shift1"] = prev[col]
    if len(df) >= 6:
        r5 = df.iloc[-6]
        for col in r5.index:
            r[f"{col}_shift5"] = r5[col]

    bias = _indicator_bias(r)
    return bias


def _local_extrema(series: pd.Series, window: int = 3) -> tuple[pd.Series, pd.Series]:
    """Return (maxima_mask, minima_mask) for local extrema."""
    roll_max = series.rolling(window=window, center=True).max()
    roll_min = series.rolling(window=window, center=True).min()
    maxima = (series == roll_max) & (series.shift(1) < series) & (series.shift(-1) < series)
    minima = (series == roll_min) & (series.shift(1) > series) & (series.shift(-1) > series)
    return maxima, minima


def detect_divergence(df: pd.DataFrame) -> list[str]:
    """Detect classic price-indicator divergences within the analysis window.

    Returns a list of human-readable divergence alerts.
    """
    alerts: list[str] = []
    if len(df) < 10:
        return alerts

    close = df["close_val"].reset_index(drop=True)

    # ── Price-MACD Divergence ──
    if "macd" in df.columns:
        macd = df["macd"].reset_index(drop=True)
        price_max, price_min = _local_extrema(close, window=3)
        macd_max, macd_min = _local_extrema(macd, window=3)

        # Top divergence: price higher high, MACD lower high
        pmax_idx = price_max.to_numpy().nonzero()[0]
        if len(pmax_idx) >= 2:
            for i in range(1, len(pmax_idx)):
                idx1, idx2 = pmax_idx[i - 1], pmax_idx[i]
                if close.iloc[idx2] > close.iloc[idx1] and macd.iloc[idx2] < macd.iloc[idx1]:
                    d1 = str(df.iloc[idx1]["trade_date"])[:10]
                    d2 = str(df.iloc[idx2]["trade_date"])[:10]
                    alerts.append(f"📉 顶背离 [{d1}→{d2}]: 价格新高({close.iloc[idx2]:.2f}) MACD未跟进({macd.iloc[idx2]:.3f}<{macd.iloc[idx1]:.3f})")
                    break  # only report the most recent

        # Bottom divergence: price lower low, MACD higher low
        pmin_idx = price_min.to_numpy().nonzero()[0]
        if len(pmin_idx) >= 2:
            for i in range(1, len(pmin_idx)):
                idx1, idx2 = pmin_idx[i - 1], pmin_idx[i]
                if close.iloc[idx2] < close.iloc[idx1] and macd.iloc[idx2] > macd.iloc[idx1]:
                    d1 = str(df.iloc[idx1]["trade_date"])[:10]
                    d2 = str(df.iloc[idx2]["trade_date"])[:10]
                    alerts.append(f"📈 底背离 [{d1}→{d2}]: 价格新低({close.iloc[idx2]:.2f}) MACD未跟进({macd.iloc[idx2]:.3f}>{macd.iloc[idx1]:.3f})")
                    break

    # ── Price-RSI Divergence ──
    if "rsi_14" in df.columns:
        rsi = df["rsi_14"].reset_index(drop=True)
        price_max, price_min = _local_extrema(close, window=3)
        rsi_max, rsi_min = _local_extrema(rsi, window=3)

        pmax_idx = price_max.to_numpy().nonzero()[0]
        if len(pmax_idx) >= 2:
            for i in range(1, len(pmax_idx)):
                idx1, idx2 = pmax_idx[i - 1], pmax_idx[i]
                if close.iloc[idx2] > close.iloc[idx1] and rsi.iloc[idx2] < rsi.iloc[idx1]:
                    d1 = str(df.iloc[idx1]["trade_date"])[:10]
                    d2 = str(df.iloc[idx2]["trade_date"])[:10]
                    alerts.append(f"📉 RSI顶背离 [{d1}→{d2}]: 价格新高 RSI未跟进({rsi.iloc[idx2]:.1f}<{rsi.iloc[idx1]:.1f})")
                    break

        pmin_idx = price_min.to_numpy().nonzero()[0]
        if len(pmin_idx) >= 2:
            for i in range(1, len(pmin_idx)):
                idx1, idx2 = pmin_idx[i - 1], pmin_idx[i]
                if close.iloc[idx2] < close.iloc[idx1] and rsi.iloc[idx2] > rsi.iloc[idx1]:
                    d1 = str(df.iloc[idx1]["trade_date"])[:10]
                    d2 = str(df.iloc[idx2]["trade_date"])[:10]
                    alerts.append(f"📈 RSI底背离 [{d1}→{d2}]: 价格新低 RSI未跟进({rsi.iloc[idx2]:.1f}>{rsi.iloc[idx1]:.1f})")
                    break

    # ── Price-OBV Divergence (volume-based) ──
    if "obv" in df.columns:
        obv = df["obv"].reset_index(drop=True)
        price_max, price_min = _local_extrema(close, window=3)
        obv_max, obv_min = _local_extrema(obv, window=3)

        pmax_idx = price_max.to_numpy().nonzero()[0]
        if len(pmax_idx) >= 2:
            for i in range(1, len(pmax_idx)):
                idx1, idx2 = pmax_idx[i - 1], pmax_idx[i]
                if close.iloc[idx2] > close.iloc[idx1] and obv.iloc[idx2] < obv.iloc[idx1]:
                    d1 = str(df.iloc[idx1]["trade_date"])[:10]
                    d2 = str(df.iloc[idx2]["trade_date"])[:10]
                    alerts.append(f"⚠️ 量价顶背离 [{d1}→{d2}]: 价格新高 OBV下降(资金出逃)")
                    break

        pmin_idx = price_min.to_numpy().nonzero()[0]
        if len(pmin_idx) >= 2:
            for i in range(1, len(pmin_idx)):
                idx1, idx2 = pmin_idx[i - 1], pmin_idx[i]
                if close.iloc[idx2] < close.iloc[idx1] and obv.iloc[idx2] > obv.iloc[idx1]:
                    d1 = str(df.iloc[idx1]["trade_date"])[:10]
                    d2 = str(df.iloc[idx2]["trade_date"])[:10]
                    alerts.append(f"🔥 量价底背离 [{d1}→{d2}]: 价格新低 OBV上升(主力吸筹)")
                    break

    return alerts


def _build_resonance_block(resonance: dict[str, dict[str, int]], divergences: list[str]) -> list[str]:
    """Build the resonance radar panel."""
    lines = []
    lines.append("╔" + "═" * 78 + "╗")
    lines.append(f"║  指标共振雷达{' ' * 62}║")
    lines.append("╠" + "═" * 78 + "╣")

    # Dimension labels mapping
    dim_labels = {
        "trend": "趋势结构",
        "momentum": "动量时机",
        "volatility": "波动风险",
        "volume": "量价确认",
    }

    for dim, label in dim_labels.items():
        counts = resonance.get(dim, {"bull": 0, "bear": 0, "neutral": 0})
        total = counts["bull"] + counts["bear"] + counts["neutral"]
        if total == 0:
            continue
        bull_pct = counts["bull"] / total * 100
        bear_pct = counts["bear"] / total * 100
        neut_pct = counts["neutral"] / total * 100

        # Determine consensus
        if counts["bull"] > counts["bear"] + counts["neutral"]:
            consensus = "✅ 一致看多"
        elif counts["bear"] > counts["bull"] + counts["neutral"]:
            consensus = "❌ 一致看空"
        elif counts["bull"] > counts["bear"]:
            consensus = "📈 偏多"
        elif counts["bear"] > counts["bull"]:
            consensus = "📉 偏空"
        else:
            consensus = "➖ 分歧"

        bar_bull = int(round(bull_pct / 100 * 8))
        bar_bear = int(round(bear_pct / 100 * 8))
        bar_neut = 8 - bar_bull - bar_bear
        bar = "█" * bar_bull + "▓" * bar_neut + "░" * bar_bear

        row = f"  {label:<10} {bar}  多:{counts['bull']} 空:{counts['bear']} 中:{counts['neutral']}  {consensus}"
        lines.append(f"║{row:<78}║")

    # Divergences
    if divergences:
        lines.append("╠" + "═" * 78 + "╣")
        lines.append(f"║  指标背离检测{' ' * 62}║")
        lines.append(f"║  {'─'*74}  ║")
        for alert in divergences[:6]:
            lines.append(f"║  {alert:<76}║")
    else:
        lines.append("╠" + "═" * 78 + "╣")
        lines.append(f"║  背离检测：当前窗口内未检出显著背离{' ' * 37}║")

    lines.append("╚" + "═" * 78 + "╝")
    return lines


# ─── Phase 4: Signal Performance Backtest ────────────────────────────────────

def evaluate_signal_performance(df: pd.DataFrame, signals: list[tuple]) -> list[tuple]:
    """Augment each signal with post-signal forward returns (1d/5d/10d).

    Returns list of (date, indicator, signal_name, ret_1d, ret_5d, ret_10d, hit).
    'hit' is True if 5d return is positive (for win-rate stats).
    """
    # Build date → index mapping
    df_r = df.reset_index(drop=True)
    date_idx = {str(row["trade_date"])[:10]: i for i, row in df_r.iterrows()}

    enhanced: list[tuple] = []
    for sig_date, sig_ind, sig_name in signals:
        idx = date_idx.get(sig_date)
        if idx is None:
            enhanced.append((sig_date, sig_ind, sig_name, None, None, None, None))
            continue

        close_now = df_r.iloc[idx]["close_val"]
        ret_1d = None
        ret_5d = None
        ret_10d = None

        if idx + 1 < len(df_r):
            ret_1d = (df_r.iloc[idx + 1]["close_val"] - close_now) / close_now * 100
        if idx + 5 < len(df_r):
            ret_5d = (df_r.iloc[idx + 5]["close_val"] - close_now) / close_now * 100
        if idx + 10 < len(df_r):
            ret_10d = (df_r.iloc[idx + 10]["close_val"] - close_now) / close_now * 100

        hit = ret_5d is not None and ret_5d > 0
        enhanced.append((sig_date, sig_ind, sig_name, ret_1d, ret_5d, ret_10d, hit))

    return enhanced


def _build_signal_radar_block(signals_perf: list[tuple]) -> list[str]:
    """Build signal radar with performance annotations."""
    lines = []
    lines.append("╔" + "═" * 78 + "╗")
    lines.append(f"║  信号雷达 (区间内){' ' * 57}║")
    lines.append("╠" + "═" * 78 + "╣")

    # Stats
    valid_hits = [s for s in signals_perf if s[6] is not None]
    if valid_hits:
        win_rate = sum(1 for s in valid_hits if s[6]) / len(valid_hits) * 100
        valid_5d = [s[4] for s in valid_hits if s[4] is not None]
        avg_5d = sum(valid_5d) / len(valid_5d) if valid_5d else 0.0
        header = f"  信号统计: 样本{len(valid_hits)}个  5日胜率:{win_rate:.0f}%  平均收益:{avg_5d:+.2f}%"
        lines.append(f"║{header:<78}║")
        lines.append(f"║  {'─'*74}  ║")

    if signals_perf:
        for sig in signals_perf:
            sig_date, sig_ind, sig_name, ret_1d, ret_5d, ret_10d, hit = sig
            base = f"  [{sig_date}] {sig_ind} {sig_name}"
            perf_parts = []
            if ret_1d is not None:
                perf_parts.append(f"1日{ret_1d:+.1f}%")
            if ret_5d is not None:
                perf_parts.append(f"5日{ret_5d:+.1f}%")
            if ret_10d is not None:
                perf_parts.append(f"10日{ret_10d:+.1f}%")
            if perf_parts:
                perf_str = " | ".join(perf_parts)
                line = f"{base:<50} {perf_str}"
            else:
                line = base
            lines.append(f"║{line:<78}║")
    else:
        lines.append(f"║  区间内无显著信号{' ' * 59}║")

    lines.append("╚" + "═" * 78 + "╝")
    return lines


# ─── Phase 3: Market Regime Detection + Adaptive Weights ─────────────────────

REGIME_PROFILES: dict[str, dict[str, Any]] = {
    "强趋势多头": {
        "weights": {"trend": 0.50, "momentum": 0.20, "volatility": 0.10, "volume": 0.20},
        "desc": "ADX强势，价格站上长期均线，顺趋势做多",
        "threshold_bonus": 0.3,  # 评分阈值上浮
    },
    "强趋势空头": {
        "weights": {"trend": 0.50, "momentum": 0.20, "volatility": 0.10, "volume": 0.20},
        "desc": "ADX强势，价格跌破长期均线，顺趋势做空/空仓",
        "threshold_bonus": 0.3,
    },
    "趋势回调": {
        "weights": {"trend": 0.40, "momentum": 0.25, "volatility": 0.15, "volume": 0.20},
        "desc": "中期趋势完好，短期回踩关键均线，关注止跌信号",
        "threshold_bonus": 0.0,
    },
    "震荡整理": {
        "weights": {"trend": 0.20, "momentum": 0.35, "volatility": 0.25, "volume": 0.20},
        "desc": "ADX弱势，布林带收窄，高抛低吸，不追趋势",
        "threshold_bonus": -0.3,
    },
    "低波动蓄势": {
        "weights": {"trend": 0.25, "momentum": 0.25, "volatility": 0.30, "volume": 0.20},
        "desc": "波动极低，方向未明，等待突破信号",
        "threshold_bonus": -0.3,
    },
    "普通趋势": {
        "weights": {"trend": 0.35, "momentum": 0.25, "volatility": 0.15, "volume": 0.25},
        "desc": "趋势中等强度，常规分析",
        "threshold_bonus": 0.0,
    },
}


def detect_market_regime(df: pd.DataFrame) -> tuple[str, dict[str, float]]:
    """Detect the current market regime based on trend/volatility/volume characteristics.

    Returns (regime_name, weights_dict).
    """
    n = len(df)
    if n < 20:
        return "普通趋势", REGIME_PROFILES["普通趋势"]["weights"].copy()

    # 1. ADX-based trend strength
    adx_mean = df["adx"].mean() if "adx" in df.columns else 20.0
    adx_trending = adx_mean > 25

    # 2. Long-term trend direction
    long_trend_bull = False
    long_trend_bear = False
    if "ma_250" in df.columns:
        ma250 = df["ma_250"].iloc[-1]
        close = df["close_val"].iloc[-1]
        if pd.notna(ma250):
            long_trend_bull = close > ma250
            long_trend_bear = close < ma250

    # 3. Volatility state
    bb_width_mean = df["bb_bandwidth"].mean() if "bb_bandwidth" in df.columns else 0.05
    atr_pct_mean = (df["atr_14"] / df["close_val"] * 100).mean() if "atr_14" in df.columns else 2.0
    low_vol = bb_width_mean < 0.05 and atr_pct_mean < 1.5
    high_vol = bb_width_mean > 0.10 or atr_pct_mean > 3.0

    # 4. Price vs short-term MAs
    ma_bull = False
    ma_bear = False
    if "ma_5" in df.columns and "ma_20" in df.columns:
        ma_bull = df["ma_5"].iloc[-1] > df["ma_20"].iloc[-1]
        ma_bear = df["ma_5"].iloc[-1] < df["ma_20"].iloc[-1]

    # Decision tree
    if adx_trending and long_trend_bull and ma_bull:
        regime = "强趋势多头"
    elif adx_trending and long_trend_bear and ma_bear:
        regime = "强趋势空头"
    elif low_vol and not adx_trending:
        regime = "低波动蓄势"
    elif not adx_trending and not long_trend_bull and not long_trend_bear:
        regime = "震荡整理"
    elif long_trend_bull and not ma_bull:
        regime = "趋势回调"
    elif long_trend_bear and not ma_bear:
        regime = "趋势回调"  # bear market bounce
    else:
        regime = "普通趋势"

    weights = REGIME_PROFILES[regime]["weights"].copy()
    return regime, weights


def _score_label_adaptive(val: float, regime: str) -> str:
    """Score label adjusted by market regime threshold."""
    bonus = REGIME_PROFILES.get(regime, {}).get("threshold_bonus", 0.0)
    adjusted = val + bonus

    if adjusted >= 8:
        return "强烈偏多"
    if adjusted >= 6.5:
        return "谨慎偏多"
    if adjusted >= 5.5:
        return "中性偏强"
    if adjusted >= 4.5:
        return "中性"
    if adjusted >= 3.5:
        return "中性偏弱"
    if adjusted >= 2:
        return "谨慎偏空"
    return "强烈偏空"


# ─── Phase 5: Action Plan Builder ──────────────────────────────────────────────

def build_action_plan(
    df: pd.DataFrame,
    scores: dict[str, float],
    regime: str,
    resonance: dict[str, dict[str, int]],
    tf_scores: dict[str, dict],
    div_alerts: list[str],
) -> list[str]:
    """Generate a concrete trading action plan based on all analysis results."""
    lines = []
    close = df["close_val"].iloc[-1]
    overall = scores.get("overall", 5.0)
    trend = scores.get("trend", 5.0)
    momentum = scores.get("momentum", 5.0)
    vol_risk = scores.get("volatility", 5.0)

    # ── 1. Determine action ──
    has_top_div = any("顶背离" in a for a in div_alerts)
    has_bot_div = any("底背离" in a for a in div_alerts)
    trend_bullish = trend >= 6.5
    trend_bearish = trend <= 4.0
    mom_bullish = momentum >= 6.5
    mom_bearish = momentum <= 4.0

    if overall >= 8 and regime in ("强趋势多头", "趋势回调") and trend_bullish and not has_top_div:
        action = "🚀 加仓做多 / 持有多头"
        action_detail = "多周期共振向上，趋势强劲，无顶背离警告"
    elif overall >= 6.5 and trend_bullish and mom_bullish and not has_top_div:
        action = "📈 轻仓试多"
        action_detail = "趋势与动量配合良好，可小仓位跟进"
    elif overall <= 3.5 and regime in ("强趋势空头",) and trend_bearish:
        action = "🔻 减仓 / 空仓观望"
        action_detail = "空头趋势明确，回避为主"
    elif overall <= 4.5 and has_top_div and trend_bearish:
        action = "⚠️ 减仓 / 止盈"
        action_detail = "顶背离+趋势转弱，锁定利润"
    elif overall <= 4.5 and has_bot_div and not trend_bearish:
        action = "🔍 关注低吸机会"
        action_detail = "底背离出现，等待确认信号后建仓"
    elif regime == "震荡整理":
        action = "➖ 高抛低吸 / 观望"
        action_detail = "震荡市不追趋势，区间内操作"
    elif regime == "低波动蓄势":
        action = "⏳ 等待突破"
        action_detail = "波动极低，方向未明，等待放量突破"
    else:
        action = "👁️ 观望"
        action_detail = "信号混杂，暂不开仓"

    # ── 2. Key levels ──
    # Support: recent 5-day low or BB lower (whichever is closer to close)
    recent_low = df["low_val"].tail(5).min()
    support = recent_low
    if "bb_lower" in df.columns:
        bb_low = df["bb_lower"].iloc[-1]
        support = max(support, bb_low)  # use the higher (closer) support

    # Resistance: recent 10-day high or BB upper
    recent_high = df["high_val"].tail(10).max()
    resistance = recent_high
    if "bb_upper" in df.columns:
        bb_up = df["bb_upper"].iloc[-1]
        resistance = max(resistance, bb_up)

    # Stop loss: ATR-based or below recent low (whichever is closer)
    atr = df["atr_14"].iloc[-1] if "atr_14" in df.columns else close * 0.02
    stop_loss = max(recent_low * 0.985, close - atr * 1.5)
    stop_pct = (stop_loss - close) / close * 100 if close else 0

    # Targets: ensure they are above current price
    target_1 = max(close * 1.03, close + (resistance - close) * 0.6)
    target_2 = max(close * 1.06, resistance)
    if "r1" in df.columns and pd.notna(df["r1"].iloc[-1]):
        target_1 = max(target_1, df["r1"].iloc[-1])
    if "r2" in df.columns and pd.notna(df["r2"].iloc[-1]):
        target_2 = max(target_2, df["r2"].iloc[-1])

    # ── 3. Position sizing ──
    if vol_risk >= 8:
        position = "10-20% (高波动，严控仓位)"
    elif overall >= 8:
        position = "30-50% (信号强，可重仓)"
    elif overall >= 6:
        position = "20-30% (信号中等，适度参与)"
    else:
        position = "10%以下 (信号弱，试探性)"

    # ── 4. Key observations ──
    observations: list[str] = []
    if has_top_div:
        observations.append("顶背离出现，警惕反转")
    if has_bot_div:
        observations.append("底背离出现，关注止跌")
    if vol_risk >= 8:
        observations.append("波动风险极高，缩小仓位")
    if momentum >= 8:
        observations.append("动量过热，注意回踩")
    if momentum <= 3:
        observations.append("动量低迷，等待修复")
    if trend_bullish and mom_bearish:
        observations.append("趋势向上但动量不足，或现分歧")
    if not observations:
        observations.append("各维度信号相对一致，按评分操作")

    # ── 5. Build output ──
    lines.append("╔" + "═" * 78 + "╗")
    lines.append(f"║  大师行动计划{' ' * 62}║")
    lines.append("╠" + "═" * 78 + "╣")
    lines.append(f"║  建议操作: {action:<56}║")
    lines.append(f"║  决策依据: {action_detail:<56}║")
    lines.append("╠" + "═" * 78 + "╣")
    lines.append(f"║  入场区间: {support:.2f} ~ {close:.2f} (当前){' ' * 40}║")
    lines.append(f"║  止损位:   {stop_loss:.2f}  ({stop_pct:+.1f}%){' ' * 46}║")
    lines.append(f"║  目标位1:  {target_1:.2f}  (潜在收益 {((target_1 - close) / close * 100):+.1f}%){' ' * 30}║")
    lines.append(f"║  目标位2:  {target_2:.2f}  (潜在收益 {((target_2 - close) / close * 100):+.1f}%){' ' * 30}║")
    lines.append("╠" + "═" * 78 + "╣")
    lines.append(f"║  仓位建议: {position:<58}║")
    lines.append(f"║  关键观察: {'; '.join(observations[:3]):<56}║")
    lines.append("╚" + "═" * 78 + "╝")
    return lines


def _bar(percent: float, width: int = 20) -> str:
    filled = int(round(percent / 100 * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def _score_label(val: float) -> str:
    if val >= 8:
        return "强烈偏多"
    if val >= 6.5:
        return "谨慎偏多"
    if val >= 5.5:
        return "中性偏强"
    if val >= 4.5:
        return "中性"
    if val >= 3.5:
        return "中性偏弱"
    if val >= 2:
        return "谨慎偏空"
    return "强烈偏空"


def _candle_pattern(row: pd.Series, prev: pd.Series | None) -> str:
    """Simple candlestick pattern annotation."""
    o, h, l, c = row["open_val"], row["high_val"], row["low_val"], row["close_val"]
    body = abs(c - o)
    rng = h - l if h != l else 1e-9
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    is_yang = c >= o

    # Doji
    if body / rng < 0.1:
        return "十字星"
    # Hammer / Hanging man
    if lower_shadow > body * 2 and upper_shadow < body * 0.5:
        return "锤子线" if not is_yang else "倒锤子"
    # Shooting star / inverted hammer
    if upper_shadow > body * 2 and lower_shadow < body * 0.5:
        return "流星线" if is_yang else "倒锤子"
    # Marubozu
    if upper_shadow < body * 0.05 and lower_shadow < body * 0.05:
        return "光头光脚"
    # Big candle
    if body / rng > 0.8:
        return "大阳线" if is_yang else "大阴线"
    # Gap
    if prev is not None:
        prev_high, prev_low = prev["high_val"], prev["low_val"]
        if l > prev_high:
            return "向上跳空"
        if h < prev_low:
            return "向下跳空"
    return "-"


# ─── Phase 6: Combo Candlestick Pattern Engine ─────────────────────────────────

def detect_combo_patterns(df: pd.DataFrame) -> list[tuple]:
    """Detect multi-bar candlestick patterns (engulfing, stars, three-crow/soldier).

    Returns list of (date, pattern_name, confirmation_note).
    """
    patterns: list[tuple] = []
    n = len(df)
    if n < 3:
        return patterns

    for i in range(2, n):
        r0 = df.iloc[i - 2]  # 3 bars ago
        r1 = df.iloc[i - 1]  # previous
        r2 = df.iloc[i]      # current

        o0, h0, l0, c0 = r0["open_val"], r0["high_val"], r0["low_val"], r0["close_val"]
        o1, h1, l1, c1 = r1["open_val"], r1["high_val"], r1["low_val"], r1["close_val"]
        o2, h2, l2, c2 = r2["open_val"], r2["high_val"], r2["low_val"], r2["close_val"]

        body0 = abs(c0 - o0)
        body1 = abs(c1 - o1)
        body2 = abs(c2 - o2)
        rng0 = h0 - l0 if h0 != l0 else 1e-9
        rng1 = h1 - l1 if h1 != l1 else 1e-9
        rng2 = h2 - l2 if h2 != l2 else 1e-9

        yang0, yang1, yang2 = c0 >= o0, c1 >= o1, c2 >= o2
        yin0, yin1, yin2 = not yang0, not yang1, not yang2

        date = str(r2["trade_date"])[:10]

        def _vol_confirm(cur_vol, prev_vol) -> str:
            if pd.isna(cur_vol) or pd.isna(prev_vol):
                return ""
            if cur_vol > prev_vol * 1.3:
                return "·放量确认"
            elif cur_vol < prev_vol * 0.7:
                return "·缩量"
            return "·量平"

        vol_note = _vol_confirm(r2.get("volume", np.nan), r1.get("volume", np.nan))

        # ── 2-bar patterns ──
        # Bullish Engulfing
        if yin1 and yang2 and o2 <= c1 and c2 >= o1 and body2 > body1 * 1.1:
            patterns.append((date, "看涨吞没", vol_note))
            continue
        # Bearish Engulfing
        if yang1 and yin2 and o2 >= c1 and c2 <= o1 and body2 > body1 * 1.1:
            patterns.append((date, "看跌吞没", vol_note))
            continue

        # ── 3-bar patterns ──
        # Morning Star (yin + small body + yang, with gap)
        if yin0 and body1 / rng1 < 0.3 and yang2:
            gap_down = c0 > o1 or h0 > l1  # loose gap condition
            gap_up = o2 > c1 or l2 > h1
            if gap_down and gap_up and c2 > (o0 + c0) / 2:
                patterns.append((date, "早晨之星", vol_note))
                continue

        # Evening Star (yang + small body + yin, with gap)
        if yang0 and body1 / rng1 < 0.3 and yin2:
            gap_up = c0 < o1 or l0 < h1
            gap_down = o2 < c1 or h2 < l1
            if gap_up and gap_down and c2 < (o0 + c0) / 2:
                patterns.append((date, "黄昏之星", vol_note))
                continue

        # Three White Soldiers
        if yang0 and yang1 and yang2:
            if c2 > c1 > c0 and o2 > o1 and o1 > o0:
                if body0 / rng0 > 0.5 and body1 / rng1 > 0.5 and body2 / rng2 > 0.5:
                    patterns.append((date, "白三兵", vol_note))
                    continue

        # Three Black Crows
        if yin0 and yin1 and yin2:
            if c2 < c1 < c0 and o2 < o1 and o1 < o0:
                if body0 / rng0 > 0.5 and body1 / rng1 > 0.5 and body2 / rng2 > 0.5:
                    patterns.append((date, "三只乌鸦", vol_note))
                    continue

    return patterns


def _build_combo_pattern_block(patterns: list[tuple]) -> list[str]:
    """Build the combo candlestick pattern panel."""
    lines = []
    lines.append("╔" + "═" * 78 + "╗")
    lines.append(f"║  组合K线形态识别{' ' * 60}║")
    lines.append("╠" + "═" * 78 + "╣")
    if patterns:
        for date, name, note in patterns[-10:]:  # last 10 patterns
            line = f"  [{date}] {name}{note}"
            lines.append(f"║{line:<78}║")
    else:
        lines.append(f"║  当前窗口内未检出显著组合形态{' ' * 46}║")
    lines.append("╚" + "═" * 78 + "╝")
    return lines


def _build_candle_section(df: pd.DataFrame) -> list[str]:
    """Build the K-line data overview section — print ALL bars."""
    lines = []
    lines.append("▌K线数据概览")
    lines.append("─" * 78)

    # --- Full bars table ---
    df_calc = df.copy()
    df_calc["change_pct"] = df_calc["close_val"].pct_change() * 100
    df_calc["amplitude_pct"] = (df_calc["high_val"] - df_calc["low_val"]) / df_calc["close_val"].shift(1) * 100

    lines.append(f"  全部 {len(df)} 根K线明细:")
    header = f"    {'日期':<12} {'开盘':>8} {'最高':>8} {'最低':>8} {'收盘':>8} {'涨跌%':>7} {'振幅%':>6} {'形态':<6}"
    lines.append(header)
    lines.append("    " + "-" * 66)

    for i in range(len(df_calc)):
        row = df_calc.iloc[i]
        prev_row = df_calc.iloc[i - 1] if i > 0 else None
        date_str = str(row["trade_date"])[:10]
        chg = row["change_pct"]
        amp = row["amplitude_pct"]
        chg_str = f"{chg:>+7.2f}" if pd.notna(chg) else "     -"
        amp_str = f"{amp:>6.2f}" if pd.notna(amp) else "    -"
        pattern = _candle_pattern(row, prev_row)
        lines.append(
            f"    {date_str:<12} {row['open_val']:>8.2f} {row['high_val']:>8.2f} "
            f"{row['low_val']:>8.2f} {row['close_val']:>8.2f} "
            f"{chg_str} {amp_str} {pattern:<6}"
        )

    # --- Overall statistics ---
    lines.append("")
    lines.append(f"  区间统计 ({len(df)}根K线):")

    total_return = (df["close_val"].iloc[-1] - df["close_val"].iloc[0]) / df["close_val"].iloc[0] * 100
    cummax = df["close_val"].cummax()
    drawdown = ((df["close_val"] - cummax) / cummax * 100).min()
    daily_ret = df["close_val"].pct_change().dropna()
    vol_ann = daily_ret.std() * np.sqrt(252) * 100 if len(daily_ret) > 1 else 0.0

    max_idx = df["high_val"].idxmax()
    min_idx = df["low_val"].idxmin()
    max_price = df.loc[max_idx, "high_val"]
    min_price = df.loc[min_idx, "low_val"]
    max_date = str(df.loc[max_idx, "trade_date"])[:10]
    min_date = str(df.loc[min_idx, "trade_date"])[:10]

    total_amount = df["amount"].sum() / 1e8 if "amount" in df.columns else 0.0
    avg_amount = total_amount / len(df) if len(df) > 0 else 0.0

    yang_count = (df["close_val"] >= df["open_val"]).sum()
    yin_count = len(df) - yang_count
    yang_pct = yang_count / len(df) * 100

    # Consecutive up/down days
    signs = np.sign(df["close_val"] - df["open_val"])
    max_consec_up = 0
    max_consec_down = 0
    cur_up = 0
    cur_down = 0
    for s in signs:
        if s >= 0:
            cur_up += 1
            cur_down = 0
            max_consec_up = max(max_consec_up, cur_up)
        else:
            cur_down += 1
            cur_up = 0
            max_consec_down = max(max_consec_down, cur_down)

    lines.append(f"    区间涨幅: {total_return:>+7.2f}%       最大回撤: {drawdown:>7.2f}%       年化波动率: {vol_ann:.2f}%")
    lines.append(f"    最高价: {max_price:.2f} ({max_date})    最低价: {min_price:.2f} ({min_date})")
    lines.append(f"    总成交额: {total_amount:,.1f}亿    日均成交额: {avg_amount:.2f}亿")
    lines.append(f"    阳线: {yang_count}根({yang_pct:.1f}%)    阴线: {yin_count}根({100-yang_pct:.1f}%)    最大连涨: {max_consec_up}天    最大连跌: {max_consec_down}天")

    return lines


def analyze(code: str, bars: int = 250, save: bool = False) -> str:
    lines = []

    # Resolve name → code if needed
    try:
        resolved_code = resolve_code(code)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    name = get_name(resolved_code)
    display_name = f"{resolved_code} ({name})" if name else resolved_code

    df_full = fetch_and_compute(resolved_code, bars)
    if df_full is None or df_full.empty:
        return f"[ERROR] No data found for {display_name}"

    # Primary analysis window (user-specified bars)
    df = df_full.iloc[-bars:].copy() if len(df_full) > bars else df_full.copy()

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else latest
    start_date = df["trade_date"].iloc[0]
    end_date = df["trade_date"].iloc[-1]
    close = latest["close_val"]
    prev_close = prev["close_val"]
    change_pct = (close - prev_close) / prev_close * 100 if prev_close else 0.0
    amplitude = (latest["high_val"] - latest["low_val"]) / prev_close * 100 if prev_close else 0.0
    amount = latest.get("amount", 0)

    # ─── Phase 3: Market Regime Detection ────────────────────────────────────
    regime, adaptive_weights = detect_market_regime(df)
    regime_info = REGIME_PROFILES.get(regime, {})

    # ─── Multi-Timeframe Analysis (Phase 1) ──────────────────────────────────
    tf_scores = calc_multi_timeframe_scores(df_full, bars, weights_override=adaptive_weights)
    divergences = detect_timeframe_divergence(tf_scores)

    # ─── Header ──────────────────────────────────────────────────────────────
    lines.append("╔" + "═" * 78 + "╗")
    lines.append(f"║  技术分析大师全量指标面板{' ' * 54}║")
    lines.append(f"║  股票: {display_name:<28}  区间: {start_date} ~ {end_date}  K线: {len(df):<4}  ║")
    lines.append(f"║  最新: {close:>10.2f}  涨跌: {change_pct:>+.2f}%  振幅: {amplitude:.2f}%  额: {amount/1e8:.2f}亿  ║")
    lines.append(f"║  市场环境: {regime:<12}  权重: 趋势{adaptive_weights['trend']:.0%} 动量{adaptive_weights['momentum']:.0%} 波动{adaptive_weights['volatility']:.0%} 量价{adaptive_weights['volume']:.0%}  ║")
    lines.append("╚" + "═" * 78 + "╝")
    lines.append("")

    # ─── Multi-Timeframe Fusion Panel ────────────────────────────────────────
    lines.extend(_build_multitimeframe_block(tf_scores, divergences))
    lines.append("")

    # ─── K-Line Data Section ─────────────────────────────────────────────────
    lines.extend(_build_candle_section(df))
    lines.append("")

    # ─── Phase 6: Combo Candlestick Patterns ─────────────────────────────────
    combo_patterns = detect_combo_patterns(df)
    if combo_patterns:
        lines.extend(_build_combo_pattern_block(combo_patterns))
        lines.append("")

    # ─── Indicator Layers ────────────────────────────────────────────────────
    for layer in INDICATOR_LAYERS:
        lines.append(f"▌{layer['title']}")
        lines.append("─" * 78)
        lines.append(f"  ({layer['desc']})")
        lines.append("")

        for ind in layer["indicators"]:
            # Check if indicator columns exist
            first_col = ind["cols"][0][0]
            if first_col not in df.columns:
                continue

            # Build value dict for formatting
            fmt_dict = {"close_val": close}
            for col, _ in ind["cols"]:
                fmt_dict[col] = latest.get(col, np.nan)

            # Add shifted values for context
            for shift in [1, 5]:
                if len(df) > shift:
                    for col, _ in ind["cols"]:
                        fmt_dict[f"{col}_shift{shift}"] = df.iloc[-shift - 1].get(col, np.nan)

            # Special derived fields
            if first_col == "atr_14":
                fmt_dict["atr_pct"] = latest.get("atr_14", 0) / close * 100 if close else 0
            if "supertrend_direction" in latest:
                fmt_dict["direction"] = "UP" if latest["supertrend_direction"] == -1 else "DOWN"

            # Format value line
            try:
                val_line = ind["format"].format(**fmt_dict)
            except (KeyError, ValueError):
                val_parts = [f"{label}:{_format_value(latest.get(col, np.nan))}" for col, label in ind["cols"]]
                val_line = "  ".join(val_parts)

            # State
            try:
                state = ind["state_fn"](fmt_dict)
            except Exception:
                state = "N/A"

            lines.append(f"  [{ind['priority']:>2}] {ind['name']} ({ind['name_zh']})")
            lines.append(f"       数值: {val_line}")
            lines.append(f"       状态: {state}")
            lines.append("")

    # ─── Period Technical Summary (use primary window scores already computed) ──
    scores = tf_scores["primary"]["scores"]
    period_summary = tf_scores["primary"]["summary"]
    lines.append("▌区间技术摘要")
    lines.append("─" * 78)
    lines.append(f"  {period_summary}")
    lines.append("")

    # ─── Phase 2: Resonance Radar + Divergence ───────────────────────────────
    resonance = build_resonance_radar(df)
    div_alerts = detect_divergence(df)
    lines.extend(_build_resonance_block(resonance, div_alerts))
    lines.append("")

    # ─── Signal Radar (Phase 4: with performance backtest) ─────────────────
    signals = build_signal_radar(df)
    signals_perf = evaluate_signal_performance(df, signals)
    lines.extend(_build_signal_radar_block(signals_perf))
    lines.append("")

    # ─── Phase 5: Action Plan ────────────────────────────────────────────────
    lines.extend(build_action_plan(df, scores, regime, resonance, tf_scores, div_alerts))
    lines.append("")

    # ─── Master Assessment ───────────────────────────────────────────────────
    lines.append("╔" + "═" * 78 + "╗")
    lines.append(f"║  大师综合研判{' ' * 62}║")
    lines.append("╠" + "═" * 78 + "╣")
    lines.append(f"║  趋势方向: {_bar(scores['trend'] / 10 * 100)}  {scores['trend']:.1f}/10{' ' * 10}║")
    lines.append(f"║  动量状态: {_bar(scores['momentum'] / 10 * 100)}  {scores['momentum']:.1f}/10{' ' * 10}║")
    lines.append(f"║  波动风险: {_bar(scores['volatility'] / 10 * 100)}  {scores['volatility']:.1f}/10  (越低越安全){' ' * 2}║")
    lines.append(f"║  量价配合: {_bar(scores['volume'] / 10 * 100)}  {scores['volume']:.1f}/10{' ' * 10}║")
    lines.append("╠" + "═" * 78 + "╣")
    overall = scores["overall"]
    label = _score_label_adaptive(overall, regime)
    lines.append(f"║  综合评分: {_bar(overall / 10 * 100)}  {overall:.1f}/10  [{label}]{' ' * 10}║")
    lines.append("╚" + "═" * 78 + "╝")

    text = "\n".join(lines)
    print(text)

    if save:
        out_dir = Path(ROOT) / "logs"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"master_{resolved_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        out_path.write_text(text, encoding="utf-8")
        print(f"\n[Saved] {out_path}")

    return text


def main():
    parser = argparse.ArgumentParser(description="Technical Analysis Master Panel")
    parser.add_argument("code", help="Stock code, e.g. 688018")
    parser.add_argument("--bars", "-b", type=int, default=250, help="Number of bars to analyze (default: 250)")
    parser.add_argument("--save", "-s", action="store_true", help="Save report to logs/")
    args = parser.parse_args()

    analyze(args.code, bars=args.bars, save=args.save)


if __name__ == "__main__":
    main()
