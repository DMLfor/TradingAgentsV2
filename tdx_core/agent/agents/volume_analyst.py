"""Volume Analyst agent node for LangGraph workflow.

Philosophy: "Volume leads price."
Two-step: quant scoring → LLM persona reasoning.
"""

import json
import os

from langchain_core.messages import HumanMessage

from tdx_core.agent.base import AgentSignal, _cast
from tdx_core.agent.graph.state import AgentState
from tdx_core.agent.llm_client import LLMClient, llm_available
from tdx_core.agent.agents.persona_prompts import PERSONA_PROMPTS

AGENT_ID = "volume_analyst"


def _quant_analysis(df) -> dict:
    """Step 1: Pure algorithmic volume-price quant scoring."""
    latest = df.iloc[-1]
    obv = latest.get("obv")
    mfi = latest.get("mfi_14")
    cmf = latest.get("cmf_20")
    vol = latest.get("volume")
    close = latest.get("close_val")

    # Volume ratio vs 20-day average
    vol_ratio = 1.0
    if vol is not None and len(df) >= 20 and "volume" in df.columns:
        vol_ma20 = df["volume"].iloc[-20:].mean()
        if vol_ma20 and vol_ma20 > 0:
            vol_ratio = vol / vol_ma20

    # 1. OBV trend (0-20)
    obv_score = 5
    if obv is not None and len(df) > 5 and "obv" in df.columns:
        obv_prev = df["obv"].iloc[-5]
        if obv > obv_prev * 1.02:
            obv_score = 20
        elif obv > obv_prev:
            obv_score = 15
        elif obv < obv_prev * 0.98:
            obv_score = 0
        else:
            obv_score = 5

    # 2. Price-OBV divergence (0-20)
    obv_div_score = 10
    div_type = "none"
    if len(df) >= 10 and "obv" in df.columns and "close_val" in df.columns:
        recent_close = df["close_val"].iloc[-5:].min()
        prior_close = df["close_val"].iloc[-10:-5].min()
        recent_obv = df["obv"].iloc[-5:].min()
        prior_obv = df["obv"].iloc[-10:-5].min()
        if recent_close < prior_close and recent_obv > prior_obv:
            obv_div_score = 20
            div_type = "bullish"
        elif recent_close > prior_close and recent_obv < prior_obv:
            obv_div_score = 0
            div_type = "bearish"

    # 3. MFI state (0-20)
    mfi_score = 5
    if mfi is not None:
        if mfi < 30:
            mfi_score = 20
        elif mfi < 50:
            mfi_score = 10
        elif mfi < 70:
            mfi_score = 10
        elif mfi < 80:
            mfi_score = 5
        else:
            mfi_score = 0

    # 4. CMF money flow (0-20)
    cmf_score = 5
    if cmf is not None:
        if cmf > 0.1:
            cmf_score = 20
        elif cmf > 0:
            cmf_score = 15
        elif cmf > -0.1:
            cmf_score = 5
        else:
            cmf_score = 0

    # 5. Volume ratio (0-20)
    vol_score = 10
    if vol_ratio > 2.0:
        vol_score = 20
    elif vol_ratio > 1.5:
        vol_score = 15
    elif vol_ratio > 1.0:
        vol_score = 10
    elif vol_ratio > 0.5:
        vol_score = 5
    else:
        vol_score = 5

    total_score = obv_score + obv_div_score + mfi_score + cmf_score + vol_score

    if (cmf_score >= 15 or obv_score >= 15) and div_type != "bearish":
        signal = "bullish"
    elif div_type == "bearish" or cmf_score == 0:
        signal = "bearish"
    else:
        signal = "neutral"

    confidence = int(min(total_score / 100 * 100, 100))

    facts = {
        "obv_score": obv_score,
        "obv_divergence_score": obv_div_score,
        "mfi_score": mfi_score,
        "cmf_score": cmf_score,
        "volume_score": vol_score,
        "total_score": total_score,
        "volume_ratio": vol_ratio,
        "divergence_type": div_type,
        "algo_signal": signal,
        "algo_confidence": confidence,
        "metrics": {
            "obv": _cast(obv),
            "mfi_14": _cast(mfi),
            "cmf_20": _cast(cmf),
            "volume_ratio": _cast(vol_ratio),
            "volume": _cast(vol),
            "close": _cast(close),
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
            f"OBV{'创新高' if facts['obv_score'] >= 15 else '上行'}，"
            f"CMF={metrics['cmf_20']:.2f}资金净流入，"
            f"量比{metrics['volume_ratio']:.1f}，总分{facts['total_score']}/100"
        )
    elif signal == "bearish":
        reasoning = (
            f"资金流出{'，检测到顶背离' if div == 'bearish' else ''}，"
            f"CMF={metrics['cmf_20']:.2f}，总分{facts['total_score']}/100"
        )
    else:
        reasoning = (
            f"OBV{'上行' if facts['obv_score'] >= 15 else '走平'}，"
            f"MFI={metrics['mfi_14']:.1f}，CMF={metrics['cmf_20']:.2f}，"
            f"总分{facts['total_score']}/100"
        )

    if div == "bullish":
        reasoning += "，检测到价格-OBV底背离"

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


def volume_analyst_agent(state: AgentState) -> dict:
    """Volume Analyst: quant scoring → LLM persona reasoning."""
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
