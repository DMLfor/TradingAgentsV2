"""Base models and utilities for the agent analysis module."""

import json
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field


def _cast(v):
    """Convert numpy scalars to native Python types for JSON serialization."""
    if isinstance(v, (np.integer, np.int64, np.int32)):
        return int(v)
    if isinstance(v, (np.floating, np.float64, np.float32)):
        return float(v)
    if isinstance(v, dict):
        return {k: _cast(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_cast(item) for item in v]
    return v


class AgentSignal(BaseModel):
    """Unified signal schema for every specialist analyst agent."""

    signal: Literal["bullish", "bearish", "neutral"] = Field(
        ..., description="Directional signal"
    )
    confidence: int = Field(
        ..., ge=0, le=100, description="Confidence level 0-100"
    )
    reasoning: str = Field(..., description="Concise Chinese reasoning")
    metrics: dict[str, float | str] = Field(
        default_factory=dict, description="Key indicator snapshot"
    )

    def model_dump_casted(self) -> dict:
        """Dump with numpy type coercion for safe JSON serialization."""
        return _cast(self.model_dump())


class RiskManagerOutput(BaseModel):
    """Output schema for the risk management agent."""

    risk_level: Literal["low", "medium", "high"] = Field(
        ..., description="Overall risk assessment"
    )
    stop_loss: float = Field(..., description="Suggested stop-loss price")
    position_size_pct: int = Field(
        ..., ge=0, le=100, description="Suggested position size 0-100%"
    )
    risk_notes: str = Field(..., description="Concise risk warnings in Chinese")
    max_drawdown_20d: float = Field(..., description="Max drawdown over last 20 days")

    def model_dump_casted(self) -> dict:
        return _cast(self.model_dump())


class PortfolioManagerOutput(BaseModel):
    """Final composite output from the portfolio manager agent."""

    signal: Literal[
        "强烈偏多", "谨慎偏多", "中性偏强", "中性", "中性偏弱", "谨慎偏空"
    ] = Field(..., description="Composite directional signal")
    confidence: int = Field(..., ge=0, le=100)
    composite_score: float = Field(
        ..., ge=0, le=10, description="Numeric score compatible with existing 0-10 scale"
    )
    reasoning: str = Field(..., description="LLM-generated Chinese narrative")
    action_plan: str = Field(..., description="Action recommendation")
    risk_notes: str = Field(default="", description="Risk warnings")

    def model_dump_casted(self) -> dict:
        return _cast(self.model_dump())


# Backward compatibility alias
CompositeResult = PortfolioManagerOutput
