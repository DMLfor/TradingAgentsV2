"""Stock metadata & sector filtering engine.

Loads metadata JSON (path configurable via TdxConfig) and provides fast
inverted-index lookups by industry level, board, and name.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import TdxConfig

# ─── In-memory caches ─────────────────────────────────────────────────────────

_METADATA: dict[str, Any] | None = None
_DEFAULT_CONFIG: TdxConfig | None = None


def _default_config() -> TdxConfig:
    """Lazy-load default TdxConfig (respects cloud auto-detect)."""
    global _DEFAULT_CONFIG
    if _DEFAULT_CONFIG is None:
        _DEFAULT_CONFIG = TdxConfig()
    return _DEFAULT_CONFIG


def _metadata_path(config: TdxConfig | None = None) -> Path:
    """Resolve metadata JSON path from config or default."""
    cfg = config or _default_config()
    return Path(cfg.metadata_path)


def _load(config: TdxConfig | None = None) -> dict[str, Any]:
    """Lazy-load metadata JSON."""
    global _METADATA
    if _METADATA is not None:
        return _METADATA
    path = _metadata_path(config)
    if not path.exists():
        raise FileNotFoundError(
            f"Metadata not found: {path}\n"
            "Run: python scripts/update_stock_metadata.py"
        )
    _METADATA = json.loads(path.read_text(encoding="utf-8"))
    return _METADATA


def reload(config: TdxConfig | None = None) -> None:
    """Reload metadata from disk (useful after regeneration)."""
    global _METADATA
    _METADATA = None
    _load(config)


# ─── Public API ───────────────────────────────────────────────────────────────


def get_meta(code: str, config: TdxConfig | None = None) -> dict[str, str] | None:
    """Return metadata dict for a 6-digit stock code."""
    return _load(config)["stocks"].get(code)


def get_name(code: str, config: TdxConfig | None = None) -> str | None:
    """Return stock name from metadata (overrides names.py if available)."""
    m = get_meta(code, config)
    return m["name"] if m else None


def get_level1(code: str, config: TdxConfig | None = None) -> str | None:
    m = get_meta(code, config)
    return m["level1"] if m else None


def get_level2(code: str, config: TdxConfig | None = None) -> str | None:
    m = get_meta(code, config)
    return m["level2"] if m else None


def get_level3(code: str, config: TdxConfig | None = None) -> str | None:
    m = get_meta(code, config)
    return m["level3"] if m else None


def get_board(code: str, config: TdxConfig | None = None) -> str | None:
    m = get_meta(code, config)
    return m["board"] if m else None


# ─── Filtering ────────────────────────────────────────────────────────────────


def by_level1(industry: str, config: TdxConfig | None = None) -> list[str]:
    """Return list of stock codes in given 一级行业."""
    return _load(config)["index"]["by_level1"].get(industry, [])


def by_level2(industry: str, config: TdxConfig | None = None) -> list[str]:
    """Return list of stock codes in given 二级行业."""
    return _load(config)["index"]["by_level2"].get(industry, [])


def by_level3(industry: str, config: TdxConfig | None = None) -> list[str]:
    """Return list of stock codes in given 三级行业."""
    return _load(config)["index"]["by_level3"].get(industry, [])


def by_board(board: str, config: TdxConfig | None = None) -> list[str]:
    """Return list of stock codes on given board."""
    return _load(config)["index"]["by_board"].get(board, [])


def filter_stocks(
    level1: str | None = None,
    level2: str | None = None,
    level3: str | None = None,
    board: str | None = None,
    codes: list[str] | None = None,
    config: TdxConfig | None = None,
) -> list[str]:
    """Multi-condition filter. Returns codes matching ALL given criteria."""
    data = _load(config)
    result: set[str] = set(codes) if codes else set(data["stocks"].keys())

    if level1:
        result &= set(data["index"]["by_level1"].get(level1, []))
    if level2:
        result &= set(data["index"]["by_level2"].get(level2, []))
    if level3:
        result &= set(data["index"]["by_level3"].get(level3, []))
    if board:
        result &= set(data["index"]["by_board"].get(board, []))

    return sorted(result)


# ─── Discovery / Enumeration ──────────────────────────────────────────────────


def list_level1(config: TdxConfig | None = None) -> list[str]:
    """Return all 一级行业 names."""
    return sorted(_load(config)["index"]["by_level1"].keys())


def list_level2(level1: str | None = None, config: TdxConfig | None = None) -> list[str]:
    """Return all 二级行业 names, optionally filtered by 一级行业."""
    data = _load(config)
    if level1 is None:
        return sorted(data["index"]["by_level2"].keys())
    codes = set(data["index"]["by_level1"].get(level1, []))
    result: set[str] = set()
    for c in codes:
        m = data["stocks"].get(c)
        if m and m.get("level2"):
            result.add(m["level2"])
    return sorted(result)


def list_level3(
    level1: str | None = None,
    level2: str | None = None,
    config: TdxConfig | None = None,
) -> list[str]:
    """Return all 三级行业 names, optionally filtered by upper levels."""
    data = _load(config)
    pool = set(data["stocks"].keys())
    if level1:
        pool &= set(data["index"]["by_level1"].get(level1, []))
    if level2:
        pool &= set(data["index"]["by_level2"].get(level2, []))
    result: set[str] = set()
    for c in pool:
        m = data["stocks"].get(c)
        if m and m.get("level3"):
            result.add(m["level3"])
    return sorted(result)


def list_boards(config: TdxConfig | None = None) -> list[str]:
    """Return all board names."""
    return sorted(_load(config)["index"]["by_board"].keys())


# ─── Stats ────────────────────────────────────────────────────────────────────


def sector_stats(config: TdxConfig | None = None) -> dict[str, Any]:
    """Return summary statistics of the metadata."""
    return _load(config)["meta"]
