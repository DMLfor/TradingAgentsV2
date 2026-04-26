"""Portfolio Manager agent node for LangGraph workflow.

Philosophy: "The buck stops here."
Aggregates all specialist signals + risk manager output into final decision.
"""

import json
import os

from langchain_core.messages import HumanMessage

from tdx_core.agent.base import PortfolioManagerOutput, _cast
from tdx_core.agent.graph.state import AgentState
from tdx_core.agent.llm_client import LLMClient, llm_available
from tdx_core.agent.agents.persona_prompts import PERSONA_PROMPTS

AGENT_ID = "portfolio_manager"


def _build_algorithmic_composite(signals: dict) -> dict:
    """Compute algorithmic pre-score as input to portfolio manager."""
    weights = {
        "trend_follower": 0.25,
        "mean_reversion_trader": 0.20,
        "momentum_hunter": 0.20,
        "volatility_trader": 0.15,
        "volume_analyst": 0.20,
    }

    score_map = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}
    weighted_score = 0.0
    total_weight = 0.0
    avg_confidence = 0.0

    for agent_id, weight in weights.items():
        payload = signals.get(agent_id, {})
        # payload may be {code: {...}} or {...}
        if isinstance(payload, dict) and len(payload) == 1:
            inner = list(payload.values())[0]
        else:
            inner = payload

        s = inner.get("signal", "neutral") if isinstance(inner, dict) else "neutral"
        c = inner.get("confidence", 50) if isinstance(inner, dict) else 50

        weighted_score += score_map.get(s, 0.0) * weight * (c / 100.0)
        total_weight += weight
        avg_confidence += c * weight

    if total_weight > 0:
        weighted_score /= total_weight
        avg_confidence /= total_weight

    composite_score = (weighted_score + 1.0) * 5.0
    composite_score = max(0.0, min(10.0, composite_score))

    if composite_score >= 7.8:
        algo_signal = "强烈偏多"
    elif composite_score >= 7.0:
        algo_signal = "谨慎偏多"
    elif composite_score >= 6.0:
        algo_signal = "中性偏强"
    elif composite_score >= 5.0:
        algo_signal = "中性"
    elif composite_score >= 4.0:
        algo_signal = "中性偏弱"
    else:
        algo_signal = "谨慎偏空"

    return {
        "score": round(composite_score, 2),
        "signal": algo_signal,
        "confidence": int(avg_confidence),
    }


def _build_prompt(facts: dict) -> list[dict]:
    system_msg = PERSONA_PROMPTS[AGENT_ID]
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": json.dumps(facts, ensure_ascii=False, indent=2)},
    ]


