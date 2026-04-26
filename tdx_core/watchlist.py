"""股票关注池管理模块.

支持多池管理（default/tech/etf等），持久化存储为 JSON.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import TdxConfig
from .metadata import get_meta, get_name


DEFAULT_WATCHLIST_PATH = "config/watchlist.json"


class WatchlistManager:
    """关注池管理器."""

    def __init__(self, config_path: str | None = None):
        self.path = Path(config_path or DEFAULT_WATCHLIST_PATH)
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {"pools": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _ensure_pool(self, pool: str) -> dict[str, Any]:
        if pool not in self._data["pools"]:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._data["pools"][pool] = {
                "codes": [],
                "created_at": now,
                "updated_at": now,
            }
        return self._data["pools"][pool]

    def add(self, codes: list[str], pool: str = "default") -> list[str]:
        """添加股票到关注池，返回实际新增的股票（去重）."""
        p = self._ensure_pool(pool)
        existing = set(p["codes"])
        added = []
        for c in codes:
            c = c.strip()
            if c and c not in existing:
                p["codes"].append(c)
                existing.add(c)
                added.append(c)
        if added:
            p["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save()
        return added

    def remove(self, codes: list[str], pool: str = "default") -> list[str]:
        """从关注池删除股票，返回实际删除的股票."""
        p = self._ensure_pool(pool)
        to_remove = set(c.strip() for c in codes if c.strip())
        removed = [c for c in p["codes"] if c in to_remove]
        p["codes"] = [c for c in p["codes"] if c not in to_remove]
        if removed:
            p["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save()
        return removed

    def clear(self, pool: str = "default") -> int:
        """清空关注池，返回清空的数量."""
        p = self._ensure_pool(pool)
        count = len(p["codes"])
        p["codes"] = []
        if count:
            p["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save()
        return count

    def get_codes(self, pool: str = "default") -> list[str]:
        """返回指定池的代码列表."""
        return list(self._data.get("pools", {}).get(pool, {}).get("codes", []))

    def pools(self) -> list[str]:
        """返回所有池名称."""
        return list(self._data.get("pools", {}).keys())

    def list_items(self, pool: str = "default") -> list[dict[str, Any]]:
        """列出关注池股票，带名称/板块/行业信息."""
        codes = self.get_codes(pool)
        items = []
        for code in codes:
            meta = get_meta(code)
            name = get_name(code) or code
            item: dict[str, Any] = {
                "code": code,
                "name": name,
            }
            if meta:
                item["level1"] = meta.get("level1", "")
                item["level2"] = meta.get("level2", "")
                item["level3"] = meta.get("level3", "")
                item["board"] = meta.get("board", "")
            else:
                item["level1"] = item["level2"] = item["level3"] = item["board"] = ""
            items.append(item)
        return items

    def info(self, pool: str = "default") -> dict[str, Any]:
        """返回池的元信息."""
        p = self._data.get("pools", {}).get(pool, {})
        return {
            "name": pool,
            "count": len(p.get("codes", [])),
            "created_at": p.get("created_at", ""),
            "updated_at": p.get("updated_at", ""),
        }
