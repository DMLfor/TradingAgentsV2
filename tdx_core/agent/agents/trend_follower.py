"""Trend Follower agent node for LangGraph workflow.

Philosophy: "The trend is your friend."
Two-step: quant scoring → LLM persona reasoning.
"""

import json
import os

from langchain_core.messages import HumanMessage

from tdx_core.agent.base import AgentSignal, _cast
from tdx_core.agent.graph.state import AgentState
from tdx_core.agent.llm_client import LLMClient, llm_available
from tdx_core.agent.agents.persona_prompts import PERSONA_PROMPTS

AGENT_ID = "trend_follower"


def _quant_analysis(df) -> dict:
    """Step 1: Pure algorithmic trend quant scoring."""
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    ma5 = latest.get("ma_5")
    ma20 = latest.get("ma_20")
    ma60 = latest.get("ma_60")
    macd = latest.get("macd")
    macd_sig = latest.get("macd_signal")
    macd_hist = latest.get("macd_hist")
    adx = latest.get("adx")
    close = latest.get("close_val")

    # 1. MA alignment (0-20)
    ma_score = 0
    if ma5 is not None and ma20 is not None:
        if ma5 > ma20 > ma60:
            ma_score = 20
        elif ma5 > ma20:
            ma_score = 10
        elif ma5 < ma20:
            ma_score = 0
        else:
            ma_score = 5

    # 2. MACD direction (0-20)
    macd_score = 0
    if macd is not None and macd_sig is not None:
        if macd > macd_sig and macd > 0:
            macd_score = 20
        elif macd > macd_sig and macd <= 0:
            macd_score = 5
        elif macd < macd_sig and macd > 0:
            macd_score = 10
        else:
            macd_score = 0

    # 3. ADX strength (0-20)
    adx_score = 5
    if adx is not None:
        if adx > 30:
            adx_score = 20
        elif adx > 20:
            adx_score = 10

    # 4. Price position vs MA20 (0-20)
    price_score = 0
    if close is not None and ma20 is not None:
        if close > ma20:
            if ma5 is not None and close > ma5:
                price_score = 20
            else:
                price_score = 15
        elif ma5 is not None and close > ma5:
            price_score = 10
        else:
            price_score = 0

    # 5. Trend persistence (0-20)
    persist_score = 5
    if len(df) >= 20 and close is not None:
        recent_high = df["high_val"].iloc[-20:].max()
        if close >= recent_high * 0.98:
            persist_score = 20
        elif close >= recent_high * 0.95:
            persist_score = 15
        elif close >= recent_high * 0.90:
            persist_score = 10

    total_score = ma_score + macd_score + adx_score + price_score + persist_score

    # Algorithmic fallback signal
    if total_score >= 60 and ma5 is not None and ma20 is not None and ma5 > ma20:
        signal = "bullish"
    elif total_score <= 30 and ma5 is not None and ma20 is not None and ma5 < ma20:
        signal = "bearish"
    else:
        signal = "neutral"

    confidence = int(min(total_score / 100 * 100, 100))

    facts = {
        "ma_score": ma_score,
        "macd_score": macd_score,
        "adx_score": adx_score,
        "price_score": price_score,
        "persistence_score": persist_score,
        "total_score": total_score,
        "algo_signal": signal,
        "algo_confidence": confidence,
        "metrics": {
            "ma_5": _cast(ma5),
            "ma_20": _cast(ma20),
            "ma_60": _cast(ma60),
            "macd": _cast(macd),
            "macd_signal": _cast(macd_sig),
            "macd_hist": _cast(macd_hist),
            "adx": _cast(adx),
            "close": _cast(close),
        },
    }
    return facts


def _algo_fallback(facts: dict) -> dict:
    """Fallback when LLM is disabled or unavailable."""
    metrics = facts["metrics"]
    signal = facts["algo_signal"]
    confidence = facts["algo_confidence"]

    if signal == "bullish":
        reasoning = (
            f"均线多头排列，MACD金叉，ADX={metrics['adx']:.1f}确认趋势强度，"
            f"总分{facts['total_score']}/100"
        )
    elif signal == "bearish":
        reasoning = (
            f"均线空头排列，MACD弱势，ADX={metrics['adx']:.1f}，"
            f"总分{facts['total_score']}/100"
        )
    else:
        reasoning = (
            f"趋势信号混杂，均线/MACD/ADX未形成一致方向，"
            f"总分{facts['total_score']}/100"
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


def trend_follower_agent(state: AgentState) -> dict:
    """Trend Follower: quant scoring → LLM persona reasoning."""
    code = state["data"]["code"]
    df = state["data"]["df"]
    use_llm = state["data"].get("use_llm", True)
    model = state["data"].get("model")

    # Step 1: Quant scoring
    facts = _quant_analysis(df)

    # Step 2: LLM persona reasoning
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
