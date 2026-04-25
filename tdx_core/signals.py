# -*- coding: utf-8 -*-
"""交易信号引擎 — 从技术指标生成明确的 BUY/SELL/HOLD 信号.

Usage:
    from tdx_core.signals import SignalEngine
    from tdx_core import TdxQuery

    with TdxQuery() as q:
        engine = SignalEngine(q)
        sig = engine.generate("515180", "rsi30_bounce")
        print(sig.action)  # "BUY" / "SELL" / "HOLD"
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from .indicators import bollinger, macd, rsi as rsi_ind, atr, adx

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "logs" / "signal_history.json"


@dataclass
class Signal:
    """标准化交易信号."""
    action: Literal["BUY", "SELL", "HOLD", "WATCH"]
    strength: Literal["STRONG", "NORMAL", "WEAK"] = "NORMAL"
    confidence: float = 0.5  # 0.0 ~ 1.0
    strategy: str = ""
    triggers: list[str] = field(default_factory=list)
    rationale: str = ""
    risk_level: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    price: float = 0.0
    date: str = ""
    extra: dict = field(default_factory=dict)


class SignalEngine:
    """信号生成引擎."""

    def __init__(self, query):
        self._query = query
        self._history: dict | None = None

    # ─── 公共 API ─────────────────────────────────────────────────────────────

    def generate(self, code: str, strategy: str, **params) -> Signal:
        """为指定代码生成今日信号."""
        df = self._query.get_daily(code)
        if df is None or df.empty:
            return Signal(
                action="HOLD", confidence=0.0, strategy=strategy,
                rationale="无数据", date=datetime.now().strftime("%Y-%m-%d")
            )

        df = df.sort_values("trade_date").reset_index(drop=True)
        # 保留足够历史用于指标计算
        df = df.iloc[-260:].copy()
        for col in ["open_val", "high_val", "low_val", "close_val", "volume", "amount"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        today = df.iloc[-1]
        date_str = str(today["trade_date"])
        price = float(today["close_val"])

        # 路由到具体策略
        if strategy == "rsi30_bounce":
            sig = self._rsi30_bounce(df, params)
        elif strategy == "macd_golden":
            sig = self._macd_golden(df, params)
        elif strategy == "bollinger_bounce":
            sig = self._bollinger_bounce(df, params)
        elif strategy == "trend_follow":
            sig = self._trend_follow(df, params)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        sig.strategy = strategy
        sig.price = price
        sig.date = date_str
        return sig

    def get_history(self, code: str, strategy: str) -> list[dict]:
        """读取某代码某策略的历史信号."""
        data = self._load_history()
        return data.get(code, {}).get(strategy, [])

    def append_if_triggered(self, code: str, signal: Signal) -> bool:
        """如果信号是 BUY/SELL，追加到历史记录. 返回是否写入."""
        if signal.action not in ("BUY", "SELL"):
            return False
        data = self._load_history()
        data.setdefault(code, {}).setdefault(signal.strategy, [])
        # 避免同一天重复写入
        hist = data[code][signal.strategy]
        if hist and hist[-1].get("date") == signal.date and hist[-1].get("action") == signal.action:
            return False
        hist.append({
            "date": signal.date,
            "action": signal.action,
            "price": round(signal.price, 3),
            "strategy": signal.strategy,
        })
        self._save_history(data)
        return True

    def get_stats(self, code: str, strategy: str) -> dict:
        """计算策略历史信号统计."""
        hist = self.get_history(code, strategy)
        if not hist:
            return {}

        # 配对 BUY/SELL 计算盈亏
        trades = []
        buy_price = None
        buy_date = None
        for h in hist:
            if h["action"] == "BUY":
                buy_price = h["price"]
                buy_date = h["date"]
            elif h["action"] == "SELL" and buy_price is not None:
                pnl_pct = (h["price"] - buy_price) / buy_price * 100
                hold_days = self._days_diff(buy_date, h["date"])
                trades.append({
                    "buy_date": buy_date, "sell_date": h["date"],
                    "buy_price": buy_price, "sell_price": h["price"],
                    "pnl_pct": pnl_pct, "hold_days": hold_days,
                })
                buy_price = None

        if not trades:
            return {"total_signals": len(hist), "closed_trades": 0}

        wins = [t for t in trades if t["pnl_pct"] > 0]
        losses = [t for t in trades if t["pnl_pct"] <= 0]
        return {
            "total_signals": len(hist),
            "closed_trades": len(trades),
            "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
            "avg_pnl_pct": round(sum(t["pnl_pct"] for t in trades) / len(trades), 2),
            "avg_win_pct": round(sum(t["pnl_pct"] for t in wins) / len(wins), 2) if wins else 0,
            "avg_loss_pct": round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0,
            "avg_hold_days": round(sum(t["hold_days"] for t in trades) / len(trades), 1),
            "total_return_pct": round(sum(t["pnl_pct"] for t in trades), 2),
            "last_trade": trades[-1],
        }

    # ─── 策略实现 ─────────────────────────────────────────────────────────────

    def _rsi30_bounce(self, df: pd.DataFrame, params: dict) -> Signal:
        """RSI<30 买入，RSI>70 卖出."""
        rsi_buy = params.get("rsi_buy", 30)
        rsi_sell = params.get("rsi_sell", 70)
        period = params.get("period", 14)

        df = rsi_ind(df, period=period)
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else last
        rsi_val = float(last["rsi_14"])
        prev_rsi = float(prev["rsi_14"])
        price = float(last["close_val"])

        triggers = []
        action = "HOLD"
        confidence = 0.5
        rationale = f"RSI({period})={rsi_val:.1f}"

        # 买入：RSI 从下向上突破 30（超卖反弹）
        if prev_rsi < rsi_buy and rsi_val >= rsi_buy:
            action = "BUY"
            confidence = min(1.0, (rsi_buy - prev_rsi) / 20 + 0.6)
            triggers.append(f"RSI 从 {prev_rsi:.1f} 突破 {rsi_buy} 超卖线")
        # 卖出：RSI 从上向下突破 70（超买回落）
        elif prev_rsi > rsi_sell and rsi_val <= rsi_sell:
            action = "SELL"
            confidence = min(1.0, (prev_rsi - rsi_sell) / 20 + 0.6)
            triggers.append(f"RSI 从 {prev_rsi:.1f} 跌破 {rsi_sell} 超买线")
        else:
            dist_buy = rsi_val - rsi_buy
            dist_sell = rsi_sell - rsi_val
            if dist_buy < 0:
                triggers.append(f"RSI 处于超卖区 ({dist_buy:.1f} 点)")
                action = "WATCH"
                confidence = min(0.8, abs(dist_buy) / 30)
            elif dist_sell < 0:
                triggers.append(f"RSI 处于超买区 ({abs(dist_sell):.1f} 点)")
                action = "WATCH"
                confidence = min(0.8, abs(dist_sell) / 30)
            else:
                triggers.append(f"RSI 中性，距离买入/卖出阈值均 > {min(dist_buy, dist_sell):.1f} 点")

        return Signal(
            action=action, confidence=confidence, strategy="rsi30_bounce",
            triggers=triggers, rationale=rationale, risk_level="MEDIUM",
            extra={"rsi": rsi_val, "rsi_buy": rsi_buy, "rsi_sell": rsi_sell}
        )

    def _macd_golden(self, df: pd.DataFrame, params: dict) -> Signal:
        """MACD 金叉买入，死叉卖出."""
        df = macd(df, fast=12, slow=26, signal=9)
        df = adx(df, period=14)
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else last

        macd_val = float(last["macd"])
        macd_sig = float(last["macd_signal"])
        macd_hist = float(last["macd_hist"])
        prev_macd = float(prev["macd"])
        prev_sig = float(prev["macd_signal"])

        adx_val = float(last.get("adx", 20))
        plus_di = float(last.get("plus_di", 50))
        minus_di = float(last.get("minus_di", 50))

        triggers = []
        action = "HOLD"
        confidence = 0.5

        # 金叉：DIF 上穿 DEA
        golden = prev_macd <= prev_sig and macd_val > macd_sig
        death = prev_macd >= prev_sig and macd_val < macd_sig

        strength = "NORMAL"

        if golden:
            action = "BUY"
            confidence = 0.7
            triggers.append("MACD 金叉：DIF 上穿 DEA")
            if macd_val > 0 and adx_val > 25:
                strength = "STRONG"
                confidence = 0.95
                triggers.append("🔥 金叉在零轴上方 + ADX 强势确认（强烈买入）")
            elif macd_val > 0:
                strength = "NORMAL"
                confidence = 0.85
                triggers.append("金叉在零轴上方（强势）")
            elif adx_val > 25:
                strength = "NORMAL"
                confidence = 0.8
                triggers.append("金叉 + ADX 趋势确认")
            else:
                strength = "WEAK"
                confidence = 0.65
                triggers.append("金叉在零轴下方（偏弱）")
            if plus_di > minus_di:
                triggers.append("+DI > -DI，多头主导")
                confidence += 0.05
        elif death:
            action = "SELL"
            confidence = 0.7
            triggers.append("MACD 死叉：DIF 下穿 DEA")
            if macd_val < 0 and adx_val > 25:
                strength = "STRONG"
                confidence = 0.9
                triggers.append("🔥 死叉在零轴下方 + ADX 确认（强烈卖出）")
            elif macd_val < 0:
                strength = "NORMAL"
                confidence = 0.8
                triggers.append("死叉在零轴下方（弱势）")
            else:
                strength = "NORMAL"
                confidence = 0.75
        else:
            if macd_val > macd_sig:
                triggers.append(f"MACD 金叉维持，DIF={macd_val:.3f} > DEA={macd_sig:.3f}")
                action = "HOLD"
                confidence = 0.6
            else:
                triggers.append(f"MACD 死叉维持，DIF={macd_val:.3f} < DEA={macd_sig:.3f}")
                action = "HOLD"
                confidence = 0.4

        return Signal(
            action=action, strength=strength, confidence=min(1.0, confidence), strategy="macd_golden",
            triggers=triggers, rationale=f"MACD={macd_val:.3f}, DEA={macd_sig:.3f}, HIST={macd_hist:+.3f}",
            risk_level="MEDIUM" if adx_val < 25 else "HIGH",
            extra={"macd": macd_val, "macd_signal": macd_sig, "adx": adx_val}
        )

    def _bollinger_bounce(self, df: pd.DataFrame, params: dict) -> Signal:
        """布林带触及下轨买入，触及上轨卖出."""
        df = bollinger(df, period=20, std_dev=2.0)
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else last

        close = float(last["close_val"])
        bb_upper = float(last["bb_upper"])
        bb_lower = float(last["bb_lower"])
        bb_pctb = float(last["bb_pctb"])
        prev_close = float(prev["close_val"])
        prev_lower = float(prev["bb_lower"])
        prev_upper = float(prev["bb_upper"])

        triggers = []
        action = "HOLD"
        confidence = 0.5

        # 买入：价格触及或跌破下轨后反弹
        if prev_close <= prev_lower and close > prev_lower:
            action = "BUY"
            confidence = 0.75
            triggers.append(f"价格触及下轨 {bb_lower:.3f} 后反弹")
        # 卖出：价格触及或突破上轨后回落
        elif prev_close >= prev_upper and close < prev_upper:
            action = "SELL"
            confidence = 0.75
            triggers.append(f"价格触及上轨 {bb_upper:.3f} 后回落")
        else:
            if close <= bb_lower:
                triggers.append(f"价格跌破下轨 ({bb_pctb:.2f}%B)")
                action = "WATCH"
                confidence = 0.7
            elif close >= bb_upper:
                triggers.append(f"价格突破上轨 ({bb_pctb:.2f}%B)")
                action = "WATCH"
                confidence = 0.7
            else:
                triggers.append(f"价格在中轨附近 ({bb_pctb:.2f}%B)")

        return Signal(
            action=action, confidence=confidence, strategy="bollinger_bounce",
            triggers=triggers, rationale=f"%B={bb_pctb:.3f}, 上轨={bb_upper:.3f}, 下轨={bb_lower:.3f}",
            risk_level="MEDIUM",
            extra={"bb_pctb": bb_pctb, "bb_upper": bb_upper, "bb_lower": bb_lower}
        )

    def _trend_follow(self, df: pd.DataFrame, params: dict) -> Signal:
        """均线多头排列买入，空头排列卖出."""
        df["ma5"] = df["close_val"].rolling(window=5, min_periods=1).mean()
        df["ma10"] = df["close_val"].rolling(window=10, min_periods=1).mean()
        df["ma20"] = df["close_val"].rolling(window=20, min_periods=1).mean()
        df["ma60"] = df["close_val"].rolling(window=60, min_periods=1).mean()

        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else last

        c = float(last["close_val"])
        ma5, ma10, ma20, ma60 = float(last["ma5"]), float(last["ma10"]), float(last["ma20"]), float(last["ma60"])
        p_c = float(prev["close_val"])
        p_ma5, p_ma10, p_ma20 = float(prev["ma5"]), float(prev["ma10"]), float(prev["ma20"])

        triggers = []
        action = "HOLD"
        confidence = 0.5

        bull_now = c > ma5 > ma10 > ma20
        bull_prev = p_c > p_ma5 > p_ma10 > p_ma20
        bear_now = c < ma5 < ma10 < ma20
        bear_prev = p_c < p_ma5 < p_ma10 < p_ma20

        if bull_now and not bull_prev:
            action = "BUY"
            confidence = 0.8
            triggers.append("均线多头排列形成：MA5>MA10>MA20，价格站上所有均线")
        elif bear_now and not bear_prev:
            action = "SELL"
            confidence = 0.8
            triggers.append("均线空头排列形成：MA5<MA10<MA20，价格跌破所有均线")
        elif bull_now:
            triggers.append("多头排列维持")
            action = "HOLD"
            confidence = 0.65
        elif bear_now:
            triggers.append("空头排列维持")
            action = "HOLD"
            confidence = 0.35
        else:
            triggers.append("均线纠缠/整理中")
            action = "HOLD"
            confidence = 0.5

        return Signal(
            action=action, confidence=confidence, strategy="trend_follow",
            triggers=triggers, rationale=f"MA5={ma5:.3f}, MA10={ma10:.3f}, MA20={ma20:.3f}, MA60={ma60:.3f}",
            risk_level="MEDIUM",
            extra={"ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60}
        )

    # ─── 历史记录管理 ─────────────────────────────────────────────────────────

    def _load_history(self) -> dict:
        if self._history is not None:
            return self._history
        if HISTORY_PATH.exists():
            try:
                self._history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
                return self._history
            except Exception as exc:
                logger.warning("Failed to load signal history: %s", exc)
        self._history = {}
        return self._history

    def _save_history(self, data: dict):
        self._history = data
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    @staticmethod
    def _days_diff(d1: str, d2: str) -> int:
        """计算两个日期字符串之间的天数差."""
        try:
            a = datetime.strptime(str(d1)[:10], "%Y-%m-%d")
            b = datetime.strptime(str(d2)[:10], "%Y-%m-%d")
            return abs((b - a).days)
        except Exception:
            return 0
