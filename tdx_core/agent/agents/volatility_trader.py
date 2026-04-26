"""Volatility Trader agent node for LangGraph workflow.

Philosophy: "Low volatility breeds opportunity, high volatility breeds risk."
Two-step: quant scoring → LLM persona reasoning.
"""

import json
import os

from langchain_core.messages import HumanMessage

from tdx_core.agent.base import AgentSignal, _cast
from tdx_core.agent.graph.state import AgentState
from tdx_core.agent.llm_client import LLMClient, llm_available
from tdx_core.agent.agents.persona_prompts import PERSONA_PROMPTS

AGENT_ID = "volatility_trader"


def _quant_analysis(df) -> dict:
    """Step 1: Pure algorithmic volatility quant scoring."""
    latest = df.iloc[-1]
    bb_pctb = latest.get("bb_pctb")
    bb_bw = latest.get("bb_bandwidth")
    atr = latest.get("atr_14")
    close = latest.get("close_val")

    # 1. %B position (0-20)
    bb_score = 10
    if bb_pctb is not None:
        if bb_pctb < 0.2:
            bb_score = 20
        elif bb_pctb < 0.5:
            bb_score = 15
        elif bb_pctb < 0.8:
            bb_score = 10
        else:
            bb_score = 5

    # 2. Bandwidth state (0-20)
    bw_score = 10
    if bb_bw is not None and len(df) > 20:
        prev_bw = df["bb_bandwidth"].iloc[-20:-1].mean()
        if prev_bw is not None and prev_bw > 0:
            if bb_bw < prev_bw * 0.5:
                bw_score = 20  # extreme squeeze
            elif bb_bw < prev_bw * 0.8:
                bw_score = 15  # squeeze
            elif bb_bw > prev_bw * 1.3:
                bw_score = 5   # expanding
            else:
                bw_score = 10

    # 3. ATR percentile (0-20)
    atr_pct = 50.0
    atr_score = 10
    if atr is not None and len(df) >= 60 and "atr_14" in df.columns:
        atr_hist = df["atr_14"].iloc[-60:].dropna()
        if len(atr_hist) > 0:
            atr_pct = (atr_hist <= atr).mean() * 100
            if atr_pct < 20:
                atr_score = 20
            elif atr_pct < 40:
                atr_score = 15
            elif atr_pct > 80:
                atr_score = 5
            elif atr_pct > 60:
                atr_score = 10
            else:
                atr_score = 10

    # 4. Price amplitude (0-20)
    amp_score = 10
    if len(df) >= 5 and close is not None:
        recent_high = df["high_val"].iloc[-5:].max()
        recent_low = df["low_val"].iloc[-5:].min()
        if recent_low > 0:
            amp = (recent_high - recent_low) / recent_low * 100
            if amp < 3:
                amp_score = 20
            elif amp < 5:
                amp_score = 15
            elif amp < 10:
                amp_score = 10
            else:
                amp_score = 5

    # 5. Support / resistance distance (0-20)
    sr_score = 10
    if len(df) >= 20 and close is not None:
        r_high = df["high_val"].iloc[-20:].max()
        r_low = df["low_val"].iloc[-20:].min()
        if r_high > r_low:
            pos = (close - r_low) / (r_high - r_low)
            if pos < 0.2:
                sr_score = 20
            elif pos < 0.4:
                sr_score = 15
            elif pos > 0.8:
                sr_score = 5
            elif pos > 0.6:
                sr_score = 10
            else:
                sr_score = 10

    total_score = bb_score + bw_score + atr_score + amp_score + sr_score

    if atr_score >= 15 and bb_score >= 15 and bb_pctb is not None and bb_pctb < 0.5:
        signal = "bullish"
    elif atr_score <= 5 and bb_score <= 5 and bb_pctb is not None and bb_pctb > 0.8:
        signal = "bearish"
    else:
        signal = "neutral"

    confidence = int(min(total_score / 100 * 100, 100))

    recent_high = df["high_val"].iloc[-20:].max() if len(df) >= 20 else df["high_val"].max()
    recent_low = df["low_val"].iloc[-20:].min() if len(df) >= 20 else df["low_val"].min()

    facts = {
        "bb_score": bb_score,
        "bandwidth_score": bw_score,
        "atr_score": atr_score,
        "amplitude_score": amp_score,
        "sr_score": sr_score,
        "total_score": total_score,
        "atr_percentile": atr_pct,
        "algo_signal": signal,
        "algo_confidence": confidence,
        "metrics": {
            "bb_pctb": _cast(bb_pctb),
            "bb_bandwidth": _cast(bb_bw),
            "atr_14": _cast(atr),
            "atr_percentile": _cast(atr_pct),
            "recent_high": _cast(recent_high),
            "recent_low": _cast(recent_low),
            "close": _cast(close),
        },
    }
    return facts


def _algo_fallback(facts: dict) -> dict:
    metrics = facts["metrics"]
    signal = facts["algo_signal"]
    confidence = facts["algo_confidence"]

    if signal == "bullish":
        reasoning = (
            f"布林带%B={metrics['bb_pctb']:.2f}接近下轨，"
            f"ATR百分位={metrics['atr_percentile']:.1f}%低波动蓄势，总分{facts['total_score']}/100"
        )
    elif signal == "bearish":
        reasoning = (
            f"布林带%B={metrics['bb_pctb']:.2f}接近上轨，"
            f"ATR百分位={metrics['atr_percentile']:.1f}%高波动，总分{facts['total_score']}/100"
        )
    else:
        reasoning = (
            f"布林带%B={metrics['bb_pctb']:.2f}中位，"
            f"ATR百分位={metrics['atr_percentile']:.1f}%波动中性，总分{facts['total_score']}/100"
        )

    result = AgentSignal(
        signal=signal, confidence=confidence, reasoning=reasoning, metrics=metrics
    )
    return result.model_dump_casted()


def _build_prompt(facts: dict) -> list[dict]:
    system_msg = PERSONA_PROMPTS[AGENT_ID]
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": json.dumps(facts, ensure_ascii=False, indent=2)},
    ]


def volatility_trader_agent(state: AgentState) -> dict:
    """Volatility Trader: quant scoring → LLM persona reasoning."""
    code = state["data"]["code"]
    df = state["data"]["df"]
    use_llm = state["data"].get("use_llm", True)
    model = state["data"].get("model")

    facts = _quant_analysis(df)

    if use_llm and llm_available():
        try:
            client = LLMClient(model=model)
            messages = _build_prompt(facts)
            result = client.call(messages, AgentSignal)
            signal_data = result.model_dump_casted()
        except Exception:
            signal_data = _algo_fallback(facts)
    else:
        signal_data = _algo_fallback(facts)

    signal_data["code"] = code
    state["data"].setdefault("analyst_signals", {})[AGENT_ID] = {code: signal_data}

    msg = HumanMessage(
        content=json.dumps({code: signal_data}, ensure_ascii=False), name=AGENT_ID
    )
    return {"messages": [msg], "data": state["data"]}
