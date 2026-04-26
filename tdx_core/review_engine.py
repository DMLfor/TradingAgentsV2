"""每日市场复盘引擎 — 基于 TDX 数据生成结构化复盘数据.

Usage:
    from tdx_core import TdxQuery
    from tdx_core.review_engine import DailyReviewEngine

    with TdxQuery() as q:
        engine = DailyReviewEngine(q, date="2026-04-25")
        overview = engine.market_overview()
        heatmap = engine.sector_heatmap()
        sentiment = engine.sentiment_gauge()
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from . import TdxIndicators, TdxQuery, get_name, get_meta
from .indicators import atr, bollinger, macd, rsi

logger = logging.getLogger(__name__)

# ─── 默认配置 ─────────────────────────────────────────────────────────────────

DEFAULT_INDICES: dict[str, str] = {
    "000001": "上证指数",
    "399001": "深证成指",
    "399006": "创业板指",
    "000016": "上证50",
    "000300": "沪深300",
    "000905": "中证500",
    "000852": "中证1000",
    "000688": "科创50",
}

DEFAULT_ETF_CODES = ["515180", "159545"]

# 情绪档位阈值（基于上涨家数占比 up_ratio 为主，涨停数为辅）
SENTIMENT_ADVICE = {
    "冰点": "市场极度恐慌，空仓或极小仓位试错",
    "低迷": "亏钱效应明显，控制仓位在3成以下",
    "谨慎": "方向不明，观望为主，仓位3-5成",
    "中性": "结构性机会，精选个股，仓位5-7成",
    "活跃": "赚钱效应扩散，积极参与，仓位7-8成",
    "过热": "情绪高潮，逐步减仓锁定利润，仓位5成以下",
}


# ─── 辅助函数：ETF 分析 ───────────────────────────────────────────────────────


def _calc_vol_percentile(atr_series: pd.Series, window: int = 60) -> float:
    """计算当前 ATR 在滚动窗口中的百分位 (0~1)."""
    if len(atr_series) < window + 1:
        return float("nan")
    current = float(atr_series.iloc[-1])
    hist = atr_series.iloc[-window:-1].dropna().astype(float)
    if len(hist) == 0:
        return float("nan")
    return float((hist < current).sum() / len(hist))


def _generate_etf_grid(center: float, atr_val: float, step_mult: float,
                       grid_count: int, grid_dir: str) -> dict:
    """生成 ETF 动态网格档位."""
    step = atr_val * step_mult
    result: dict[str, Any] = {"center": round(center, 3), "step": round(step, 3)}
    if grid_dir == "buy_only":
        result["buy_levels"] = [round(center - i * step, 3) for i in range(1, grid_count + 1)]
        result["sell_levels"] = []
        result["note"] = "强趋势向上，暂停卖出网格，防止卖飞"
    elif grid_dir == "sell_only":
        result["buy_levels"] = []
        result["sell_levels"] = [round(center + i * step, 3) for i in range(1, grid_count + 1)]
        result["note"] = "强趋势向下，暂停买入网格，保留现金"
    else:
        result["buy_levels"] = [round(center - i * step, 3) for i in range(1, grid_count + 1)]
        result["sell_levels"] = [round(center + i * step, 3) for i in range(1, grid_count + 1)]
        result["note"] = "标准双向网格"
    return result


def _analyze_etf(code: str, query: TdxQuery, end_date: str | None = None) -> dict | None:
    """分析单个 ETF，返回趋势状态和网格参数."""
    try:
        df = query.get_daily(code, end_date=end_date)
        if df is None or df.empty or len(df) < 60:
            return None

        df = df.sort_values("trade_date").reset_index(drop=True)
        if end_date and not df.empty and str(df.iloc[-1]["trade_date"]) != end_date:
            # end_date 无数据，向前找最近一天
            df = df[df["trade_date"] <= end_date]
        df = df.iloc[-120:].copy()
        for col in ["open_val", "high_val", "low_val", "close_val", "volume", "amount"]:
            if col in df.columns:
                df[col] = df[col].astype(float)

        df = bollinger(df, period=20, std_dev=2.0)
        df = atr(df, period=14)
        df = rsi(df, period=14)
        df = macd(df, fast=12, slow=26, signal=9)
        df["ma20"] = df["close_val"].rolling(window=20, min_periods=1).mean()
        df["ma60"] = df["close_val"].rolling(window=60, min_periods=1).mean()
        df["atr_pct"] = df["atr_14"] / df["close_val"] * 100

        # 简化 ADX
        from tdx_core.indicators._core import true_range
        tr = true_range(df["high_val"], df["low_val"], df["close_val"])
        atr_val = tr.ewm(alpha=1.0 / 14, adjust=False).mean()
        plus_dm = (df["high_val"] - df["high_val"].shift(1)).clip(lower=0)
        minus_dm = (df["low_val"].shift(1) - df["low_val"]).clip(lower=0)
        plus_dm = plus_dm.where(plus_dm > minus_dm, 0)
        minus_dm = minus_dm.where(minus_dm > plus_dm, 0)
        plus_di = 100 * plus_dm.ewm(alpha=1.0 / 14, adjust=False).mean() / atr_val
        minus_di = 100 * minus_dm.ewm(alpha=1.0 / 14, adjust=False).mean() / atr_val
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        df["adx"] = dx.ewm(alpha=1.0 / 14, adjust=False).mean()
        df["plus_di"] = plus_di
        df["minus_di"] = minus_di

        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else last

        close = float(last["close_val"])
        ma20 = float(last["ma20"])
        ma60 = float(last["ma60"])
        macd_val = float(last["macd"])
        macd_signal = float(last["macd_signal"])
        macd_hist = float(last["macd_hist"])
        adx = float(last["adx"])
        plus_di_val = float(last["plus_di"])
        minus_di_val = float(last["minus_di"])
        rsi_val = float(last["rsi_14"])
        bb_pctb = float(last["bb_pctb"])
        atr_pct = float(last["atr_pct"])

        ma_bull = close > ma20 > ma60
        ma_bear = close < ma20 < ma60
        trend_score = 8.0 if ma_bull else (3.0 if ma_bear else 5.0)

        macd_bull = macd_val > macd_signal and macd_hist > float(prev.get("macd_hist", macd_hist))
        macd_bear = macd_val < macd_signal and macd_hist < float(prev.get("macd_hist", macd_hist))
        macd_score = 8.0 if macd_bull else (3.0 if macd_bear else 5.0)

        if adx > 30:
            adx_score = 8.0 if plus_di_val > minus_di_val else 2.0
        elif adx > 20:
            adx_score = 6.5 if plus_di_val > minus_di_val else 3.5
        else:
            adx_score = 5.0

        avg_trend = (trend_score + macd_score + adx_score) / 3

        if rsi_val > 70:
            momentum_score = 8.0
        elif rsi_val > 55:
            momentum_score = 6.5
        elif rsi_val > 45:
            momentum_score = 5.0
        elif rsi_val > 30:
            momentum_score = 3.5
        else:
            momentum_score = 2.0

        vol_pct = _calc_vol_percentile(df["atr_14"], window=60)
        vol_score = (1.0 - vol_pct) * 10.0 if not np.isnan(vol_pct) else 5.0

        if avg_trend >= 7.0 and momentum_score >= 6.0:
            state, state_zh, core_pct, grid_pct, grid_dir, step_mult = (
                "STRONG_UP", "强趋势向上", 0.80, 0.20, "buy_only", 1.0
            )
        elif avg_trend >= 6.0:
            state, state_zh, core_pct, grid_pct, grid_dir, step_mult = (
                "WEAK_UP", "弱趋势向上", 0.70, 0.30, "both", 0.9
            )
        elif avg_trend >= 4.5 and vol_score >= 6.0:
            state, state_zh, core_pct, grid_pct, grid_dir, step_mult = (
                "CONSOLIDATE", "震荡整理", 0.60, 0.40, "both", 0.6
            )
        elif avg_trend >= 3.5:
            state, state_zh, core_pct, grid_pct, grid_dir, step_mult = (
                "WEAK_DOWN", "弱趋势向下", 0.60, 0.40, "both", 1.2
            )
        else:
            state, state_zh, core_pct, grid_pct, grid_dir, step_mult = (
                "STRONG_DOWN", "强趋势向下", 0.50, 0.50, "sell_only", 1.5
            )

        grid = _generate_etf_grid(ma20, float(last["atr_14"]), step_mult, 3, grid_dir)

        return {
            "code": code,
            "name": get_name(code) or code,
            "state": state,
            "state_zh": state_zh,
            "trend_score": round(avg_trend, 2),
            "momentum_score": round(momentum_score, 2),
            "vol_score": round(vol_score, 2),
            "vol_pct": round(float(vol_pct) * 100, 1) if not np.isnan(vol_pct) else None,
            "core_pct": core_pct,
            "grid_pct": grid_pct,
            "grid_dir": grid_dir,
            "close": close,
            "ma20": ma20,
            "rsi": rsi_val,
            "bb_pctb": bb_pctb,
            "atr_pct": atr_pct,
            "grid": grid,
        }
    except Exception as exc:
        logger.debug("ETF 分析失败 %s: %s", code, exc)
        return None


# ─── 辅助函数：回撤选股 ───────────────────────────────────────────────────────


def _compute_pullback_scores(df: pd.DataFrame) -> dict[str, float] | None:
    """计算 5 因子回撤评分 (0~100)."""
    if df is None or df.empty or len(df) < 30:
        return None

    latest = df.iloc[-1]
    required_cols = ["ma_5", "ma_20", "ma_60", "macd", "rsi_14", "volume"]
    for col in required_cols:
        if col not in df.columns:
            return None

    close = float(latest["close_val"])
    ma_60 = latest["ma_60"]
    ma_5 = latest["ma_5"]
    scores: dict[str, float] = {}

    # 1. Trend (0~25)
    trend = 0.0
    if pd.notna(ma_60) and close > ma_60:
        trend += 15.0
    ma_60_5ago = df["ma_60"].iloc[-6] if len(df) >= 6 else df["ma_60"].iloc[0]
    if pd.notna(ma_60) and pd.notna(ma_60_5ago) and ma_60 > ma_60_5ago:
        trend += 10.0
    scores["trend"] = max(0.0, min(25.0, trend))

    # 2. Pullback (0~25)
    recent_20_high = df["high_val"].tail(20).max()
    pullback = 0.0
    if recent_20_high and recent_20_high > 0:
        pullback_pct = (recent_20_high - close) / recent_20_high * 100
        if 5 <= pullback_pct <= 15:
            pullback = 25.0
        elif 3 <= pullback_pct < 5:
            pullback = 18.0
        elif 15 < pullback_pct <= 25:
            pullback = 12.0
        elif pullback_pct > 25:
            pullback = 5.0
        elif 0 <= pullback_pct < 3:
            pullback = 8.0
    if pd.notna(ma_5) and close < ma_5:
        pullback += 3.0
    scores["pullback"] = max(0.0, min(25.0, pullback))

    # 3. Oversold (0~20)
    rsi = latest["rsi_14"]
    oversold = 0.0
    if pd.notna(rsi):
        if 30 <= rsi <= 50:
            oversold = 20.0
        elif 50 < rsi <= 55:
            oversold = 12.0
        elif 25 <= rsi < 30:
            oversold = 10.0
        elif rsi < 25:
            oversold = 3.0
        elif 55 < rsi <= 65:
            oversold = 5.0
    scores["oversold"] = max(0.0, min(20.0, oversold))

    # 4. Volume (0~15)
    vol = latest["volume"]
    vol_ma20 = df["volume"].tail(20).mean()
    volume_score = 0.0
    if vol_ma20 and vol_ma20 > 0 and pd.notna(vol):
        vol_ratio = vol / vol_ma20
        if vol_ratio < 0.7:
            volume_score = 15.0
        elif vol_ratio < 0.9:
            volume_score = 12.0
        elif vol_ratio < 1.0:
            volume_score = 8.0
        elif vol_ratio < 1.2:
            volume_score = 4.0
    scores["volume"] = max(0.0, min(15.0, volume_score))

    # 5. Momentum (0~15)
    macd_val = latest["macd"]
    momentum = 0.0
    if pd.notna(macd_val):
        if macd_val > 0:
            momentum = 15.0
        elif macd_val > -0.5:
            momentum = 8.0
        else:
            momentum = 3.0
    scores["momentum"] = max(0.0, min(15.0, momentum))

    return scores


def _generate_pullback_plan(df: pd.DataFrame, scores: dict[str, float],
                            code: str, name: str) -> dict | None:
    """生成回撤选股交易计划 (返回 dict 而非 dataclass)."""
    if not scores or df is None or df.empty:
        return None

    latest = df.iloc[-1]
    close = float(latest["close_val"])
    ma_60 = latest.get("ma_60", float("nan"))
    recent_20_high = df["high_val"].tail(20).max()
    recent_20_low = df["low_val"].tail(20).min()

    entry = close
    stop_from_low = recent_20_low * (1.0 - 3.0 / 100.0) if recent_20_low else close * 0.97
    if pd.notna(ma_60):
        stop = max(float(ma_60), stop_from_low)
    else:
        stop = stop_from_low
    target = recent_20_high if recent_20_high else close * 1.05

    if entry > stop and target > entry:
        risk_reward = (target - entry) / (entry - stop)
    else:
        risk_reward = 0.0

    total = sum(scores.values())
    if total >= 80 and risk_reward >= 2.0:
        pos = "重仓 60-80%"
    elif total >= 65 and risk_reward >= 1.5:
        pos = "中等 30-50%"
    elif total >= 55 and risk_reward >= 1.2:
        pos = "轻仓 10-20%"
    else:
        pos = "观望"

    return {
        "code": code,
        "name": name or code,
        "trend_score": round(scores.get("trend", 0), 1),
        "pullback_score": round(scores.get("pullback", 0), 1),
        "oversold_score": round(scores.get("oversold", 0), 1),
        "volume_score": round(scores.get("volume", 0), 1),
        "momentum_score": round(scores.get("momentum", 0), 1),
        "total_score": round(total, 1),
        "entry_price": round(entry, 2),
        "stop_price": round(stop, 2),
        "target_price": round(target, 2),
        "risk_reward": round(risk_reward, 2),
        "position_suggestion": pos,
        "close_price": round(close, 2),
    }


# ─── 核心引擎 ─────────────────────────────────────────────────────────────────


class DailyReviewEngine:
    """每日技术复盘引擎."""

    def __init__(self, query: TdxQuery, date: str | None = None):
        self.q = query
        self.date = date or datetime.now().strftime("%Y-%m-%d")
        self._effective_date: str | None = None
        self._prev_date: str | None = None
        self._market_df: pd.DataFrame | None = None

    # ── 内部工具 ──

    def _resolve_effective_date(self) -> str:
        """解析有效交易日：self.date 若数据充足则直接用，否则向前回退到最近一个数据完整的交易日."""
        if self._effective_date is not None:
            return self._effective_date

        # 1) 先检查用户指定的日期
        if self.q.config.db_type == "mysql":
            sql = "SELECT COUNT(*) as cnt FROM tdx_daily WHERE trade_date = %s"
        else:
            sql = "SELECT COUNT(*) as cnt FROM tdx_daily WHERE trade_date = ?"
        df = self.q.execute(sql, (self.date,))
        cnt = int(df["cnt"].iloc[0])
        if cnt > 100:
            self._effective_date = self.date
            return self._effective_date

        # 2) 往前 10 天找数据充足的日期
        if self.q.config.db_type == "mysql":
            sql = """
                SELECT trade_date, COUNT(*) as cnt 
                FROM tdx_daily 
                WHERE trade_date <= %s AND trade_date >= DATE_SUB(%s, INTERVAL 10 DAY)
                GROUP BY trade_date
                HAVING COUNT(*) > 100
                ORDER BY trade_date DESC
                LIMIT 1
            """
        else:
            sql = """
                SELECT trade_date, COUNT(*) as cnt 
                FROM tdx_daily 
                WHERE trade_date <= ? AND trade_date >= date(?, '-10 days')
                GROUP BY trade_date
                HAVING COUNT(*) > 100
                ORDER BY trade_date DESC
                LIMIT 1
            """
        df = self.q.execute(sql, (self.date, self.date))
        if not df.empty:
            self._effective_date = str(df["trade_date"].iloc[0])
            return self._effective_date

        # 3) fallback: 数据库 MAX(trade_date)
        df = self.q.execute("SELECT MAX(trade_date) as max_date FROM tdx_daily")
        self._effective_date = str(df["max_date"].iloc[0])
        return self._effective_date

    def _get_prev_trade_date(self) -> str:
        if self._prev_date is not None:
            return self._prev_date
        latest = self._resolve_effective_date()
        if self.q.config.db_type == "mysql":
            sql = "SELECT MAX(trade_date) as prev_date FROM tdx_daily WHERE trade_date < %s"
        else:
            sql = "SELECT MAX(trade_date) as prev_date FROM tdx_daily WHERE trade_date < ?"
        df = self.q.execute(sql, (latest,))
        self._prev_date = str(df["prev_date"].iloc[0])
        return self._prev_date

    def _fetch_recent_days(self, days: int = 5) -> pd.DataFrame:
        """获取最近 N 个交易日的全市场数据（含涨跌幅）."""
        effective_date = self._resolve_effective_date()

        # 获取最近 days+1 个有效交易日（多取1天用于计算第一天的涨跌幅）
        if self.q.config.db_type == "mysql":
            sql = """
                SELECT trade_date FROM (
                    SELECT DISTINCT trade_date
                    FROM tdx_daily
                    WHERE trade_date <= %s AND trade_date >= DATE_SUB(%s, INTERVAL 20 DAY)
                    ORDER BY trade_date DESC
                    LIMIT %s
                ) t ORDER BY trade_date ASC
            """
        else:
            sql = """
                SELECT trade_date FROM (
                    SELECT DISTINCT trade_date
                    FROM tdx_daily
                    WHERE trade_date <= ? AND trade_date >= date(?, '-20 days')
                    ORDER BY trade_date DESC
                    LIMIT ?
                ) ORDER BY trade_date ASC
            """
        date_df = self.q.execute(sql, (effective_date, effective_date, days + 1))
        dates = [str(d) for d in date_df["trade_date"].tolist()]

        if len(dates) < 2:
            return pd.DataFrame()

        # 获取这些日期的所有股票数据
        placeholders = ",".join(["?"] * len(dates)) if self.q.config.db_type != "mysql" else ",".join(["%s"] * len(dates))
        if self.q.config.db_type == "mysql":
            sql = f"""
                SELECT code, trade_date, close_val, volume, amount
                FROM tdx_daily
                WHERE trade_date IN ({placeholders})
                ORDER BY code, trade_date
            """
        else:
            sql = f"""
                SELECT code, trade_date, close_val, volume, amount
                FROM tdx_daily
                WHERE trade_date IN ({placeholders})
                ORDER BY code, trade_date
            """
        df = self.q.execute(sql, tuple(dates))
        for col in ["close_val", "volume", "amount"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # 计算每只股票的 prev_close 和 change_pct
        df = df.sort_values(["code", "trade_date"])
        df["prev_close"] = df.groupby("code")["close_val"].shift(1)
        df["change_pct"] = (df["close_val"] - df["prev_close"]) / df["prev_close"] * 100
        df["change_pct"] = df["change_pct"].replace([np.inf, -np.inf], np.nan)
        df["data_anomaly"] = df["change_pct"].abs() > 50

        return df

    def _fetch_all_latest(self) -> pd.DataFrame:
        """获取全市场最新日数据（含涨跌幅）."""
        if self._market_df is not None:
            return self._market_df

        effective_date = self._resolve_effective_date()
        df = self._fetch_recent_days(1)
        if df.empty:
            self._market_df = pd.DataFrame()
            return self._market_df

        # 只保留最新一天的数据（trade_date 可能是 datetime/date 对象，统一转字符串比较）
        df = df[df["trade_date"].astype(str) == effective_date].copy()
        self._market_df = df
        return df

    # ── 大盘环境 ──

    def market_overview(self, indices: dict[str, str] | None = None) -> list[dict]:
        """分析主要宽基指数的技术面状态."""
        indices = indices or DEFAULT_INDICES
        results: list[dict] = []
        effective_date = self._resolve_effective_date()

        for code, name in indices.items():
            try:
                df = self.q.get_daily(code, end_date=effective_date)
                if df is None or df.empty or len(df) < 60:
                    continue
                df = df.sort_values("trade_date").reset_index(drop=True)
                df = df.iloc[-60:].copy()
                for col in ["open_val", "high_val", "low_val", "close_val", "volume", "amount"]:
                    if col in df.columns:
                        df[col] = df[col].astype(float)

                df = TdxIndicators.compute(df, indicators=["ma", "macd", "rsi"])
                last = df.iloc[-1]

                close = float(last["close_val"])
                prev_close = float(df.iloc[-2]["close_val"]) if len(df) >= 2 else close
                change_pct = (close - prev_close) / prev_close * 100
                data_anomaly = abs(change_pct) > 50

                # 量比
                vol = float(last["volume"])
                vol_ma5 = df["volume"].tail(5).mean()
                vol_ma10 = df["volume"].tail(10).mean()
                vol_ratio_5 = vol / vol_ma5 if vol_ma5 and vol_ma5 > 0 else 1.0
                vol_ratio_10 = vol / vol_ma10 if vol_ma10 and vol_ma10 > 0 else 1.0

                # 均线状态
                ma5 = last.get("ma_5")
                ma10 = last.get("ma_10")
                ma20 = last.get("ma_20")
                ma60 = last.get("ma_60")
                try:
                    ma_bull = close > ma5 > ma10 > ma20 > ma60
                    ma_bear = close < ma5 < ma10 < ma20 < ma60
                    if ma_bull:
                        ma_state = "多头排列"
                    elif ma_bear:
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
                rsi_val = float(last.get("rsi_14", 50))

                results.append({
                    "code": code,
                    "name": name,
                    "close": round(close, 2),
                    "change_pct": round(change_pct, 2),
                    "volume": round(vol, 0),
                    "amount": round(float(last.get("amount", 0)), 0),
                    "vol_ratio_5": round(vol_ratio_5, 2),
                    "vol_ratio_10": round(vol_ratio_10, 2),
                    "ma_state": ma_state,
                    "macd_state": macd_state,
                    "rsi": round(rsi_val, 1),
                    "data_anomaly": data_anomaly,
                })
            except Exception as exc:
                logger.debug("大盘分析失败 %s: %s", code, exc)
                continue

        return results

    # ── 市场风格 ──

    def market_style(self) -> dict:
        """判断大盘vs小盘风格."""
        try:
            effective_date = self._resolve_effective_date()
            df_large = self.q.get_daily("000300", end_date=effective_date)
            df_small = self.q.get_daily("000852", end_date=effective_date)
            if df_large is None or df_small is None or len(df_large) < 20 or len(df_small) < 20:
                return {"style": "未知", "large_return": None, "small_return": None}

            df_large = df_large.sort_values("trade_date").reset_index(drop=True)
            df_small = df_small.sort_values("trade_date").reset_index(drop=True)

            large_ret = (float(df_large.iloc[-1]["close_val"]) / float(df_large.iloc[-20]["close_val"]) - 1) * 100
            small_ret = (float(df_small.iloc[-1]["close_val"]) / float(df_small.iloc[-20]["close_val"]) - 1) * 100

            if abs(large_ret) > 100 or abs(small_ret) > 100:
                return {
                    "style": "数据异常",
                    "large_return": None,
                    "small_return": None,
                    "diff": None,
                }

            diff = large_ret - small_ret
            if diff > 2.0:
                style = "大盘蓝筹占优"
            elif diff < -2.0:
                style = "小盘成长占优"
            else:
                style = "风格均衡"

            return {
                "style": style,
                "large_return": round(large_ret, 2),
                "small_return": round(small_ret, 2),
                "diff": round(diff, 2),
            }
        except Exception as exc:
            logger.debug("市场风格判断失败: %s", exc)
            return {"style": "未知", "large_return": None, "small_return": None}

    # ── 趋势评分（历史趋势结合当天，防追涨杀跌） ──

    def _market_trend_score(self) -> dict:
        """基于8大宽基指数的综合技术面 + 历史位置感，计算趋势评分."""
        effective_date = self._resolve_effective_date()
        overview = self.market_overview()
        if not overview:
            return {"trend_score": 0, "stage": "未知", "details": []}

        # 1A. 即时技术面评分（基于 market_overview 结果）
        instant_scores = []
        weights = {
            "000001": 0.20, "000300": 0.20, "399006": 0.15,
            "000016": 0.10, "399001": 0.10, "000905": 0.10,
            "000852": 0.10, "000688": 0.05,
        }
        for item in overview:
            code = item["code"]
            w = weights.get(code, 0.05)
            s = 0.0
            # 均线
            if item["ma_state"] == "多头排列":
                s += 10.0
            elif item["ma_state"] == "空头排列":
                s -= 10.0
            # MACD
            if "金叉" in item["macd_state"]:
                s += 8.0
            elif "死叉" in item["macd_state"]:
                s -= 8.0
            # RSI 均值回归视角
            rsi = item.get("rsi", 50)
            if rsi > 70:
                s -= 5.0
            elif rsi < 30:
                s += 5.0
            # 20日收益（从 overview 的 change_pct 倒推不现实，这里用 close 和 20日前比较）
            instant_scores.append(s * w)

        instant_score = sum(instant_scores)

        # 1B. 历史位置感 — 价格历史分位 + 连涨连跌天数
        position_penalty = 0.0
        consecutive_score = 0.0
        for code in ["000001", "000300", "399006"]:
            try:
                df = self.q.get_daily(code, end_date=effective_date)
                if df is None or len(df) < 60:
                    continue
                df = df.sort_values("trade_date").reset_index(drop=True)
                df["close_val"] = df["close_val"].astype(float)
                # 数据清洗：过滤单日跳变>50% 和 混入的个股数据
                df["change_pct"] = df["close_val"].pct_change() * 100
                df = df[df["change_pct"].abs() <= 50].copy()
                tail5 = df.tail(5)
                if len(tail5) >= 3 and tail5["close_val"].min() < 1000 and tail5["close_val"].max() > 3000:
                    df = df[df["close_val"] > 1000].copy()
                if len(df) < 20:
                    continue

                close = float(df.iloc[-1]["close_val"])
                high_60 = float(df["close_val"].tail(60).max())
                low_60 = float(df["close_val"].tail(60).min())
                if high_60 > low_60:
                    pct = (close - low_60) / (high_60 - low_60)
                    if pct > 0.80:
                        position_penalty -= 3.0  # 高位区
                    elif pct < 0.20:
                        position_penalty += 3.0  # 低位区

                # 连涨/连跌天数（基于清洗后的数据）
                changes = df["close_val"].diff().tail(10).tolist()
                consecutive = 0
                for ch in reversed(changes):
                    if ch > 0 and consecutive >= 0:
                        consecutive += 1
                    elif ch < 0 and consecutive <= 0:
                        consecutive -= 1
                    else:
                        break
                if consecutive >= 5:
                    consecutive_score -= 3.0
                elif consecutive <= -5:
                    consecutive_score += 3.0
            except Exception as exc:
                logger.debug("趋势评分历史数据失败 %s: %s", code, exc)

        # 1C. 情绪历史分位（最近30个交易日）
        emotion_hist_score = 0.0
        try:
            df_hist = self._fetch_recent_days(30)
            if not df_hist.empty:
                daily_ratios = []
                for date_str, group in df_hist.groupby("trade_date"):
                    group_clean = group[~group.get("data_anomaly", False)]
                    total = len(group_clean)
                    up = int((group_clean["change_pct"] > 0).sum())
                    if total > 100:
                        daily_ratios.append(up / total)
                if len(daily_ratios) >= 5:
                    today_ratio = daily_ratios[-1]
                    rank = sum(1 for r in daily_ratios[:-1] if r < today_ratio) / max(1, len(daily_ratios) - 1)
                    if rank > 0.80:
                        emotion_hist_score -= 2.0  # 情绪过热
                    elif rank < 0.20:
                        emotion_hist_score += 2.0  # 情绪过冷
        except Exception as exc:
            logger.debug("情绪历史分位计算失败: %s", exc)

        total_score = instant_score + position_penalty + consecutive_score + emotion_hist_score

        # 档位判定
        if total_score >= 40:
            stage = "强多头"
        elif total_score >= 10:
            stage = "弱多头"
        elif total_score > -10:
            stage = "震荡"
        elif total_score > -40:
            stage = "弱空头"
        else:
            stage = "强空头"

        return {
            "trend_score": round(total_score, 1),
            "stage": stage,
            "instant_score": round(instant_score, 1),
            "position_penalty": round(position_penalty, 1),
            "consecutive_score": round(consecutive_score, 1),
            "emotion_hist_score": round(emotion_hist_score, 1),
            "overview": overview,
        }

    # ── 板块热力 ──

    def sector_heatmap(self, level: str = "level1") -> tuple[pd.DataFrame, pd.DataFrame]:
        """返回领涨/领跌板块 TOP5."""
        df = self._fetch_all_latest()
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()

        # 附加行业分类
        def _get_sector(code: str) -> str:
            m = get_meta(code, self.q.config)
            return m.get(level, "未知") if m else "未知"

        df["sector"] = df["code"].apply(_get_sector)

        grouped = df.groupby("sector").agg({
            "change_pct": "mean",
            "volume": "mean",
            "amount": "mean",
            "code": "count",
        }).reset_index()
        grouped.columns = ["sector", "avg_change_pct", "avg_volume", "avg_amount", "count"]
        grouped = grouped[grouped["count"] >= 3]  # 至少3只股票才统计
        grouped = grouped[grouped["sector"] != "未知"]  # 过滤无分类的
        grouped = grouped.sort_values("avg_change_pct", ascending=False)

        top5 = grouped.head(5).reset_index(drop=True)
        bottom5 = grouped.tail(5).reset_index(drop=True)

        # 为每个板块找一只代表强势股
        def _pick_repr(sector: str) -> str:
            sector_df = df[df["sector"] == sector].sort_values("change_pct", ascending=False)
            if sector_df.empty:
                return ""
            top = sector_df.iloc[0]
            name = get_name(top["code"]) or ""
            return f"{top['code']}{f'({name})' if name else ''}"

        top5["repr"] = top5["sector"].apply(_pick_repr)
        bottom5["repr"] = bottom5["sector"].apply(_pick_repr)

        return top5, bottom5

    # ── 市场情绪 ──

    def sentiment_trend(self, days: int = 5) -> dict:
        """分析最近 N 天的情绪趋势."""
        df = self._fetch_recent_days(days)
        if df.empty:
            return {"error": "数据不足", "history": []}

        # 按日期分组统计
        history = []
        for date_str, group in df.groupby("trade_date"):
            group_clean = group[~group.get("data_anomaly", False)]
            total = len(group_clean)
            up = int((group_clean["change_pct"] > 0).sum())
            down = int((group_clean["change_pct"] < 0).sum())
            limit_up = int((group_clean["change_pct"] >= 9.8).sum())
            limit_down = int((group_clean["change_pct"] <= -9.8).sum())
            if total < 100 or (up == 0 and down == 0 and limit_up == 0 and limit_down == 0):
                continue
            history.append({
                "date": str(date_str),
                "total": total,
                "up": up,
                "down": down,
                "up_ratio": round(up / total, 3),
                "limit_up": limit_up,
                "limit_down": limit_down,
            })

        if len(history) < 2:
            return {"trend": "数据不足", "stage": "未知", "history": history}

        # 趋势分析
        up_ratios = [h["up_ratio"] for h in history]
        avg_up = sum(up_ratios) / len(up_ratios)
        latest = history[-1]
        prev = history[-2]

        # 趋势方向
        if latest["up_ratio"] > prev["up_ratio"] * 1.15 and latest["up_ratio"] > avg_up * 1.1:
            trend = "升温"
        elif latest["up_ratio"] < prev["up_ratio"] * 0.85 and latest["up_ratio"] < avg_up * 0.9:
            trend = "降温"
        elif abs(latest["up_ratio"] - prev["up_ratio"]) < 0.03:
            trend = "企稳"
        else:
            trend = "波动"

        # 阶段判断
        if all(up_ratios[i] < up_ratios[i+1] for i in range(len(up_ratios)-1)):
            stage = "持续回暖"
        elif all(up_ratios[i] > up_ratios[i+1] for i in range(len(up_ratios)-1)):
            stage = "持续退潮"
        else:
            stage = "震荡"

        return {
            "trend": trend,
            "stage": stage,
            "avg_up_ratio": round(avg_up, 3),
            "latest_up_ratio": latest["up_ratio"],
            "prev_up_ratio": prev["up_ratio"],
            "history": history,
        }

    # ── 量价分析 ──

    def _volume_price_analysis(self) -> dict:
        """全市场量价分析：量能状态 + 资金流向 + 量价背离."""
        effective_date = self._resolve_effective_date()

        # A. 全市场量能状态（当日 vs 近期均值）
        volume_state = "未知"
        volume_change_pct = 0.0
        try:
            df_hist = self._fetch_recent_days(20)
            if not df_hist.empty:
                daily_amount = df_hist.groupby("trade_date")["amount"].sum()
                if len(daily_amount) >= 5:
                    today_amount = daily_amount.iloc[-1]
                    ma5_amount = daily_amount.iloc[-5:].mean()
                    ma20_amount = daily_amount.iloc[-20:].mean() if len(daily_amount) >= 20 else ma5_amount
                    if ma5_amount and ma5_amount > 0:
                        volume_change_pct = (today_amount - ma5_amount) / ma5_amount * 100
                        if volume_change_pct > 30:
                            volume_state = "显著放量"
                        elif volume_change_pct > 10:
                            volume_state = "温和放量"
                        elif volume_change_pct > -10:
                            volume_state = "量能常态"
                        elif volume_change_pct > -30:
                            volume_state = "温和缩量"
                        else:
                            volume_state = "显著缩量"
        except Exception as exc:
            logger.debug("量能状态计算失败: %s", exc)

        # B. 涨跌量价配合度
        money_flow = "未知"
        up_amount = 0.0
        down_amount = 0.0
        try:
            df = self._fetch_all_latest()
            if not df.empty:
                df_clean = df[~df.get("data_anomaly", False)]
                up_df = df_clean[df_clean["change_pct"] > 0]
                down_df = df_clean[df_clean["change_pct"] < 0]
                up_amount = float(up_df["amount"].sum()) if not up_df.empty else 0.0
                down_amount = float(down_df["amount"].sum()) if not down_df.empty else 0.0
                total_amount = up_amount + down_amount
                if total_amount > 0:
                    up_ratio_amt = up_amount / total_amount
                    down_ratio_amt = down_amount / total_amount
                    if up_ratio_amt > 0.55 and down_ratio_amt < 0.40:
                        money_flow = "多头主导"
                    elif down_ratio_amt > 0.55 and up_ratio_amt < 0.40:
                        money_flow = "空头主导"
                    elif up_ratio_amt > 0.50 and down_ratio_amt > 0.40:
                        money_flow = "分歧加大"
                    else:
                        money_flow = "交投清淡"
                else:
                    money_flow = "数据不足"
        except Exception as exc:
            logger.debug("资金流向计算失败: %s", exc)

        # C. 大盘指数量价背离检测（近5日）
        divergence = []
        for code in ["000001", "000300"]:
            try:
                df = self.q.get_daily(code, end_date=effective_date)
                if df is None or len(df) < 10:
                    continue
                df = df.sort_values("trade_date").reset_index(drop=True)
                df["close_val"] = df["close_val"].astype(float)
                df["volume"] = df["volume"].astype(float)
                recent = df.tail(5)
                if len(recent) < 3:
                    continue
                price_trend = float(recent["close_val"].iloc[-1]) - float(recent["close_val"].iloc[0])
                vol_trend = float(recent["volume"].iloc[-1]) - float(recent["volume"].iloc[0])
                name = DEFAULT_INDICES.get(code, code)
                if price_trend > 0 and vol_trend < 0:
                    divergence.append(f"{name}: 价涨量缩（上涨乏力）")
                elif price_trend < 0 and vol_trend < 0:
                    divergence.append(f"{name}: 价跌量缩（抛压衰竭）")
                elif price_trend > 0 and vol_trend > 0:
                    divergence.append(f"{name}: 价涨量增（健康上涨）")
                elif price_trend < 0 and vol_trend > 0:
                    divergence.append(f"{name}: 价跌量增（恐慌抛售）")
            except Exception as exc:
                logger.debug("背离检测失败 %s: %s", code, exc)

        return {
            "volume_state": volume_state,
            "volume_change_pct": round(volume_change_pct, 2),
            "money_flow": money_flow,
            "up_amount": round(up_amount / 1e8, 1),   # 亿元
            "down_amount": round(down_amount / 1e8, 1),
            "divergence": divergence if divergence else ["无明显背离"],
        }

    # ── 明日前瞻 ──

    def _next_day_outlook(self, sentiment: dict, trend_data: dict, vp_data: dict) -> dict:
        """基于趋势+情绪+量价，推演明日关键技术位与情景."""
        effective_date = self._resolve_effective_date()
        trend_score = trend_data.get("trend_score", 0)
        stage = trend_data.get("stage", "震荡")

        # A. 关键技术位（基于上证）
        support = "未知"
        resistance = "未知"
        key_level = "未知"
        try:
            df = self.q.get_daily("000001", end_date=effective_date)
            if df is not None and len(df) >= 20:
                df = df.sort_values("trade_date").reset_index(drop=True)
                df["close_val"] = df["close_val"].astype(float)
                # 过滤数据异常：单日跳变>50% 或 数据混杂（如指数数据混入个股）
                df["change_pct"] = df["close_val"].pct_change() * 100
                df = df[df["change_pct"].abs() <= 50].copy()
                # 若数据中混入了低价股票数据（指数 tail(5) 同时出现 <1000 和 >3000）
                tail5 = df.tail(5)
                if len(tail5) >= 3 and tail5["close_val"].min() < 1000 and tail5["close_val"].max() > 3000:
                    df = df[df["close_val"] > 1000].copy()
                if len(df) < 3:
                    raise ValueError("过滤异常后数据不足")
                close = float(df.iloc[-1]["close_val"])
                ma5 = float(df["close_val"].tail(min(5, len(df))).mean())
                ma10 = float(df["close_val"].tail(min(10, len(df))).mean())
                ma20 = float(df["close_val"].tail(min(20, len(df))).mean())
                ma60 = float(df["close_val"].tail(min(60, len(df))).mean()) if len(df) >= 3 else ma20
                recent_low = float(df["close_val"].tail(min(5, len(df))).min())
                recent_high = float(df["close_val"].tail(min(5, len(df))).max())

                # 支撑：低于当前价的最近均线或近期低点
                support_candidates = [c for c in [ma5, ma10, ma20, recent_low] if c < close * 0.998]
                if support_candidates:
                    support = round(max(support_candidates), 2)
                else:
                    support = round(min(ma20, close * 0.99), 2)

                # 压力：高于当前价的最近均线或近期高点
                resistance_candidates = [c for c in [ma5, ma10, ma20, recent_high] if c > close * 1.002]
                if resistance_candidates:
                    resistance = round(min(resistance_candidates), 2)
                else:
                    resistance = round(max(ma20, close * 1.01), 2)

                # 关键观察位
                key_level = round(ma20, 2)
        except Exception as exc:
            logger.debug("关键技术位计算失败: %s", exc)

        # B. 情景推演
        up_ratio = sentiment.get("up_ratio", 0.5)
        volume_state = vp_data.get("volume_state", "未知")
        money_flow = vp_data.get("money_flow", "未知")

        scenarios = []
        if stage in ("强多头", "弱多头") and "放量" in volume_state and money_flow in ("多头主导", "分歧加大"):
            scenarios.append({"label": "偏多", "prob": "中高", "condition": "量能维持+情绪不骤降", "action": "持仓或逢低加仓"})
        if stage in ("强空头", "弱空头") and "缩量" in volume_state:
            scenarios.append({"label": "偏空", "prob": "中高", "condition": "反弹无量+情绪低迷", "action": "减仓或观望"})
        if stage == "震荡" or ("常态" in volume_state and money_flow == "交投清淡"):
            scenarios.append({"label": "中性", "prob": "中高", "condition": "缩量震荡+方向不明", "action": "控制仓位，等待方向"})
        if not scenarios:
            scenarios.append({"label": "中性", "prob": "中等", "condition": "多空因素交织", "action": "灵活应对"})

        # C. 明日观察要点
        watch_points = []
        if volume_state in ("显著缩量", "温和缩量"):
            watch_points.append("开盘30分钟量能是否回升（对比今日同期）")
        if "背离" in str(vp_data.get("divergence", [])):
            watch_points.append("量价背离是否修复（价涨需放量确认）")
        if sentiment.get("limit_up", 0) > 50:
            watch_points.append("涨停家数持续性（今日≥50家，明日能否维持）")
        if not watch_points:
            watch_points.append("大盘是否守住关键支撑位")
            watch_points.append("领涨板块是否延续（还是轮动）")

        return {
            "support": support,
            "resistance": resistance,
            "key_level": key_level,
            "scenarios": scenarios,
            "watch_points": watch_points,
        }

    def sentiment_gauge(self) -> dict:
        """全市场情绪近似统计（融合单日数据与5日趋势、趋势评分、量价分析）."""
        df = self._fetch_all_latest()
        if df.empty:
            return {"error": "无数据"}

        df_clean = df[~df.get("data_anomaly", False)]
        total = len(df_clean)
        up = int((df_clean["change_pct"] > 0).sum())
        down = int((df_clean["change_pct"] < 0).sum())
        flat = total - up - down
        limit_up = int((df_clean["change_pct"] >= 9.8).sum())
        limit_down = int((df_clean["change_pct"] <= -9.8).sum())

        up_ratio = up / total if total > 0 else 0
        limit_ratio = limit_up / total if total > 0 else 0

        # 情绪档位（以 up_ratio 为主，涨停数为辅）
        base_sentiment = "未知"
        if up_ratio >= 0.70:
            base_sentiment = "过热"
        elif up_ratio >= 0.55:
            base_sentiment = "活跃"
        elif up_ratio >= 0.45:
            base_sentiment = "中性"
        elif up_ratio >= 0.30:
            base_sentiment = "中性" if limit_up >= 60 else "谨慎"
        elif up_ratio >= 0.15:
            base_sentiment = "低迷"
        else:
            base_sentiment = "冰点" if (limit_down > limit_up * 2 and limit_down > 50) else "低迷"

        # 获取趋势并融合修正
        trend_data = self.sentiment_trend(days=5)
        sentiment = base_sentiment
        trend_label = ""
        if "error" not in trend_data and trend_data.get("history"):
            trend = trend_data.get("trend", "")
            stage = trend_data.get("stage", "")

            # 趋势修正：升温时情绪标签向上修正一档，降温时向下修正一档
            if trend == "升温":
                if base_sentiment == "低迷":
                    sentiment = "谨慎"
                elif base_sentiment == "谨慎":
                    sentiment = "中性"
                trend_label = "·升温"
            elif trend == "降温":
                if base_sentiment == "活跃":
                    sentiment = "中性"
                elif base_sentiment == "中性":
                    sentiment = "谨慎"
                trend_label = "·降温"
            elif stage == "持续回暖":
                trend_label = "·持续回暖"
            elif stage == "持续退潮":
                trend_label = "·持续退潮"

        sentiment = f"{sentiment}{trend_label}"

        # ── 趋势评分修正（防追涨杀跌） ──
        trend_score_data = self._market_trend_score()
        trend_stage = trend_score_data.get("stage", "震荡")
        trend_score_val = trend_score_data.get("trend_score", 0)
        trend_adjusted = sentiment  # 修正后的情绪标签（用于仓位）
        trend_notes = []

        # 强空头时，反弹不追
        if trend_stage == "强空头" and base_sentiment in ("活跃", "过热"):
            trend_adjusted = "中性" if base_sentiment == "活跃" else "中性"
            trend_notes.append("趋势空头，反弹勿追")
        # 强多头时，回调是机会
        elif trend_stage == "强多头" and base_sentiment in ("低迷", "谨慎"):
            if base_sentiment == "低迷":
                trend_adjusted = "谨慎"
            trend_notes.append("趋势多头，回调是机会")
        # 高位区+活跃 → 降档
        elif trend_score_data.get("position_penalty", 0) < -1 and base_sentiment in ("活跃", "过热"):
            trend_adjusted = "中性" if base_sentiment == "活跃" else "中性"
            trend_notes.append("价格高位区，警惕滞涨")
        # 低位区+低迷 → 升档
        elif trend_score_data.get("position_penalty", 0) > 1 and base_sentiment in ("低迷", "冰点"):
            trend_adjusted = "谨慎" if base_sentiment == "低迷" else "谨慎"
            trend_notes.append("价格低位区，关注反弹")

        # ── 量价修正 ──
        vp_data = self._volume_price_analysis()
        volume_state = vp_data.get("volume_state", "未知")
        money_flow = vp_data.get("money_flow", "未知")
        vp_notes = []

        if base_sentiment in ("活跃", "过热") and "缩量" in volume_state:
            # 上涨但无量 → 虚涨，降一档
            if trend_adjusted == "活跃":
                trend_adjusted = "中性"
            elif trend_adjusted == "过热":
                trend_adjusted = "活跃"
            vp_notes.append("上涨无量，虚涨风险")
        elif base_sentiment in ("低迷", "冰点") and "缩量" in volume_state:
            # 下跌缩量 → 抛压衰竭，可升一档
            if trend_adjusted == "冰点":
                trend_adjusted = "低迷"
            vp_notes.append("下跌缩量，抛压衰竭")
        elif base_sentiment in ("低迷", "谨慎", "中性") and "放量" in volume_state and money_flow == "空头主导":
            # 下跌放量 → 恐慌，再降一档
            if trend_adjusted == "中性":
                trend_adjusted = "谨慎"
            elif trend_adjusted == "谨慎":
                trend_adjusted = "低迷"
            vp_notes.append("下跌放量，恐慌抛售")

        # 量价背离风险提示
        divergence = vp_data.get("divergence", [])
        if divergence and "无明显背离" not in divergence:
            vp_notes.extend([d for d in divergence if "乏力" in d or "背离" in d])

        # 最终情绪标签：简洁档位 + 趋势标签（修正注释单独字段展示）
        final_sentiment = trend_adjusted
        if trend_label:
            final_sentiment = f"{trend_adjusted}{trend_label}"

        all_notes = trend_notes + vp_notes

        advice = SENTIMENT_ADVICE.get(trend_adjusted, SENTIMENT_ADVICE.get(base_sentiment, ""))

        return {
            "total": total,
            "up": up,
            "down": down,
            "flat": flat,
            "up_ratio": round(up_ratio, 3),
            "limit_up": limit_up,
            "limit_down": limit_down,
            "limit_ratio": round(limit_ratio, 4),
            "sentiment": final_sentiment,
            "base_sentiment": base_sentiment,
            "trend_adjusted": trend_adjusted,
            "advice": advice,
            "trend": trend_data.get("trend", ""),
            "stage": trend_data.get("stage", ""),
            "trend_history": trend_data.get("history", []),
            "trend_score": trend_score_val,
            "trend_stage": trend_stage,
            "volume_state": volume_state,
            "money_flow": money_flow,
            "volume_change_pct": vp_data.get("volume_change_pct", 0),
            "divergence": divergence,
            "trend_notes": trend_notes,
            "vp_notes": vp_notes,
        }

    # ── ETF 跟踪 ──

    def etf_tracker(self, codes: list[str] | None = None) -> list[dict]:
        """ETF 策略日报."""
        codes = codes or DEFAULT_ETF_CODES
        effective_date = self._resolve_effective_date()
        results = []
        for code in codes:
            result = _analyze_etf(code, self.q, end_date=effective_date)
            if result:
                results.append(result)
        return results

    # ── 信号雷达 ──

    def signal_radar(self, codes: list[str] | None = None) -> list[dict]:
        """扫描活跃股的技术信号."""
        if codes is None:
            # 默认扫描涨跌幅前 200 的活跃股
            df = self._fetch_all_latest()
            if df.empty or len(df) < 200:
                return []
            top200 = df.nlargest(100, "change_pct")["code"].tolist()
            bottom200 = df.nsmallest(100, "change_pct")["code"].tolist()
            codes = list(dict.fromkeys(top200 + bottom200))  # 去重保持顺序

        signals_config = [
            ("macd", "golden_cross", "MACD金叉"),
            ("rsi", "oversold", "RSI超卖"),
            ("bollinger", "lower_touch", "布林带下轨"),
        ]

        from .analyzer import TdxIndicatorAnalyzer
        analyzer = TdxIndicatorAnalyzer(self.q)
        results = []

        for indicator, signal_type, label in signals_config:
            try:
                df_sig = analyzer.find_signals(codes, indicator=indicator,
                                              signal_type=signal_type, lookback=5)
                count = len(df_sig)
                repr_codes = df_sig["code"].head(5).tolist() if not df_sig.empty else []
                repr_names = [f"{c}({get_name(c) or ''})" for c in repr_codes]
                results.append({
                    "signal": label,
                    "count": count,
                    "repr": ", ".join(repr_names) if repr_names else "无",
                })
            except Exception as exc:
                logger.debug("信号扫描失败 %s %s: %s", indicator, signal_type, exc)
                results.append({"signal": label, "count": 0, "repr": "扫描失败"})

        return results

    # ── 回撤选股 ──

    def pullback_picks(self, board: str | None = None,
                       min_score: float = 60.0,
                       top_n: int = 15,
                       workers: int = 12) -> list[dict]:
        """运行 5 因子回撤选股."""
        # 确定股票池
        if board:
            from .metadata import by_board
            codes = by_board(board, self.q.config)
        else:
            # 默认只扫描最新交易日有数据的股票，避免 get_stock_list() 返回全部历史代码
            # 按成交额取前 2000 活跃股，保证 MySQL 环境下速度可接受
            df_latest = self._fetch_all_latest()
            if not df_latest.empty:
                df_latest = df_latest.sort_values("amount", ascending=False).head(2000)
            codes = df_latest["code"].tolist() if not df_latest.empty else []

        if not codes:
            return []

        effective_date = self._resolve_effective_date()

        def _analyze(code: str) -> dict | None:
            try:
                df = self.q.get_daily(code, end_date=effective_date)
                if df is None or df.empty or len(df) < 60:
                    return None
                df = df.sort_values("trade_date").reset_index(drop=True)
                if len(df) > 150:
                    df = df.iloc[-150:].copy()
                df = TdxIndicators.compute(df, indicators=["ma", "macd", "rsi"])
                scores = _compute_pullback_scores(df)
                if not scores or sum(scores.values()) < min_score:
                    return None
                plan = _generate_pullback_plan(df, scores, code, get_name(code) or code)
                return plan
            except Exception:
                return None

        picks = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_analyze, c): c for c in codes}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    picks.append(result)

        picks.sort(key=lambda x: x["total_score"], reverse=True)
        return picks[:top_n]

    # ── 交易计划 ──

    def generate_action_plan(self, data: dict) -> str:
        """基于复盘数据生成次日交易计划建议（融合趋势评分+量价分析+明日前瞻）."""
        sentiment = data.get("sentiment", {})
        style = data.get("market_style", {})
        picks = data.get("pullback_picks", [])
        etf_list = data.get("etf_tracker", [])
        outlook = data.get("outlook", {})

        # 使用修正后的情绪档位（而非原始 up_ratio）
        trend_adjusted = sentiment.get("trend_adjusted", "中性")
        trend_stage = sentiment.get("trend_stage", "震荡")
        trend_score = sentiment.get("trend_score", 0)
        volume_state = sentiment.get("volume_state", "未知")
        money_flow = sentiment.get("money_flow", "未知")
        limit_up = sentiment.get("limit_up", 0)
        limit_down = sentiment.get("limit_down", 0)

        # 方向判断 & 仓位（基于修正后情绪 + 趋势系数）
        base_positions = {
            "过热": ("情绪过热，逐步减仓锁定利润", "5-6成"),
            "活跃": ("赚钱效应扩散，积极参与", "6-7成"),
            "中性": ("结构性机会，精选个股", "4-5成"),
            "谨慎": ("方向不明，防守为主", "3-4成"),
            "低迷": ("亏钱效应明显，控制仓位", "2-3成"),
            "冰点": ("市场恐慌，空仓或极小仓位试错", "0-1成"),
        }
        direction, position = base_positions.get(trend_adjusted, ("观望", "3-4成"))

        # 趋势系数修正仓位
        if trend_stage == "强多头":
            position = position.replace("5-6", "6-7").replace("6-7", "7-8").replace("4-5", "5-6").replace("3-4", "4-5").replace("2-3", "3-4")
        elif trend_stage == "强空头":
            position = position.replace("6-7", "5-6").replace("5-6", "4-5").replace("4-5", "3-4").replace("3-4", "2-3").replace("2-3", "1-2")

        # ETF 建议
        etf_lines = []
        for etf in etf_list:
            etf_lines.append(
                f"  {etf['code']}({etf['name']}): {etf['state_zh']}，"
                f"评分{etf['trend_score']}/10，RSI={etf['rsi']:.1f}"
            )

        # 关注标的
        pick_lines = []
        for p in picks[:5]:
            pick_lines.append(
                f"  {p['code']}({p['name']}): 评分{p['total_score']}, "
                f"买入{p['entry_price']}, 止损{p['stop_price']}, "
                f"盈亏比{p['risk_reward']}"
            )

        # 风险预案
        risks = []
        if limit_down > limit_up * 2:
            risks.append("跌停家数远超涨停，情绪恶化，立即减仓至3成以下")
        if trend_stage == "强空头" and "反弹" in direction:
            risks.append("趋势空头中的反弹，不参与或极小仓位试错")
        if "缩量" in volume_state and trend_adjusted in ("活跃", "过热"):
            risks.append("上涨无量，谨防虚涨回落")
        for etf in etf_list:
            if etf["state"] == "STRONG_DOWN":
                risks.append(f"{etf['code']}进入强下跌趋势，暂停该品种网格买入")
        if not risks:
            risks.append("若大盘跌破关键均线支撑或量能异常萎缩，灵活减仓")

        # 明日前瞻
        outlook_lines = []
        if outlook:
            support = outlook.get("support", "未知")
            resistance = outlook.get("resistance", "未知")
            key_level = outlook.get("key_level", "未知")
            outlook_lines.append(f"  支撑: {support} | 压力: {resistance} | 关键位: {key_level}")
            outlook_lines.append("")
            scenarios = outlook.get("scenarios", [])
            if scenarios:
                outlook_lines.append("  情景推演:")
                for sc in scenarios:
                    outlook_lines.append(f"    [{sc['label']}] 概率{sc['prob']} — {sc['condition']} → {sc['action']}")
            watch_points = outlook.get("watch_points", [])
            if watch_points:
                outlook_lines.append("")
                outlook_lines.append("  明日观察要点:")
                for wp in watch_points:
                    outlook_lines.append(f"    · {wp}")

        lines = [
            f"**方向判断**: {direction}",
            f"**仓位建议**: {position}",
            f"**市场风格**: {style.get('style', '未知')}",
            f"**趋势状态**: {trend_stage} (评分: {trend_score})",
            f"**量能状态**: {volume_state} | 资金流向: {money_flow}",
            "",
            "**ETF 策略状态**:",
        ]
        lines.extend(etf_lines or ["  无"])
        lines.append("")
        lines.append("**关注标的 (5因子回撤选股)**:")
        lines.extend(pick_lines or ["  今日无符合条件的标的"])
        lines.append("")
        lines.append("**明日前瞻**:")
        lines.extend(outlook_lines or ["  暂无数据"])
        lines.append("")
        lines.append("**风险预案**:")
        for r in risks:
            lines.append(f"  - {r}")
        lines.append("  - 严格执行止损，单票亏损不超过总资金的2%")

        return "\n".join(lines)
