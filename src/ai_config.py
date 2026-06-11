#!/usr/bin/env python3
"""
Shared LLM provider configuration for crewAI and AutoGen.
Reads OPENAI_API_KEY or ANTHROPIC_API_KEY from environment.
"""

import os
from typing import Optional, Tuple


def get_provider() -> Tuple[Optional[str], Optional[str]]:
    """Returns (provider_name, api_key) or (None, None)."""
    if os.getenv("OPENAI_API_KEY"):
        return "openai", os.getenv("OPENAI_API_KEY")
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic", os.getenv("ANTHROPIC_API_KEY")
    return None, None


def is_available() -> bool:
    """Returns True if any LLM provider is configured."""
    provider, _ = get_provider()
    return provider is not None


def get_openai_config() -> Optional[list]:
    """
    Returns AutoGen-compatible config_list.
    AutoGen supports both OpenAI and Anthropic via litellm prefix.
    """
    provider, api_key = get_provider()
    if provider == "openai":
        return [{"model": "gpt-4o-mini", "api_key": api_key}]
    if provider == "anthropic":
        return [{"model": "anthropic/claude-3-haiku-20240307", "api_key": api_key}]
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
    except ImportError:
        # crewAI will use its own default if langchain wrapper is missing
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
    return "none"
