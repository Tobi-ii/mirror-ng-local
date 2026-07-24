"""
llm_clients.py — OpenRouter-based LLM client factory for Mirror.ng.

Provides a pre-configured OpenAI-compatible client pointing at the
OpenRouter API gateway, plus the fallback model chain used for
transaction categorization and other ML tasks.

OpenRouter acts as a unified router across multiple model providers,
allowing automatic fallback if the primary model is rate-limited or
unavailable.
"""
import os
from openai import OpenAI


def get_nvidia_client() -> OpenAI:
    """Return an OpenAI client pre-configured for the NVIDIA NIM free tier.

    Reads NVIDIA_API_KEY from the environment.
    """
    return OpenAI(
        api_key=os.getenv("NVIDIA_API_KEY"),
        base_url="https://integrate.api.nvidia.com/v1"
    )


def get_openrouter_client() -> OpenAI:
    """Return an OpenAI client pre-configured for the OpenRouter API.

    Reads OPENROUTER_API_KEY from the environment.  No API key
    validation is performed here — errors surface on the first
    request.

    Returns:
        An OpenAI client instance with the base URL overridden to
        https://openrouter.ai/api/v1.
    """
    return OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )


# Fallback chain: models are tried left-to-right until one succeeds.
# The free-tier models (deepseek-v4-flash:free, qwen-3-235b-a22b:free)
# are attempted first to minimise cost, falling back to paid models.
MODEL_CHAIN = "deepseek/deepseek-v4-flash:free,qwen/qwen-3-235b-a22b:free,deepseek/deepseek-v3.2,anthropic/claude-3.5-haiku"
