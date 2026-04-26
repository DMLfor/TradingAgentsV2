"""Mean Reversion Trader agent node for LangGraph workflow.

Philosophy: "What goes up must come down, and vice versa."
Two-step: quant scoring → LLM persona reasoning.
"""

import json
import os

from langchain_core.messages import HumanMessage

from tdx_core.agent.base import AgentSignal, _cast
from tdx_core.agent.graph.state import AgentState
from tdx_core.agent.llm_client import LLMClient, llm_available
from tdx_core.agent.agents.persona_prompts import PERSONA_PROMPTS

AGENT_ID = "mean_reversion_trader"


def _quant_analysis(df) -> dict:
    """Step 1: Pure algorithmic mean-reversion quant scoring."""
    latest = df.iloc[-1]
    rsi = latest.get("rsi_14")
    bb_pctb = latest.get("bb_pctb")
    stoch_k = latest.get("stoch_k")
    stoch_d = latest.get("stoch_d")
    cci = latest.get("cci_20")
    close = latest.get("close_val")

    # 1. RSI extremes (0-20)
    rsi_score = 5
    if rsi is not None:
        if rsi < 30:
            rsi_score = 20
        elif rsi < 40:
            rsi_score = 10
        elif rsi > 70:
            rsi_score = 0
        else:
            rsi_score = 5

    # 2. Bollinger %B position (0-20)
    bb_score = 5
    if bb_pctb is not None:
        if bb_pctb < 0.1:
            bb_score = 20
        elif bb_pctb < 0.3:
            bb_score = 10
        elif bb_pctb > 0.9:
            bb_score = 0
        elif bb_pctb > 0.7:
            bb_score = 5
        else:
            bb_score = 10

    # 3. Stochastic extremes (0-20)
    stoch_score = 5
    if stoch_k is not None and stoch_d is not None:
        if stoch_k < 20 and stoch_d < 20:
            stoch_score = 20
        elif stoch_k < 30:
            stoch_score = 15
        elif stoch_k > 80 and stoch_d > 80:
            stoch_score = 0
        elif stoch_k > 80:
            stoch_score = 5
        else:
            stoch_score = 10

    # 4. CCI extremes (0-20)
    cci_score = 5
    if cci is not None:
        if cci < -100:
            cci_score = 20
        elif cci < -50:
            cci_score = 10
        elif cci > 100:
            cci_score = 0
        else:
            cci_score = 10

    # 5. Recent drawdown (0-20)
    drawdown_score = 5
    if len(df) >= 5 and close is not None:
        recent_high = df["high_val"].iloc[-5:].max()
        if recent_high > 0:
            dd = (recent_high - close) / recent_high * 100
            if dd > 10:
                drawdown_score = 20
            elif dd > 5:
                drawdown_score = 15
            elif dd > 2:
                drawdown_score = 10
            else:
                drawdown_score = 5

    total_score = rsi_score + bb_score + stoch_score + cci_score + drawdown_score

    # Count oversold / overbought conditions
    oversold = sum([
        1 if rsi is not None and rsi < 40 else 0,
        1 if bb_pctb is not None and bb_pctb < 0.3 else 0,
        1 if stoch_k is not None and stoch_k < 30 else 0,
        1 if cci is not None and cci < -80 else 0,
    ])
    overbought = sum([
        1 if rsi is not None and rsi > 70 else 0,
        1 if bb_pctb is not None and bb_pctb > 0.9 else 0,
        1 if stoch_k is not None and stoch_k > 80 else 0,
        1 if cci is not None and cci > 100 else 0,
    ])

    if oversold >= 3:
        signal = "bullish"
    elif overbought >= 2:
        signal = "bearish"
    else:
        signal = "neutral"

    confidence = int(min(total_score / 100 * 100, 100))

    facts = {
        "rsi_score": rsi_score,
        "bb_score": bb_score,
        "stoch_score": stoch_score,
        "cci_score": cci_score,
        "drawdown_score": drawdown_score,
        "total_score": total_score,
        "oversold_count": oversold,
        "overbought_count": overbought,
        "algo_signal": signal,
        "algo_confidence": confidence,
        "metrics": {
            "rsi_14": _cast(rsi),
            "bb_pctb": _cast(bb_pctb),
            "stoch_k": _cast(stoch_k),
            "stoch_d": _cast(stoch_d),
            "cci_20": _cast(cci),
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
            f"RSI={metrics['rsi_14']:.1f}超卖，布林带%B={metrics['bb_pctb']:.2f}接近下轨，"
            f"共{facts['oversold_count']}项指标超卖，总分{facts['total_score']}/100"
        )
    elif signal == "bearish":
        reasoning = (
            f"RSI={metrics['rsi_14']:.1f}超买，布林带%B={metrics['bb_pctb']:.2f}接近上轨，"
            f"共{facts['overbought_count']}项指标超买，总分{facts['total_score']}/100"
        )
    else:
        reasoning = (
            f"RSI={metrics['rsi_14']:.1f}中性，指标分散未形成一致极端偏离，"
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


def mean_reversion_trader_agent(state: AgentState) -> dict:
    """Mean Reversion Trader: quant scoring → LLM persona reasoning."""
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
