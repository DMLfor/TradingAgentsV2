"""Risk Manager agent node for LangGraph workflow.

Philosophy: "Survival first."
Two-step: quant risk assessment → LLM persona reasoning.
"""

import json
import os

from langchain_core.messages import HumanMessage

from tdx_core.agent.base import RiskManagerOutput, _cast
from tdx_core.agent.graph.state import AgentState
from tdx_core.agent.llm_client import LLMClient, llm_available
from tdx_core.agent.agents.persona_prompts import PERSONA_PROMPTS

AGENT_ID = "risk_manager"


def _quant_analysis(df, signals: dict) -> dict:
    """Step 1: Pure algorithmic risk quant assessment."""
    latest = df.iloc[-1]
    close = latest.get("close_val")
    atr = latest.get("atr_14")

    # 1. ATR stop-loss
    stop_loss = close - 2 * atr if close is not None and atr is not None else close * 0.95 if close else 0

    # 2. ATR percentile
    atr_pct = 50.0
    if atr is not None and len(df) >= 60 and "atr_14" in df.columns:
        atr_hist = df["atr_14"].iloc[-60:].dropna()
        if len(atr_hist) > 0:
            atr_pct = (atr_hist <= atr).mean() * 100

    # 3. Recent max drawdown
    max_dd = 0.0
    if len(df) >= 20:
        high_20d = df["high_val"].iloc[-20:].max()
        low_20d = df["low_val"].iloc[-20:].min()
        if high_20d > 0:
            max_dd = (high_20d - low_20d) / high_20d * 100

    # 4. Analyst disagreement
    signal_counts = {"bullish": 0, "bearish": 0, "neutral": 0}
    for agent_id, payload in signals.items():
        if agent_id == AGENT_ID:
            continue
        if isinstance(payload, dict):
            # payload may be {code: {...}} or {...}
            inner = payload
            if len(payload) == 1 and isinstance(list(payload.values())[0], dict):
                inner = list(payload.values())[0]
            s = inner.get("signal", "neutral")
            signal_counts[s] = signal_counts.get(s, 0) + 1

    total_analysts = sum(signal_counts.values())
    majority = max(signal_counts.values()) if total_analysts > 0 else 0
    disagreement = (total_analysts - majority) / total_analysts if total_analysts > 0 else 0

    # 5. Price extremes distance
    price_pos = 0.5
    if len(df) >= 20 and close is not None:
        high_20d = df["high_val"].iloc[-20:].max()
        low_20d = df["low_val"].iloc[-20:].min()
        if high_20d > low_20d:
            price_pos = (close - low_20d) / (high_20d - low_20d)

    # Risk scoring
    risk_score = 0
    if atr_pct > 70:
        risk_score += 2
    elif atr_pct > 40:
        risk_score += 1

    if max_dd > 15:
        risk_score += 2
    elif max_dd > 8:
        risk_score += 1

    if disagreement > 0.5:
        risk_score += 2
    elif disagreement > 0.3:
        risk_score += 1

    if price_pos > 0.9:
        risk_score += 1  # near high, reversal risk
    elif price_pos < 0.1:
        risk_score += 1  # near low, breakdown risk

    if risk_score <= 2:
        risk_level = "low"
        position_size = 80
    elif risk_score <= 4:
        risk_level = "medium"
        position_size = 50
    else:
        risk_level = "high"
        position_size = 20

    facts = {
        "atr": _cast(atr),
        "atr_percentile": _cast(atr_pct),
        "stop_loss": _cast(stop_loss),
        "max_drawdown_20d": _cast(max_dd),
        "analyst_bullish": signal_counts["bullish"],
        "analyst_bearish": signal_counts["bearish"],
        "analyst_neutral": signal_counts["neutral"],
        "disagreement_ratio": _cast(disagreement),
        "price_position_20d": _cast(price_pos),
        "risk_score": risk_score,
        "algo_risk_level": risk_level,
        "algo_position_size": position_size,
    }
    return facts


def _algo_fallback(facts: dict) -> dict:
    risk_level = facts["algo_risk_level"]
    position_size = facts["algo_position_size"]
    max_dd = facts["max_drawdown_20d"]
    atr_pct = facts["atr_percentile"]

    if risk_level == "low":
        risk_notes = f"风险可控：ATR百分位{atr_pct:.1f}%，近20日最大回撤{max_dd:.1f}%，分析师分歧低"
    elif risk_level == "medium":
        risk_notes = f"中等风险：ATR百分位{atr_pct:.1f}%，近20日最大回撤{max_dd:.1f}%，需注意波动"
    else:
        risk_notes = f"高风险：ATR百分位{atr_pct:.1f}%，近20日最大回撤{max_dd:.1f}%，建议降低仓位"

    result = RiskManagerOutput(
        risk_level=risk_level,
        stop_loss=facts["stop_loss"],
        position_size_pct=position_size,
        risk_notes=risk_notes,
        max_drawdown_20d=max_dd,
    )
    return result.model_dump_casted()


def _build_prompt(facts: dict) -> list[dict]:
    system_msg = PERSONA_PROMPTS[AGENT_ID]
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": json.dumps(facts, ensure_ascii=False, indent=2)},
    ]


def risk_manager_agent(state: AgentState) -> dict:
    """Risk Manager: quant assessment → LLM persona reasoning."""
    code = state["data"]["code"]
    df = state["data"]["df"]
    signals = state["data"].get("analyst_signals", {})
    use_llm = state["data"].get("use_llm", True)
    model = state["data"].get("model")

    # Step 1: Quant risk assessment
    facts = _quant_analysis(df, signals)

    # Step 2: LLM persona reasoning
    if use_llm and llm_available():
        try:
            client = LLMClient(model=model)
            messages = _build_prompt(facts)
            result = client.call(messages, RiskManagerOutput)
            risk_data = result.model_dump_casted()
        except Exception:
            risk_data = _algo_fallback(facts)
    else:
        risk_data = _algo_fallback(facts)

    state["data"]["risk_manager_output"] = risk_data

    msg = HumanMessage(
        content=json.dumps(risk_data, ensure_ascii=False), name=AGENT_ID
    )
    return {"messages": [msg], "data": state["data"]}
