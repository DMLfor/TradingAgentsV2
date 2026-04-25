"""Stock code ↔ name resolution.

Reads from config/stock_names.json (path configurable via TdxConfig).
Falls back to an in-memory minimal map if the file is missing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from .config import TdxConfig

_MINIMAL_MAP = {
    "000001": "平安银行",
    "000002": "万科A",
    "000333": "美的集团",
    "000858": "五粮液",
    "002594": "比亚迪",
    "300750": "宁德时代",
    "600000": "浦发银行",
    "600009": "上海机场",
    "600036": "招商银行",
    "600276": "恒瑞医药",
    "600519": "贵州茅台",
    "600887": "伊利股份",
    "601012": "隆基绿能",
    "601318": "中国平安",
    "601888": "中国中免",
    "603288": "海天味业",
    "688008": "澜起科技",
    "688012": "中微公司",
    "688018": "乐鑫科技",
    "688111": "金山办公",
    "688981": "中芯国际",
}

_CODE_TO_NAME: Dict[str, str] = {}
_NAME_TO_CODE: Dict[str, str] = {}
_initialized = False


def _names_path(config: TdxConfig | None = None) -> Path:
    """Resolve names JSON path from config or default."""
    cfg = config or TdxConfig()
    return Path(cfg.names_path)


def _init(config: TdxConfig | None = None) -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    path = _names_path(config)
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for code, name in data.items():
                if isinstance(code, str) and isinstance(name, str):
                    _CODE_TO_NAME[code] = name
                    _NAME_TO_CODE[name] = code
        except Exception:
            pass

    # Always overlay the minimal map (ensures well-known stocks use correct names)
    for code, name in _MINIMAL_MAP.items():
        old_name = _CODE_TO_NAME.get(code)
        if old_name and old_name in _NAME_TO_CODE:
            del _NAME_TO_CODE[old_name]
        _CODE_TO_NAME[code] = name
        _NAME_TO_CODE[name] = code


def reload(config: TdxConfig | None = None) -> None:
    """Reload the name map from disk."""
    global _initialized
    _initialized = False
    _CODE_TO_NAME.clear()
    _NAME_TO_CODE.clear()
    _init(config)


def get_name(code: str, config: TdxConfig | None = None) -> Optional[str]:
    """Return stock name for a 6-digit code."""
    _init(config)
    return _CODE_TO_NAME.get(code)


def get_code(name: str, config: TdxConfig | None = None) -> Optional[str]:
    """Return exact-match code for a stock name."""
    _init(config)
    return _NAME_TO_CODE.get(name)


def fuzzy_search(name: str, limit: int = 5, config: TdxConfig | None = None) -> List[tuple[str, str]]:
    """Fuzzy search stock names. Returns list of (code, name) tuples."""
    _init(config)
    name = name.strip()
    results: List[tuple[str, str]] = []

    # Exact match first
    exact = _NAME_TO_CODE.get(name)
    if exact:
        results.append((exact, name))

    # Prefix / substring match
    lower_query = name.lower()
    for s_name, s_code in _NAME_TO_CODE.items():
        if s_name == name:
            continue
        if lower_query in s_name.lower() or s_name.lower().startswith(lower_query):
            results.append((s_code, s_name))
        if len(results) >= limit * 2:
            break

    return results[:limit]


def resolve_code(stock_str: str, config: TdxConfig | None = None) -> str:
    """Resolve a stock identifier to its 6-digit code.

    - 6-digit numeric strings are returned as-is.
    - Names are looked up exactly, then fuzzily.
    - Raises ValueError if unresolvable or ambiguous.
    """
    stock_str = stock_str.strip()
    if not stock_str:
        raise ValueError("Empty stock identifier")

    if re.fullmatch(r"\d{6}", stock_str):
        return stock_str

    _init(config)

    code = _NAME_TO_CODE.get(stock_str)
    if code:
        return code

    fuzzy = fuzzy_search(stock_str, limit=5, config=config)
    if not fuzzy:
        raise ValueError(f"Unknown stock: '{stock_str}'")

    if len(fuzzy) == 1:
        return fuzzy[0][0]

    candidates = ", ".join(f"{c} ({n})" for c, n in fuzzy)
    raise ValueError(f"Ambiguous name '{stock_str}'; candidates: {candidates}")


def resolve_codes(stock_strs: str | List[str], config: TdxConfig | None = None) -> List[str]:
    """Resolve a comma-separated string or list of identifiers to codes."""
    if isinstance(stock_strs, str):
        parts = [p.strip() for p in stock_strs.split(",") if p.strip()]
    else:
        parts = [p.strip() for p in stock_strs if p.strip()]
    return [resolve_code(p, config) for p in parts]


def all_names(config: TdxConfig | None = None) -> Dict[str, str]:
    """Return a copy of the full code→name map."""
    _init(config)
    return _CODE_TO_NAME.copy()
