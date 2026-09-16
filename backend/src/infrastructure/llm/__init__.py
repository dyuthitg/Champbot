"""
LLM access layer.

All model inference in the system is routed through OpenRouter via a provider
that exposes two independently-configurable model slots:

- ``content``        -> humanistic copywriting (comments, DMs, posts)
- ``classification`` -> fast/cheap intent & relevance classification

Model choice per slot is configurable in backend config and, per organization,
in the admin settings UI.
"""

from src.infrastructure.llm.provider import (
    LLMProvider,
    LLMResult,
    ModelSlot,
    OpenRouterConfig,
    Slot,
)

__all__ = [
    "LLMProvider",
    "LLMResult",
    "ModelSlot",
    "OpenRouterConfig",
    "Slot",
]
