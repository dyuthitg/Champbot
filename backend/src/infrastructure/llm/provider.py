"""
OpenRouter-backed LLM provider with two configurable model slots.

The provider resolves, per call, which OpenRouter model to use:

    per-org override (OrgModelSettings, added in a later phase)
        -> backend config default (OpenRouterConfig)
            -> hard-coded fallback

The actual HTTP client is injectable so the provider is unit-testable without
network access. In production the client is an OpenRouter-compatible OpenAI
async client (see ``openrouter_client.py``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, List, Optional, Protocol, Sequence


class Slot(str, Enum):
    """The two independently-configurable model roles."""
    CONTENT = "content"
    CLASSIFICATION = "classification"


@dataclass
class ModelSlot:
    """Model + sampling params for one slot."""
    model: str
    temperature: float = 0.7
    max_tokens: int = 512


# Sensible defaults: a strong writer for copy, a cheap/fast model for labels.
_DEFAULT_CONTENT = ModelSlot(model="anthropic/claude-3.5-sonnet", temperature=0.7, max_tokens=512)
_DEFAULT_CLASSIFICATION = ModelSlot(
    model="meta-llama/llama-3.1-8b-instruct", temperature=0.0, max_tokens=64
)


@dataclass
class OpenRouterConfig:
    """Backend defaults for OpenRouter access and the two slots."""
    api_key: str = ""
    base_url: str = "https://openrouter.ai/api/v1"
    # Optional attribution headers OpenRouter uses for rankings.
    referer: str = ""
    app_title: str = "Social Bot LinkedIn"
    content: ModelSlot = field(default_factory=lambda: _DEFAULT_CONTENT)
    classification: ModelSlot = field(default_factory=lambda: _DEFAULT_CLASSIFICATION)

    @classmethod
    def from_env(cls) -> "OpenRouterConfig":
        """Build config from environment variables."""
        cfg = cls(
            api_key=os.getenv("OPENROUTER_API_KEY", ""),
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            referer=os.getenv("OPENROUTER_REFERER", ""),
        )
        if os.getenv("OPENROUTER_CONTENT_MODEL"):
            cfg.content = ModelSlot(model=os.environ["OPENROUTER_CONTENT_MODEL"])
        if os.getenv("OPENROUTER_CLASSIFICATION_MODEL"):
            cfg.classification = ModelSlot(
                model=os.environ["OPENROUTER_CLASSIFICATION_MODEL"],
                temperature=0.0,
                max_tokens=64,
            )
        return cfg

    def slot(self, slot: Slot) -> ModelSlot:
        return self.content if slot == Slot.CONTENT else self.classification


@dataclass
class LLMResult:
    """Normalized completion result."""
    text: str
    model: str
    slot: Slot
    raw: Optional[dict] = None


class ChatClient(Protocol):
    """Minimal async chat client the provider depends on."""
    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[dict],
        temperature: float,
        max_tokens: int,
    ) -> str:
        ...


# An async resolver that returns a per-org override for a slot, or None.
SettingsResolver = Callable[[Optional[str], Slot], Awaitable[Optional[ModelSlot]]]


class LLMProvider:
    """
    Slot-aware LLM facade over OpenRouter.

    Args:
        config: backend defaults.
        client: injectable :class:`ChatClient`; lazily built if omitted.
        settings_resolver: optional async callable resolving a per-org slot
            override (wired to OrgModelSettings in a later phase).
    """

    def __init__(
        self,
        config: OpenRouterConfig,
        client: Optional[ChatClient] = None,
        settings_resolver: Optional[SettingsResolver] = None,
    ):
        self.config = config
        self._client = client
        self._settings_resolver = settings_resolver

    def _get_client(self) -> ChatClient:
        if self._client is None:
            # Lazy import so unit tests that inject a client don't need openai.
            from src.infrastructure.llm.openrouter_client import OpenRouterClient
            self._client = OpenRouterClient(self.config)
        return self._client

    async def _resolve_slot(self, slot: Slot, org_id: Optional[str]) -> ModelSlot:
        if self._settings_resolver is not None:
            override = await self._settings_resolver(org_id, slot)
            if override is not None:
                return override
        return self.config.slot(slot)

    async def complete(
        self,
        slot: Slot,
        messages: List[dict],
        *,
        org_id: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResult:
        """
        Run a chat completion for the given slot.

        Explicit ``model``/``temperature``/``max_tokens`` override the resolved
        slot config for this call only.
        """
        slot_cfg = await self._resolve_slot(slot, org_id)
        use_model = model or slot_cfg.model
        use_temp = slot_cfg.temperature if temperature is None else temperature
        use_max = max_tokens or slot_cfg.max_tokens

        text = await self._get_client().chat(
            model=use_model,
            messages=messages,
            temperature=use_temp,
            max_tokens=use_max,
        )
        return LLMResult(text=text, model=use_model, slot=slot)

    async def write(self, messages: List[dict], **kw) -> LLMResult:
        """Convenience: run the CONTENT slot (copywriting)."""
        return await self.complete(Slot.CONTENT, messages, **kw)

    async def classify(self, messages: List[dict], **kw) -> LLMResult:
        """Convenience: run the CLASSIFICATION slot (fast intent/relevance)."""
        return await self.complete(Slot.CLASSIFICATION, messages, **kw)