def _algo_fallback(facts: dict) -> dict:
    """Algorithmic fallback when LLM is unavailable."""
    algo = facts["algorithmic_composite"]
    score = algo["score"]
    signal = algo["signal"]
    confidence = algo["confidence"]

    # Adjust for risk
    risk = facts.get("risk_manager", {})
    risk_level = risk.get("risk_level", "medium")
    if risk_level == "high" and score >= 6.0:
        # downgrade
        if score >= 7.0:
            signal = "中性偏强"
        elif score >= 6.0:
            signal = "中性"
        confidence = int(confidence * 0.7)

    if score >= 7.0:
        action_plan = "维持或加仓，关注量能持续性"
    elif score >= 6.0:
        action_plan = "持有观察，等待更明确信号"
    elif score >= 5.0:
        action_plan = "中性观望，控制仓位"
    elif score >= 4.0:
        action_plan = "减仓或观望，等待企稳"
    else:
        action_plan = "规避风险，降低仓位"

    if risk_level == "high":
        action_plan = "【高风险】" + action_plan.replace("加仓", "谨慎")

    # Build reasoning from specialists
    parts = []
    for agent_id, sig_data in facts.get("specialist_signals", {}).items():
        label = {
            "trend_follower": "趋势",
            "mean_reversion_trader": "均值回归",
            "momentum_hunter": "动量",
            "volatility_trader": "波动率",
            "volume_analyst": "量价",
        }.get(agent_id, agent_id)
        s = sig_data.get("signal", "neutral")
        c = sig_data.get("confidence", 0)
        cn = {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"}.get(s, s)
        parts.append(f"{label}{cn}(置信度{c}%)")

    reasoning = (
        f"算法综合评分{score:.1f}/10。"
        + "，".join(parts)
        + f"。风险等级：{risk_level}。各维度加权聚合得出最终判断。"
    )

    # Risk notes
    notes = []
    rsi = facts.get("latest_indicators", {}).get("rsi_14")
    if rsi is not None and rsi > 75:
        notes.append("RSI超买")
    if rsi is not None and rsi < 25:
        notes.append("RSI超卖")
    vol_ratio = facts.get("latest_indicators", {}).get("volume_ratio", 1.0)
    if vol_ratio > 3.0:
        notes.append("成交量异常放大")
    if not notes:
        notes.append(f"风险等级{risk_level}，关注趋势逆转信号")

    return PortfolioManagerOutput(
        signal=signal,
        confidence=confidence,
        composite_score=round(score, 2),
        reasoning=reasoning,
        action_plan=action_plan,
        risk_notes="；".join(notes),
    ).model_dump_casted()


def portfolio_manager_agent(state: AgentState) -> dict:
    """Portfolio Manager: aggregate all signals + risk into final decision."""
    code = state["data"]["code"]
    name = state["data"].get("name", code)
    df = state["data"]["df"]
    signals = state["data"].get("analyst_signals", {})
    risk_output = state["data"].get("risk_manager_output", {})
    use_llm = state["data"].get("use_llm", True)
    model = state["data"].get("model")

    # Prepare compact specialist signals
    specialist_signals = {}
    for agent_id, payload in signals.items():
        if agent_id == "risk_manager":
            continue
        if isinstance(payload, dict):
            if len(payload) == 1 and isinstance(list(payload.values())[0], dict):
                inner = list(payload.values())[0]
            else:
                inner = payload
            specialist_signals[agent_id] = {
                "signal": inner.get("signal", "neutral"),
                "confidence": inner.get("confidence", 50),
                "reasoning": inner.get("reasoning", "")[:80],
            }

    # Algorithmic pre-composite
    algo_composite = _build_algorithmic_composite(signals)

    latest = df.iloc[-1]
    facts = {
        "stock": {"code": code, "name": name, "close": _cast(latest.get("close_val"))},
        "specialist_signals": specialist_signals,
        "risk_manager": {
            "risk_level": risk_output.get("risk_level", "medium"),
            "stop_loss": risk_output.get("stop_loss", 0),
            "position_size_pct": risk_output.get("position_size_pct", 50),
            "risk_notes": risk_output.get("risk_notes", ""),
        },
        "latest_indicators": {
            "ma_5": _cast(latest.get("ma_5")),
            "ma_20": _cast(latest.get("ma_20")),
            "ma_60": _cast(latest.get("ma_60")),
            "macd": _cast(latest.get("macd")),
            "rsi_14": _cast(latest.get("rsi_14")),
            "bb_pctb": _cast(latest.get("bb_pctb")),
            "atr_14": _cast(latest.get("atr_14")),
            "mfi_14": _cast(latest.get("mfi_14")),
            "volume_ratio": _cast(
                latest.get("volume") / df["volume"].iloc[-20:].mean()
                if latest.get("volume") and len(df) >= 20 else 1.0
            ),
        },
        "algorithmic_composite": algo_composite,
    }

    if use_llm and llm_available():
        try:
            client = LLMClient(model=model)
            messages = _build_prompt(facts)
            result = client.call(messages, PortfolioManagerOutput)
            composite_data = result.model_dump_casted()
        except Exception:
            composite_data = _algo_fallback(facts)
    else:
        composite_data = _algo_fallback(facts)

    state["data"]["composite_result"] = {code: composite_data}

    msg = HumanMessage(
        content=json.dumps({code: composite_data}, ensure_ascii=False), name=AGENT_ID
    )
    return {"messages": [msg], "data": state["data"]}
