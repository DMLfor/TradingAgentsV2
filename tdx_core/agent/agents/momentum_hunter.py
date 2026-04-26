"""Momentum Hunter agent node for LangGraph workflow.

Philosophy: "The strong get stronger."
Two-step: quant scoring → LLM persona reasoning.
"""

import json
import os

from langchain_core.messages import HumanMessage

from tdx_core.agent.base import AgentSignal, _cast
from tdx_core.agent.graph.state import AgentState
from tdx_core.agent.llm_client import LLMClient, llm_available
from tdx_core.agent.agents.persona_prompts import PERSONA_PROMPTS

AGENT_ID = "momentum_hunter"


def _quant_analysis(df) -> dict:
    """Step 1: Pure algorithmic momentum quant scoring."""
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    rsi = latest.get("rsi_14")
    cci = latest.get("cci_20")
    macd_hist = latest.get("macd_hist")
    close = latest.get("close_val")

    # 1. Price momentum (0-20)
    mom_score = 5
    if len(df) >= 5 and close is not None:
        prev_close = df["close_val"].iloc[-5]
        if prev_close > 0:
            ret_5d = (close - prev_close) / prev_close * 100
            if ret_5d > 8:
                mom_score = 20
            elif ret_5d > 5:
                mom_score = 15
            elif ret_5d > 2:
                mom_score = 10
            elif ret_5d > 0:
                mom_score = 5
            else:
                mom_score = 0

    # 2. RSI strength zone (0-20)
    rsi_score = 5
    if rsi is not None:
        if 50 < rsi <= 70:
            rsi_score = 20
        elif 40 < rsi <= 50:
            rsi_score = 10
        elif 70 < rsi <= 80:
            rsi_score = 10
        elif rsi > 80:
            rsi_score = 0
        else:
            rsi_score = 5

    # 3. CCI breakout (0-20)
    cci_score = 5
    if cci is not None:
        if cci > 100:
            cci_score = 20
        elif cci > 50:
            cci_score = 15
        elif cci > 0:
            cci_score = 10
        else:
            cci_score = 0

    # 4. MACD histogram momentum (0-20)
    hist_score = 5
    if macd_hist is not None and len(df) >= 4:
        hists = df["macd_hist"].iloc[-4:].tolist()
        if len(hists) >= 3:
            expanding = all(hists[i] < hists[i+1] for i in range(len(hists)-1))
            if expanding and macd_hist > 0:
                hist_score = 20
            elif expanding:
                hist_score = 15
            elif macd_hist > 0:
                hist_score = 10
            else:
                hist_score = 0

    # 5. Price-RSI divergence (0-20)
    div_score = 10
    div_type = "none"
    if len(df) >= 10 and "rsi_14" in df.columns and "close_val" in df.columns:
        recent_close = df["close_val"].iloc[-5:].min()
        prior_close = df["close_val"].iloc[-10:-5].min()
        recent_rsi = df["rsi_14"].iloc[-5:].min()
        prior_rsi = df["rsi_14"].iloc[-10:-5].min()
        if recent_close < prior_close and recent_rsi > prior_rsi:
            div_score = 20
            div_type = "bullish"
        elif recent_close > prior_close and recent_rsi < prior_rsi:
            div_score = 0
            div_type = "bearish"

    total_score = mom_score + rsi_score + cci_score + hist_score + div_score

    if mom_score >= 10 and rsi_score >= 10 and div_type != "bearish":
        signal = "bullish"
    elif div_type == "bearish" or (mom_score == 0 and rsi_score <= 5):
        signal = "bearish"
    else:
        signal = "neutral"

    confidence = int(min(total_score / 100 * 100, 100))

    facts = {
        "momentum_score": mom_score,
        "rsi_score": rsi_score,
        "cci_score": cci_score,
        "hist_score": hist_score,
        "divergence_score": div_score,
        "total_score": total_score,
        "divergence_type": div_type,
        "algo_signal": signal,
        "algo_confidence": confidence,
        "metrics": {
            "rsi_14": _cast(rsi),
            "cci_20": _cast(cci),
            "macd_hist": _cast(macd_hist),
            "close": _cast(close),
            "ret_5d_pct": _cast(
                (close - df["close_val"].iloc[-5]) / df["close_val"].iloc[-5] * 100
                if len(df) >= 5 and close is not None else 0
            ),
        },
    }
    return facts


def _algo_fallback(facts: dict) -> dict:
    metrics = facts["metrics"]
    signal = facts["algo_signal"]
    confidence = facts["algo_confidence"]
    div = facts.get("divergence_type", "none")

    if signal == "bullish":
        reasoning = (
            f"5日涨幅{metrics['ret_5d_pct']:.1f}%，RSI={metrics['rsi_14']:.1f}强势区，"
            f"MACD动量{'扩张' if facts['hist_score'] >= 15 else '一般'}，总分{facts['total_score']}/100"
        )
    elif signal == "bearish":
        reasoning = (
            f"动量衰竭{', 检测到顶背离' if div == 'bearish' else ''}，"
            f"RSI={metrics['rsi_14']:.1f}，总分{facts['total_score']}/100"
        )
    else:
        reasoning = (
            f"5日涨幅{metrics['ret_5d_pct']:.1f}%，动量一般，"
            f"RSI={metrics['rsi_14']:.1f}，总分{facts['total_score']}/100"
        )

    if div == "bullish":
        reasoning += "，检测到价格-RSI底背离"

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


def momentum_hunter_agent(state: AgentState) -> dict:
    """Momentum Hunter: quant scoring → LLM persona reasoning."""
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
