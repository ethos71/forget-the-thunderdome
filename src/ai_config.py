#!/usr/bin/env python3
"""
Shared LLM provider configuration for crewAI and AutoGen.

Three-tier waterfall (LOCAL-FIRST — Ollama carries everything it can):
  1. Ollama — a local Ollama server is reachable → use a free local model via
              Ollama's OpenAI-compatible endpoint. Preferred even when a paid
              key is set, so nothing hits a paid account by default.
  2. Paid   — Ollama is unreachable (or FTT_FORCE_PAID=1 is set) and
              OPENAI_API_KEY or ANTHROPIC_API_KEY is set → use that provider.
  3. None   — neither → AI features stay disabled (callers fall back).

Escape hatch: set FTT_FORCE_PAID=1 to force the paid tier even when Ollama is up.
"""

import json
import os
import urllib.request
from typing import List, Optional, Tuple

# ── Local Ollama (free tier) ────────────────────────────────────────────────

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_OPENAI_BASE = f"{OLLAMA_HOST}/v1"

# Preference order when auto-selecting a local model. A coder model is a good
# default for the structured JSON work these agents do; then general models.
_OLLAMA_MODEL_PREFERENCE = [
    "qwen2.5-coder:7b",
    "qwen2.5:14b",
    "llama3.1:8b",
]
_OLLAMA_FALLBACK_MODEL = "llama3.1:8b"

# Cache the server probe so callers (which each call get_provider) don't each
# pay the ~2s timeout. None = not yet probed.
_ollama_cache: Optional[Tuple[bool, List[str]]] = None


def detect_ollama(timeout: float = 2.0) -> Tuple[bool, List[str]]:
    """
    Probe the local Ollama server for installed models.
    Returns (reachable, [model_names]). Never raises — (False, []) on any error.
    """
    global _ollama_cache
    if _ollama_cache is not None:
        return _ollama_cache
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [m["name"] for m in data.get("models", []) if m.get("name")]
        _ollama_cache = (True, models)
    except Exception:
        _ollama_cache = (False, [])
    return _ollama_cache


def get_ollama_model() -> str:
    """
    Pick the local model to use: honor FTT_OLLAMA_MODEL, else the first
    installed model in the preference order, else llama3.1:8b.
    """
    override = os.getenv("FTT_OLLAMA_MODEL")
    if override:
        return override
    _, installed = detect_ollama()
    for model in _OLLAMA_MODEL_PREFERENCE:
        if model in installed:
            return model
    return _OLLAMA_FALLBACK_MODEL


# ── Provider selection ──────────────────────────────────────────────────────


def _get_paid_provider() -> Tuple[Optional[str], Optional[str]]:
    """Returns the paid tier (openai > anthropic) if a key is set, else (None, None)."""
    if os.getenv("OPENAI_API_KEY"):
        return "openai", os.getenv("OPENAI_API_KEY")
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic", os.getenv("ANTHROPIC_API_KEY")
    return None, None


def get_provider() -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (provider_name, api_key). api_key is None for the ollama tier.

    Local-first: a reachable Ollama server wins even when a paid key is set.
    Set FTT_FORCE_PAID=1 to prefer the paid key; the paid tier is also used
    when Ollama is unreachable. Falls through to (None, None) if neither.
    """
    if os.getenv("FTT_FORCE_PAID") == "1":
        provider, api_key = _get_paid_provider()
        if provider is not None:
            return provider, api_key
        # FTT_FORCE_PAID set but no key — fall back to local Ollama if up.

    reachable, _ = detect_ollama()
    if reachable:
        return "ollama", None
    return _get_paid_provider()


def is_available() -> bool:
    """Returns True if any LLM provider is configured (paid or local Ollama)."""
    provider, _ = get_provider()
    return provider is not None


def get_openai_config() -> Optional[list]:
    """
    Returns AutoGen-compatible config_list.
    AutoGen supports OpenAI and Anthropic via litellm prefix, and local Ollama
    via its OpenAI-compatible endpoint (price [0, 0] silences cost warnings).
    """
    provider, api_key = get_provider()
    if provider == "openai":
        return [{"model": "gpt-4o-mini", "api_key": api_key}]
    if provider == "anthropic":
        return [{"model": "anthropic/claude-3-haiku-20240307", "api_key": api_key}]
    if provider == "ollama":
        return [{
            "model": get_ollama_model(),
            "base_url": OLLAMA_OPENAI_BASE,
            "api_key": "ollama",
            "price": [0, 0],
        }]
    return None


def get_crewai_llm():
    """
    Returns an LLM instance for crewAI.
    Returns None if no provider is configured.
    """
    provider, api_key = get_provider()
    if provider is None:
        return None
    try:
        if provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.1)
        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model="claude-3-haiku-20240307", api_key=api_key, temperature=0.1
            )
        if provider == "ollama":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=get_ollama_model(),
                base_url=OLLAMA_OPENAI_BASE,
                api_key="ollama",
                temperature=0.1,
            )
    except ImportError:
        # crewAI will use its own default client if the langchain wrapper is
        # missing; point that client at the right endpoint via env vars.
        if provider == "ollama":
            os.environ["OPENAI_API_BASE"] = OLLAMA_OPENAI_BASE
            os.environ["OPENAI_API_KEY"] = "ollama"
        else:
            os.environ["OPENAI_API_KEY"] = api_key if provider == "openai" else ""
            os.environ["ANTHROPIC_API_KEY"] = api_key if provider == "anthropic" else ""
    return None


def get_model_name() -> str:
    """Returns a human-readable model name for logging."""
    provider, _ = get_provider()
    if provider == "openai":
        return "gpt-4o-mini"
    if provider == "anthropic":
        return "claude-3-haiku"
    if provider == "ollama":
        return f"{get_ollama_model()} (local)"
    return "none"
