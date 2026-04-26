"""Agent state definitions and reasoning display helpers."""

import json
import operator
from typing import Any, Sequence

from langchain_core.messages import BaseMessage
from typing_extensions import Annotated, TypedDict


def merge_dicts(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Merge two dicts for LangGraph state reduction."""
    return {**a, **b}


class AgentState(TypedDict):
    """Shared state passed between all agent nodes."""

    messages: Annotated[Sequence[BaseMessage], operator.add]
    data: Annotated[dict[str, Any], merge_dicts]
    metadata: Annotated[dict[str, Any], merge_dicts]


def show_agent_reasoning(output: dict | str, agent_name: str) -> None:
    """Print agent reasoning to CLI in a formatted block (Chinese, no emoji)."""
    width = 50
    title = f" {agent_name} "
    pad = (width - len(title)) // 2
    header = "=" * pad + title + "=" * (width - pad - len(title))
    print(f"\n{header}")

    def _serialize(obj: Any) -> Any:
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        if isinstance(obj, (int, float, bool, str)):
            return obj
        if isinstance(obj, (list, tuple)):
            return [_serialize(item) for item in obj]
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        return str(obj)

    if isinstance(output, (dict, list)):
        print(json.dumps(_serialize(output), indent=2, ensure_ascii=False))
    else:
        try:
            parsed = json.loads(output)
            print(json.dumps(parsed, indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            print(output)

    print("=" * width)
