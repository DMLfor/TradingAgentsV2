"""LangGraph workflow builder for the agent analysis system.

Workflow topology (ai-hedge-fund style):
    start_node → [5 specialists in parallel] → risk_manager → portfolio_manager → END
"""

from langgraph.graph import END, StateGraph

from tdx_core.agent.graph.state import AgentState
from tdx_core.agent.agents.trend_follower import trend_follower_agent
from tdx_core.agent.agents.mean_reversion_trader import mean_reversion_trader_agent
from tdx_core.agent.agents.momentum_hunter import momentum_hunter_agent
from tdx_core.agent.agents.volatility_trader import volatility_trader_agent
from tdx_core.agent.agents.volume_analyst import volume_analyst_agent
from tdx_core.agent.agents.risk_manager import risk_manager_agent
from tdx_core.agent.agents.portfolio_manager import portfolio_manager_agent


ANALYST_CONFIG = {
    "trend_follower": {
        "display_name": "趋势跟踪者",
        "description": "均线派交易员，信奉'趋势是朋友'，基于 MA/MACD/ADX 判断趋势方向",
        "agent_func": trend_follower_agent,
        "order": 0,
    },
    "mean_reversion_trader": {
        "display_name": "均值回归者",
        "description": "超跌反弹猎手，信奉'物极必反'，基于 RSI/布林带/Stochastic 判断极端偏离",
        "agent_func": mean_reversion_trader_agent,
        "order": 1,
    },
    "momentum_hunter": {
        "display_name": "动量猎人",
        "description": "突破追势者，信奉'强者恒强'，基于价格动量/RSI/CCI 判断 momentum",
        "agent_func": momentum_hunter_agent,
        "order": 2,
    },
    "volatility_trader": {
        "display_name": "波动率交易者",
        "description": "波段操作者，信奉'低波动蓄势，高波动出货'，基于布林带/ATR 判断波动率 regime",
        "agent_func": volatility_trader_agent,
        "order": 3,
    },
    "volume_analyst": {
        "display_name": "量价分析师",
        "description": "资金追踪者，信奉'量为价先'，基于 OBV/MFI/CMF 判断资金进出",
        "agent_func": volume_analyst_agent,
        "order": 4,
    },
}


def start(state: AgentState) -> AgentState:
    """Entry point node — returns state unchanged."""
    return state


def create_workflow(selected_analysts: list[str] | None = None) -> StateGraph:
    """Build the LangGraph StateGraph for agent analysis.

    Workflow:
        start_node → [selected specialists in parallel]
                   → risk_manager → portfolio_manager → END
    """
    workflow = StateGraph(AgentState)
    workflow.add_node("start_node", start)

    if selected_analysts is None:
        selected_analysts = list(ANALYST_CONFIG.keys())

    # Add specialist nodes, all connected from start_node
    for key in selected_analysts:
        config = ANALYST_CONFIG[key]
        node_name = f"{key}_agent"
        workflow.add_node(node_name, config["agent_func"])
        workflow.add_edge("start_node", node_name)

    # Risk manager waits for all specialists
    workflow.add_node("risk_manager", risk_manager_agent)
    for key in selected_analysts:
        workflow.add_edge(f"{key}_agent", "risk_manager")

    # Portfolio manager waits for risk manager
    workflow.add_node("portfolio_manager", portfolio_manager_agent)
    workflow.add_edge("risk_manager", "portfolio_manager")

    workflow.add_edge("portfolio_manager", END)
    workflow.set_entry_point("start_node")

    return workflow


def get_analyst_nodes():
    """Return mapping of analyst keys to (node_name, agent_func) tuples."""
    return {
        key: (f"{key}_agent", config["agent_func"])
        for key, config in ANALYST_CONFIG.items()
    }
