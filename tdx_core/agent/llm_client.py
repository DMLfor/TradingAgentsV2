"""OpenAI-compatible LLM client with Pydantic structured output, retry, and persistent cache."""

import hashlib
import json
import os
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)

CACHE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "llm_cache.json"


class LLMCache:
    """Persistent file-backed cache for LLM calls keyed by (model, prompt_hash)."""

    def __init__(self, cache_file: Path = CACHE_FILE):
        self._cache_file = cache_file
        self._store: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._cache_file.exists():
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    self._store = json.load(f)
            except Exception:
                self._store = {}

    def _save(self) -> None:
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(self._store, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _key(self, model: str, messages: list[dict]) -> str:
        payload = json.dumps({"model": model, "messages": messages}, ensure_ascii=False, sort_keys=True)
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    def get(self, model: str, messages: list[dict]) -> dict | None:
        return self._store.get(self._key(model, messages))

    def set(self, model: str, messages: list[dict], value: BaseModel) -> None:
        self._store[self._key(model, messages)] = value.model_dump()
        self._save()

    def clear(self) -> None:
        self._store.clear()
        self._save()

    def info(self) -> dict:
        return {"size": len(self._store), "file": str(self._cache_file)}


# Global cache instance
_llm_cache = LLMCache()


class LLMClient:
    """Thin wrapper around OpenAI SDK for Kimi/Moonshot API with persistent caching."""

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("KIMI_MODEL", "kimi-k2.6")
        api_key = os.getenv("KIMI_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")

        if not api_key:
            raise RuntimeError(
                "KIMI_API_KEY or OPENAI_API_KEY environment variable required."
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai package not installed. Run: pip install openai"
            ) from exc

        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def call(self, messages: list[dict], response_model: type[ModelT], max_retries: int = 3, use_cache: bool = True) -> ModelT:
        """Call LLM with JSON-mode structured output, persistent cache, and retries.
        
        Falls back to moonshot-v1-8k if the configured model returns 404.
        """
        # Try persistent cache first
        if use_cache:
            cached = _llm_cache.get(self.model, messages)
            if cached is not None:
                return response_model(**cached)

        models_to_try = [self.model]
        if self.model != "moonshot-v1-8k":
            models_to_try.append("moonshot-v1-8k")

        for model in models_to_try:
            last_exc = None
            for attempt in range(1, max_retries + 1):
                try:
                    completion = self._client.beta.chat.completions.parse(
                        model=model,
                        messages=messages,
                        response_format=response_model,
                    )
                    parsed = completion.choices[0].message.parsed
                    if parsed is None:
                        raise RuntimeError("LLM returned empty parsed response")
                    if use_cache:
                        _llm_cache.set(self.model, messages, parsed)
                    return parsed
                except Exception as exc:
                    last_exc = exc
                    err_str = str(exc).lower()
                    if "not found" in err_str or "permission denied" in err_str:
                        # Model not available, break to try fallback model
                        break
                    if attempt == max_retries:
                        break
        return self._default(response_model)

    @staticmethod
    def _default(model_class: type[ModelT]) -> ModelT:
        """Create a safe default instance on total failure."""
        defaults = {}
        for name, field_info in model_class.model_fields.items():
            ann = field_info.annotation
            if ann == str:
                defaults[name] = "LLM调用失败，使用默认分析"
            elif ann == float:
                defaults[name] = 0.0
            elif ann == int:
                defaults[name] = 0
            elif hasattr(ann, "__args__"):
                defaults[name] = ann.__args__[0]
            else:
                defaults[name] = None
        return model_class(**defaults)


def llm_available() -> bool:
    """Check whether LLM can be used in current environment."""
    if not os.getenv("KIMI_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        return False
    try:
        import openai
        return True
    except ImportError:
        return False
